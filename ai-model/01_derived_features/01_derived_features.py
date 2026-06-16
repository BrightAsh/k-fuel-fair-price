# %% [markdown]
# # AI Model 01 파생 변수/격자화 전 데이터 준비
#
# `data collection/` 안의 수집 산출물을 읽어 격자화 전에 필요한 표준 CSV를 만듭니다.
#
# - 자동 수집 산출물: `data collection/{dataset}/final/`
# - 수동 수집 산출물: `data collection/z_pa_{dataset}/final/`
# - 01 산출물: `data collection/derived_data/`

# %%
# ============================================================
# 0. 공통 경로 설정
# ============================================================
from pathlib import Path
import json
import math
import re
import shutil
import subprocess
import sys
import time
import unicodedata

import numpy as np
import pandas as pd
import requests

from google.colab import drive, userdata
from IPython.display import display

drive.mount("/content/drive")

ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"

ROOT_DIR = Path(ROOT_PATH)
DATA_COLLECTION_DIR = ROOT_DIR / "data collection"
DERIVED_DIR = DATA_COLLECTION_DIR / "derived_data"

DATA_COLLECTION_PATH = str(DATA_COLLECTION_DIR) + "/"
DERIVED_DATA_PATH = str(DERIVED_DIR) + "/"

DERIVED_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = "2008-01-01"
END_DATE = None  # None이면 수집된 데이터의 최대 날짜 또는 오늘 날짜 사용

GEOCODE_FACILITY_IF_MISSING = True
GEOCODE_SLEEP_SEC = 0.20

Z_PA_FACILITY_DIR = DATA_COLLECTION_DIR / "z_pa_facility"
for sub in ["raw", "final", "logs"]:
    (Z_PA_FACILITY_DIR / sub).mkdir(parents=True, exist_ok=True)

def get_secret(name, default=""):
    try:
        value = userdata.get(name)
        return value if value is not None else default
    except Exception:
        return default

GEOCODER_TOKEN = get_secret("GEOCODER_TOKEN", "") or get_secret("GIMI9_GEOCODER_TOKEN", "")
KAKAO_REST_API_KEY = get_secret("KAKAO_REST_API_KEY", "")
NAVER_MAPS_CLIENT_ID = get_secret("NAVER_MAPS_CLIENT_ID", "") or get_secret("NAVER_CLIENT_ID", "")
NAVER_MAPS_CLIENT_SECRET = get_secret("NAVER_MAPS_CLIENT_SECRET", "") or get_secret("NAVER_CLIENT_SECRET", "")
VWORLD_API_KEY = get_secret("VWORLD_API_KEY", "")

GEOCODER_BATCH_SIZE = 1000
GEOCODER_TIMEOUT = 60
GEOCODER_MAX_RETRY = 3
GEOCODER_RETRY_SLEEP_SEC = 1.0
ENABLE_SECONDARY_GEOCODERS = True
COMPARE_SECONDARY_GEOCODERS = True
ENABLE_VWORLD_GEOCODER = False  # VWorld 문서상 API 결과 저장 제한이 있어 기본값은 사용 안 함
SECONDARY_GEOCODE_SLEEP_SEC = 0.20
GEOCODER_PROVIDER_DISTANCE_REVIEW_M = 500

CELL_SIZE_M = 500
SOURCE_CRS = "EPSG:4326"
WORK_CRS = "EPSG:5179"

ESSENTIAL_DERIVED_CSV_OUTPUTS = [
    "national_daily_features.csv",
    "station_location_history.csv",
    "station_attribute_history.csv",
    "station_latest_profile.csv",
    "station_points.csv",
    "facility_points.csv",
    "facility_location_data_final.csv",
    "official_land_price_grid.csv",
]
ESSENTIAL_DERIVED_FILE_OUTPUTS = ESSENTIAL_DERIVED_CSV_OUTPUTS + [
    f"korea_land_grid_{CELL_SIZE_M}m.parquet",
]
UNUSED_DERIVED_OUTPUTS = [
    "data_readiness_summary.csv",
    "fx_usdkrw_daily.csv",
    "crude_daily.csv",
    "intl_products_daily.csv",
    "retail_avg_daily.csv",
    "brand_gasoline_daily.csv",
    "brand_diesel_daily.csv",
    "refinery_weekly_supply_daily_like.csv",
    "gasoline_tax_daily.csv",
    "diesel_tax_daily.csv",
    "station_metadata_latlon",
    "station_missing_coordinates.csv",
    "station_price_manifest.csv",
    "station_point_summary.csv",
    "station_geocode_summary.csv",
    "facility_geocode_cache.csv",
    "facility_missing_coordinates.csv",
    "facility_unknown_types.csv",
    "facility_point_summary.csv",
    f"south_korea_land_mask_{CELL_SIZE_M}m.gpkg",
    "korea_land_grid_summary.csv",
    "official_land_price_snapshots.csv",
    "influence_feature_config.csv",
    "missing_input_requirements.csv",
    "derived_outputs_summary.csv",
]

CLEAN_UNUSED_DERIVED_OUTPUTS = True
if CLEAN_UNUSED_DERIVED_OUTPUTS:
    for filename in UNUSED_DERIVED_OUTPUTS:
        path = DERIVED_DIR / filename
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"[REMOVE UNUSED OUTPUT] {path}")

print(f"ROOT_PATH            = {ROOT_PATH}")
print(f"DATA_COLLECTION_PATH = {DATA_COLLECTION_PATH}")
print(f"DERIVED_DATA_PATH    = {DERIVED_DATA_PATH}")
print(f"CELL_SIZE_M          = {CELL_SIZE_M}")
GEOCODER_PROVIDER_LIST_FOR_PRINT = [
    name for name, enabled in [
        ("GIMI9", bool(GEOCODER_TOKEN)),
        ("Kakao", ENABLE_SECONDARY_GEOCODERS and bool(KAKAO_REST_API_KEY)),
        ("Naver", ENABLE_SECONDARY_GEOCODERS and bool(NAVER_MAPS_CLIENT_ID and NAVER_MAPS_CLIENT_SECRET)),
        ("VWorld", ENABLE_SECONDARY_GEOCODERS and ENABLE_VWORLD_GEOCODER and bool(VWORLD_API_KEY)),
    ]
    if enabled
]
print(f"GEOCODER_PROVIDERS   = {GEOCODER_PROVIDER_LIST_FOR_PRINT}")

# %%
# ============================================================
# 1. 공통 함수
# ============================================================
REGION_NAMES = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]

REQUIREMENT_COLUMNS = [
    "collection_type",
    "dataset",
    "required_for",
    "status",
    "expected_path",
    "note",
]
requirement_rows = []

def add_requirement(collection_type, dataset, required_for, status, expected_path, note):
    requirement_rows.append({
        "collection_type": collection_type,
        "dataset": dataset,
        "required_for": required_for,
        "status": status,
        "expected_path": str(expected_path),
        "note": note,
    })

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
    s = re.sub(r"[\s/()\[\]{}:;,.]+", "_", s)
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
    if display is not None:
        display(df.head(n))
    else:
        print(df.head(n).to_string(index=False))

def normalize_space(x):
    x = "" if pd.isna(x) else str(x)
    x = unicodedata.normalize("NFKC", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x

def valid_lonlat(lon, lat):
    try:
        lon = float(lon)
        lat = float(lat)
    except Exception:
        return False
    return 120 <= lon <= 135 and 30 <= lat <= 45

def to_float_or_none(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None

def geocoding_provider_names():
    names = []
    if GEOCODER_TOKEN:
        names.append("GIMI9")
    if ENABLE_SECONDARY_GEOCODERS and KAKAO_REST_API_KEY:
        names.append("Kakao")
    if ENABLE_SECONDARY_GEOCODERS and NAVER_MAPS_CLIENT_ID and NAVER_MAPS_CLIENT_SECRET:
        names.append("Naver")
    if ENABLE_SECONDARY_GEOCODERS and ENABLE_VWORLD_GEOCODER and VWORLD_API_KEY:
        names.append("VWorld")
    return names

def has_any_geocoder():
    return len(geocoding_provider_names()) > 0

def address_query_variants(address):
    s = normalize_space(address)
    if not s:
        return []
    variants = [s]
    no_parentheses = normalize_space(re.sub(r"\([^)]*\)", " ", s))
    variants.append(no_parentheses)
    no_tail_notes = normalize_space(re.sub(r"\s*-\s*(변경|등록).*?$", "", no_parentheses))
    variants.append(no_tail_notes)

    out = []
    seen = set()
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out

def haversine_m(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(float, [lon1, lat1, lon2, lat2])
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def make_geocode_result(ok, lon, lat, message, source_label, source_input, matched_address=""):
    lon = to_float_or_none(lon)
    lat = to_float_or_none(lat)
    ok = bool(ok and valid_lonlat(lon, lat))
    return {
        "ok": ok,
        "latitude": lat if ok else None,
        "longitude": lon if ok else None,
        "message": "" if ok else normalize_space(message),
        "errmsg": "" if ok else normalize_space(message),
        "source_label": source_label,
        "source_input": source_input,
        "matched_address": normalize_space(matched_address),
        "needs_review": False,
        "provider_distance_m": 0.0,
    }

def call_geocoder_batch(addresses, token, timeout=60, max_retry=3, retry_sleep_sec=1.0):
    url = "https://geocode-api.gimi9.com/geocode"
    headers = {
        "Content-Type": "application/json",
        "Authorization": token,
    }
    payload = {"q": addresses}
    last_error = None
    for attempt in range(1, max_retry + 1):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if res.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"retryable_status={res.status_code}, body={res.text[:500]}")
            res.raise_for_status()
            return res.json()
        except Exception as e:
            last_error = e
            if attempt < max_retry:
                time.sleep(retry_sleep_sec * attempt)
    raise last_error

def normalize_geocoder_item(item, original_input, source_label):
    if item is None:
        return {
            "ok": False,
            "latitude": None,
            "longitude": None,
            "message": "지오코더 응답 누락",
            "errmsg": "지오코더 응답 누락",
            "source_label": source_label,
            "source_input": original_input,
        }
    ok = bool(item.get("success", False))
    latitude = item.get("y_axis", None)
    longitude = item.get("x_axis", None)
    errmsg = normalize_space(item.get("errmsg", ""))
    return {
        "ok": ok,
        "latitude": float(latitude) if latitude is not None else None,
        "longitude": float(longitude) if longitude is not None else None,
        "message": "" if ok else (errmsg if errmsg else "지오코딩 실패"),
        "errmsg": errmsg,
        "bld_mgt_no": normalize_space(item.get("bld_mgt_no", "")),
        "addressCls": normalize_space(item.get("addressCls", "")),
        "hd_nm": normalize_space(item.get("hd_nm", "")),
        "source_label": source_label,
        "source_input": original_input,
    }

def geocode_with_kakao(address):
    if not KAKAO_REST_API_KEY:
        return None

    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    last_message = "Kakao 결과 없음"
    for query in address_query_variants(address):
        try:
            res = requests.get(
                url,
                headers=headers,
                params={"query": query, "analyze_type": "similar", "size": 10},
                timeout=15,
            )
            if res.status_code in (429, 500, 502, 503, 504):
                last_message = f"Kakao retryable_status={res.status_code}"
                continue
            res.raise_for_status()
            data = res.json()
            for item in data.get("documents", []):
                lon = item.get("x")
                lat = item.get("y")
                if valid_lonlat(lon, lat):
                    return make_geocode_result(
                        True,
                        lon,
                        lat,
                        "",
                        "geocode_api_kakao",
                        address,
                        item.get("address_name", query),
                    )
        except Exception as e:
            last_message = f"Kakao 예외: {repr(e)}"

    return make_geocode_result(False, None, None, last_message, "geocode_api_kakao", address)

def geocode_with_naver(address):
    if not (NAVER_MAPS_CLIENT_ID and NAVER_MAPS_CLIENT_SECRET):
        return None

    url = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
    headers = {
        "x-ncp-apigw-api-key-id": NAVER_MAPS_CLIENT_ID,
        "x-ncp-apigw-api-key": NAVER_MAPS_CLIENT_SECRET,
        "Accept": "application/json",
    }
    last_message = "Naver 결과 없음"
    for query in address_query_variants(address):
        try:
            res = requests.get(url, headers=headers, params={"query": query}, timeout=15)
            if res.status_code in (429, 500, 502, 503, 504):
                last_message = f"Naver retryable_status={res.status_code}"
                continue
            res.raise_for_status()
            data = res.json()
            for item in data.get("addresses", []):
                lon = item.get("x")
                lat = item.get("y")
                if valid_lonlat(lon, lat):
                    return make_geocode_result(
                        True,
                        lon,
                        lat,
                        "",
                        "geocode_api_naver",
                        address,
                        item.get("roadAddress") or item.get("jibunAddress") or query,
                    )
        except Exception as e:
            last_message = f"Naver 예외: {repr(e)}"

    return make_geocode_result(False, None, None, last_message, "geocode_api_naver", address)

def geocode_with_vworld(address):
    if not (ENABLE_VWORLD_GEOCODER and VWORLD_API_KEY):
        return None

    url = "https://api.vworld.kr/req/address"
    last_message = "VWorld 결과 없음"
    for query in address_query_variants(address):
        for address_type in ["road", "parcel"]:
            try:
                res = requests.get(
                    url,
                    params={
                        "service": "address",
                        "request": "getcoord",
                        "version": "2.0",
                        "crs": "epsg:4326",
                        "address": query,
                        "refine": "true",
                        "simple": "false",
                        "format": "json",
                        "type": address_type,
                        "key": VWORLD_API_KEY,
                    },
                    timeout=15,
                )
                if res.status_code in (429, 500, 502, 503, 504):
                    last_message = f"VWorld retryable_status={res.status_code}"
                    continue
                res.raise_for_status()
                data = res.json()
                response = data.get("response", {})
                if response.get("status") != "OK":
                    last_message = normalize_space(response.get("status", "VWorld 결과 없음"))
                    continue
                point = response.get("result", {}).get("point", {})
                lon = point.get("x")
                lat = point.get("y")
                if valid_lonlat(lon, lat):
                    refined = response.get("refined", {})
                    return make_geocode_result(
                        True,
                        lon,
                        lat,
                        "",
                        f"geocode_api_vworld_{address_type}",
                        address,
                        refined.get("text", query),
                    )
            except Exception as e:
                last_message = f"VWorld 예외: {repr(e)}"

    return make_geocode_result(False, None, None, last_message, "geocode_api_vworld", address)

def combine_provider_candidates(candidates, failures, address):
    valid = [c for c in candidates if c and c.get("ok") and valid_lonlat(c.get("longitude"), c.get("latitude"))]
    if not valid:
        if failures:
            return failures[-1]
        return make_geocode_result(False, None, None, "보조 geocoder 결과 없음", "secondary_geocoder", address)

    chosen = valid[0].copy()
    if len(valid) >= 2:
        distances = [
            haversine_m(chosen["longitude"], chosen["latitude"], c["longitude"], c["latitude"])
            for c in valid[1:]
        ]
        max_distance = max(distances) if distances else 0.0
        chosen["provider_distance_m"] = round(float(max_distance), 2)
        if max_distance > GEOCODER_PROVIDER_DISTANCE_REVIEW_M:
            chosen["needs_review"] = True
            chosen["message"] = f"provider_distance_review>{GEOCODER_PROVIDER_DISTANCE_REVIEW_M}m"
    return chosen

def geocode_with_secondary_providers(address):
    if not ENABLE_SECONDARY_GEOCODERS:
        return None

    provider_functions = [
        geocode_with_kakao,
        geocode_with_naver,
    ]
    if ENABLE_VWORLD_GEOCODER:
        provider_functions.append(geocode_with_vworld)

    candidates = []
    failures = []
    for provider_fn in provider_functions:
        result = provider_fn(address)
        if result is None:
            continue
        if result.get("ok"):
            candidates.append(result)
            if not COMPARE_SECONDARY_GEOCODERS:
                break
        else:
            failures.append(result)
        time.sleep(SECONDARY_GEOCODE_SLEEP_SEC)

    if not candidates and not failures:
        return None
    return combine_provider_candidates(candidates, failures, address)

def geocode_addresses_with_geocoder(addresses, token=None, batch_size=1000, progress_name="GEOCODER"):
    token = token or GEOCODER_TOKEN
    addresses = [normalize_space(x) for x in addresses if normalize_space(x)]
    addresses = sorted(set(addresses))
    cache = {}
    if not addresses:
        return cache

    if not token:
        for addr in addresses:
            cache[addr] = {
                "ok": False,
                "latitude": None,
                "longitude": None,
                "message": "GEOCODER_TOKEN 없음",
                "errmsg": "GEOCODER_TOKEN 없음",
                "source_label": progress_name,
                "source_input": addr,
            }
    else:
        total = len(addresses)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch = addresses[start:end]
            batch_no = start // batch_size + 1
            batch_total = math.ceil(total / batch_size)
            print(f"[{progress_name}] batch {batch_no}/{batch_total} rows={len(batch):,} progress={end:,}/{total:,}")

            try:
                data = call_geocoder_batch(
                    batch,
                    token=token,
                    timeout=GEOCODER_TIMEOUT,
                    max_retry=GEOCODER_MAX_RETRY,
                    retry_sleep_sec=GEOCODER_RETRY_SLEEP_SEC,
                )
                results = data.get("results", [])
            except Exception as e:
                for addr in batch:
                    cache[addr] = {
                        "ok": False,
                        "latitude": None,
                        "longitude": None,
                        "message": f"지오코더 요청 예외: {repr(e)}",
                        "errmsg": f"지오코더 요청 예외: {repr(e)}",
                        "source_label": progress_name,
                        "source_input": addr,
                    }
                continue

            if len(results) == len(batch):
                for addr, item in zip(batch, results):
                    cache[addr] = normalize_geocoder_item(item, addr, progress_name)
            else:
                results_by_input = {normalize_space(item.get("inputaddr", "")): item for item in results}
                for addr in batch:
                    cache[addr] = normalize_geocoder_item(results_by_input.get(normalize_space(addr)), addr, progress_name)

    fallback_targets = [
        addr for addr in addresses
        if geocoder_result_to_lonlat(cache.get(addr)) is None
    ]
    if fallback_targets and ENABLE_SECONDARY_GEOCODERS:
        available_secondary = [
            name for name in geocoding_provider_names()
            if name in {"Kakao", "Naver", "VWorld"}
        ]
        if available_secondary:
            print(f"[{progress_name}] secondary geocoder 대상 {len(fallback_targets):,}건 provider={available_secondary}")
            for i, addr in enumerate(fallback_targets, start=1):
                result = geocode_with_secondary_providers(addr)
                if result is not None:
                    cache[addr] = result
                if i % 100 == 0 or i == len(fallback_targets):
                    print(f"[{progress_name}] secondary progress={i:,}/{len(fallback_targets):,}")

    return cache

def geocoder_result_to_lonlat(result):
    if result is None or not result.get("ok"):
        return None
    lon = result.get("longitude")
    lat = result.get("latitude")
    if not valid_lonlat(lon, lat):
        return None
    return float(lon), float(lat)

def resolve_collected_file(dataset, final_pattern):
    final_path = latest_under(DATA_COLLECTION_DIR / dataset / "final", final_pattern)
    if final_path is not None:
        return final_path
    return latest_under(DATA_COLLECTION_DIR / dataset, final_pattern)

def has_station_region_dirs(root):
    root = Path(root)
    if not root.exists():
        return False
    for p in root.iterdir():
        if not p.is_dir():
            continue
        if nfc(p.name) in REGION_NAMES:
            return True
        if (p / "gasoline.csv").exists() or (p / "diesel.csv").exists() or (p / "metadata__latlon.json").exists():
            return True
    return False

def resolve_station_region_root():
    candidates = [
        DATA_COLLECTION_DIR / "gas_station_prices_by_region" / "final",
        DATA_COLLECTION_DIR / "gas_station_prices_by_region",
    ]
    for p in candidates:
        if has_station_region_dirs(p):
            return p
    return candidates[0]

def resolve_facility_source():
    zpa_final = DATA_COLLECTION_DIR / "z_pa_facility" / "final"
    return first_existing([
        zpa_final / "facility_location_data_final.csv",
        zpa_final / "1 facility_location_data_final.csv",
        zpa_final / "facility_points.csv",
        zpa_final / "facility_data_with_latlon.csv",
        zpa_final / "facility_data_geocoded.csv",
        zpa_final / "1 facility_location_data.csv",
        zpa_final / "facility_data.csv",
    ])

def resolve_facility_cache_source():
    zpa_final = DATA_COLLECTION_DIR / "z_pa_facility" / "final"
    return first_existing([
        zpa_final / "facility_geocode_cache.csv",
        DERIVED_DIR / "facility_geocode_cache.csv",
    ])

def resolve_official_land_price_source():
    return latest_under(DATA_COLLECTION_DIR / "official_land_price" / "final", "*.csv")

# %%
# ============================================================
# 2. 입력 파일 확인
# ============================================================
INPUT_SPECS = [
    {
        "input_name": "fx_usdkrw",
        "collection_type": "automatic",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("fx_usdkrw", "fx_usdkrw_*.csv"),
        "expected": DATA_COLLECTION_DIR / "fx_usdkrw" / "final" / "fx_usdkrw_*.csv",
    },
    {
        "input_name": "crude",
        "collection_type": "automatic",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("crude", "crude_*.csv"),
        "expected": DATA_COLLECTION_DIR / "crude" / "final" / "crude_*.csv",
    },
    {
        "input_name": "intl_products",
        "collection_type": "automatic",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("intl_products", "intl_products_*.csv"),
        "expected": DATA_COLLECTION_DIR / "intl_products" / "final" / "intl_products_*.csv",
    },
    {
        "input_name": "retail_avg",
        "collection_type": "automatic",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("retail_avg", "retail_avg_*.csv"),
        "expected": DATA_COLLECTION_DIR / "retail_avg" / "final" / "retail_avg_*.csv",
    },
    {
        "input_name": "brand_gasoline",
        "collection_type": "automatic",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("brand_price", "brand_gasoline_*.csv"),
        "expected": DATA_COLLECTION_DIR / "brand_price" / "final" / "brand_gasoline_*.csv",
    },
    {
        "input_name": "brand_diesel",
        "collection_type": "automatic",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("brand_price", "brand_diesel_*.csv"),
        "expected": DATA_COLLECTION_DIR / "brand_price" / "final" / "brand_diesel_*.csv",
    },
    {
        "input_name": "gasoline_tax_trend",
        "collection_type": "automatic",
        "required_for": "national_daily_features",
        "path": latest_under(DATA_COLLECTION_DIR / "fuel_tax_trend" / "final", "gasoline_tax_trend_*.xls"),
        "expected": DATA_COLLECTION_DIR / "fuel_tax_trend" / "final" / "gasoline_tax_trend_*.xls",
    },
    {
        "input_name": "diesel_tax_trend",
        "collection_type": "automatic",
        "required_for": "national_daily_features",
        "path": latest_under(DATA_COLLECTION_DIR / "fuel_tax_trend" / "final", "diesel_tax_trend_*.xls"),
        "expected": DATA_COLLECTION_DIR / "fuel_tax_trend" / "final" / "diesel_tax_trend_*.xls",
    },
    {
        "input_name": "refinery_weekly_supply",
        "collection_type": "automatic",
        "required_for": "national_daily_features",
        "path": resolve_collected_file("refinery_weekly_supply", "refinery_weekly_supply_prices_by_product_*.csv"),
        "expected": DATA_COLLECTION_DIR / "refinery_weekly_supply" / "final" / "refinery_weekly_supply_prices_by_product_*.csv",
    },
    {
        "input_name": "gas_station_prices_by_region",
        "collection_type": "large_collection_not_in_git",
        "required_for": "station_points_and_grid_panel",
        "path": resolve_station_region_root(),
        "expected": DATA_COLLECTION_DIR / "gas_station_prices_by_region" / "final" / "{region}/gasoline.csv,diesel.csv,metadata__latlon.json",
    },
    {
        "input_name": "facility",
        "collection_type": "manual_z_pa",
        "required_for": "facility_points_and_grid_features",
        "path": resolve_facility_source(),
        "expected": DATA_COLLECTION_DIR / "z_pa_facility" / "final" / "facility_data.csv",
    },
    {
        "input_name": "official_land_price",
        "collection_type": "automatic",
        "required_for": "official_land_price_join",
        "path": resolve_official_land_price_source(),
        "expected": DATA_COLLECTION_DIR / "official_land_price" / "final" / "*.csv",
    },
]

readiness_rows = []
for spec in INPUT_SPECS:
    p = spec["path"]
    exists = bool(p is not None and Path(p).exists())
    row = {
        "input_name": spec["input_name"],
        "collection_type": spec["collection_type"],
        "required_for": spec["required_for"],
        "exists": exists,
        "path": str(p) if p is not None else "",
        "expected_path": str(spec["expected"]),
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
            date_col = find_col(sample.columns, ["date", "날짜", "일자", "변동일자", "기간", "week_end"])
            if date_col:
                tmp = sample.rename(columns={date_col: "date"})
                row["date_min"], row["date_max"] = date_min_max(tmp, "date")
        elif exists and Path(p).is_dir():
            region_dirs = [x for x in Path(p).iterdir() if x.is_dir()]
            row["note"] = f"region_dirs={len(region_dirs)}"
    except Exception as e:
        row["note"] = f"inspect_error={type(e).__name__}: {e}"

    if not exists:
        add_requirement(
            spec["collection_type"],
            spec["input_name"],
            spec["required_for"],
            "missing",
            spec["expected"],
            "입력 경로를 찾지 못했습니다.",
        )
    readiness_rows.append(row)

readiness = pd.DataFrame(readiness_rows)
display_df(readiness, "[입력 준비 여부]")

# %%
# ============================================================
# 3. 전국 일별 파생 데이터 생성
# ============================================================
def standardize_daily_table(path, prefix, output_filename, date_candidates=None):
    if path is None or not Path(path).exists():
        print(f"[SKIP] {output_filename}: input 없음")
        return pd.DataFrame(columns=["date"])

    date_candidates = date_candidates or ["date", "날짜", "일자", "변동일자", "기간", "week_end"]
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
    print(f"[READY] {output_filename}: rows={len(out):,} cols={len(out.columns):,} (중간 파일 저장 안 함)")
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
# 4. 주유소 위치/속성 파생 데이터 생성
# ============================================================
def find_region_dir(station_root, region):
    station_root = Path(station_root)
    region_dir = station_root / region
    if region_dir.exists():
        return region_dir
    if not station_root.exists():
        return region_dir
    matches = [p for p in station_root.iterdir() if p.is_dir() and nfc(p.name) == nfc(region)]
    return matches[0] if matches else region_dir

def find_station_metadata_path(region_dir):
    for name in ["metadata__latlon.json", "metadata_latlon.json", "metadata.json"]:
        p = Path(region_dir) / name
        if p.exists():
            return p
    return Path(region_dir) / "metadata__latlon.json"

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

def metadata_has_valid_locations(meta):
    for info in meta.values():
        values = info.get("location", [])
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, list) and len(item) >= 3 and valid_lonlat(item[2], item[1]):
                return True
    return False

def geocode_station_metadata_locations(meta, region):
    address_rows = []
    for station_id, info in meta.items():
        existing_valid_dates = set()
        for loc_item in info.get("location", []):
            if isinstance(loc_item, list) and len(loc_item) >= 3 and valid_lonlat(loc_item[2], loc_item[1]):
                existing_valid_dates.add(str(loc_item[0]).strip())

        address_history = info.get("address", [])
        if not isinstance(address_history, list):
            continue
        for item in address_history:
            if isinstance(item, list) and len(item) >= 2:
                effective_date = str(item[0]).strip()
                if effective_date in existing_valid_dates:
                    continue
                address = normalize_space(item[1])
                if address:
                    address_rows.append({
                        "station_id": station_id,
                        "effective_date": effective_date,
                        "address": address,
                    })

    if not address_rows:
        return meta, {
            "region": region,
            "address_count": 0,
            "success_count": 0,
            "fail_count": 0,
            "note": "좌표 보강 대상 address 없음",
        }

    unique_addresses = sorted({r["address"] for r in address_rows})
    geocode_cache = geocode_addresses_with_geocoder(
        unique_addresses,
        token=GEOCODER_TOKEN,
        batch_size=1000,
        progress_name=f"STATION_GEOCODER_{region}",
    )

    success_count = 0
    fail_count = 0
    for station_id, info in meta.items():
        address_history = info.get("address", [])
        if not isinstance(address_history, list) or len(address_history) == 0:
            continue

        existing_by_date = {}
        for item in info.get("location", []):
            if isinstance(item, list) and len(item) >= 3 and valid_lonlat(item[2], item[1]):
                existing_by_date[str(item[0]).strip()] = [item[0], float(item[1]), float(item[2])]

        location_history = []
        for item in address_history:
            if not isinstance(item, list) or len(item) < 2:
                continue
            dt = str(item[0]).strip()
            if dt in existing_by_date:
                location_history.append(existing_by_date[dt])
                success_count += 1
                continue

            address = normalize_space(item[1])
            result = geocode_cache.get(address)
            lonlat = geocoder_result_to_lonlat(result)
            if lonlat is None:
                location_history.append([dt, None, None])
                fail_count += 1
            else:
                lon, lat = lonlat
                location_history.append([dt, round(lat, 8), round(lon, 8)])
                success_count += 1

        if location_history:
            info["location"] = location_history

    return meta, {
        "region": region,
        "address_count": len(unique_addresses),
        "success_count": success_count,
        "fail_count": fail_count,
        "note": " / ".join(geocoding_provider_names()) if has_any_geocoder() else "geocoder 없음",
    }

station_root = resolve_station_region_root()
station_manifest_rows = []
location_rows = []
attribute_rows = []
latest_rows = []
station_geocode_summary_rows = []

print(f"[주유소 입력 root] {station_root}")

for region in REGION_NAMES:
    region_dir = find_region_dir(station_root, region)
    gasoline_path = region_dir / "gasoline.csv"
    diesel_path = region_dir / "diesel.csv"
    if not diesel_path.exists() and (region_dir / "deisel.csv").exists():
        diesel_path = region_dir / "deisel.csv"
    metadata_path = find_station_metadata_path(region_dir)

    g_info = price_file_info(gasoline_path)
    d_info = price_file_info(diesel_path)
    meta_exists = metadata_path.exists()
    meta_has_location = False
    meta_count = 0
    valid_location_count = 0

    if meta_exists:
        with open(metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta_count = len(meta)

        if has_any_geocoder():
            meta, geo_summary = geocode_station_metadata_locations(meta, region)
            if geo_summary.get("address_count", 0) > 0 or geo_summary.get("fail_count", 0) > 0:
                station_geocode_summary_rows.append(geo_summary)

        if not metadata_has_valid_locations(meta):
            add_requirement(
                "large_collection_not_in_git",
                "gas_station_prices_by_region",
                "station_points_and_grid_panel",
                "missing_coordinates",
                region_dir / "metadata__latlon.json",
                f"{region} 지역 metadata에 유효 좌표가 없습니다. GEOCODER/Kakao/Naver 설정 후 재실행하거나 metadata__latlon.json을 넣어야 합니다.",
            )

        for station_id, info in meta.items():
            loc_values = info.get("location", [])
            if isinstance(loc_values, list) and len(loc_values) > 0:
                meta_has_location = True

            for row in event_list_to_rows(station_id, info, "location"):
                row["source_region"] = region
                row["metadata_file"] = metadata_path.name
                location_rows.append(row)
            for field in ["region", "station_name", "address", "brand", "is_self"]:
                for row in event_list_to_rows(station_id, info, field):
                    row["source_region"] = region
                    row["metadata_file"] = metadata_path.name
                    attribute_rows.append(row)

            loc = latest_event_value(info, "location")
            latest = {
                "station_id": station_id,
                "source_region": region,
                "lat": np.nan,
                "lon": np.nan,
                "location_effective_date": "",
                "metadata_file": metadata_path.name,
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
    else:
        add_requirement(
            "large_collection_not_in_git",
            "gas_station_prices_by_region",
            "station_points_and_grid_panel",
            "missing",
            region_dir / "metadata__latlon.json",
            f"{region} 지역 metadata__latlon.json이 필요합니다.",
        )

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
        "metadata_exists": meta_exists,
        "metadata_file": metadata_path.name if meta_exists else "",
        "metadata_has_location": meta_has_location,
        "metadata_station_count": meta_count,
        "valid_latest_location_count": valid_location_count,
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
    valid_coord_by_station = (
        station_latest_profile[station_latest_profile["coord_valid"] == True]
        .sort_values(["station_id", "location_effective_date"], na_position="last")
        .drop_duplicates("station_id", keep="last")
        .set_index("station_id")[["lon", "lat", "location_effective_date"]]
    )
    fill_mask = (
        (station_latest_profile["coord_valid"] != True) &
        station_latest_profile["station_id"].isin(valid_coord_by_station.index)
    )
    if fill_mask.any():
        fill_ids = station_latest_profile.loc[fill_mask, "station_id"]
        station_latest_profile.loc[fill_mask, "lon"] = fill_ids.map(valid_coord_by_station["lon"])
        station_latest_profile.loc[fill_mask, "lat"] = fill_ids.map(valid_coord_by_station["lat"])
        station_latest_profile.loc[fill_mask, "location_effective_date"] = fill_ids.map(valid_coord_by_station["location_effective_date"])
        station_latest_profile["coord_valid"] = (
            station_latest_profile["lon"].between(120, 135) &
            station_latest_profile["lat"].between(30, 45)
        )
        print(f"[INFO] 같은 station_id의 기존 유효 좌표로 결측 보강: {int(fill_mask.sum()):,}건")
else:
    station_latest_profile = pd.DataFrame(columns=[
        "station_id", "source_region", "lat", "lon", "coord_valid",
        "location_effective_date", "region", "station_name", "address", "brand", "is_self",
    ])

if "coord_valid" in station_latest_profile.columns:
    station_manifest["valid_latest_location_count"] = station_manifest["region"].map(
        station_latest_profile[station_latest_profile["coord_valid"]]
        .groupby("source_region")["station_id"]
        .nunique()
    ).fillna(0).astype(int)

station_points_cols = [
    "station_id", "source_region", "station_name", "address", "brand", "is_self",
    "lon", "lat", "coord_valid", "location_effective_date", "metadata_file",
]
station_points_all = station_latest_profile.copy()
for c in station_points_cols:
    if c not in station_points_all.columns:
        station_points_all[c] = np.nan
station_points_all = station_points_all[station_points_cols].copy()

if len(station_points_all) > 0:
    station_point_summary = (
        station_points_all
        .groupby(["source_region", "coord_valid"], dropna=False)
        .size()
        .reset_index(name="station_count")
        .sort_values(["source_region", "coord_valid"])
    )
else:
    station_point_summary = pd.DataFrame(columns=["source_region", "coord_valid", "station_count"])

missing_station_coord = station_points_all[(station_points_all["coord_valid"] != True)].copy()
if len(missing_station_coord) > 0:
    print(f"[주의] 좌표가 없거나 범위를 벗어난 주유소 최신 프로필 {len(missing_station_coord):,}건")
    add_requirement(
        "large_collection_not_in_git",
        "gas_station_prices_by_region",
        "station_points_and_grid_panel",
        "missing_coordinates",
        DATA_COLLECTION_DIR / "gas_station_prices_by_region" / "final" / "{region}" / "metadata__latlon.json",
        f"좌표가 없거나 한국 범위를 벗어난 주유소 최신 프로필 {len(missing_station_coord):,}건이 있습니다.",
    )
station_points = station_points_all[station_points_all["coord_valid"] == True].copy()
if len(station_points) > 0:
    station_duplicate_qc = (
        station_points
        .assign(coord_key=lambda d: d["lon"].round(8).astype(str) + "|" + d["lat"].round(8).astype(str))
        .groupby("station_id", dropna=False)
        .agg(
            row_count=("station_id", "size"),
            source_region_count=("source_region", "nunique"),
            coord_count=("coord_key", "nunique"),
            address_count=("address", "nunique"),
        )
        .reset_index()
    )
    duplicate_station_qc = station_duplicate_qc[station_duplicate_qc["row_count"] > 1].copy()
    duplicate_station_coord_conflict = duplicate_station_qc[
        (duplicate_station_qc["coord_count"] > 1) |
        (duplicate_station_qc["address_count"] > 1)
    ].copy()
    if len(duplicate_station_qc) > 0:
        print(
            f"[INFO] station_id 중복 {len(duplicate_station_qc):,}개: "
            "같은 station_id는 station_points에서 1개 좌표만 사용합니다."
        )
    if len(duplicate_station_coord_conflict) > 0:
        print(f"[주의] station_id별 좌표/주소 충돌 {len(duplicate_station_coord_conflict):,}개")
        display_df(duplicate_station_coord_conflict, "[station_id 좌표/주소 충돌 샘플]", n=20)

    station_points_before = len(station_points)
    station_points = (
        station_points
        .sort_values(["station_id", "source_region", "station_name"], na_position="last")
        .drop_duplicates("station_id", keep="first")
        .reset_index(drop=True)
    )
    if len(station_points) != station_points_before:
        print(f"[INFO] station_points station_id 중복 제거: {station_points_before:,} -> {len(station_points):,}")
save_csv(station_location_history, "station_location_history.csv")
save_csv(station_attribute_history, "station_attribute_history.csv")
save_csv(station_latest_profile, "station_latest_profile.csv")
save_csv(station_points, "station_points.csv")

display_df(station_manifest, "[주유소 지역별 입력 manifest]")
display_df(station_points, "[주유소 포인트]")

# %%
# ============================================================
# 5. 시설 좌표 파생 데이터 생성
# ============================================================
def normalize_facility_type(x):
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if ("저유" in s) or ("저장" in s):
        return "storage"
    if "공장" in s:
        return "factory"
    if "대리점" in s:
        return "agency"
    return np.nan

def geocode_address(address):
    address = normalize_space(address)
    if not address:
        return {"lon": np.nan, "lat": np.nan, "geocode_source": "", "geocode_status": "empty_address"}

    result = geocode_addresses_with_geocoder(
        [address],
        token=GEOCODER_TOKEN,
        batch_size=1,
        progress_name="FACILITY_GEOCODER",
    ).get(address)
    lonlat = geocoder_result_to_lonlat(result)
    source = result.get("source_label", "geocode_api") if isinstance(result, dict) else "geocode_api"
    if source == "FACILITY_GEOCODER" or source.startswith("STATION_GEOCODER_") or source == "GEOCODER":
        source = "geocode_api_gimi9"
    if lonlat is None:
        status = result.get("message", "not_found") if isinstance(result, dict) else "not_found"
        return {"lon": np.nan, "lat": np.nan, "geocode_source": source, "geocode_status": status}

    lon, lat = lonlat
    status = "ok"
    if result.get("needs_review"):
        status = f"ok_needs_review_distance_{result.get('provider_distance_m')}m"
    return {"lon": lon, "lat": lat, "geocode_source": source, "geocode_status": status}

def empty_facility_points(source_path=""):
    return pd.DataFrame(columns=[
        "facility_id", "brand", "facility_type_raw", "facility_type", "name",
        "address", "lon", "lat", "coord_valid", "source_path",
        "geocode_source", "geocode_status",
    ])

def load_facility_source(path):
    if path is None or not Path(path).exists():
        return empty_facility_points("")
    raw = read_table_flexible(path)

    brand_col = find_col(raw.columns, ["상표", "brand"])
    type_col = find_col(raw.columns, ["대상", "구분", "facility_type_raw", "type"])
    name_col = find_col(raw.columns, ["이름", "name", "시설명"])
    address_col = find_col(raw.columns, ["주소", "address"])
    lon_col = find_col(raw.columns, ["경도", "lon", "lng", "longitude", "x"])
    lat_col = find_col(raw.columns, ["위도", "lat", "latitude", "y"])

    missing = []
    if brand_col is None:
        missing.append("상표/brand")
    if type_col is None:
        missing.append("대상/구분/type")
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

if len(facility_points) == 0:
    add_requirement(
        "manual_z_pa",
        "z_pa_facility",
        "facility_points_and_grid_features",
        "missing",
        DATA_COLLECTION_DIR / "z_pa_facility" / "final" / "facility_data.csv",
        "시설 원천 파일이 없습니다. 필수 컬럼은 상표, 구분/대상, 이름, 주소입니다.",
    )

cache_source = resolve_facility_cache_source()
if cache_source is not None:
    cache = read_csv_flexible(cache_source)
else:
    cache = pd.DataFrame(columns=["address", "lon", "lat", "geocode_source", "geocode_status"])

cache_map = {
    str(r["address"]): r.to_dict()
    for _, r in cache.iterrows()
    if "address" in r and pd.notna(r["address"])
}

need_geo_mask = ~(facility_points["lon"].between(120, 135) & facility_points["lat"].between(30, 45))
has_address_for_geocode = "address" in facility_points.columns and facility_points["address"].astype(str).str.strip().ne("").any()
if len(facility_points) > 0 and GEOCODE_FACILITY_IF_MISSING and need_geo_mask.any() and has_address_for_geocode:
    if not has_any_geocoder():
        print("[주의] 시설 좌표 결측이 있지만 GEOCODER/Kakao/Naver 키가 없어 geocoding을 건너뜁니다.")
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
            print(f"[INFO] 시설 좌표 조회 cache는 최종 입력이 아니므로 파일로 저장하지 않습니다. 신규 조회 {len(new_cache_rows):,}건")

facility_points["lon"] = clean_number_series(facility_points["lon"])
facility_points["lat"] = clean_number_series(facility_points["lat"])
facility_points["coord_valid"] = (
    facility_points["lon"].between(120, 135) &
    facility_points["lat"].between(30, 45)
)

facility_missing = facility_points[~facility_points["coord_valid"]].copy()
facility_unknown_type = facility_points[facility_points["facility_type"].isna()].copy()
if len(facility_missing) > 0:
    print(f"[주의] 좌표가 없거나 범위를 벗어난 시설 {len(facility_missing):,}건")
    add_requirement(
        "manual_z_pa",
        "z_pa_facility",
        "facility_points_and_grid_features",
        "missing_coordinates",
        DATA_COLLECTION_DIR / "z_pa_facility" / "final" / "facility_location_data_final.csv",
        f"시설 좌표가 없거나 한국 범위를 벗어난 행 {len(facility_missing):,}건이 있습니다.",
    )
if len(facility_unknown_type) > 0:
    print(f"[주의] facility_type을 판정하지 못한 시설 {len(facility_unknown_type):,}건")
    add_requirement(
        "manual_z_pa",
        "z_pa_facility",
        "facility_points_and_grid_features",
        "unknown_facility_type",
        DATA_COLLECTION_DIR / "z_pa_facility" / "final" / "facility_data.csv",
        "구분/대상 값이 공장, 저유소, 대리점 중 하나로 매핑되지 않는 행이 있습니다.",
    )

facility_for_grid = facility_points.rename(columns={
    "brand": "상표",
    "facility_type_raw": "대상",
    "lon": "경도",
    "lat": "위도",
}).copy()

facility_location_cols = ["상표", "대상", "경도", "위도"]
for c in facility_location_cols:
    if c not in facility_for_grid.columns:
        facility_for_grid[c] = np.nan

facility_point_summary = (
    facility_points
    .groupby(["facility_type", "coord_valid"], dropna=False)
    .size()
    .reset_index(name="facility_count")
    .sort_values(["facility_type", "coord_valid"])
    if len(facility_points) > 0
    else pd.DataFrame(columns=["facility_type", "coord_valid", "facility_count"])
)

facility_for_grid_valid = facility_for_grid[
    (facility_points["coord_valid"] == True) &
    facility_points["facility_type"].notna()
].copy()
save_csv(facility_points, "facility_points.csv")
save_csv(facility_for_grid_valid[facility_location_cols], "facility_location_data_final.csv")
display_df(facility_points, "[시설 좌표 파생 데이터]")

# %%
# ============================================================
# 6. 전국 500m 격자틀 생성
# ============================================================
def ensure_geospatial_packages():
    packages = [
        ("geopandas", "geopandas"),
        ("pyproj", "pyproj"),
        ("shapely", "shapely"),
        ("pyogrio", "pyogrio"),
        ("pyarrow", "pyarrow"),
    ]
    missing = []
    for import_name, pip_name in packages:
        try:
            __import__(import_name)
        except Exception:
            missing.append(pip_name)
    if missing:
        print(f"[설치] geospatial packages: {missing}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *missing])

ensure_geospatial_packages()

import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
from pyproj import Transformer

TO_WORK = Transformer.from_crs(SOURCE_CRS, WORK_CRS, always_xy=True)
TO_WGS = Transformer.from_crs(WORK_CRS, SOURCE_CRS, always_xy=True)

GEO_BOUNDARY_RAW_DIR = DATA_COLLECTION_DIR / "geo_boundary" / "raw"
GEO_BOUNDARY_FINAL_DIR = DATA_COLLECTION_DIR / "geo_boundary" / "final"
GEO_BOUNDARY_RAW_DIR.mkdir(parents=True, exist_ok=True)
GEO_BOUNDARY_FINAL_DIR.mkdir(parents=True, exist_ok=True)

LAND_MASK_PATH = DERIVED_DIR / f"south_korea_land_mask_{CELL_SIZE_M}m.gpkg"
LAND_GRID_PATH = DERIVED_DIR / f"korea_land_grid_{CELL_SIZE_M}m.parquet"
NE_ZIP_PATH = GEO_BOUNDARY_RAW_DIR / "ne_10m_admin_0_scale_rank_minor_islands.zip"
NE_URLS = [
    "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_scale_rank_minor_islands.zip",
    "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_scale_rank_minor_islands.zip",
]
GUARD_ISLANDS = [
    {"name": "Jeju", "lon": 126.5312, "lat": 33.4996, "radius_m": 35000},
    {"name": "Ulleung", "lon": 130.9057, "lat": 37.4846, "radius_m": 7000},
    {"name": "Dokdo", "lon": 131.8702, "lat": 37.2418, "radius_m": 1000},
]

def snap_down(v, cell):
    return int(np.floor(v / cell) * cell)

def snap_up(v, cell):
    return int(np.ceil(v / cell) * cell)

def add_center_and_grid_id(df, cell_size_m=500):
    out = df.copy()
    out["cell_x"] = out["cell_x"].astype("int32")
    out["cell_y"] = out["cell_y"].astype("int32")
    out["center_x"] = out["cell_x"].astype("float64") + cell_size_m / 2.0
    out["center_y"] = out["cell_y"].astype("float64") + cell_size_m / 2.0
    center_lon, center_lat = TO_WGS.transform(
        out["center_x"].to_numpy(),
        out["center_y"].to_numpy(),
    )
    out["center_lon"] = np.round(center_lon, 8)
    out["center_lat"] = np.round(center_lat, 8)
    out["grid_col"] = (out["cell_x"] // cell_size_m).astype("int64")
    out["grid_row"] = (out["cell_y"] // cell_size_m).astype("int64")
    out["grid_id"] = [
        f"G{cell_size_m}_{c}_{r}"
        for c, r in zip(out["grid_col"], out["grid_row"])
    ]
    return out[[
        "grid_id",
        "cell_x", "cell_y",
        "center_x", "center_y",
        "center_lon", "center_lat",
        "grid_col", "grid_row",
    ]]

def distinct_grid_from_lonlat(df, lon_col="lon", lat_col="lat", cell_size_m=500):
    work = df.copy()
    if lon_col not in work.columns or lat_col not in work.columns:
        return pd.DataFrame(columns=[
            "grid_id", "cell_x", "cell_y",
            "center_x", "center_y",
            "center_lon", "center_lat",
            "grid_col", "grid_row",
        ])

    work[lon_col] = pd.to_numeric(work[lon_col], errors="coerce")
    work[lat_col] = pd.to_numeric(work[lat_col], errors="coerce")
    work = work.dropna(subset=[lon_col, lat_col]).copy()
    work = work[
        work[lon_col].between(120, 135) &
        work[lat_col].between(30, 45)
    ].copy()

    if len(work) == 0:
        return pd.DataFrame(columns=[
            "grid_id", "cell_x", "cell_y",
            "center_x", "center_y",
            "center_lon", "center_lat",
            "grid_col", "grid_row",
        ])

    x, y = TO_WORK.transform(work[lon_col].to_numpy(), work[lat_col].to_numpy())
    out = pd.DataFrame({
        "cell_x": (np.floor(np.asarray(x) / cell_size_m).astype(np.int64) * cell_size_m).astype("int32"),
        "cell_y": (np.floor(np.asarray(y) / cell_size_m).astype(np.int64) * cell_size_m).astype("int32"),
    }).drop_duplicates().reset_index(drop=True)
    return add_center_and_grid_id(out, cell_size_m=cell_size_m)

def download_ne_zip(zip_path, urls):
    zip_path = Path(zip_path)
    if zip_path.exists() and zip_path.stat().st_size > 0:
        print(f"[다운로드 생략] {zip_path}")
        return zip_path

    for url in urls:
        try:
            print(f"[다운로드 시도] {url}")
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            if zip_path.exists() and zip_path.stat().st_size > 0:
                print(f"[다운로드 완료] {zip_path} ({zip_path.stat().st_size:,} bytes)")
                return zip_path
        except Exception as e:
            print(f"[다운로드 실패] {e}")

    raise RuntimeError("Natural Earth zip 다운로드 실패")

def load_korea_land_geom_from_ne(zip_path):
    gdf = gpd.read_file(f"zip://{zip_path}")
    if gdf.crs is None:
        gdf = gdf.set_crs(SOURCE_CRS)

    obj_cols = [c for c in gdf.columns if str(gdf[c].dtype) == "object"]
    mask = np.zeros(len(gdf), dtype=bool)
    for c in obj_cols:
        s = gdf[c].astype(str)
        mask |= s.eq("KOR").to_numpy()
        mask |= s.str.contains("South Korea", case=False, na=False).to_numpy()
        mask |= s.str.contains("Republic of Korea", case=False, na=False).to_numpy()
        mask |= s.str.contains("Korea, South", case=False, na=False).to_numpy()

    kor = gdf.loc[mask].copy()
    if len(kor) == 0:
        raise RuntimeError("Natural Earth에서 South Korea feature를 찾지 못했습니다.")

    kor = kor.to_crs(WORK_CRS)
    kor = kor[kor.geometry.notna() & (~kor.geometry.is_empty)].copy()
    land_geom = unary_union(list(kor.geometry))

    guard_patches = []
    for spec in GUARD_ISLANDS:
        x, y = TO_WORK.transform(spec["lon"], spec["lat"])
        p = Point(x, y)
        if not p.within(land_geom):
            guard_patches.append(p.buffer(spec["radius_m"]))
            print(f"[guard island 추가] {spec['name']}")

    if guard_patches:
        land_geom = unary_union([land_geom] + guard_patches)

    return gpd.GeoDataFrame(
        {"name": ["south_korea_land"]},
        geometry=[land_geom],
        crs=WORK_CRS,
    )

def build_land_grid_from_geom(land_gdf, cell_size_m=500):
    minx, miny, maxx, maxy = land_gdf.total_bounds
    minx = snap_down(minx, cell_size_m)
    miny = snap_down(miny, cell_size_m)
    maxx = snap_up(maxx, cell_size_m)
    maxy = snap_up(maxy, cell_size_m)

    x_vals = np.arange(minx, maxx, cell_size_m, dtype=np.int64)
    y_vals = np.arange(miny, maxy, cell_size_m, dtype=np.int64)
    xx = np.repeat(x_vals, len(y_vals))
    yy = np.tile(y_vals, len(x_vals))
    center_x = xx + cell_size_m / 2.0
    center_y = yy + cell_size_m / 2.0

    cand = gpd.GeoDataFrame(
        {
            "cell_x": xx.astype("int32"),
            "cell_y": yy.astype("int32"),
            "center_x": center_x.astype("float64"),
            "center_y": center_y.astype("float64"),
        },
        geometry=gpd.points_from_xy(center_x, center_y),
        crs=WORK_CRS,
    )

    inside = gpd.sjoin(
        cand,
        land_gdf[["geometry"]],
        how="inner",
        predicate="within",
    ).drop(columns=["index_right", "geometry"])

    inside = pd.DataFrame(inside).reset_index(drop=True)
    return add_center_and_grid_id(inside[["cell_x", "cell_y"]], cell_size_m=cell_size_m)

print("=" * 100)
print("[격자틀] Natural Earth 다운로드/로드")
download_ne_zip(NE_ZIP_PATH, NE_URLS)

print("=" * 100)
print("[격자틀] 남한 육지 mask 생성")
land_gdf = load_korea_land_geom_from_ne(NE_ZIP_PATH)
print("[INFO] land mask는 중간 객체로만 사용하고 파일로 저장하지 않습니다.")

print("=" * 100)
print("[격자틀] Natural Earth 기준 육지 grid 생성")
base_land_grid = build_land_grid_from_geom(land_gdf, cell_size_m=CELL_SIZE_M)
print(f" - base land grid 수: {len(base_land_grid):,}")

print("=" * 100)
print("[격자틀] 주유소/시설 포인트 patch grid 생성")
station_patch_grid = distinct_grid_from_lonlat(
    station_location_history if len(station_location_history) > 0 else station_points,
    lon_col="lon",
    lat_col="lat",
    cell_size_m=CELL_SIZE_M,
)
facility_patch_grid = distinct_grid_from_lonlat(
    facility_points,
    lon_col="lon",
    lat_col="lat",
    cell_size_m=CELL_SIZE_M,
)
print(f" - station patch grid 수: {len(station_patch_grid):,}")
print(f" - facility patch grid 수: {len(facility_patch_grid):,}")

print("=" * 100)
print("[격자틀] 최종 land grid 합치기")
final_land_grid = pd.concat(
    [
        base_land_grid[["cell_x", "cell_y"]],
        station_patch_grid[["cell_x", "cell_y"]],
        facility_patch_grid[["cell_x", "cell_y"]],
    ],
    ignore_index=True,
).drop_duplicates().reset_index(drop=True)
final_land_grid = add_center_and_grid_id(final_land_grid, cell_size_m=CELL_SIZE_M)
final_land_grid.to_parquet(LAND_GRID_PATH, index=False, compression="zstd")
print(f"[저장] {LAND_GRID_PATH}")

base_keys = base_land_grid[["cell_x", "cell_y"]].drop_duplicates()
station_only = station_patch_grid[["cell_x", "cell_y"]].merge(
    base_keys, on=["cell_x", "cell_y"], how="left", indicator=True
)
station_only = station_only[station_only["_merge"] == "left_only"]
facility_only = facility_patch_grid[["cell_x", "cell_y"]].merge(
    base_keys, on=["cell_x", "cell_y"], how="left", indicator=True
)
facility_only = facility_only[facility_only["_merge"] == "left_only"]

land_grid_summary = pd.DataFrame([{
    "cell_size_m": CELL_SIZE_M,
    "base_land_grid_count": len(base_land_grid),
    "station_patch_grid_count": len(station_patch_grid),
    "facility_patch_grid_count": len(facility_patch_grid),
    "station_patch_only_count": len(station_only),
    "facility_patch_only_count": len(facility_only),
    "final_land_grid_count": len(final_land_grid),
    "land_grid_path": str(LAND_GRID_PATH),
    "land_mask_path": str(LAND_MASK_PATH),
}])
display_df(land_grid_summary, "[전국 500m 격자틀 요약]")

# %%
# ============================================================
# 7. 공시지가 파생 데이터 생성
# ============================================================
official_source = resolve_official_land_price_source()
print(f"[공시지가 입력] {official_source}")

if official_source is None or not Path(official_source).exists():
    add_requirement(
        "automatic",
        "official_land_price",
        "official_land_price_join",
        "missing",
        DATA_COLLECTION_DIR / "official_land_price" / "final" / "*.csv",
        "공시지가 입력 파일을 찾지 못했습니다.",
    )
    official = pd.DataFrame(columns=["grid_id", "cell_x", "cell_y"])
    snapshot_summary_df = pd.DataFrame(columns=["snapshot_col", "snapshot_date", "not_null", "null", "min", "max"])
else:
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

    official_values = official[["cell_x", "cell_y"] + snapshot_cols].copy()
    official = (
        final_land_grid[["grid_id", "cell_x", "cell_y"]]
        .merge(official_values, on=["cell_x", "cell_y"], how="left")
    )

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
    snapshot_summary_df = pd.DataFrame(snapshot_summary)

save_csv(official, "official_land_price_grid.csv")
display_df(snapshot_summary_df, "[공시지가 snapshot 요약]")

# %%
# ============================================================
# 8. 격자화 단계 영향력 파라미터 기록
# ============================================================
influence_config = pd.DataFrame([
    {
        "feature": "station_neighbor_influence",
        "source_points": "station_points.csv",
        "computed_in": "ai-model/02_spatial_grid_build",
        "target": "observed station grid daily panel",
        "band_km": 3.0,
        "cutoff_km": 15.0,
        "note": "같은 날짜의 다른 grid station_count_total을 지수감쇠 합산합니다.",
    },
    {
        "feature": "storage_influence",
        "source_points": "facility_points.csv",
        "computed_in": "ai-model/02_spatial_grid_build",
        "target": "full land grid static facility features",
        "band_km": 20.0,
        "cutoff_km": 60.0,
        "note": "저유소 포인트를 full land grid 중심점에 지수감쇠 합산합니다.",
    },
    {
        "feature": "agency_influence",
        "source_points": "facility_points.csv",
        "computed_in": "ai-model/02_spatial_grid_build",
        "target": "full land grid static facility features",
        "band_km": 10.0,
        "cutoff_km": 30.0,
        "note": "대리점 포인트를 full land grid 중심점에 지수감쇠 합산합니다.",
    },
    {
        "feature": "factory_influence",
        "source_points": "facility_points.csv",
        "computed_in": "ai-model/02_spatial_grid_build",
        "target": "full land grid static facility features",
        "band_km": 35.0,
        "cutoff_km": 105.0,
        "note": "공장 포인트를 full land grid 중심점에 지수감쇠 합산합니다.",
    },
])
display_df(influence_config, "[격자화 영향력 파라미터]")

# %%
# ============================================================
# 9. 최종 산출물 검증
# ============================================================
missing_requirements = pd.DataFrame(requirement_rows, columns=REQUIREMENT_COLUMNS)
if len(missing_requirements) > 0:
    display_df(missing_requirements, "[확인 필요 항목]")

summary_rows = []
for filename in ESSENTIAL_DERIVED_CSV_OUTPUTS:
    path = DERIVED_DIR / filename
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
display_df(derived_summary, "[AI Model 01 저장 산출물]")

required_outputs = ESSENTIAL_DERIVED_CSV_OUTPUTS
missing_outputs = [x for x in required_outputs if not (DERIVED_DIR / x).exists()]
if missing_outputs:
    raise RuntimeError(f"필수 산출물 누락: {missing_outputs}")

required_files = [
    LAND_GRID_PATH,
]
missing_files = [str(x) for x in required_files if not Path(x).exists()]
if missing_files:
    raise RuntimeError(f"필수 격자 파일 누락: {missing_files}")

print("\n[AI Model 01 완료]")
print(f"- DERIVED_DATA_PATH: {DERIVED_DATA_PATH}")
print(f"- saved_output_count: {len(ESSENTIAL_DERIVED_FILE_OUTPUTS):,}")
for filename in ESSENTIAL_DERIVED_FILE_OUTPUTS:
    print(f"  - {filename}")
print(f"- missing_requirements: {len(missing_requirements):,}")

# %%
# ============================================================
# 10. 좌표 범위 이탈 QC 지도
# ============================================================
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

def split_coord_quality(df, source_name, lon_col="lon", lat_col="lat"):
    work = df.copy()
    work["_lon_num"] = pd.to_numeric(work[lon_col], errors="coerce") if lon_col in work.columns else np.nan
    work["_lat_num"] = pd.to_numeric(work[lat_col], errors="coerce") if lat_col in work.columns else np.nan

    missing_mask = work["_lon_num"].isna() | work["_lat_num"].isna()
    outside_mask = (
        ~missing_mask &
        ~(work["_lon_num"].between(120, 135) & work["_lat_num"].between(30, 45))
    )

    outside = work.loc[outside_mask].copy()
    outside["point_type"] = source_name
    outside["lon"] = outside["_lon_num"]
    outside["lat"] = outside["_lat_num"]
    return outside, int(missing_mask.sum()), int(outside_mask.sum())

station_outside, station_missing_coord, station_outside_coord = split_coord_quality(
    station_latest_profile,
    "station",
)
facility_outside, facility_missing_coord, facility_outside_coord = split_coord_quality(
    facility_points,
    "facility",
)

coord_qc_summary = pd.DataFrame([
    {
        "point_type": "station",
        "total_rows": len(station_latest_profile),
        "missing_lonlat": station_missing_coord,
        "outside_korea_range": station_outside_coord,
        "valid_lonlat": int(len(station_latest_profile) - station_missing_coord - station_outside_coord),
    },
    {
        "point_type": "facility",
        "total_rows": len(facility_points),
        "missing_lonlat": facility_missing_coord,
        "outside_korea_range": facility_outside_coord,
        "valid_lonlat": int(len(facility_points) - facility_missing_coord - facility_outside_coord),
    },
])
display_df(coord_qc_summary, "[좌표 QC 요약]")

outside_points = pd.concat(
    [station_outside, facility_outside],
    ignore_index=True,
    sort=False,
)

def missing_coord_sample(df, source_name, lon_col="lon", lat_col="lat"):
    work = df.copy()
    work["_lon_num"] = pd.to_numeric(work[lon_col], errors="coerce") if lon_col in work.columns else np.nan
    work["_lat_num"] = pd.to_numeric(work[lat_col], errors="coerce") if lat_col in work.columns else np.nan
    missing = work[work["_lon_num"].isna() | work["_lat_num"].isna()].copy()
    missing["point_type"] = source_name
    return missing

missing_points = pd.concat(
    [
        missing_coord_sample(station_latest_profile, "station"),
        missing_coord_sample(facility_points, "facility"),
    ],
    ignore_index=True,
    sort=False,
)

sample_cols = [
    c for c in [
        "point_type", "station_id", "source_region", "station_name",
        "brand", "facility_type_raw", "name", "address", "lon", "lat",
        "geocode_status",
    ]
    if c in set(outside_points.columns).union(set(missing_points.columns))
]

if len(outside_points) > 0:
    try:
        korea_bg = land_gdf.to_crs(SOURCE_CRS)
    except Exception:
        try:
            korea_bg = load_korea_land_geom_from_ne(NE_ZIP_PATH).to_crs(SOURCE_CRS)
        except Exception as e:
            korea_bg = None
            print(f"[주의] 대한민국 배경 지도를 불러오지 못했습니다: {type(e).__name__}: {e}")

    fig, ax = plt.subplots(figsize=(8, 9))

    if korea_bg is not None:
        korea_bg.plot(ax=ax, color="#f2f2f2", edgecolor="#555555", linewidth=0.7)

    ax.add_patch(
        Rectangle(
            (120, 30),
            15,
            15,
            fill=False,
            edgecolor="#888888",
            linewidth=1.2,
            linestyle="--",
            label="valid lon/lat range",
        )
    )

    style_by_type = {
        "station": {"color": "#d62728", "marker": "x", "s": 42},
        "facility": {"color": "#1f77b4", "marker": "o", "s": 32},
    }

    for point_type, part in outside_points.groupby("point_type"):
        style = style_by_type.get(point_type, {"color": "#333333", "marker": "o", "s": 28})
        ax.scatter(
            part["lon"],
            part["lat"],
            label=f"{point_type} out of range",
            alpha=0.85,
            **style,
        )

    x_values = outside_points["lon"].dropna().tolist() + [120, 135]
    y_values = outside_points["lat"].dropna().tolist() + [30, 45]
    x_margin = max(0.5, (max(x_values) - min(x_values)) * 0.08)
    y_margin = max(0.5, (max(y_values) - min(y_values)) * 0.08)
    ax.set_xlim(min(x_values) - x_margin, max(x_values) + x_margin)
    ax.set_ylim(min(y_values) - y_margin, max(y_values) + y_margin)

    ax.set_title("Coordinate QC: Out-of-range Points", fontsize=14)
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.5)
    ax.legend(loc="upper right")
    plt.show()

    display_df(outside_points[sample_cols], "[Out-of-range coordinate sample]", n=50)
else:
    print("[INFO] Numeric out-of-range lon/lat points: 0")
    print("[INFO] 범위를 벗어난 숫자 좌표는 없습니다. 문제 행은 lon/lat 값 자체가 비어 있어 지도에 찍을 수 없습니다.")
    display_df(missing_points[sample_cols], "[Missing lon/lat sample]", n=50)
