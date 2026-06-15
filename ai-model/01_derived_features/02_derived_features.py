# %% [markdown]
# # AI Model 02 파생 변수/파생 데이터 추가
#
# AI Model 01의 자동 수집/1차 전처리 산출물을 읽어 AI Model 03 격자화 전에 필요한 표준 CSV를 만듭니다.
#
# 산출물은 `DATA_COLLECTION_PATH/derived_data/`에 저장합니다.

# %%
# ============================================================
# AI Model 02 공통 경로 설정
# ============================================================
from google.colab import drive
drive.mount("/content/drive")

from pathlib import Path
import json
import os
import re
import time
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
import requests

ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
DATA_PATH = os.path.join(ROOT_PATH, "data") + "/"
PROCESSED_PATH = os.path.join(ROOT_PATH, "preprocessed_data") + "/"
DATA_COLLECTION_PATH = os.path.join(ROOT_PATH, "data collection") + "/"
DERIVED_DATA_PATH = os.path.join(DATA_COLLECTION_PATH, "derived_data") + "/"

ROOT_DIR = Path(ROOT_PATH)
DATA_DIR = Path(DATA_PATH)
PROCESSED_DIR = Path(PROCESSED_PATH)
DATA_COLLECTION_DIR = Path(DATA_COLLECTION_PATH)
DERIVED_DIR = Path(DERIVED_DATA_PATH)
DERIVED_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = "2008-01-01"
END_DATE = None  # None이면 수집된 데이터의 최대 날짜 또는 오늘 날짜 사용

GEOCODE_FACILITY_IF_MISSING = True
GEOCODE_SLEEP_SEC = 0.20

try:
    from google.colab import userdata
except Exception:
    userdata = None

def get_secret(name, default=""):
    if userdata is None:
        return default
    try:
        value = userdata.get(name)
        return value if value is not None else default
    except Exception:
        return default

KAKAO_REST_API_KEY = get_secret("KAKAO_REST_API_KEY", "")
VWORLD_API_KEY = get_secret("VWORLD_API_KEY", "")

print(f"ROOT_PATH           = {ROOT_PATH}")
print(f"DATA_PATH           = {DATA_PATH}")
print(f"PROCESSED_PATH      = {PROCESSED_PATH}")
print(f"DATA_COLLECTION_PATH= {DATA_COLLECTION_PATH}")
print(f"DERIVED_DATA_PATH   = {DERIVED_DATA_PATH}")

# %%
# ============================================================
# 공통 함수
# ============================================================
REGION_NAMES = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

def nfc(x):
    if x is None:
        return x
    return unicodedata.normalize("NFC", str(x))

def read_csv_flexible(path, **kwargs):
    path = Path(path)
    last_error = None
    for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except Exception as e:
            last_error = e
    raise last_error

def read_table_flexible(path, **kwargs):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in [".csv", ".txt"]:
        return read_csv_flexible(path, **kwargs)

    if suffix in [".xls", ".xlsx", ".html", ".htm"]:
        try:
            return pd.read_excel(path, **kwargs)
        except Exception:
            tables = pd.read_html(path, **kwargs)
            if not tables:
                raise ValueError(f"표를 찾지 못했습니다: {path}")
            tables = sorted(tables, key=lambda x: x.shape[0] * x.shape[1], reverse=True)
            return tables[0]

    return read_csv_flexible(path, **kwargs)

def first_existing(paths):
    for p in paths:
        if p is None:
            continue
        p = Path(p)
        if p.exists():
            return p
    return None

def latest_glob(patterns):
    files = []
    for pattern in patterns:
        files.extend(Path().glob(str(pattern)) if not str(pattern).startswith("/") else Path("/").glob(str(pattern).lstrip("/")))
    files = [p for p in files if p.exists() and p.is_file()]
    if not files:
        return None
    return sorted(files, key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)[0]

def latest_under(base, pattern):
    base = Path(base)
    if not base.exists():
        return None
    files = [p for p in base.glob(pattern) if p.exists() and p.is_file()]
    if not files:
        return None
    return sorted(files, key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)[0]

def find_col(columns, candidates):
    norm = {nfc(c).strip(): c for c in columns}
    for cand in candidates:
        cand = nfc(cand).strip()
        if cand in norm:
            return norm[cand]
    lower = {nfc(c).strip().lower(): c for c in columns}
    for cand in candidates:
        cand = nfc(cand).strip().lower()
        if cand in lower:
            return lower[cand]
    return None

def parse_korean_short_date(value):
    if pd.isna(value):
        return pd.NaT
    s = str(value).strip()
    m = re.match(r"^(\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일$", s)
    if not m:
        return pd.NaT
    yy, mm, dd = map(int, m.groups())
    year = 2000 + yy if yy < 80 else 1900 + yy
    return pd.Timestamp(year=year, month=mm, day=dd)

def parse_date_series(s):
    out = pd.to_datetime(s, errors="coerce")
    miss = out.isna()
    if miss.any():
        parsed = s[miss].map(parse_korean_short_date)
        out.loc[miss] = parsed
    return out

def clean_number_series(s):
    return pd.to_numeric(
        s.astype(str)
         .str.replace(",", "", regex=False)
         .str.replace(" ", "", regex=False)
         .replace({"nan": np.nan, "None": np.nan, "": np.nan, "-": np.nan}),
        errors="coerce",
    )

def safe_col_name(name):
    s = nfc(name).strip()
    s = re.sub(r"[\s/()\\[\\]{}:;,.]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def save_csv(df, filename):
    path = DERIVED_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {path} rows={len(df):,} cols={len(df.columns):,}")
    return path

def date_min_max(df, date_col="date"):
    if date_col not in df.columns or len(df) == 0:
        return (None, None)
    d = parse_date_series(df[date_col])
    if d.notna().sum() == 0:
        return (None, None)
    return (d.min().strftime("%Y-%m-%d"), d.max().strftime("%Y-%m-%d"))

def display_df(df, title=None, n=20):
    if title:
        print("\n" + "=" * 100)
        print(title)
    try:
        display(df.head(n))
    except Exception:
        print(df.head(n).to_string(index=False))

def resolve_collected_file(dataset, final_pattern, data_filename=None):
    candidates = []
    p = latest_under(DATA_COLLECTION_DIR / dataset / "final", final_pattern)
    if p is not None:
        candidates.append(p)
    if data_filename:
        p2 = DATA_DIR / data_filename
        if p2.exists():
            candidates.append(p2)
    return candidates[0] if candidates else None

def resolve_station_region_root():
    candidates = [
        DATA_COLLECTION_DIR / "gas_station_prices_by_region" / "final",
        PROCESSED_DIR / "additional_data" / "gas_station_prices_by_region",
    ]
    for p in candidates:
        if p.exists() and any(x.is_dir() for x in p.iterdir()):
            return p
    return candidates[0]

def resolve_facility_source():
    return first_existing([
        DATA_COLLECTION_DIR / "facility" / "final" / "facility_location_data_final.csv",
        DATA_COLLECTION_DIR / "facility" / "final" / "facility_points.csv",
        PROCESSED_DIR / "additional_data" / "1 facility_location_data_final.csv",
        DATA_COLLECTION_DIR / "facility" / "final" / "facility_data.csv",
        DATA_DIR / "facility_data.csv",
    ])

def resolve_official_land_price_source():
    return first_existing([
        DATA_COLLECTION_DIR / "official_land_price" / "final" / "공시지가.csv",
        DATA_DIR / "공시지가.csv",
    ])

# %%
# ============================================================
# 1. 원문 코드 입력 파일 확인 + AI Model 01 산출물 준비 여부
# ============================================================
INPUT_SPECS = [
    {
        "input_name": "fx_usdkrw",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("fx_usdkrw", "fx_usdkrw_*.csv", "fx_usdkrw.csv"),
    },
    {
        "input_name": "crude",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("crude", "crude_*.csv", "crude.csv"),
    },
    {
        "input_name": "intl_products",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("intl_products", "intl_products_*.csv", "intl_products.csv"),
    },
    {
        "input_name": "retail_avg",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("retail_avg", "retail_avg_*.csv", "retail_avg.csv"),
    },
    {
        "input_name": "brand_gasoline",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("brand_price", "brand_gasoline_*.csv", "brand_gasoline.csv"),
    },
    {
        "input_name": "brand_diesel",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("brand_price", "brand_diesel_*.csv", "brand_diesel.csv"),
    },
    {
        "input_name": "gasoline_tax_trend",
        "required_for": "national_daily_features",
        "path": first_existing([
            latest_under(DATA_COLLECTION_DIR / "fuel_tax_trend" / "final", "gasoline_tax_trend_*.xls"),
            DATA_DIR / "gasoline_tax_trend.xls",
        ]),
    },
    {
        "input_name": "diesel_tax_trend",
        "required_for": "national_daily_features",
        "path": first_existing([
            latest_under(DATA_COLLECTION_DIR / "fuel_tax_trend" / "final", "diesel_tax_trend_*.xls"),
            DATA_DIR / "diesel_tax_trend.xls",
        ]),
    },
    {
        "input_name": "refinery_weekly_supply",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("refinery_weekly_supply", "refinery_weekly_supply_prices_by_product_*.csv", "refinery_weekly_supply_prices_by_product.csv"),
    },
    {
        "input_name": "gas_station_prices_by_region",
        "required_for": "grid_station_panel",
        "path": resolve_station_region_root(),
    },
    {
        "input_name": "facility",
        "required_for": "facility_grid_features",
        "path": resolve_facility_source(),
    },
    {
        "input_name": "official_land_price",
        "required_for": "official_land_price_join",
        "path": resolve_official_land_price_source(),
    },
]

readiness_rows = []
for spec in INPUT_SPECS:
    p = spec["path"]
    exists = bool(p is not None and Path(p).exists())
    row = {
        "input_name": spec["input_name"],
        "required_for": spec["required_for"],
        "exists": exists,
        "path": str(p) if p is not None else "",
        "is_dir": bool(exists and Path(p).is_dir()),
        "rows": np.nan,
        "columns": "",
        "date_min": "",
        "date_max": "",
        "note": "",
    }
    try:
        if exists and Path(p).is_file():
            sample = read_table_flexible(p)
            row["rows"] = len(sample)
            row["columns"] = ", ".join(map(str, sample.columns))
            date_col = find_col(sample.columns, ["date", "날짜", "일자", "변동일자", "week_end"])
            if date_col:
                tmp = sample.rename(columns={date_col: "date"})
                row["date_min"], row["date_max"] = date_min_max(tmp, "date")
        elif exists and Path(p).is_dir():
            row["note"] = f"region_dirs={len([x for x in Path(p).iterdir() if x.is_dir()])}"
    except Exception as e:
        row["note"] = f"inspect_error={type(e).__name__}: {e}"
    readiness_rows.append(row)

readiness = pd.DataFrame(readiness_rows)
save_csv(readiness, "data_readiness_summary.csv")
display_df(readiness, "[입력 준비 여부]")

# %%
# ============================================================
# 2. 전국 일별 파생 데이터 생성
# ============================================================
def standardize_daily_table(path, prefix, output_filename, date_candidates=None):
    if path is None or not Path(path).exists():
        print(f"[SKIP] {output_filename}: input 없음")
        return pd.DataFrame(columns=["date"])

    date_candidates = date_candidates or ["date", "날짜", "일자", "변동일자", "week_end"]
    raw = read_table_flexible(path)
    date_col = find_col(raw.columns, date_candidates)
    if date_col is None:
        print(f"[SKIP] {output_filename}: date 컬럼 없음 -> {list(raw.columns)}")
        return pd.DataFrame(columns=["date"])

    out = pd.DataFrame()
    out["date"] = parse_date_series(raw[date_col])
    for c in raw.columns:
        if c == date_col:
            continue
        s = clean_number_series(raw[c])
        if s.notna().sum() == 0:
            continue
        out[f"{prefix}_{safe_col_name(c)}"] = s

    out = out.dropna(subset=["date"]).copy()
    out = out.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    save_csv(out, output_filename)
    return out

def build_tax_daily(path, fuel_prefix, date_index):
    if path is None or not Path(path).exists():
        return pd.DataFrame({"date": date_index})

    raw = read_table_flexible(path)
    date_col = find_col(raw.columns, ["변동일자", "date", "날짜", "일자"])
    if date_col is None:
        return pd.DataFrame({"date": date_index})

    out = pd.DataFrame()
    out["effective_date"] = parse_date_series(raw[date_col])

    for c in raw.columns:
        if c == date_col:
            continue
        s = clean_number_series(raw[c])
        if s.notna().sum() == 0:
            continue
        out[f"{fuel_prefix}_tax_{safe_col_name(c)}"] = s

    out = out.dropna(subset=["effective_date"]).copy()
    out = out.sort_values("effective_date").drop_duplicates("effective_date", keep="last")
    calendar = pd.DataFrame({"date": pd.to_datetime(date_index)})
    merged = pd.merge_asof(
        calendar.sort_values("date"),
        out.sort_values("effective_date"),
        left_on="date",
        right_on="effective_date",
        direction="backward",
    )
    if "effective_date" in merged.columns:
        merged[f"{fuel_prefix}_tax_effective_date"] = merged["effective_date"].dt.strftime("%Y-%m-%d")
        merged = merged.drop(columns=["effective_date"])
    merged["date"] = merged["date"].dt.strftime("%Y-%m-%d")
    return merged

source_by_name = {r["input_name"]: Path(r["path"]) if r["path"] else None for _, r in readiness.iterrows()}

daily_tables = []
daily_tables.append(standardize_daily_table(source_by_name.get("fx_usdkrw"), "fx", "fx_usdkrw_daily.csv"))
daily_tables.append(standardize_daily_table(source_by_name.get("crude"), "crude", "crude_daily.csv"))
daily_tables.append(standardize_daily_table(source_by_name.get("intl_products"), "intl_product", "intl_products_daily.csv"))
daily_tables.append(standardize_daily_table(source_by_name.get("retail_avg"), "retail", "retail_avg_daily.csv"))
daily_tables.append(standardize_daily_table(source_by_name.get("brand_gasoline"), "brand_gasoline", "brand_gasoline_daily.csv"))
daily_tables.append(standardize_daily_table(source_by_name.get("brand_diesel"), "brand_diesel", "brand_diesel_daily.csv"))
daily_tables.append(standardize_daily_table(source_by_name.get("refinery_weekly_supply"), "refinery_weekly", "refinery_weekly_supply_daily_like.csv", ["date", "week_end", "기준일"]))

non_empty_dates = []
for df in daily_tables:
    if "date" in df.columns and len(df) > 0:
        non_empty_dates.extend(pd.to_datetime(df["date"], errors="coerce").dropna().tolist())

start_dt = pd.Timestamp(START_DATE)
if END_DATE:
    end_dt = pd.Timestamp(END_DATE)
elif non_empty_dates:
    end_dt = max(non_empty_dates)
else:
    end_dt = pd.Timestamp.today().normalize()

date_index = pd.date_range(start_dt, end_dt, freq="D").strftime("%Y-%m-%d")

tax_gasoline = build_tax_daily(source_by_name.get("gasoline_tax_trend"), "gasoline", date_index)
tax_diesel = build_tax_daily(source_by_name.get("diesel_tax_trend"), "diesel", date_index)
save_csv(tax_gasoline, "gasoline_tax_daily.csv")
save_csv(tax_diesel, "diesel_tax_daily.csv")
daily_tables.extend([tax_gasoline, tax_diesel])

national = pd.DataFrame({"date": date_index})
for df in daily_tables:
    if len(df) == 0:
        continue
    national = national.merge(df, on="date", how="left")

national = national.sort_values("date").reset_index(drop=True)
save_csv(national, "national_daily_features.csv")
display_df(national, "[전국 일별 파생 데이터]")

# %%
# ============================================================
# 3. 주유소 위치/속성 파생 데이터 생성
# ============================================================
def event_list_to_rows(station_id, info, field):
    rows = []
    values = info.get(field, [])
    if not isinstance(values, list):
        return rows

    for item in values:
        if not isinstance(item, list) or len(item) == 0:
            continue
        if field == "location" and len(item) >= 3:
            rows.append({
                "station_id": station_id,
                "field": field,
                "effective_date": item[0],
                "lat": item[1],
                "lon": item[2],
                "value": "",
            })
        elif field != "location" and len(item) >= 2:
            rows.append({
                "station_id": station_id,
                "field": field,
                "effective_date": item[0],
                "lat": np.nan,
                "lon": np.nan,
                "value": item[1],
            })
    return rows

def latest_event_value(info, field):
    values = info.get(field, [])
    if not isinstance(values, list) or len(values) == 0:
        return None
    rows = []
    for item in values:
        if isinstance(item, list) and len(item) >= 2:
            rows.append(item)
    if not rows:
        return None
    rows = sorted(rows, key=lambda x: str(x[0]))
    return rows[-1]

def price_file_info(path):
    if path is None or not Path(path).exists():
        return {"exists": False, "rows": 0, "station_cols": 0, "date_min": "", "date_max": ""}
    cols = read_csv_flexible(path, nrows=0).columns.tolist()
    station_cols = [c for c in cols if str(c) != "date"]
    try:
        dates = read_csv_flexible(path, usecols=["date"])
        d = parse_date_series(dates["date"])
        date_min = d.min().strftime("%Y-%m-%d") if d.notna().any() else ""
        date_max = d.max().strftime("%Y-%m-%d") if d.notna().any() else ""
        rows = len(dates)
    except Exception:
        date_min, date_max, rows = "", "", np.nan
    return {"exists": True, "rows": rows, "station_cols": len(station_cols), "date_min": date_min, "date_max": date_max}

station_root = resolve_station_region_root()
station_manifest_rows = []
location_rows = []
attribute_rows = []
latest_rows = []

print(f"[주유소 입력 root] {station_root}")

for region in REGION_NAMES:
    region_dir = station_root / region
    if not region_dir.exists():
        matches = [p for p in station_root.iterdir() if p.is_dir() and nfc(p.name) == nfc(region)] if station_root.exists() else []
        region_dir = matches[0] if matches else region_dir

    gasoline_path = region_dir / "gasoline.csv"
    diesel_path = region_dir / "diesel.csv"
    metadata_path = region_dir / "metadata__latlon.json"

    g_info = price_file_info(gasoline_path)
    d_info = price_file_info(diesel_path)
    meta_exists = metadata_path.exists()
    meta_count = 0

    if meta_exists:
        with open(metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta_count = len(meta)

        for station_id, info in meta.items():
            for row in event_list_to_rows(station_id, info, "location"):
                row["source_region"] = region
                location_rows.append(row)
            for field in ["region", "station_name", "address", "brand", "is_self"]:
                for row in event_list_to_rows(station_id, info, field):
                    row["source_region"] = region
                    attribute_rows.append(row)

            loc = latest_event_value(info, "location")
            latest = {
                "station_id": station_id,
                "source_region": region,
                "lat": np.nan,
                "lon": np.nan,
                "location_effective_date": "",
            }
            if loc is not None and len(loc) >= 3:
                latest["location_effective_date"] = loc[0]
                latest["lat"] = loc[1]
                latest["lon"] = loc[2]

            for field in ["region", "station_name", "address", "brand", "is_self"]:
                ev = latest_event_value(info, field)
                latest[field] = ev[1] if ev is not None and len(ev) >= 2 else ""
                latest[f"{field}_effective_date"] = ev[0] if ev is not None and len(ev) >= 2 else ""

            latest_rows.append(latest)

    station_manifest_rows.append({
        "region": region,
        "region_dir": str(region_dir),
        "gasoline_exists": g_info["exists"],
        "gasoline_rows": g_info["rows"],
        "gasoline_station_cols": g_info["station_cols"],
        "gasoline_date_min": g_info["date_min"],
        "gasoline_date_max": g_info["date_max"],
        "diesel_exists": d_info["exists"],
        "diesel_rows": d_info["rows"],
        "diesel_station_cols": d_info["station_cols"],
        "diesel_date_min": d_info["date_min"],
        "diesel_date_max": d_info["date_max"],
        "metadata_latlon_exists": meta_exists,
        "metadata_station_count": meta_count,
    })

station_manifest = pd.DataFrame(station_manifest_rows)
station_location_history = pd.DataFrame(location_rows)
station_attribute_history = pd.DataFrame(attribute_rows)
station_latest_profile = pd.DataFrame(latest_rows)

if len(station_location_history) > 0:
    station_location_history["effective_date"] = parse_date_series(station_location_history["effective_date"]).dt.strftime("%Y-%m-%d")
    station_location_history["lat"] = clean_number_series(station_location_history["lat"])
    station_location_history["lon"] = clean_number_series(station_location_history["lon"])
    station_location_history["coord_valid"] = (
        station_location_history["lon"].between(120, 135) &
        station_location_history["lat"].between(30, 45)
    )

if len(station_attribute_history) > 0:
    station_attribute_history["effective_date"] = parse_date_series(station_attribute_history["effective_date"]).dt.strftime("%Y-%m-%d")

if len(station_latest_profile) > 0:
    station_latest_profile["lat"] = clean_number_series(station_latest_profile["lat"])
    station_latest_profile["lon"] = clean_number_series(station_latest_profile["lon"])
    station_latest_profile["coord_valid"] = (
        station_latest_profile["lon"].between(120, 135) &
        station_latest_profile["lat"].between(30, 45)
    )

save_csv(station_manifest, "station_price_manifest.csv")
save_csv(station_location_history, "station_location_history.csv")
save_csv(station_attribute_history, "station_attribute_history.csv")
save_csv(station_latest_profile, "station_latest_profile.csv")

display_df(station_manifest, "[주유소 지역별 입력 manifest]")
display_df(station_latest_profile, "[주유소 최신 프로필]")

# %%
# ============================================================
# 4. 시설 좌표 파생 데이터 생성
# ============================================================
def normalize_facility_type(x):
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if "저유소" in s:
        return "storage"
    if "공장" in s:
        return "factory"
    if "대리점" in s:
        return "agency"
    return np.nan

def geocode_kakao(address):
    if not KAKAO_REST_API_KEY:
        return None
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    r = requests.get(url, headers=headers, params={"query": address}, timeout=15)
    r.raise_for_status()
    docs = r.json().get("documents", [])
    if not docs:
        return None
    d = docs[0]
    return {
        "lon": d.get("x"),
        "lat": d.get("y"),
        "geocode_source": "kakao",
        "geocode_status": "ok",
    }

def geocode_vworld(address):
    if not VWORLD_API_KEY:
        return None
    url = "https://api.vworld.kr/req/address"
    base_params = {
        "service": "address",
        "request": "getcoord",
        "version": "2.0",
        "crs": "epsg:4326",
        "address": address,
        "refine": "true",
        "simple": "false",
        "format": "json",
        "key": VWORLD_API_KEY,
    }
    for addr_type in ["road", "parcel"]:
        params = dict(base_params)
        params["type"] = addr_type
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        js = r.json()
        if js.get("response", {}).get("status") == "OK":
            point = js["response"]["result"]["point"]
            return {
                "lon": point.get("x"),
                "lat": point.get("y"),
                "geocode_source": f"vworld_{addr_type}",
                "geocode_status": "ok",
            }
    return None

def geocode_address(address):
    address = "" if pd.isna(address) else str(address).strip()
    if not address:
        return {"lon": np.nan, "lat": np.nan, "geocode_source": "", "geocode_status": "empty_address"}

    for fn in [geocode_kakao, geocode_vworld]:
        try:
            result = fn(address)
            if result is not None:
                return result
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return {"lon": np.nan, "lat": np.nan, "geocode_source": "", "geocode_status": "not_found"}

def load_facility_source(path):
    if path is None or not Path(path).exists():
        raise FileNotFoundError("시설 입력 파일을 찾지 못했습니다.")
    raw = read_table_flexible(path)

    brand_col = find_col(raw.columns, ["상표", "brand"])
    type_col = find_col(raw.columns, ["대상", "구분", "facility_type_raw", "type"])
    name_col = find_col(raw.columns, ["이름", "name", "시설명"])
    address_col = find_col(raw.columns, ["주소", "address"])
    lon_col = find_col(raw.columns, ["경도", "lon", "lng", "longitude", "x"])
    lat_col = find_col(raw.columns, ["위도", "lat", "latitude", "y"])

    missing = []
    if brand_col is None:
        missing.append("상표")
    if type_col is None:
        missing.append("대상/구분")
    if missing:
        raise ValueError(f"시설 파일 필수 컬럼 누락: {missing} | columns={list(raw.columns)}")

    out = pd.DataFrame()
    out["brand"] = raw[brand_col].astype(str).str.strip()
    out["facility_type_raw"] = raw[type_col].astype(str).str.strip()
    out["name"] = raw[name_col].astype(str).str.strip() if name_col else ""
    out["address"] = raw[address_col].astype(str).str.strip() if address_col else ""
    out["lon"] = clean_number_series(raw[lon_col]) if lon_col else np.nan
    out["lat"] = clean_number_series(raw[lat_col]) if lat_col else np.nan
    out["facility_type"] = out["facility_type_raw"].map(normalize_facility_type)
    out["source_path"] = str(path)
    out["geocode_source"] = "source_file" if lon_col and lat_col else ""
    out["geocode_status"] = np.where(out["lon"].notna() & out["lat"].notna(), "ok", "missing_coord")
    out["facility_id"] = [f"F{i:06d}" for i in range(1, len(out) + 1)]
    return out

facility_source = resolve_facility_source()
print(f"[시설 입력] {facility_source}")
facility_points = load_facility_source(facility_source)

cache_path = DERIVED_DIR / "facility_geocode_cache.csv"
if cache_path.exists():
    cache = read_csv_flexible(cache_path)
else:
    cache = pd.DataFrame(columns=["address", "lon", "lat", "geocode_source", "geocode_status"])

cache_map = {
    str(r["address"]): r.to_dict()
    for _, r in cache.iterrows()
    if "address" in r and pd.notna(r["address"])
}

need_geo_mask = ~(facility_points["lon"].between(120, 135) & facility_points["lat"].between(30, 45))
if GEOCODE_FACILITY_IF_MISSING and need_geo_mask.any():
    if not KAKAO_REST_API_KEY and not VWORLD_API_KEY:
        print("[주의] 시설 좌표 결측이 있지만 KAKAO_REST_API_KEY/VWORLD_API_KEY가 없어 geocoding을 건너뜁니다.")
    else:
        print(f"[시설 geocoding] 대상 {int(need_geo_mask.sum()):,}건")
        new_cache_rows = []
        for idx in facility_points.index[need_geo_mask]:
            address = str(facility_points.at[idx, "address"]).strip()
            if address in cache_map:
                result = cache_map[address]
            else:
                result = geocode_address(address)
                result["address"] = address
                new_cache_rows.append(result)
                time.sleep(GEOCODE_SLEEP_SEC)

            facility_points.at[idx, "lon"] = result.get("lon", np.nan)
            facility_points.at[idx, "lat"] = result.get("lat", np.nan)
            facility_points.at[idx, "geocode_source"] = result.get("geocode_source", "")
            facility_points.at[idx, "geocode_status"] = result.get("geocode_status", "")

        if new_cache_rows:
            cache = pd.concat([cache, pd.DataFrame(new_cache_rows)], ignore_index=True)
            cache = cache.drop_duplicates("address", keep="last")
            save_csv(cache, "facility_geocode_cache.csv")

facility_points["lon"] = clean_number_series(facility_points["lon"])
facility_points["lat"] = clean_number_series(facility_points["lat"])
facility_points["coord_valid"] = (
    facility_points["lon"].between(120, 135) &
    facility_points["lat"].between(30, 45)
)

facility_for_grid = facility_points.rename(columns={
    "brand": "상표",
    "facility_type_raw": "대상",
    "lon": "경도",
    "lat": "위도",
}).copy()

save_csv(facility_points, "facility_points.csv")
save_csv(facility_for_grid[["상표", "대상", "경도", "위도"]], "facility_location_data_final.csv")

facility_missing = int((~facility_points["coord_valid"]).sum())
display_df(facility_points, "[시설 좌표 파생 데이터]")
if facility_missing > 0:
    raise RuntimeError(
        f"시설 좌표가 아직 없는 행이 {facility_missing:,}건 있습니다. "
        "KAKAO_REST_API_KEY 또는 VWORLD_API_KEY를 Colab 보안 비밀에 넣고 다시 실행하거나, "
        "facility_location_data_final.csv를 직접 준비해야 합니다."
    )

# %%
# ============================================================
# 5. 공시지가 파생 데이터 생성
# ============================================================
official_source = resolve_official_land_price_source()
print(f"[공시지가 입력] {official_source}")
if official_source is None or not Path(official_source).exists():
    raise FileNotFoundError("공시지가 입력 파일을 찾지 못했습니다.")

official_raw = read_csv_flexible(official_source)
required_cols = {"cell_x", "cell_y"}
missing = required_cols - set(official_raw.columns)
if missing:
    raise ValueError(f"공시지가 필수 컬럼 누락: {missing}")

snapshot_cols = sorted([c for c in official_raw.columns if re.match(r"^p_\d{8}$", str(c))])
if not snapshot_cols:
    raise ValueError("공시지가 p_YYYYMMDD snapshot 컬럼을 찾지 못했습니다.")

dup_cell = int(official_raw[["cell_x", "cell_y"]].duplicated().sum())
if dup_cell > 0:
    raise ValueError(f"공시지가 cell_x/cell_y 중복: {dup_cell:,}건")

official = official_raw.copy()
official["cell_x"] = clean_number_series(official["cell_x"]).astype("int32")
official["cell_y"] = clean_number_series(official["cell_y"]).astype("int32")
for c in snapshot_cols:
    official[c] = clean_number_series(official[c])

snapshot_summary = []
for c in snapshot_cols:
    snapshot_summary.append({
        "snapshot_col": c,
        "snapshot_date": c.replace("p_", ""),
        "not_null": int(official[c].notna().sum()),
        "null": int(official[c].isna().sum()),
        "min": float(official[c].min()) if official[c].notna().any() else np.nan,
        "max": float(official[c].max()) if official[c].notna().any() else np.nan,
    })

save_csv(official, "official_land_price_grid.csv")
save_csv(pd.DataFrame(snapshot_summary), "official_land_price_snapshots.csv")
display_df(pd.DataFrame(snapshot_summary), "[공시지가 snapshot 요약]")

# %%
# ============================================================
# 6. 최종 산출물 검증
# ============================================================
summary_rows = []
for path in sorted(DERIVED_DIR.glob("*.csv")):
    try:
        df = read_csv_flexible(path)
        dmin, dmax = date_min_max(df, "date") if "date" in df.columns else ("", "")
        summary_rows.append({
            "file": path.name,
            "path": str(path),
            "rows": len(df),
            "columns": len(df.columns),
            "date_min": dmin,
            "date_max": dmax,
            "has_lat": "lat" in df.columns or "위도" in df.columns,
            "has_lon": "lon" in df.columns or "경도" in df.columns,
        })
    except Exception as e:
        summary_rows.append({
            "file": path.name,
            "path": str(path),
            "rows": np.nan,
            "columns": np.nan,
            "date_min": "",
            "date_max": "",
            "has_lat": False,
            "has_lon": False,
            "error": f"{type(e).__name__}: {e}",
        })

derived_summary = pd.DataFrame(summary_rows)
save_csv(derived_summary, "derived_outputs_summary.csv")
display_df(derived_summary, "[AI Model 02 최종 산출물]")

required_outputs = [
    "data_readiness_summary.csv",
    "national_daily_features.csv",
    "station_price_manifest.csv",
    "station_location_history.csv",
    "station_attribute_history.csv",
    "station_latest_profile.csv",
    "facility_points.csv",
    "facility_location_data_final.csv",
    "official_land_price_grid.csv",
    "official_land_price_snapshots.csv",
]
missing_outputs = [x for x in required_outputs if not (DERIVED_DIR / x).exists()]
if missing_outputs:
    raise RuntimeError(f"필수 산출물 누락: {missing_outputs}")

print("\n[AI Model 02 완료]")
print(f"- DERIVED_DATA_PATH: {DERIVED_DATA_PATH}")
print(f"- csv_count: {len(list(DERIVED_DIR.glob('*.csv'))):,}")
