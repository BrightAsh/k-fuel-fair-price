from __future__ import annotations

import argparse
import calendar
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


LITER_PER_BBL = 158.987294928

FINAL_COLUMNS = [
    "date",
    "두바이",
    "브렌트",
    "WTI",
    "휘발유92RON",
    "경유0.05",
    "경유0.001",
    "usdkrw",
    "두바이_원리터",
    "브렌트_원리터",
    "WTI_원리터",
    "휘발유92RON_원리터",
    "경유0.05_원리터",
    "경유0.001_원리터",
    "보통휘발유_평균",
    "자동차용경유_평균",
    "보통휘발유_정유사평균",
    "보통휘발유_SK에너지",
    "보통휘발유_GS칼텍스",
    "보통휘발유_HD현대오일뱅크",
    "보통휘발유_S-OIL",
    "보통휘발유_알뜰주유소",
    "보통휘발유_알뜰-자영",
    "보통휘발유_자가상표",
    "자동차용경유_정유사평균",
    "자동차용경유_SK에너지",
    "자동차용경유_GS칼텍스",
    "자동차용경유_HD현대오일뱅크",
    "자동차용경유_S-OIL",
    "자동차용경유_알뜰주유소",
    "자동차용경유_알뜰-자영",
    "자동차용경유_자가상표",
    "보통휘발유_개별소비세",
    "보통휘발유_교통에너지환경세",
    "보통휘발유_교육세",
    "보통휘발유_주행세",
    "보통휘발유_판매부과금",
    "자동차용경유_개별소비세",
    "자동차용경유_교통에너지환경세",
    "자동차용경유_교육세",
    "자동차용경유_주행세",
    "자동차용경유_판매부과금",
    "정유소_세전_보통휘발유",
    "정유소_세전_자동차용경유",
]


def read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def latest_file(base: Path, pattern: str) -> Path:
    files = [p for p in base.glob(pattern) if p.is_file()]
    if not files:
        raise FileNotFoundError(f"{base}/{pattern}")
    return sorted(files, key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)[0]


def parse_date(value: Any) -> pd.Timestamp:
    text = str(value).strip().replace("\xa0", "").replace(" ", "")
    if not text or text.lower() == "nan":
        return pd.NaT
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            target = text[:8] if fmt == "%Y%m%d" else text[:10]
            return pd.Timestamp(datetime.strptime(target, fmt))
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
    day = {1: 7, 2: 14, 3: 21, 4: 28}.get(week, last_day)
    return pd.Timestamp(year, month, min(day, last_day))


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).replace("\xa0", "").strip() for col in out.columns]
    aliases = {
        "기간": "기간",
        "구분": "구분",
        "변환": "변환",
        "원자료": "원자료",
        "일반휘발유": "보통휘발유",
        "자동차용 경유": "자동차용경유",
        "보통 휘발유": "보통휘발유",
        "휘발유[95RON]": "휘발유(95RON)",
        "휘발유[92RON]": "휘발유(92RON)",
        "경유[0.05%]": "경유(0.05%)",
        "경유[0.001%]": "경유(0.001%)",
        "(알뜰-자영)": "알뜰-자영",
    }
    return out.rename(columns={col: aliases.get(col, col) for col in out.columns})


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
        .replace({"": pd.NA, "-": pd.NA, "nan": pd.NA, "None": pd.NA}),
        errors="coerce",
    )


def coerce_numeric(df: pd.DataFrame, exclude: list[str] | None = None) -> pd.DataFrame:
    exclude = exclude or []
    out = df.copy()
    for col in out.columns:
        if col not in exclude:
            out[col] = to_numeric(out[col])
    return out


def read_crude(path: Path) -> pd.DataFrame:
    df = normalize_columns(read_csv(path))
    df["date"] = df["기간"].apply(parse_date)
    out = df.drop(columns=["기간"]).rename(columns={"Dubai": "두바이", "Brent": "브렌트"})
    return coerce_numeric(out, ["date"]).dropna(subset=["date"]).sort_values("date")


def read_retail_avg(path: Path) -> pd.DataFrame:
    df = normalize_columns(read_csv(path))
    df["date"] = df["구분"].apply(parse_date)
    out = df.drop(columns=["구분"]).rename(
        columns={"보통휘발유": "보통휘발유_평균", "자동차용경유": "자동차용경유_평균"}
    )
    return coerce_numeric(out, ["date"]).dropna(subset=["date"]).sort_values("date")


def read_brand(path: Path, prefix: str) -> pd.DataFrame:
    df = normalize_columns(read_csv(path))
    df["date"] = df["구분"].apply(parse_date)
    df = df.drop(columns=["구분"]).rename(columns={"(알뜰-자영)": "알뜰-자영"})
    rename_map = {col: f"{prefix}_{col}" for col in df.columns if col != "date"}
    return coerce_numeric(df.rename(columns=rename_map), ["date"]).dropna(subset=["date"]).sort_values("date")


def read_fx(path: Path) -> pd.DataFrame:
    df = normalize_columns(read_csv(path))
    date_col = "변환" if "변환" in df.columns else df.columns[0]
    value_col = "원자료" if "원자료" in df.columns else df.columns[1]
    out = pd.DataFrame({"date": df[date_col].apply(parse_date), "usdkrw": to_numeric(df[value_col])})
    return out.dropna(subset=["date"]).sort_values("date")


def read_intl_products(path: Path) -> pd.DataFrame:
    df = normalize_columns(read_csv(path))
    df["date"] = df["기간"].apply(parse_date)
    out = df.rename(
        columns={
            "휘발유(92RON)": "휘발유92RON",
            "경유(0.05%)": "경유0.05",
            "경유(0.001%)": "경유0.001",
        }
    )
    keep = ["date", "휘발유92RON", "경유0.05"]
    keep = [col for col in keep if col in out.columns]
    out = coerce_numeric(out[keep], ["date"]).dropna(subset=["date"]).sort_values("date")
    out["non_nulls"] = out.drop(columns=["date"]).notna().sum(axis=1)
    return out.sort_values(["date", "non_nulls"]).drop_duplicates("date", keep="last").drop(columns=["non_nulls"])


def read_diesel001(path: Path) -> pd.DataFrame:
    df = normalize_columns(read_csv(path))
    df["date"] = df["기간"].apply(parse_date)
    value_col = "경유(0.001%)" if "경유(0.001%)" in df.columns else df.columns[-1]
    out = pd.DataFrame({"date": df["date"], "경유0.001": to_numeric(df[value_col])})
    out = out.dropna(subset=["date"]).sort_values("date")
    calendar_df = pd.DataFrame({"date": pd.date_range(out["date"].min(), out["date"].max(), freq="D")})
    return calendar_df.merge(out, on="date", how="left").ffill()


def read_excel_html(path: Path) -> pd.DataFrame:
    try:
        return pd.read_excel(path, header=0)
    except Exception:
        tables = pd.read_html(path, header=0)
        if not tables:
            raise
        return tables[0]


def read_tax(path: Path, prefix: str) -> pd.DataFrame:
    df = read_excel_html(path)
    if "변동일자" not in df.columns:
        df.columns = df.iloc[0]
        df = df.iloc[1:].copy()
    df = normalize_columns(df).drop(columns=["합계"], errors="ignore")
    df["date"] = df["변동일자"].apply(parse_date)
    df = df.drop(columns=["변동일자"]).dropna(subset=["date"])
    df = coerce_numeric(df, ["date"]).sort_values("date").reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=["date"])
    calendar_df = pd.DataFrame({"date": pd.date_range(df["date"].min(), df["date"].max(), freq="D")})
    out = calendar_df.merge(df, on="date", how="left").sort_values("date")
    value_cols = [col for col in out.columns if col != "date"]
    out[value_cols] = out[value_cols].ffill()
    return out.rename(columns={col: f"{prefix}_{col}" for col in value_cols})


def read_refinery(path: Path) -> pd.DataFrame:
    df = normalize_columns(read_csv(path))
    df["date"] = df["구분"].apply(parse_week_end)
    rename_map = {
        "보통휘발유": "정유소_세전_보통휘발유",
        "자동차용경유": "정유소_세전_자동차용경유",
    }
    out = df[["date", "보통휘발유", "자동차용경유"]].rename(columns=rename_map)
    return coerce_numeric(out, ["date"]).dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")


def add_krw_liter_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    conversions = {
        "두바이": "두바이_원리터",
        "브렌트": "브렌트_원리터",
        "WTI": "WTI_원리터",
        "휘발유92RON": "휘발유92RON_원리터",
        "경유0.05": "경유0.05_원리터",
        "경유0.001": "경유0.001_원리터",
    }
    for source, target in conversions.items():
        if source in out.columns:
            out[target] = out[source] * out["usdkrw"] / LITER_PER_BBL
    return out


def build_preprocessed(repo_root: Path) -> Path:
    base = repo_root / "data-analysis" / "00_data_collection" / "outputs"
    paths = {
        "crude": latest_file(base / "crude", "crude_*.csv"),
        "retail": latest_file(base / "retail_avg", "retail_avg_*.csv"),
        "brand_g": latest_file(base / "brand_price", "brand_gasoline_*.csv"),
        "brand_d": latest_file(base / "brand_price", "brand_diesel_*.csv"),
        "fx": latest_file(base / "fx_usdkrw", "fx_usdkrw_*.csv"),
        "intl": latest_file(base / "intl_products", "intl_products_*.csv"),
        "diesel001": latest_file(base / "intl_products", "intl_product_diesel(0.001)_*.csv"),
        "tax_g": latest_file(base / "fuel_tax_trend", "gasoline_tax_trend_*.xls"),
        "tax_d": latest_file(base / "fuel_tax_trend", "diesel_tax_trend_*.xls"),
        "refinery": latest_file(base / "refinery_weekly_supply", "refinery_weekly_supply_prices_by_product_*.csv"),
    }

    crude = read_crude(paths["crude"])
    retail = read_retail_avg(paths["retail"])
    brand_g = read_brand(paths["brand_g"], "보통휘발유")
    brand_d = read_brand(paths["brand_d"], "자동차용경유")
    fx = read_fx(paths["fx"])
    intl = read_intl_products(paths["intl"])
    diesel001 = read_diesel001(paths["diesel001"])
    tax_g = read_tax(paths["tax_g"], "보통휘발유")
    tax_d = read_tax(paths["tax_d"], "자동차용경유")
    refinery = read_refinery(paths["refinery"])

    start = max(retail["date"].min(), crude["date"].min(), fx["date"].min())
    end = min(retail["date"].max(), crude["date"].max(), fx["date"].max())
    calendar_df = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})

    merged = calendar_df
    for frame in [crude, intl, diesel001, fx]:
        merged = merged.merge(frame, on="date", how="left")
    market_cols = [col for col in merged.columns if col != "date"]
    merged[market_cols] = merged[market_cols].ffill()
    merged = add_krw_liter_columns(merged)

    for frame in [retail, brand_g, brand_d, tax_g, tax_d, refinery]:
        merged = merged.merge(frame, on="date", how="left")

    for col in FINAL_COLUMNS:
        if col not in merged.columns:
            merged[col] = pd.NA
    merged = merged[FINAL_COLUMNS].sort_values("date").reset_index(drop=True)
    merged["date"] = merged["date"].dt.strftime("%Y-%m-%d")

    out_dir = repo_root / "data-analysis" / "01_data_preprocessing" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "분석용일별통합데이터.csv"
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[preprocess] saved {out_path} rows={len(merged)} cols={len(merged.columns)}")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    build_preprocessed(Path(args.repo_root).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
