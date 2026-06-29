from __future__ import annotations

import argparse
import calendar
import io
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import requests


REQUEST_TIMEOUT = 60
REQUEST_RETRY = 3
REQUEST_SLEEP_SEC = 0.5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

LITER_PER_BBL = 158.987294928

COL_DATE_FX = "변환"
COL_VALUE_FX = "원자료"
COL_PERIOD = "기간"
COL_DATE = "구분"
COL_GASOLINE = "보통휘발유"
COL_DIESEL = "자동차용경유"

BRAND_COLUMNS = [
    COL_DATE,
    "정유사평균",
    "SK에너지",
    "GS칼텍스",
    "HD현대오일뱅크",
    "S-OIL",
    "알뜰주유소",
    "(알뜰-자영)",
    "자가상표",
]

FUEL_TAX_COLUMNS = [
    "변동일자",
    "개별소비세",
    "교통에너지환경세",
    "교육세",
    "주행세",
    "합계",
    "판매부과금",
]

REFINERY_COLUMNS = [COL_DATE, COL_GASOLINE, COL_DIESEL]


@dataclass
class CollectResult:
    name: str
    status: str
    rows: int = 0
    detail: str = ""
    files: dict[str, str] = field(default_factory=dict)


def yyyymmdd(value: str | datetime | pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def date_parts(value: str | datetime | pd.Timestamp) -> tuple[str, str, str, str]:
    ts = pd.Timestamp(value)
    return ts.strftime("%Y"), ts.strftime("%m"), ts.strftime("%d"), ts.strftime("%Y%m%d")


def full_kor_date(value: Any) -> str:
    ts = pd.Timestamp(value)
    return f"{ts.year:04d}년{ts.month:02d}월{ts.day:02d}일"


def short_kor_date(value: Any) -> str:
    ts = pd.Timestamp(value)
    return f"{ts.year % 100:02d}년{ts.month:02d}월{ts.day:02d}일"


def parse_kor_date(value: Any) -> pd.Timestamp:
    text = str(value).strip().replace("\xa0", "").replace(" ", "")
    if not text or text.lower() == "nan":
        return pd.NaT
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return pd.Timestamp(datetime.strptime(text[:10] if fmt != "%Y%m%d" else text[:8], fmt))
        except Exception:
            pass
    match = re.search(r"(?P<year>\d{2,4})\D+(?P<month>\d{1,2})\D+(?P<day>\d{1,2})", text)
    if not match:
        return pd.NaT
    year = int(match.group("year"))
    if year < 100:
        year += 2000 if year < 50 else 1900
    return pd.Timestamp(year, int(match.group("month")), int(match.group("day")))


def parse_week_end(value: Any) -> pd.Timestamp:
    text = str(value).strip().replace("\xa0", "").replace(" ", "")
    match = re.search(r"(?P<year>\d{2})\D*(?P<month>\d{1,2})\D*(?P<week>\d)\D*주", text)
    if not match:
        return pd.NaT
    year = int(match.group("year"))
    year += 2000 if year < 50 else 1900
    month = int(match.group("month"))
    week = int(match.group("week"))
    last_day = calendar.monthrange(year, month)[1]
    end_day = {1: 7, 2: 14, 3: 21, 4: 28}.get(week, last_day)
    return pd.Timestamp(year, month, min(end_day, last_day))


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).replace("\xa0", "").strip() for col in out.columns]
    aliases = {
        "일반휘발유": COL_GASOLINE,
        "보통 휘발유": COL_GASOLINE,
        "자동차용 경유": COL_DIESEL,
        "정유사상표(전체)": "정유사평균",
        "알뜰주유소(전체)": "알뜰주유소",
        "알뜰평균": "알뜰주유소",
        "알뜰(자영)": "(알뜰-자영)",
        "휘발유[95RON]": "휘발유(95RON)",
        "휘발유[92RON]": "휘발유(92RON)",
        "경유[0.001%]": "경유(0.001%)",
        "경유[0.05%]": "경유(0.05%)",
    }
    return out.rename(columns={col: aliases.get(col, col) for col in out.columns})


def numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
        .replace({"": pd.NA, "-": pd.NA, "nan": pd.NA, "None": pd.NA}),
        errors="coerce",
    )


def read_csv_bytes(raw_bytes: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("euc-kr", "cp949", "utf-8-sig", "utf-8"):
        try:
            return pd.read_csv(io.BytesIO(raw_bytes), encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"CSV decode failed: {last_error}")


def request_json(url: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRY + 1):
        try:
            res = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            res.raise_for_status()
            return res.json()
        except Exception as exc:
            last_error = exc
            if attempt < REQUEST_RETRY:
                time.sleep(REQUEST_SLEEP_SEC * attempt)
    raise RuntimeError(f"request failed: {last_error}")


def post_csv(session: requests.Session, url: str, payload: Any, headers: dict[str, str] | None = None) -> tuple[pd.DataFrame, bytes]:
    last_error: Exception | None = None
    for attempt in range(1, REQUEST_RETRY + 1):
        try:
            res = session.post(url, data=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            res.raise_for_status()
            raw_bytes = res.content
            return normalize_columns(read_csv_bytes(raw_bytes)), raw_bytes
        except Exception as exc:
            last_error = exc
            if attempt < REQUEST_RETRY:
                time.sleep(REQUEST_SLEEP_SEC * attempt)
    raise RuntimeError(f"CSV request failed: {last_error}")


def latest_file(base: Path, pattern: str) -> Path | None:
    if not base.exists():
        return None
    files = [p for p in base.glob(pattern) if p.is_file()]
    if not files:
        return None
    return sorted(files, key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)[0]


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def merge_csv_latest(
    dataset_dir: Path,
    pattern: str,
    stem: str,
    incoming: pd.DataFrame,
    date_col: str,
    date_parser,
) -> Path:
    existing_path = latest_file(dataset_dir, pattern)
    if existing_path is not None:
        existing = pd.read_csv(existing_path, encoding="utf-8-sig")
    else:
        existing = pd.DataFrame(columns=incoming.columns)

    combined = pd.concat([existing, incoming], ignore_index=True)
    if combined.empty:
        combined = pd.DataFrame(columns=incoming.columns)

    if date_col in combined.columns:
        combined["_date"] = combined[date_col].apply(date_parser)
        combined = (
            combined.dropna(subset=["_date"])
            .sort_values("_date")
            .drop_duplicates("_date", keep="last")
            .reset_index(drop=True)
        )
        min_stamp = combined["_date"].min().strftime("%Y%m%d") if len(combined) else yyyymmdd(pd.Timestamp.today())
        max_stamp = combined["_date"].max().strftime("%Y%m%d") if len(combined) else min_stamp
        combined = combined.drop(columns=["_date"])
    else:
        min_stamp = max_stamp = yyyymmdd(pd.Timestamp.today())

    out_path = dataset_dir / f"{stem}_{min_stamp}_{max_stamp}.csv"
    write_csv(out_path, combined)
    return out_path


def save_raw(path: Path, payload: bytes | str | pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        path.write_bytes(payload)
    elif isinstance(payload, pd.DataFrame):
        payload.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        path.write_text(payload, encoding="utf-8")


class Collector:
    def __init__(self, repo_root: Path, start_date: str, end_date: str):
        self.repo_root = repo_root
        self.start_date = start_date
        self.end_date = end_date
        self.outputs = repo_root / "data-analysis" / "00_data_collection" / "outputs"
        self.outputs.mkdir(parents=True, exist_ok=True)

    def dataset_dirs(self, dataset: str) -> tuple[Path, Path, Path]:
        root = self.outputs / dataset
        raw = root / "raw"
        final = root / "final"
        raw.mkdir(parents=True, exist_ok=True)
        final.mkdir(parents=True, exist_ok=True)
        return root, raw, final

    def stamp(self) -> str:
        return f"{yyyymmdd(self.start_date)}_{yyyymmdd(self.end_date)}"

    def collect_fx(self) -> CollectResult:
        dataset, raw_dir, final_dir = self.dataset_dirs("fx_usdkrw")
        api_key = os.getenv("BOK_ECOS_API_KEY", "")
        if not api_key:
            return CollectResult("fx_usdkrw", "failed", detail="BOK_ECOS_API_KEY is missing")

        stat_code = "731Y001"
        item_code = "0000001"
        page_size = 1000

        def fetch_rows(start_value: Any, end_value: Any) -> list[dict[str, Any]]:
            start_ymd = yyyymmdd(start_value)
            end_ymd = yyyymmdd(end_value)

            first_url = (
                f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/"
                f"1/{page_size}/{stat_code}/D/{start_ymd}/{end_ymd}/{item_code}"
            )
            first = request_json(first_url)
            if "RESULT" in first and "StatisticSearch" not in first:
                result = first.get("RESULT", {})
                if result.get("CODE") == "INFO-200":
                    return []
                raise RuntimeError(f"ECOS error: {first}")
            total = int(first.get("StatisticSearch", {}).get("list_total_count", 0))
            out: list[dict[str, Any]] = []
            for start_idx in range(1, total + 1, page_size):
                end_idx = min(start_idx + page_size - 1, total)
                url = (
                    f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/"
                    f"{start_idx}/{end_idx}/{stat_code}/D/{start_ymd}/{end_ymd}/{item_code}"
                )
                data = request_json(url)
                out.extend(data.get("StatisticSearch", {}).get("row", []))
                time.sleep(REQUEST_SLEEP_SEC)
            return out

        def raw_rows_to_final(rows: list[dict[str, Any]]) -> pd.DataFrame:
            raw_frame = pd.DataFrame(rows)
            if raw_frame.empty:
                return pd.DataFrame(columns=[COL_DATE_FX, COL_VALUE_FX])
            out = pd.DataFrame(
                {
                    COL_DATE_FX: pd.to_datetime(raw_frame["TIME"], format="%Y%m%d", errors="coerce"),
                    COL_VALUE_FX: numeric_series(raw_frame["DATA_VALUE"]),
                }
            ).dropna(subset=[COL_DATE_FX, COL_VALUE_FX])
            return out.drop_duplicates(COL_DATE_FX, keep="last").sort_values(COL_DATE_FX)

        target_start = pd.Timestamp(self.start_date).normalize()
        target_end = pd.Timestamp(self.end_date).normalize()
        lookback_days = int(os.getenv("KFF_FX_LOOKBACK_DAYS", "14"))
        lookback_start = target_start - timedelta(days=lookback_days)

        rows = fetch_rows(lookback_start, target_end)
        raw = pd.DataFrame(rows)
        observed = raw_rows_to_final(rows)

        calendar_frame = pd.DataFrame({COL_DATE_FX: pd.date_range(target_start, target_end, freq="D")})
        source = observed[[COL_DATE_FX, COL_VALUE_FX]].copy()

        if source.empty:
            existing_path = latest_file(dataset, "fx_usdkrw_*.csv")
            if existing_path is not None:
                existing = pd.read_csv(existing_path, encoding="utf-8-sig")
                if COL_DATE_FX in existing.columns and COL_VALUE_FX in existing.columns:
                    existing_source = existing[[COL_DATE_FX, COL_VALUE_FX]].copy()
                    existing_source[COL_DATE_FX] = existing_source[COL_DATE_FX].apply(parse_kor_date)
                    existing_source[COL_VALUE_FX] = numeric_series(existing_source[COL_VALUE_FX])
                    existing_source = existing_source.dropna(subset=[COL_DATE_FX, COL_VALUE_FX])
                    existing_source = existing_source[existing_source[COL_DATE_FX] <= target_end]
                    if not existing_source.empty:
                        source = existing_source.sort_values(COL_DATE_FX).tail(1)

        final = (
            pd.concat([source, calendar_frame], ignore_index=True)
            .drop_duplicates(COL_DATE_FX, keep="first")
            .sort_values(COL_DATE_FX)
        )
        final[COL_VALUE_FX] = final[COL_VALUE_FX].ffill()
        final = final[(final[COL_DATE_FX] >= target_start) & (final[COL_DATE_FX] <= target_end)]
        final = final.dropna(subset=[COL_DATE_FX, COL_VALUE_FX])
        final[COL_DATE_FX] = final[COL_DATE_FX].dt.strftime("%Y/%m/%d")

        raw_path = raw_dir / f"ecos_fx_usdkrw_raw_{self.stamp()}.csv"
        final_path = final_dir / f"fx_usdkrw_{self.stamp()}.csv"
        save_raw(raw_path, raw)
        write_csv(final_path, final)
        latest = merge_csv_latest(dataset, "fx_usdkrw_*.csv", "fx_usdkrw", final, COL_DATE_FX, parse_kor_date)
        detail = ""
        if raw.empty:
            detail = "ECOS returned no rows; filled target dates from latest available USD/KRW value"
        elif len(final) > len(observed[(observed[COL_DATE_FX] >= target_start) & (observed[COL_DATE_FX] <= target_end)]):
            detail = "filled missing target dates from latest available USD/KRW value"
        return CollectResult("fx_usdkrw", "completed", len(final), detail=detail, files={"raw": str(raw_path), "snapshot": str(final_path), "latest": str(latest)})

    def collect_crude(self) -> CollectResult:
        dataset, raw_dir, final_dir = self.dataset_dirs("crude")
        page_url = "https://www.opinet.co.kr/glopcoilSelect.do"
        csv_url = "https://www.opinet.co.kr/glopcoil_csv.do"
        sy, sm, sd, stddate = date_parts(self.start_date)
        ey, em, ed, enddate = date_parts(self.end_date)
        payload = [
            ("TERM", "D"), ("STA_Y", sy), ("STA_M", sm), ("STA_D", sd),
            ("END_Y", ey), ("END_M", em), ("END_D", ed),
            ("OILSRTCD", "001"), ("OILSRTCD", "002"), ("OILSRTCD", "003"),
            ("OILSRTCD1", "001"), ("OILSRTCD2", "002"), ("OILSRTCD3", "003"),
            ("STDDATE", stddate), ("ENDDATE", enddate), ("SEL_DIV", "div_dar"),
        ]
        session = requests.Session()
        session.headers.update(HEADERS)
        session.get(page_url, timeout=REQUEST_TIMEOUT)
        raw, raw_bytes = post_csv(session, csv_url, payload)
        required = [COL_PERIOD, "Dubai", "Brent", "WTI"]
        missing = [col for col in required if col not in raw.columns]
        if missing:
            raise RuntimeError(f"crude columns missing: {missing}; columns={list(raw.columns)}")
        final = raw[required].copy()
        for col in ["Dubai", "Brent", "WTI"]:
            final[col] = numeric_series(final[col])
        final["_date"] = final[COL_PERIOD].apply(parse_kor_date)
        final = (
            final.dropna(subset=["_date"])
            .dropna(subset=["Dubai", "Brent", "WTI"], how="all")
            .sort_values("_date")
            .drop_duplicates("_date", keep="last")
            .drop(columns=["_date"])
        )
        raw_path = raw_dir / f"opinet_crude_raw_{self.stamp()}.csv"
        final_path = final_dir / f"crude_{self.stamp()}.csv"
        save_raw(raw_path, raw_bytes)
        write_csv(final_path, final)
        latest = merge_csv_latest(dataset, "crude_*.csv", "crude", final, COL_PERIOD, parse_kor_date)
        return CollectResult("crude", "completed", len(final), files={"raw": str(raw_path), "snapshot": str(final_path), "latest": str(latest)})

    def collect_intl_products(self) -> CollectResult:
        dataset, raw_dir, final_dir = self.dataset_dirs("intl_products")
        page_url = "https://www.opinet.co.kr/glopopdSelect.do"
        csv_url = "https://www.opinet.co.kr/glopopd_csv.do"
        codes = [
            ("B001", "휘발유(95RON)"),
            ("B007", "휘발유(92RON)"),
            ("C001", "등유"),
            ("D009", "경유(0.001%)"),
            ("D008", "경유(0.05%)"),
            ("E001", "고유황중유(180cst/3.5%)"),
            ("F001", "나프타"),
        ]
        sy, sm, sd, stddate = date_parts(self.start_date)
        ey, em, ed, enddate = date_parts(self.end_date)
        payload: list[tuple[str, str]] = [
            ("TERM", "D"), ("HOLIDAY_YN", "Y"), ("STA_Y", sy), ("STA_M", sm), ("STA_D", sd),
            ("END_Y", ey), ("END_M", em), ("END_D", ed),
        ]
        payload.extend(("OILSRTCD", code) for code, _ in codes)
        payload.extend((f"OILSRTCD{idx}", code) for idx, (code, _) in enumerate(codes, start=1))
        payload.extend([("STDDATE", stddate), ("ENDDATE", enddate), ("SEL_DIV", "div_dar")])

        session = requests.Session()
        session.headers.update(HEADERS)
        session.get(page_url, timeout=REQUEST_TIMEOUT)
        raw, raw_bytes = post_csv(session, csv_url, payload)
        raw = normalize_columns(raw)

        out_cols = [COL_PERIOD] + [label for _, label in codes]
        for col in out_cols:
            if col not in raw.columns:
                raw[col] = pd.NA
        final = raw[out_cols].copy()
        final["_date"] = final[COL_PERIOD].apply(parse_kor_date)
        for col in out_cols:
            if col != COL_PERIOD:
                final[col] = numeric_series(final[col])
        final[COL_PERIOD] = final["_date"].apply(lambda x: short_kor_date(x) if pd.notna(x) else "")
        final = final.dropna(subset=["_date"]).sort_values("_date").drop_duplicates("_date", keep="last")
        final = final.drop(columns=["_date"]).reset_index(drop=True)
        diesel001 = final[[COL_PERIOD, "경유(0.001%)"]].copy()

        raw_path = raw_dir / f"opinet_intl_products_raw_{self.stamp()}.csv"
        final_path = final_dir / f"intl_products_{self.stamp()}.csv"
        diesel_path = final_dir / f"intl_product_diesel(0.001)_{self.stamp()}.csv"
        save_raw(raw_path, raw_bytes)
        write_csv(final_path, final)
        write_csv(diesel_path, diesel001)
        latest = merge_csv_latest(dataset, "intl_products_*.csv", "intl_products", final, COL_PERIOD, parse_kor_date)
        latest_diesel = merge_csv_latest(dataset, "intl_product_diesel(0.001)_*.csv", "intl_product_diesel(0.001)", diesel001, COL_PERIOD, parse_kor_date)
        return CollectResult(
            "intl_products",
            "completed",
            len(final),
            files={"raw": str(raw_path), "snapshot": str(final_path), "diesel_snapshot": str(diesel_path), "latest": str(latest), "latest_diesel": str(latest_diesel)},
        )

    def collect_retail_avg(self) -> CollectResult:
        dataset, raw_dir, final_dir = self.dataset_dirs("retail_avg")
        page_url = "https://www.opinet.co.kr/user/dopospdrg/dopOsPdrgSelect.do"
        csv_url = "https://www.opinet.co.kr/user/dopospdrg/dopOsPdrgCsv.do"
        sy, sm, sd, stddate = date_parts(self.start_date)
        ey, em, ed, enddate = date_parts(self.end_date)
        payload = [
            ("all_chk_cnt", "5"), ("INIF_FLAG", "N"), ("chk_cnt", "2"),
            ("h_maxYY", ey), ("h_maxQQ", ""), ("h_maxMM", f"{ey}{em}"), ("h_maxDD", enddate), ("h_maxWW", ""),
            ("sta_dt", ""), ("end_dt", ""), ("TERM", "D"),
            ("STA_Y", sy), ("STA_M", sm), ("STA_D", sd),
            ("END_Y", ey), ("END_M", em), ("END_D", ed),
            ("OIL_CD_B027", "Y"), ("OIL_CD_D047", "Y"),
        ]
        session = requests.Session()
        session.headers.update(HEADERS)
        session.get(page_url, timeout=REQUEST_TIMEOUT)
        raw, raw_bytes = post_csv(session, csv_url, payload)
        raw = normalize_columns(raw)
        required = [COL_DATE, COL_GASOLINE, COL_DIESEL]
        missing = [col for col in required if col not in raw.columns]
        if missing:
            raise RuntimeError(f"retail_avg columns missing: {missing}; columns={list(raw.columns)}")
        final = raw[required].copy()
        final["_date"] = final[COL_DATE].apply(parse_kor_date)
        final[COL_GASOLINE] = numeric_series(final[COL_GASOLINE])
        final[COL_DIESEL] = numeric_series(final[COL_DIESEL])
        final[COL_DATE] = final["_date"].apply(lambda x: full_kor_date(x) if pd.notna(x) else "")
        final = (
            final.dropna(subset=["_date"])
            .dropna(subset=[COL_GASOLINE, COL_DIESEL], how="all")
            .sort_values("_date")
            .drop_duplicates("_date", keep="last")
            .drop(columns=["_date"])
        )
        raw_path = raw_dir / f"opinet_retail_avg_raw_{self.stamp()}.csv"
        final_path = final_dir / f"retail_avg_{self.stamp()}.csv"
        save_raw(raw_path, raw_bytes)
        write_csv(final_path, final)
        latest = merge_csv_latest(dataset, "retail_avg_*.csv", "retail_avg", final, COL_DATE, parse_kor_date)
        return CollectResult("retail_avg", "completed", len(final), files={"raw": str(raw_path), "snapshot": str(final_path), "latest": str(latest)})

    @staticmethod
    def extract_hidden(html: str, name: str, default: str = "") -> str:
        match = re.search(rf'name=["\']{re.escape(name)}["\'][^>]*value=["\']([^"\']*)', html)
        return match.group(1) if match else default

    def collect_brand_price_one(self, product: str) -> tuple[pd.DataFrame, bytes]:
        page_url = "https://www.opinet.co.kr/user/dopostrm/dopOsTrmView.do"
        csv_url = "https://www.opinet.co.kr/user/dopostrm/dopOsTrmCsv.do"
        product_code = {"gasoline": "B027", "diesel": "D047"}[product]
        sy, sm, sd, _ = date_parts(self.start_date)
        ey, em, ed, _ = date_parts(self.end_date)
        headers = dict(HEADERS)
        headers["Referer"] = page_url
        session = requests.Session()
        page = session.get(page_url, headers=headers, timeout=REQUEST_TIMEOUT)
        page.raise_for_status()
        page.encoding = "utf-8"
        html = page.text
        payload = {
            "all_chk_cnt": self.extract_hidden(html, "all_chk_cnt", "5"),
            "all_chk_roc_cnt": self.extract_hidden(html, "all_chk_roc_cnt", "10"),
            "INIF_FLAG": self.extract_hidden(html, "INIF_FLAG", "N"),
            "viewType": "POLL",
            "chk_cnt": self.extract_hidden(html, "chk_cnt", "4"),
            "chk_roc_cnt": "8",
            "h_maxYY": self.extract_hidden(html, "h_maxYY", ey),
            "h_maxQQ": self.extract_hidden(html, "h_maxQQ", f"{ey}1"),
            "h_maxMM": self.extract_hidden(html, "h_maxMM", f"{ey}{em}"),
            "h_maxDD": self.extract_hidden(html, "h_maxDD", f"{ey}{em}{ed}"),
            "h_maxWW": self.extract_hidden(html, "h_maxWW", f"{ey}{em}1"),
            "sta_dt": "",
            "end_dt": "",
            "TERM": "D",
            "STA_Y": sy,
            "STA_M": sm,
            "STA_D": sd,
            "STA_Q": str((int(sm) - 1) // 3 + 1),
            "STA_W": "1",
            "END_Y": ey,
            "END_M": em,
            "END_D": ed,
            "END_Q": str((int(em) - 1) // 3 + 1),
            "END_W": "1",
            "searchType": "POLL",
            "POLL_DIV_CD_REF": "Y",
            "POLL_DIV_CD_SKE": "Y",
            "POLL_DIV_CD_GSC": "Y",
            "POLL_DIV_CD_HDO": "Y",
            "POLL_DIV_CD_SOL": "Y",
            "POLL_DIV_CD_RTO": "Y",
            "POLL_DIV_CD_RTE": "Y",
            "POLL_DIV_CD_ETC": "Y",
            "sltProdCd": product_code,
            "equal": "Y",
        }
        raw, raw_bytes = post_csv(session, csv_url, payload, headers=headers)
        return raw, raw_bytes

    def preprocess_brand(self, raw: pd.DataFrame) -> pd.DataFrame:
        raw = normalize_columns(raw)
        if COL_DATE not in raw.columns and len(raw.columns):
            raw = raw.rename(columns={raw.columns[0]: COL_DATE})
        for col in BRAND_COLUMNS:
            if col not in raw.columns:
                raw[col] = pd.NA
        final = raw[BRAND_COLUMNS].copy()
        final["_date"] = final[COL_DATE].apply(parse_kor_date)
        for col in BRAND_COLUMNS:
            if col != COL_DATE:
                final[col] = numeric_series(final[col])
        final[COL_DATE] = final["_date"].apply(lambda x: full_kor_date(x) if pd.notna(x) else "")
        final = final.dropna(subset=["_date"]).sort_values("_date").drop_duplicates("_date", keep="last")
        return final.drop(columns=["_date"]).reset_index(drop=True)

    def collect_brand_prices(self) -> CollectResult:
        dataset, raw_dir, final_dir = self.dataset_dirs("brand_price")
        raw_gas, raw_gas_bytes = self.collect_brand_price_one("gasoline")
        raw_diesel, raw_diesel_bytes = self.collect_brand_price_one("diesel")
        gas = self.preprocess_brand(raw_gas)
        diesel = self.preprocess_brand(raw_diesel)
        raw_gas_path = raw_dir / f"opinet_brand_gasoline_raw_{self.stamp()}.csv"
        raw_diesel_path = raw_dir / f"opinet_brand_diesel_raw_{self.stamp()}.csv"
        gas_path = final_dir / f"brand_gasoline_{self.stamp()}.csv"
        diesel_path = final_dir / f"brand_diesel_{self.stamp()}.csv"
        save_raw(raw_gas_path, raw_gas_bytes)
        save_raw(raw_diesel_path, raw_diesel_bytes)
        write_csv(gas_path, gas)
        write_csv(diesel_path, diesel)
        latest_gas = merge_csv_latest(dataset, "brand_gasoline_*.csv", "brand_gasoline", gas, COL_DATE, parse_kor_date)
        latest_diesel = merge_csv_latest(dataset, "brand_diesel_*.csv", "brand_diesel", diesel, COL_DATE, parse_kor_date)
        return CollectResult(
            "brand_price",
            "completed",
            len(gas) + len(diesel),
            files={"gasoline_snapshot": str(gas_path), "diesel_snapshot": str(diesel_path), "latest_gasoline": str(latest_gas), "latest_diesel": str(latest_diesel)},
        )

    def open_fuel_tax_session(self) -> requests.Session:
        url = "https://www.opinet.co.kr/user/oftvat/getOfttexSelect.do"
        session = requests.Session()
        headers = dict(HEADERS)
        gate = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        gate.raise_for_status()
        gate.encoding = "utf-8"
        match = re.search(r"frm\.opinet_key\.value\s*=\s*'([^']+)'", gate.text)
        if match:
            opened = session.post(url, data={"opinet_key": match.group(1), "netfunnel_key": ""}, headers=headers, timeout=REQUEST_TIMEOUT)
            opened.raise_for_status()
        return session

    def parse_fuel_tax_html(self, html: str) -> pd.DataFrame:
        tables = pd.read_html(io.StringIO(html), header=[0, 1])
        for table in tables:
            tmp = table.copy()
            cols = []
            for col in tmp.columns:
                if isinstance(col, tuple):
                    parts = [str(x).replace("\xa0", "").strip() for x in col if str(x).strip() and not str(x).startswith("Unnamed") and str(x).strip() != "유류세"]
                    cols.append(parts[-1] if parts else str(col[-1]).strip())
                else:
                    cols.append(str(col).replace("\xa0", "").strip())
            tmp.columns = cols
            if "변동일자" in tmp.columns:
                for col in FUEL_TAX_COLUMNS:
                    if col not in tmp.columns:
                        tmp[col] = pd.NA
                return tmp[FUEL_TAX_COLUMNS].copy()
        raise RuntimeError("fuel tax table not found")

    def collect_fuel_tax_one(self, fuel: str) -> tuple[pd.DataFrame, str]:
        code = {"gasoline": "CC", "diesel": "DD"}[fuel]
        sy, sm, sd, _ = date_parts("1997-01-01")
        ey, em, ed, _ = date_parts(self.end_date)
        payload = {
            "TERM": "T",
            "start_yy": sy,
            "start_mm": sm,
            "start_dd": sd,
            "end_yy": ey,
            "end_mm": em,
            "end_dd": ed,
            "start2_yy": sy,
            "start2_mm": sm,
            "start2_dd": sd,
            "KNOC_TERM1": code,
            "KNOC_TERM": "A",
        }
        url = "https://www.opinet.co.kr/user/oftvat/getOfttexPrintTime.do"
        headers = dict(HEADERS)
        headers["Referer"] = "https://www.opinet.co.kr/user/oftvat/getOfttexSelect.do"
        last_error: Exception | None = None
        for attempt in range(1, REQUEST_RETRY + 1):
            try:
                session = self.open_fuel_tax_session()
                res = session.post(url, data=payload, headers=headers, timeout=REQUEST_TIMEOUT)
                res.raise_for_status()
                res.encoding = "utf-8"
                html = res.text
                return self.parse_fuel_tax_html(html), html
            except Exception as exc:
                last_error = exc
                if attempt < REQUEST_RETRY:
                    time.sleep(REQUEST_SLEEP_SEC * attempt)
        raise RuntimeError(f"fuel tax collection failed: {last_error}")

    def preprocess_fuel_tax(self, raw: pd.DataFrame) -> pd.DataFrame:
        df = normalize_columns(raw)
        for col in FUEL_TAX_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[FUEL_TAX_COLUMNS].copy()
        df["_date"] = df["변동일자"].apply(parse_kor_date)
        df = df.dropna(subset=["_date"])
        df = df[df["_date"] <= pd.Timestamp(self.end_date)]
        for col in FUEL_TAX_COLUMNS:
            if col != "변동일자":
                df[col] = df[col].astype(str).str.replace(",", "", regex=False).str.strip().replace({"nan": "", "None": ""})
        df = df.sort_values("_date").drop_duplicates("_date", keep="last")
        df["변동일자"] = df["_date"].apply(full_kor_date)
        return df.drop(columns=["_date"])[FUEL_TAX_COLUMNS].reset_index(drop=True)

    @staticmethod
    def fuel_tax_xls_html(df: pd.DataFrame, title: str) -> str:
        header_html = "".join(f"<th>{escape(col)}</th>" for col in FUEL_TAX_COLUMNS)
        rows = [f"<tr>{header_html}</tr>", "<tr>" + "".join(f"<td>{escape(col)}</td>" for col in FUEL_TAX_COLUMNS) + "</tr>"]
        for _, row in df.iterrows():
            rows.append("<tr>" + "".join(f"<td>{escape('' if pd.isna(row[col]) else str(row[col]))}</td>" for col in FUEL_TAX_COLUMNS) + "</tr>")
        return "<!DOCTYPE html>\n<html>\n<head><meta charset=\"utf-8\"><title>{}</title></head>\n<body><table>\n{}\n</table></body>\n</html>\n".format(
            escape(title), "\n".join(rows)
        )

    def collect_fuel_tax(self) -> CollectResult:
        dataset, raw_dir, final_dir = self.dataset_dirs("fuel_tax_trend")
        raw_gas, html_gas = self.collect_fuel_tax_one("gasoline")
        raw_diesel, html_diesel = self.collect_fuel_tax_one("diesel")
        gas = self.preprocess_fuel_tax(raw_gas)
        diesel = self.preprocess_fuel_tax(raw_diesel)
        raw_gas_path = raw_dir / f"opinet_gasoline_tax_trend_raw_{self.stamp()}.html"
        raw_diesel_path = raw_dir / f"opinet_diesel_tax_trend_raw_{self.stamp()}.html"
        gas_path = final_dir / f"gasoline_tax_trend_{self.stamp()}.xls"
        diesel_path = final_dir / f"diesel_tax_trend_{self.stamp()}.xls"
        save_raw(raw_gas_path, html_gas)
        save_raw(raw_diesel_path, html_diesel)
        gas_html = self.fuel_tax_xls_html(gas, "gasoline_tax_trend")
        diesel_html = self.fuel_tax_xls_html(diesel, "diesel_tax_trend")
        gas_path.write_text(gas_html, encoding="utf-8-sig")
        diesel_path.write_text(diesel_html, encoding="utf-8-sig")
        latest_gas = dataset / f"gasoline_tax_trend_19970101_{yyyymmdd(self.end_date)}.xls"
        latest_diesel = dataset / f"diesel_tax_trend_19970101_{yyyymmdd(self.end_date)}.xls"
        latest_gas.write_text(gas_html, encoding="utf-8-sig")
        latest_diesel.write_text(diesel_html, encoding="utf-8-sig")
        return CollectResult(
            "fuel_tax_trend",
            "completed",
            len(gas) + len(diesel),
            files={"gasoline_snapshot": str(gas_path), "diesel_snapshot": str(diesel_path), "latest_gasoline": str(latest_gas), "latest_diesel": str(latest_diesel)},
        )

    def collect_refinery_weekly(self) -> CollectResult:
        dataset, raw_dir, final_dir = self.dataset_dirs("refinery_weekly_supply")
        page_url = "https://www.opinet.co.kr/user/dopdavcow/dopAvcowSelect.do"
        csv_url = "https://www.opinet.co.kr/user/dopavcow/dopAvcowCsv.do"
        sy, sm, sw = self.refinery_week_parts(self.start_date)
        ey, em, ew = self.refinery_week_parts(self.end_date)
        headers = dict(HEADERS)
        headers["Referer"] = page_url
        session = requests.Session()
        page = session.get(page_url, headers=headers, timeout=REQUEST_TIMEOUT)
        page.raise_for_status()
        page.encoding = "utf-8"
        html = page.text
        payload = {
            "all_chk_cnt": self.extract_hidden(html, "all_chk_cnt", "5"),
            "INIF_FLAG": self.extract_hidden(html, "INIF_FLAG", "N"),
            "chk_cnt": "2",
            "h_default_y": self.extract_hidden(html, "h_default_y", ey),
            "h_default_q": self.extract_hidden(html, "h_default_q", f"{ey}1"),
            "h_default_m": self.extract_hidden(html, "h_default_m", f"{ey}{em}"),
            "h_default_w": self.extract_hidden(html, "h_default_w", f"{ey}{em}{ew}"),
            "TERM": "W",
            "STA_Y": sy,
            "STA_M": sm,
            "STA_W": sw,
            "STA_Q": str((int(sm) - 1) // 3 + 1),
            "END_Y": ey,
            "END_M": em,
            "END_W": ew,
            "END_Q": str((int(em) - 1) // 3 + 1),
            "tgubun": "b",
            "OIL_CD_B027": "Y",
            "OIL_CD_D047": "Y",
            "equal": "N",
        }
        raw, raw_bytes = post_csv(session, csv_url, payload, headers=headers)
        raw = normalize_columns(raw)
        for col in REFINERY_COLUMNS:
            if col not in raw.columns:
                raw[col] = pd.NA
        final = raw[REFINERY_COLUMNS].copy()
        final[COL_DATE] = final[COL_DATE].astype(str).str.replace("\xa0", "", regex=False).str.replace(" ", "", regex=False).str.strip()
        final = final[final[COL_DATE].str.contains(r"\d{2}\D*\d{1,2}\D*\d주", regex=True, na=False)].copy()
        final["_date"] = final[COL_DATE].apply(parse_week_end)
        final[COL_GASOLINE] = numeric_series(final[COL_GASOLINE])
        final[COL_DIESEL] = numeric_series(final[COL_DIESEL])
        final = final.dropna(subset=["_date"]).sort_values("_date").drop_duplicates(COL_DATE, keep="last")
        final = final.drop(columns=["_date"])[REFINERY_COLUMNS].reset_index(drop=True)
        raw_path = raw_dir / f"opinet_refinery_weekly_supply_raw_{self.stamp()}.csv"
        final_path = final_dir / f"refinery_weekly_supply_prices_by_product_{self.stamp()}.csv"
        save_raw(raw_path, raw_bytes)
        write_csv(final_path, final)
        latest = merge_csv_latest(dataset, "refinery_weekly_supply_prices_by_product_*.csv", "refinery_weekly_supply_prices_by_product", final, COL_DATE, parse_week_end)
        return CollectResult("refinery_weekly_supply", "completed", len(final), files={"raw": str(raw_path), "snapshot": str(final_path), "latest": str(latest)})

    @staticmethod
    def refinery_week_parts(value: str) -> tuple[str, str, str]:
        dt = pd.Timestamp(value)
        week = min(((dt.day - 1) // 7) + 1, 5)
        return f"{dt:%Y}", f"{dt:%m}", str(week)

    def run_all(self) -> list[CollectResult]:
        tasks = [
            self.collect_fx,
            self.collect_crude,
            self.collect_intl_products,
            self.collect_retail_avg,
            self.collect_brand_prices,
            self.collect_fuel_tax,
            self.collect_refinery_weekly,
        ]
        results: list[CollectResult] = []
        for task in tasks:
            try:
                result = task()
            except Exception as exc:
                result = CollectResult(task.__name__.replace("collect_", ""), "failed", detail=repr(exc))
            results.append(result)
            print(f"[{result.status}] {result.name} rows={result.rows} {result.detail}", flush=True)
        return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    args = parser.parse_args()

    collector = Collector(Path(args.repo_root).resolve(), args.start_date, args.end_date)
    results = collector.run_all()

    log_dir = collector.repo_root / "automation" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "source_collection_v1",
        "start_date": args.start_date,
        "end_date": args.end_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results": [result.__dict__ for result in results],
    }
    (log_dir / "latest_source_collection_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = [result for result in results if result.status == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
