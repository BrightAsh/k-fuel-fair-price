from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "data-analysis" / "00_data_collection" / "outputs" / "gas_station_prices_by_region"
LOG_DIR = REPO_ROOT / "automation" / "logs"

OPINET_DOWNLOAD_URL = "https://www.opinet.co.kr/user/opdown/opDownload.do"
MIN_STATION_DATE = pd.Timestamp("2008-04-15")

ALL_REGIONS = [
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
]

EXPECTED_RAW_COLUMNS = {"번호", "지역", "상호", "주소", "기간", "상표", "셀프여부", "휘발유", "경유"}


@dataclass
class DownloadRow:
    region: str
    sigun: str
    start_date: str
    end_date: str
    status: str
    rows: int = 0
    path: str = ""
    detail: str = ""


@dataclass
class RegionResult:
    region: str
    status: str
    sigun_count: int = 0
    download_ok: int = 0
    download_failed: int = 0
    raw_rows: int = 0
    gasoline_date_min: str | None = None
    gasoline_date_max: str | None = None
    diesel_date_min: str | None = None
    diesel_date_max: str | None = None
    station_count: int = 0
    detail: str = ""
    downloads: list[DownloadRow] = field(default_factory=list)


def norm_text(value: Any) -> str:
    return unicodedata.normalize("NFC", str(value)).strip()


def safe_name(value: Any) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", str(value)).strip()


def parse_date(value: Any) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"invalid date: {value}")
    parsed = pd.Timestamp(parsed).normalize()
    if parsed < MIN_STATION_DATE:
        parsed = MIN_STATION_DATE
    return parsed


def ymd(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def date_text(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).strftime("%Y-%m-%d")


def read_csv_auto(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    candidates: list[tuple[int, int, int, str, pd.DataFrame]] = []
    last_error: Exception | None = None
    for enc in encodings:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
            col_score = len(EXPECTED_RAW_COLUMNS & set(df.columns))
            id_score = 0
            if "번호" in df.columns:
                id_score = int(df["번호"].astype(str).str.strip().str.match(r"^A\d+$", na=False).sum())
            date_score = 0
            if "기간" in df.columns:
                date_key = (
                    df["기간"].astype(str)
                    .str.replace(r"\.0$", "", regex=True)
                    .str.replace(r"\D", "", regex=True)
                    .str[:8]
                )
                date_score = int(pd.to_datetime(date_key, format="%Y%m%d", errors="coerce").notna().sum())
            candidates.append((col_score, id_score, date_score, enc, df))
        except Exception as exc:
            last_error = exc
    if not candidates:
        raise RuntimeError(f"CSV read failed: {path}; {last_error!r}")
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    col_score, _, _, enc, df = candidates[0]
    if col_score < 5:
        raise RuntimeError(f"CSV column detection failed: {path}; encoding={enc}; columns={list(df.columns)}")
    return df


def clean_station_raw(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    work = df.copy()
    work.columns = [str(c).replace("\ufeff", "").strip() for c in work.columns]
    required = ["번호", "지역", "상호", "주소", "기간", "상표", "셀프여부", "휘발유", "경유"]
    missing = [col for col in required if col not in work.columns]
    if missing:
        raise ValueError(f"missing raw columns {missing}: {path}")
    work = work[required].copy()
    work["번호"] = work["번호"].astype(str).str.strip()
    work = work[work["번호"].str.match(r"^A\d+$", na=False)].copy()
    date_key = (
        work["기간"].astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\D", "", regex=True)
        .str[:8]
    )
    work["date"] = pd.to_datetime(date_key, format="%Y%m%d", errors="coerce")
    work = work[work["date"].notna()].copy()
    for col in ["휘발유", "경유"]:
        work[col] = pd.to_numeric(
            work[col].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )
    for col in ["지역", "상호", "주소", "상표", "셀프여부"]:
        text = work[col].astype("string").str.strip()
        work[col] = text.mask(text.isin(["", "nan", "None", "<NA>"]))
    work = work.rename(
        columns={
            "번호": "station_id",
            "지역": "region",
            "상호": "station_name",
            "주소": "address",
            "상표": "brand",
            "셀프여부": "is_self",
            "휘발유": "price_gasoline",
            "경유": "price_diesel",
        }
    )
    work["date_str"] = work["date"].dt.strftime("%Y-%m-%d")
    work["source_file"] = path.name
    return work


def is_valid_station_raw(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
        return False
    try:
        head = path.read_bytes()[:8192].lower()
        if b"<html" in head or b"<!doctype html" in head or b"download.do" in head:
            return False
        clean_station_raw(read_csv_auto(path), path)
        return True
    except Exception:
        return False


def read_existing_wide(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    out = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in out.columns:
        out = out.rename(columns={out.columns[0]: "date"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).drop_duplicates("date", keep="last")
    out = out.set_index("date").sort_index()
    out.columns = [str(col) for col in out.columns]
    return out


def write_wide(path: Path, wide: pd.DataFrame) -> None:
    out = wide.copy().sort_index().sort_index(axis=1)
    out.index = pd.Index(pd.to_datetime(out.index).strftime("%Y-%m-%d"), name="date")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.reset_index().to_csv(path, index=False, encoding="utf-8-sig")


def build_price_matrix(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    temp = (
        df[["date", "station_id", value_col]]
        .sort_values(["date", "station_id"])
        .drop_duplicates(["date", "station_id"], keep="last")
    )
    wide = temp.pivot(index="date", columns="station_id", values=value_col)
    wide = wide.sort_index().sort_index(axis=1)
    if len(wide.index):
        wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="D"))
    wide.index.name = "date"
    return wide


def merge_wide(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new.copy()
    if new.empty:
        return existing.copy()
    index = existing.index.union(new.index).sort_values()
    columns = sorted(set(map(str, existing.columns)) | set(map(str, new.columns)))
    out = existing.reindex(index=index, columns=columns).copy()
    incoming = new.reindex(index=index, columns=columns)
    out.update(incoming)
    return out


def load_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def append_change(history: list[list[Any]], date_str: str, value: Any) -> list[list[Any]]:
    if pd.isna(value):
        return history
    text = str(value).strip()
    if not text:
        return history
    if not history:
        return [[date_str, text]]
    last_date, last_value = history[-1]
    if str(last_value) == text:
        return history
    if str(last_date) == date_str:
        history[-1] = [date_str, text]
    else:
        history.append([date_str, text])
    return history


def update_metadata(existing: dict[str, Any], new_rows: pd.DataFrame) -> dict[str, Any]:
    meta = dict(existing)
    if new_rows.empty:
        return meta
    work = (
        new_rows.sort_values(["station_id", "date"])
        .drop_duplicates(["station_id", "date"], keep="last")
        .copy()
    )
    key_map = {
        "region": "region",
        "station_name": "station_name",
        "address": "address",
        "brand": "brand",
        "is_self": "is_self",
    }
    for station_id, group in work.groupby("station_id", sort=True):
        item = meta.setdefault(str(station_id), {key: [] for key in key_map})
        for key in key_map:
            item.setdefault(key, [])
        for _, row in group.iterrows():
            date_str = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
            for src_col, dst_key in key_map.items():
                item[dst_key] = append_change(item.get(dst_key, []), date_str, row.get(src_col))
    return meta


def write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def station_date_bounds(path: Path) -> tuple[str | None, str | None, int, int]:
    if not path.exists():
        return None, None, 0, 0
    header = pd.read_csv(path, nrows=0, encoding="utf-8-sig")
    dates = pd.read_csv(path, usecols=[0], encoding="utf-8-sig")
    date_col = dates.columns[0]
    parsed = pd.to_datetime(dates[date_col], errors="coerce")
    return date_text(parsed.min()), date_text(parsed.max()), len(dates), max(len(header.columns) - 1, 0)


def import_selenium() -> dict[str, Any]:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import Select, WebDriverWait
    except ImportError as exc:
        raise RuntimeError("selenium is required. Install with: python -m pip install selenium") from exc
    return {
        "webdriver": webdriver,
        "Options": Options,
        "By": By,
        "EC": EC,
        "Select": Select,
        "WebDriverWait": WebDriverWait,
    }


def chrome_binary() -> str | None:
    env_path = os.environ.get("KFF_CHROME_BINARY") or os.environ.get("CHROME_PATH")
    candidates = [
        env_path,
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def create_driver(download_dir: Path, headless: bool):
    selenium = import_selenium()
    opts = selenium["Options"]()
    binary = chrome_binary()
    if binary:
        opts.binary_location = binary
    opts.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1600,1200")
    opts.add_argument("--lang=ko-KR")
    driver = selenium["webdriver"].Chrome(options=opts)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(download_dir)})
    return driver


def open_download_page(driver: Any) -> None:
    selenium = import_selenium()
    driver.get(OPINET_DOWNLOAD_URL)
    wait = selenium["WebDriverWait"](driver, 40)
    by = selenium["By"]
    ec = selenium["EC"]
    wait.until(ec.presence_of_element_located((by.ID, "span_start_date_picker")))
    wait.until(ec.presence_of_element_located((by.ID, "span_end_date_picker")))
    wait.until(ec.presence_of_element_located((by.ID, "sido")))
    wait.until(ec.presence_of_element_located((by.ID, "sigun")))


def set_daily_mode(driver: Any) -> None:
    driver.execute_script(
        """
        document.getElementById('rdo3').checked = true;
        document.getElementById('rdo4').checked = true;
        document.getElementById('rdo3').dispatchEvent(new Event('change', {bubbles:true}));
        document.getElementById('rdo4').dispatchEvent(new Event('change', {bubbles:true}));
        """
    )


def select_region(driver: Any, region: str) -> None:
    selenium = import_selenium()
    select = selenium["Select"](driver.find_element(selenium["By"].ID, "sido"))
    wanted = norm_text(region)
    for option in select.options:
        if norm_text(option.text) == wanted:
            select.select_by_visible_text(option.text.strip())
            selenium["WebDriverWait"](driver, 30).until(
                lambda d: len(selenium["Select"](d.find_element(selenium["By"].ID, "sigun")).options) >= 1
            )
            time.sleep(1.5)
            return
    raise ValueError(f"region option not found: {region}")


def sigun_list(driver: Any) -> list[str]:
    selenium = import_selenium()
    select = selenium["Select"](driver.find_element(selenium["By"].ID, "sigun"))
    skip = {"", "시/군/구", "선택", "전체", "선택하세요", "선택하세요."}
    out = []
    for option in select.options:
        text = option.text.strip()
        value = (option.get_attribute("value") or "").strip()
        if text not in skip and value:
            out.append(text)
    return out


def select_sigun(driver: Any, sigun: str) -> None:
    selenium = import_selenium()
    select = selenium["Select"](driver.find_element(selenium["By"].ID, "sigun"))
    for option in select.options:
        text = option.text.strip()
        value = (option.get_attribute("value") or "").strip()
        if text == sigun and value:
            select.select_by_visible_text(text)
            time.sleep(0.8)
            return
    raise ValueError(f"sigun option not found: {sigun}")


def set_dates(driver: Any, start: str, end: str) -> None:
    selenium = import_selenium()
    by = selenium["By"]
    start_el = driver.find_element(by.ID, "span_start_date_picker")
    end_el = driver.find_element(by.ID, "span_end_date_picker")
    driver.execute_script(
        """
        arguments[0].removeAttribute('readonly');
        arguments[1].removeAttribute('readonly');
        arguments[0].value = arguments[2];
        arguments[1].value = arguments[3];
        arguments[0].dispatchEvent(new Event('input', {bubbles:true}));
        arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
        arguments[1].dispatchEvent(new Event('input', {bubbles:true}));
        arguments[1].dispatchEvent(new Event('change', {bubbles:true}));
        """,
        start_el,
        end_el,
        ymd(start),
        ymd(end),
    )
    time.sleep(0.8)


def click_download(driver: Any) -> None:
    selenium = import_selenium()
    driver.execute_script("fn_Download(6);")
    try:
        selenium["WebDriverWait"](driver, 10).until(selenium["EC"].alert_is_present())
        alert = driver.switch_to.alert
        print(f"[confirm] {alert.text}")
        alert.accept()
    except Exception:
        pass


def wait_new_csv(download_dir: Path, before: set[str], timeout: int) -> Path | None:
    start = time.time()
    last_sizes: dict[str, int] = {}
    while time.time() - start < timeout:
        now = set(glob.glob(str(download_dir / "*")))
        new_files = now - before
        csvs = []
        for item in new_files:
            path = Path(item)
            if not path.is_file() or path.name.endswith(".crdownload"):
                continue
            if path.suffix.lower() != ".csv" or path.stat().st_size <= 0:
                continue
            csvs.append(path)
        for path in sorted(csvs, key=lambda p: p.stat().st_mtime, reverse=True):
            size = path.stat().st_size
            key = str(path)
            if last_sizes.get(key) == size:
                return path
            last_sizes[key] = size
        time.sleep(1)
    return None


def collect_region_raw(
    region: str,
    start_date: str,
    end_date: str,
    raw_dir: Path,
    temp_dir: Path,
    headless: bool,
    overwrite: bool,
    download_timeout: int,
    sigun_filter: set[str] | None,
) -> tuple[list[DownloadRow], list[pd.DataFrame]]:
    rows: list[DownloadRow] = []
    parts: list[pd.DataFrame] = []
    driver = create_driver(temp_dir, headless=headless)
    try:
        open_download_page(driver)
        set_daily_mode(driver)
        select_region(driver, region)
        siguns = sigun_list(driver)
        if sigun_filter:
            siguns = [item for item in siguns if norm_text(item) in sigun_filter]
        print(f"[REGION] {region}: sigun_count={len(siguns)}")
        for sigun in siguns:
            file_name = safe_name(f"{region}_{sigun}_{ymd(start_date)}_{ymd(end_date)}.csv")
            raw_path = raw_dir / file_name
            if raw_path.exists() and raw_path.stat().st_size > 0 and not overwrite:
                try:
                    cleaned = clean_station_raw(read_csv_auto(raw_path), raw_path)
                    parts.append(cleaned)
                    rows.append(DownloadRow(region, sigun, start_date, end_date, "skip_exists", len(cleaned), str(raw_path)))
                    print(f"[SKIP] {region}/{sigun}: {raw_path.name}")
                    continue
                except Exception:
                    raw_path.unlink(missing_ok=True)

            print(f"[DOWNLOAD] {region}/{sigun} {start_date}~{end_date}")
            try:
                select_region(driver, region)
                select_sigun(driver, sigun)
                set_dates(driver, start_date, end_date)
                before = set(glob.glob(str(temp_dir / "*")))
                click_download(driver)
                downloaded = wait_new_csv(temp_dir, before, download_timeout)
                if downloaded is None:
                    raise RuntimeError("download timeout")
                if not is_valid_station_raw(downloaded):
                    raise RuntimeError(f"downloaded CSV validation failed: {downloaded}")
                raw_path.unlink(missing_ok=True)
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(downloaded), raw_path)
                cleaned = clean_station_raw(read_csv_auto(raw_path), raw_path)
                parts.append(cleaned)
                rows.append(DownloadRow(region, sigun, start_date, end_date, "ok", len(cleaned), str(raw_path)))
                print(f"[OK] {region}/{sigun}: rows={len(cleaned):,}")
                time.sleep(1)
            except Exception as exc:
                rows.append(DownloadRow(region, sigun, start_date, end_date, "failed", 0, str(raw_path), repr(exc)))
                print(f"[FAIL] {region}/{sigun}: {exc!r}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return rows, parts


def update_region_outputs(output_root: Path, region: str, new_rows: pd.DataFrame) -> RegionResult:
    region_dir = region_output_dir(output_root, region)
    gas_path = region_dir / "gasoline.csv"
    diesel_path = region_dir / "diesel.csv"
    metadata_path = region_dir / "metadata.json"
    region_dir.mkdir(parents=True, exist_ok=True)

    existing_gas = read_existing_wide(gas_path)
    existing_diesel = read_existing_wide(diesel_path)
    new_gas = build_price_matrix(new_rows, "price_gasoline")
    new_diesel = build_price_matrix(new_rows, "price_diesel")
    merged_gas = merge_wide(existing_gas, new_gas)
    merged_diesel = merge_wide(existing_diesel, new_diesel)
    metadata = update_metadata(load_metadata(metadata_path), new_rows)

    write_wide(gas_path, merged_gas)
    write_wide(diesel_path, merged_diesel)
    write_metadata(metadata_path, metadata)

    gas_min, gas_max, _, gas_stations = station_date_bounds(gas_path)
    diesel_min, diesel_max, _, diesel_stations = station_date_bounds(diesel_path)
    return RegionResult(
        region=region,
        status="completed",
        raw_rows=int(len(new_rows)),
        gasoline_date_min=gas_min,
        gasoline_date_max=gas_max,
        diesel_date_min=diesel_min,
        diesel_date_max=diesel_max,
        station_count=max(gas_stations, diesel_stations, len(metadata)),
    )


def parse_regions(value: str) -> list[str]:
    text = value.strip()
    if not text or text.lower() == "all":
        return ALL_REGIONS
    return [norm_text(item) for item in re.split(r"[,;]", text) if item.strip()]


def region_output_dir(output_root: Path, region: str) -> Path:
    wanted = norm_text(region)
    if output_root.exists():
        for child in output_root.iterdir():
            if child.is_dir() and norm_text(child.name) == wanted:
                return child
    return output_root / wanted


def save_report(repo_root: Path, payload: dict[str, Any]) -> None:
    log_dir = repo_root / "automation" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    latest = log_dir / "latest_station_price_collection_report.json"
    stamped = log_dir / f"station_price_collection_{payload['end_date']}.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    stamped.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"[REPORT] {latest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect individual Opinet station prices by region and merge web-ready wide CSVs.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--regions", default="all")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--overwrite-downloads", action="store_true")
    parser.add_argument("--download-timeout", type=int, default=600)
    parser.add_argument("--sigun-filter", default="", help="Optional comma-separated sigun names, mainly for debugging one region.")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output_root = repo_root / "data-analysis" / "00_data_collection" / "outputs" / "gas_station_prices_by_region"
    start = parse_date(args.start_date).strftime("%Y-%m-%d")
    end = parse_date(args.end_date).strftime("%Y-%m-%d")
    if pd.Timestamp(end) < pd.Timestamp(start):
        raise ValueError("end-date is before start-date")
    regions = parse_regions(args.regions)
    sigun_filter = {norm_text(item) for item in re.split(r"[,;]", args.sigun_filter) if item.strip()} or None

    all_results: list[RegionResult] = []
    failed = False

    print("[CONFIG]")
    print(f"repo_root   = {repo_root}")
    print(f"output_root = {output_root}")
    print(f"date_range  = {start} ~ {end}")
    print(f"regions     = {', '.join(regions)}")
    print(f"headless    = {args.headless}")
    print(f"chrome      = {chrome_binary() or 'selenium-manager default'}")

    with tempfile.TemporaryDirectory(prefix="kff_opinet_station_") as temp_name:
        temp_root = Path(temp_name)
        raw_base = temp_root / "raw"
        for region in regions:
            region = norm_text(region)
            raw_dir = raw_base / region
            temp_dir = temp_root / safe_name(region)
            raw_dir.mkdir(parents=True, exist_ok=True)
            temp_dir.mkdir(parents=True, exist_ok=True)
            print("=" * 100)
            print(f"[START] {region}")
            try:
                downloads, parts = collect_region_raw(
                    region=region,
                    start_date=start,
                    end_date=end,
                    raw_dir=raw_dir,
                    temp_dir=temp_dir,
                    headless=args.headless,
                    overwrite=args.overwrite_downloads,
                    download_timeout=args.download_timeout,
                    sigun_filter=sigun_filter,
                )
                if not parts:
                    raise RuntimeError("no valid downloaded station rows")
                new_rows = pd.concat(parts, ignore_index=True, sort=False)
                result = update_region_outputs(output_root, region, new_rows)
                result.sigun_count = len(downloads)
                result.download_ok = sum(1 for row in downloads if row.status in {"ok", "skip_exists"})
                result.download_failed = sum(1 for row in downloads if row.status == "failed")
                result.downloads = downloads
                if result.download_failed:
                    result.status = "partial"
                    failed = True
                all_results.append(result)
                print(
                    f"[DONE] {region}: status={result.status}, rows={result.raw_rows:,}, "
                    f"gasoline_max={result.gasoline_date_max}, diesel_max={result.diesel_date_max}"
                )
            except Exception as exc:
                failed = True
                all_results.append(RegionResult(region=region, status="failed", detail=repr(exc)))
                print(f"[FAILED] {region}: {exc!r}")

    payload = {
        "schema_version": "station_price_collection_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start,
        "end_date": end,
        "regions": regions,
        "results": [
            {
                **{k: v for k, v in asdict(result).items() if k != "downloads"},
                "downloads": [asdict(row) for row in result.downloads],
            }
            for result in all_results
        ],
    }
    save_report(repo_root, payload)

    if failed:
        print("[RESULT] failed or partial station collection")
        return 1
    print("[RESULT] station collection completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
