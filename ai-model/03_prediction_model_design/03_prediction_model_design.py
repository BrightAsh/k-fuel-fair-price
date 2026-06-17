# Local/PyCharm execution script for AI model stage 03.
# The notebook version is kept for Colab, but local execution should use this file.


# %% [markdown] cell 0
# # AI Model 03. Grid Fair Price Prediction Model
# 2단계 산출물 `grid.parquet`을 입력으로 받아 다음날 격자별 가격 spread 모델을 학습하고,
# `2026-01-01` 이후 target_date를 test 전용으로 예측/평가합니다.
# 핵심 원칙:
# - `2026-01-01` 이후 target_date는 학습, 튜닝, 최종 재학습에 절대 사용하지 않습니다.
# - train/validation은 유류세 인하/환원 등 정책 적용 기간을 완전히 제외한 정상기간만 사용합니다.
# - feature_date는 target_date - 1일입니다. 즉 전날까지의 데이터로 당일 적정가격을 예측합니다.
# - 최근 28일 lag/rolling feature와 결측률을 만들어 시계열 흐름을 보전합니다.
# - 원문 노트북의 구조처럼 `격자 가격 - 전국 기준가격` spread를 학습합니다.
# - 후보 모델은 lag/rolling LightGBM과 temporal CNN + LSTM + static MLP 하이브리드입니다.
# - 예측 spread는 날짜별 주유소 수 가중평균이 0이 되도록 재중심화합니다.
# - test는 월 단위로 전체 격자를 읽어 예측하므로 test 표본추출은 하지 않습니다.
# 

# %% cell 1
from __future__ import annotations

import gc
import json
import math
import os
import subprocess
import shutil
import sys
import tempfile
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

warnings.filterwarnings("ignore")


def ensure_packages() -> None:
    import importlib.util

    required = {
        "duckdb": "duckdb",
        "pyarrow": "pyarrow",
        "lightgbm": "lightgbm",
        "sklearn": "scikit-learn",
        "joblib": "joblib",
    }
    missing = [pkg for module, pkg in required.items() if importlib.util.find_spec(module) is None]
    if missing:
        print(f"[INSTALL] missing packages: {missing}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *missing])


ensure_packages()

BOOST_COMPUTE_CACHE_DIR = Path(
    os.environ.get("K_FUEL_BOOST_COMPUTE_CACHE_DIR", str(Path(tempfile.gettempdir()) / "k_fuel_boost_compute_cache"))
)
try:
    BOOST_COMPUTE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("BOOST_COMPUTE_CACHE_PATH", str(BOOST_COMPUTE_CACHE_DIR))
except OSError as exc:
    print(f"[WARN] Boost.Compute cache directory setup skipped: {type(exc).__name__}: {exc}")
os.environ.setdefault("BOOST_COMPUTE_USE_OFFLINE_CACHE", "0")

import duckdb
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

try:
    from IPython.display import display
except Exception:  # pragma: no cover
    display = None

pd.set_option("display.max_columns", 200)
pd.set_option("display.width", 200)


# %% [markdown] cell 2
# ## 0. 경로와 실행 설정
# 1, 2단계 노트북과 동일하게 Google Drive를 mount한 뒤 고정 `ROOT_PATH`를 사용합니다.
# 기본 입력은 `ROOT_PATH/그리드/grid.parquet`이고, 산출물은 `ROOT_PATH/AI모델/03_prediction_model_design/`에 저장합니다.
# 로컬 테스트 상황에서만 레포 안의 `ai-model/02_spatial_grid_build/outputs/grid.parquet`을 fallback으로 사용합니다.
# 

# %% cell 3
try:
    from google.colab import drive
    drive.mount("/content/drive", force_remount=os.environ.get("K_FUEL_DRIVE_FORCE_REMOUNT", "1") == "1")
except Exception as exc:
    print(f"[INFO] Google Drive mount skipped: {type(exc).__name__}: {exc}")

ROOT_PATH = os.environ.get(
    "K_FUEL_ROOT_PATH",
    "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/",
)
ROOT_PATH = str(ROOT_PATH)
if not ROOT_PATH.endswith("/"):
    ROOT_PATH += "/"

ROOT_DIR = Path(ROOT_PATH)
DATA_COLLECTION_DIR = ROOT_DIR / "data collection"
GRID_OUTPUT_DIR = ROOT_DIR / "그리드"
MODEL_OUTPUT_DIR = ROOT_DIR / "AI모델" / "03_prediction_model_design"

DATA_COLLECTION_PATH = str(DATA_COLLECTION_DIR) + "/"
GRID_OUTPUT_PATH = str(GRID_OUTPUT_DIR) + "/"
MODEL_OUTPUT_PATH = str(MODEL_OUTPUT_DIR) + "/"

TEST_START = pd.Timestamp("2026-01-01")
TEST_START_SQL = TEST_START.strftime("%Y-%m-%d")
PREDICTION_HORIZON_DAYS = int(os.environ.get("K_FUEL_PREDICTION_HORIZON_DAYS", "1"))

TRAIN_VALID_TRAIN_RATIO = float(os.environ.get("K_FUEL_TRAIN_VALID_TRAIN_RATIO", "0.70"))
GAP_DAYS = int(os.environ.get("K_FUEL_GAP_DAYS", "7"))
EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID = os.environ.get("K_FUEL_EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID", "1") == "1"
POLICY_EXCLUDE_BUFFER_BEFORE_DAYS = int(os.environ.get("K_FUEL_POLICY_EXCLUDE_BUFFER_BEFORE_DAYS", "0"))
POLICY_EXCLUDE_BUFFER_AFTER_DAYS = int(os.environ.get("K_FUEL_POLICY_EXCLUDE_BUFFER_AFTER_DAYS", "0"))

# 표본은 hash(grid_id, date) 기반이라 시간/공간 양쪽으로 균일하게 뽑힙니다.
TRAIN_SAMPLE_PER_MILLE = int(os.environ.get("K_FUEL_TRAIN_SAMPLE_PER_MILLE", "80"))
VALID_SAMPLE_PER_MILLE = int(os.environ.get("K_FUEL_VALID_SAMPLE_PER_MILLE", "1000"))

MAX_TRAIN_TUNE_ROWS_PER_FUEL = int(os.environ.get("K_FUEL_MAX_TRAIN_TUNE_ROWS", "2500000"))
MAX_FINAL_TRAIN_ROWS_PER_FUEL = int(os.environ.get("K_FUEL_MAX_FINAL_TRAIN_ROWS", "4500000"))
MAX_VALID_ROWS_PER_FUEL = int(os.environ.get("K_FUEL_MAX_VALID_ROWS", "1100000"))

RANDOM_SEED = int(os.environ.get("K_FUEL_RANDOM_SEED", "20260616"))
USE_GPU = os.environ.get("K_FUEL_USE_GPU", "1") == "1"
USE_LGBM_GPU = os.environ.get("K_FUEL_USE_LGBM_GPU", "0") == "1"
RUN_FUELS = [x.strip() for x in os.environ.get("K_FUEL_RUN_FUELS", "gasoline,diesel").split(",") if x.strip()]
RUN_SEQUENCE_MODEL = os.environ.get("K_FUEL_RUN_SEQUENCE_MODEL", "1") == "1"
FINAL_MODEL_KIND = os.environ.get("K_FUEL_FINAL_MODEL_KIND", "auto").lower()  # auto, lgbm, sequence
SEQUENCE_MODEL_EPOCHS = int(os.environ.get("K_FUEL_SEQUENCE_MODEL_EPOCHS", "1000"))
SEQUENCE_MODEL_BATCH_SIZE = int(os.environ.get("K_FUEL_SEQUENCE_MODEL_BATCH_SIZE", "8192"))
SEQUENCE_MODEL_MAX_TRAIN_ROWS = int(os.environ.get("K_FUEL_SEQUENCE_MODEL_MAX_TRAIN_ROWS", "700000"))
SEQUENCE_MODEL_MAX_VALID_ROWS = int(os.environ.get("K_FUEL_SEQUENCE_MODEL_MAX_VALID_ROWS", "300000"))
SEQUENCE_MODEL_LR = float(os.environ.get("K_FUEL_SEQUENCE_MODEL_LR", "0.0025"))
SEQUENCE_MODEL_WEIGHT_DECAY = float(os.environ.get("K_FUEL_SEQUENCE_MODEL_WEIGHT_DECAY", "0.0001"))
SEQUENCE_LR_REDUCE_FACTOR = float(os.environ.get("K_FUEL_SEQUENCE_LR_REDUCE_FACTOR", "0.5"))
SEQUENCE_LR_PATIENCE = int(os.environ.get("K_FUEL_SEQUENCE_LR_PATIENCE", "8"))
SEQUENCE_MIN_LR = float(os.environ.get("K_FUEL_SEQUENCE_MIN_LR", "0.00001"))
SEQUENCE_EARLY_STOPPING_PATIENCE = int(os.environ.get("K_FUEL_SEQUENCE_EARLY_STOPPING_PATIENCE", "30"))
SEQUENCE_EARLY_STOPPING_MIN_DELTA = float(os.environ.get("K_FUEL_SEQUENCE_EARLY_STOPPING_MIN_DELTA", "0.001"))
SEQUENCE_GRAD_CLIP_NORM = float(os.environ.get("K_FUEL_SEQUENCE_GRAD_CLIP_NORM", "1.0"))
SEQUENCE_RESIDUAL_FROM_LAG1 = os.environ.get("K_FUEL_SEQUENCE_RESIDUAL_FROM_LAG1", "1") == "1"
SEQUENCE_MIN_EPOCHS_BEFORE_REFERENCE_ABORT = int(os.environ.get("K_FUEL_SEQUENCE_MIN_EPOCHS_BEFORE_REFERENCE_ABORT", "50"))
SEQUENCE_ABORT_WORSE_THAN_REFERENCE_RATIO = float(
    os.environ.get("K_FUEL_SEQUENCE_ABORT_WORSE_THAN_REFERENCE_RATIO", "1.30")
)

if not 0.0 < TRAIN_VALID_TRAIN_RATIO < 1.0:
    raise ValueError("K_FUEL_TRAIN_VALID_TRAIN_RATIO는 0과 1 사이여야 합니다.")

POLICY_EXCLUDE_RANGES = [
    ("2008-04-15", "2008-12-31", "fuel_tax_cut_2008_10pct"),
    ("2011-04-07", "2011-07-06", "refinery_price_cut_2011_100won"),
    ("2018-11-06", "2019-05-06", "fuel_tax_cut_2018_15pct"),
    ("2019-05-07", "2019-08-31", "fuel_tax_cut_2019_7pct"),
    ("2021-11-12", "2022-04-30", "fuel_tax_cut_2021_20pct"),
    ("2022-05-01", "2022-06-30", "fuel_tax_cut_2022_30pct"),
    ("2022-07-01", "2022-12-31", "fuel_tax_cut_2022_37pct"),
    ("2023-01-01", "2024-06-30", "fuel_tax_cut_2023_2024"),
    ("2024-07-01", "2024-10-31", "fuel_tax_cut_2024_partial"),
    ("2024-11-01", "2025-04-30", "fuel_tax_cut_2024_2025_partial"),
    ("2025-05-01", "2025-10-31", "fuel_tax_cut_2025_readjusted"),
    ("2025-11-01", "2026-03-26", "fuel_tax_cut_2025_2026_partial"),
    ("2026-03-27", "2026-05-31", "fuel_tax_cut_2026_expanded"),
]


def find_repo_root(start: Path) -> Path:
    start = start.resolve()
    for p in [start, *start.parents]:
        if (p / "ai-model").exists():
            return p
    return start


REPO_START_PATH = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
REPO_ROOT = find_repo_root(REPO_START_PATH)
STAGE2_LOCAL_GRID = REPO_ROOT / "ai-model" / "02_spatial_grid_build" / "outputs" / "grid.parquet"
STAGE3_DIR = REPO_ROOT / "ai-model" / "03_prediction_model_design"


def first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for path in paths:
        if path and Path(path).exists():
            return Path(path)
    return None


GRID_PATH = first_existing(
    [
        Path(os.environ["K_FUEL_GRID_PATH"]) if os.environ.get("K_FUEL_GRID_PATH") else None,
        GRID_OUTPUT_DIR / "grid.parquet",
        ROOT_DIR / "AI모델" / "02_spatial_grid_build" / "grid.parquet",
        STAGE2_LOCAL_GRID,
    ]
)

if GRID_PATH is None:
    raise FileNotFoundError(
        "grid.parquet을 찾지 못했습니다. K_FUEL_GRID_PATH 또는 K_FUEL_ROOT_PATH를 확인하세요."
    )

SOURCE_GRID_PATH = GRID_PATH
CACHE_GRID_TO_LOCAL = os.environ.get("K_FUEL_CACHE_GRID_TO_LOCAL", "1") == "1"
LOCAL_CACHE_DIR = Path(os.environ.get("K_FUEL_LOCAL_CACHE_DIR", "/content/kff_prediction_model_tmp"))
LOCAL_GRID_CACHE_PATH = LOCAL_CACHE_DIR / "grid.parquet"

if CACHE_GRID_TO_LOCAL and str(GRID_PATH).startswith("/content/drive/"):
    try:
        LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        source_size = GRID_PATH.stat().st_size
        cache_size = LOCAL_GRID_CACHE_PATH.stat().st_size if LOCAL_GRID_CACHE_PATH.exists() else -1
        if source_size != cache_size:
            print(f"[CACHE] Drive grid.parquet -> local: {LOCAL_GRID_CACHE_PATH}")
            print(f"[CACHE] source size = {source_size / 1024**3:.2f} GB")
            shutil.copy2(GRID_PATH, LOCAL_GRID_CACHE_PATH)
        else:
            print(f"[CACHE] reuse local grid.parquet: {LOCAL_GRID_CACHE_PATH}")
        GRID_PATH = LOCAL_GRID_CACHE_PATH
    except OSError as exc:
        if "Transport endpoint is not connected" in str(exc):
            raise RuntimeError(
                "Google Drive mount? ??????. ???? ?????? ? ?? ?? ?? ??? "
                "drive.mount(..., force_remount=True)? ??? ? ?? ?????."
            ) from exc
        raise

OUTPUT_ROOT = Path(os.environ["K_FUEL_MODEL_OUTPUT_DIR"]) if os.environ.get("K_FUEL_MODEL_OUTPUT_DIR") else None
if OUTPUT_ROOT is None:
    OUTPUT_ROOT = MODEL_OUTPUT_DIR if ROOT_DIR.exists() else STAGE3_DIR / "outputs"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

print(f"REPO_ROOT                  = {REPO_ROOT}")
print(f"ROOT_PATH                  = {ROOT_PATH}")
print(f"GRID_OUTPUT_PATH          = {GRID_OUTPUT_PATH}")
print(f"MODEL_OUTPUT_PATH         = {MODEL_OUTPUT_PATH}")
print(f"SOURCE_GRID_PATH          = {SOURCE_GRID_PATH}")
print(f"GRID_PATH                  = {GRID_PATH}")
print(f"OUTPUT_ROOT                = {OUTPUT_ROOT}")
print(f"TEST_START                 = {TEST_START_SQL}")
print(f"PREDICTION_HORIZON_DAYS    = {PREDICTION_HORIZON_DAYS}")
print(f"TRAIN_VALID_TRAIN_RATIO    = {TRAIN_VALID_TRAIN_RATIO:.2f}")
print(f"GAP_DAYS                   = {GAP_DAYS}")
print(f"EXCLUDE_POLICY_TRAIN_VALID = {EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID}")
print(f"TRAIN_SAMPLE_PER_MILLE     = {TRAIN_SAMPLE_PER_MILLE}")
print(f"VALID_SAMPLE_PER_MILLE     = {VALID_SAMPLE_PER_MILLE}")
print(f"MAX_TRAIN_TUNE_ROWS/FUEL   = {MAX_TRAIN_TUNE_ROWS_PER_FUEL:,}")
print(f"MAX_VALID_ROWS/FUEL        = {MAX_VALID_ROWS_PER_FUEL:,}")
print(f"MAX_FINAL_TRAIN_ROWS/FUEL  = {MAX_FINAL_TRAIN_ROWS_PER_FUEL:,}")
print(f"USE_GPU_SEQUENCE           = {USE_GPU}")
print(f"USE_LGBM_GPU               = {USE_LGBM_GPU}")
print(f"BOOST_COMPUTE_CACHE_PATH   = {os.environ.get('BOOST_COMPUTE_CACHE_PATH')}")
print(f"RUN_SEQUENCE_MODEL         = {RUN_SEQUENCE_MODEL}")
print(f"FINAL_MODEL_KIND           = {FINAL_MODEL_KIND}")
print(f"SEQUENCE_RESIDUAL_FROM_LAG1 = {SEQUENCE_RESIDUAL_FROM_LAG1}")
print(f"SEQUENCE_REFERENCE_ABORT    = {SEQUENCE_ABORT_WORSE_THAN_REFERENCE_RATIO:.2f}x after {SEQUENCE_MIN_EPOCHS_BEFORE_REFERENCE_ABORT} epochs")


# %% [markdown] cell 4
# ## 1. 공통 함수와 유종 설정
# 

# %% cell 5


def qid(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def qstr(value: Any) -> str:
    return "'" + str(value).replace("\\", "/").replace("'", "''") + "'"


def sql_date(value: pd.Timestamp | str) -> str:
    return f"DATE {qstr(pd.Timestamp(value).strftime('%Y-%m-%d'))}"


def adjusted_policy_exclude_ranges() -> List[Dict[str, Any]]:
    ranges: List[Dict[str, Any]] = []
    for start, end, label in POLICY_EXCLUDE_RANGES:
        adj_start = pd.Timestamp(start) - pd.Timedelta(days=POLICY_EXCLUDE_BUFFER_BEFORE_DAYS)
        adj_end = pd.Timestamp(end) + pd.Timedelta(days=POLICY_EXCLUDE_BUFFER_AFTER_DAYS)
        ranges.append(
            {
                "start": adj_start,
                "end": adj_end,
                "label": label,
            }
        )
    return ranges


def policy_exclusion_condition(date_expr: str) -> str:
    if not EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID:
        return "TRUE"
    pieces = [
        f"({date_expr} BETWEEN {sql_date(r['start'])} AND {sql_date(r['end'])})"
        for r in adjusted_policy_exclude_ranges()
    ]
    if not pieces:
        return "TRUE"
    return "NOT (" + " OR ".join(pieces) + ")"


def panel_sql() -> str:
    return f"read_parquet({qstr(GRID_PATH)})"


def read_csv_flexible(path: Path) -> pd.DataFrame:
    last_error: Optional[Exception] = None
    for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError(f"CSV 읽기 실패: {path}")


def ensure_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.floor("D")


def weighted_mae(y_true: pd.Series | np.ndarray, y_pred: pd.Series | np.ndarray, weight: pd.Series | np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    w = np.asarray(weight, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p) & np.isfinite(w) & (w > 0)
    if mask.sum() == 0:
        return float("nan")
    return float(np.sum(np.abs(y[mask] - p[mask]) * w[mask]) / np.sum(w[mask]))


def weighted_rmse(y_true: pd.Series | np.ndarray, y_pred: pd.Series | np.ndarray, weight: pd.Series | np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    w = np.asarray(weight, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p) & np.isfinite(w) & (w > 0)
    if mask.sum() == 0:
        return float("nan")
    return float(np.sqrt(np.sum(((y[mask] - p[mask]) ** 2) * w[mask]) / np.sum(w[mask])))


def safe_r2(y_true: pd.Series | np.ndarray, y_pred: pd.Series | np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p)
    if mask.sum() < 2:
        return float("nan")
    return float(r2_score(y[mask], p[mask]))


def recenter_spread_by_date(df: pd.DataFrame, raw_col: str, weight_col: str) -> pd.Series:
    tmp = df[["date", raw_col, weight_col]].copy()
    tmp["date"] = ensure_date(tmp["date"])
    tmp[raw_col] = pd.to_numeric(tmp[raw_col], errors="coerce")
    tmp[weight_col] = pd.to_numeric(tmp[weight_col], errors="coerce").fillna(0).clip(lower=0)
    tmp["_num"] = tmp[raw_col] * tmp[weight_col]
    grouped = tmp.groupby("date", dropna=False)[["_num", weight_col]].sum()
    centers = grouped["_num"] / grouped[weight_col].replace(0, np.nan)
    return tmp[raw_col] - tmp["date"].map(centers).fillna(0)


def regression_metric_row(
    y_true: pd.Series,
    y_pred: pd.Series,
    weight: pd.Series,
    prefix: str,
) -> Dict[str, float]:
    mask = pd.to_numeric(y_true, errors="coerce").notna() & pd.to_numeric(y_pred, errors="coerce").notna()
    y = pd.to_numeric(y_true[mask], errors="coerce")
    p = pd.to_numeric(y_pred[mask], errors="coerce")
    w = pd.to_numeric(weight[mask], errors="coerce").fillna(0)
    return {
        f"{prefix}_rows": int(mask.sum()),
        f"{prefix}_mae": float(mean_absolute_error(y, p)) if len(y) else float("nan"),
        f"{prefix}_rmse": float(mean_squared_error(y, p) ** 0.5) if len(y) else float("nan"),
        f"{prefix}_r2": safe_r2(y, p),
        f"{prefix}_weighted_mae": weighted_mae(y, p, w),
        f"{prefix}_weighted_rmse": weighted_rmse(y, p, w),
    }


@dataclass(frozen=True)
class FuelConfig:
    fuel: str
    label: str
    target_col: str
    station_count_col: str
    policy_subdir: str
    policy_file: str
    step2_file: str


FUEL_CONFIG: Dict[str, FuelConfig] = {
    "gasoline": FuelConfig(
        fuel="gasoline",
        label="휘발유",
        target_col="gasoline_price_mean",
        station_count_col="gasoline_station_count",
        policy_subdir="휘발유",
        policy_file="일별_정책적용_데이터_휘발유.csv",
        step2_file="gasoline_production_predictions_full_calendar.csv",
    ),
    "diesel": FuelConfig(
        fuel="diesel",
        label="경유",
        target_col="diesel_price_mean",
        station_count_col="diesel_station_count",
        policy_subdir="경유",
        policy_file="일별_정책적용_데이터_경유.csv",
        step2_file="diesel_production_predictions_full_calendar.csv",
    ),
}

for fuel in RUN_FUELS:
    if fuel not in FUEL_CONFIG:
        raise KeyError(f"지원하지 않는 유종입니다: {fuel}")


# %% [markdown] cell 6
# ## 2. 패널 점검과 feature 설계
# 

# %% cell 7
con = duckdb.connect(database=":memory:")
con.execute(f"PRAGMA threads={max(os.cpu_count() or 2, 2)}")

panel_overview = con.execute(
    f"""
    SELECT
        COUNT(*) AS rows,
        COUNT(DISTINCT grid_id) AS unique_grid_count,
        MIN(CAST(date AS DATE)) AS date_min,
        MAX(CAST(date AS DATE)) AS date_max,
        SUM(CASE WHEN CAST(date AS DATE) >= {sql_date(TEST_START)} THEN 1 ELSE 0 END) AS test_2026_rows
    FROM {panel_sql()}
    """
).df()

schema_df = con.execute(f"DESCRIBE SELECT * FROM {panel_sql()} LIMIT 0").df()
ALL_COLUMNS = schema_df["column_name"].tolist()
TYPE_BY_COLUMN = dict(zip(schema_df["column_name"], schema_df["column_type"].astype(str)))

print("[PANEL OVERVIEW]")
display(panel_overview) if display else print(panel_overview)
print("[SCHEMA]")
display(schema_df) if display else print(schema_df.to_string(index=False))


NUMERIC_TYPE_TOKENS = (
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
    "REAL",
)


def is_numeric_type(dtype: str) -> bool:
    dtype = str(dtype).upper()
    return any(token in dtype for token in NUMERIC_TYPE_TOKENS)


def select_base_panel_features() -> List[str]:
    exclude = {
        "date",
        "grid_id",
        "official_price_source_date",
        "gasoline_price_mean",
        "diesel_price_mean",
    }
    selected: List[str] = []
    for col in ALL_COLUMNS:
        if col in exclude:
            continue
        if not is_numeric_type(TYPE_BY_COLUMN.get(col, "")):
            continue
        # grid별 가격 평균/셀프 가격 평균은 target 계열이므로 leakage 방지를 위해 제외합니다.
        if "price_mean" in col and col != "official_land_price":
            continue
        selected.append(col)
    return selected


BASE_PANEL_FEATURES = select_base_panel_features()
DERIVED_FEATURES = [
    "calendar_year",
    "calendar_month",
    "calendar_dayofweek",
    "calendar_dayofyear",
    "calendar_is_weekend",
    "calendar_month_sin",
    "calendar_month_cos",
    "calendar_dayofyear_sin",
    "calendar_dayofyear_cos",
    "official_price_age_days",
    "official_price_source_year",
    "national_price_anchor",
]

SEQUENCE_LENGTH_DAYS = int(os.environ.get("K_FUEL_SEQUENCE_LENGTH_DAYS", "28"))
SPREAD_LAG_DAYS = list(range(1, SEQUENCE_LENGTH_DAYS + 1))
PRICE_LAG_DAYS = [1, 2, 3, 7, 14, 28]
COUNT_LAG_DAYS = [1, 7, 14, 28]
ROLLING_WINDOWS = [7, 14, 28]

SPREAD_LAG_FEATURES = [f"spread_lag_{d}d" for d in SPREAD_LAG_DAYS]
PRICE_LAG_FEATURES = [f"actual_grid_price_lag_{d}d" for d in PRICE_LAG_DAYS if d <= SEQUENCE_LENGTH_DAYS]
COUNT_LAG_FEATURES = [f"station_weight_lag_{d}d" for d in COUNT_LAG_DAYS if d <= SEQUENCE_LENGTH_DAYS]
ROLLING_FEATURES = []
for w in ROLLING_WINDOWS:
    if w <= SEQUENCE_LENGTH_DAYS:
        ROLLING_FEATURES.extend(
            [
                f"spread_hist_count_{w}d",
                f"spread_missing_rate_{w}d",
                f"spread_roll{w}_mean",
                f"spread_roll{w}_std",
                f"spread_roll{w}_min",
                f"spread_roll{w}_max",
                f"actual_grid_price_roll{w}_mean",
                f"actual_grid_price_roll{w}_std",
            ]
        )

TREND_FEATURES = [
    "spread_trend_1d_7d",
    "spread_trend_roll7_roll28",
    "actual_price_trend_1d_7d",
]
TIME_SERIES_FEATURES = SPREAD_LAG_FEATURES + PRICE_LAG_FEATURES + COUNT_LAG_FEATURES + ROLLING_FEATURES + TREND_FEATURES
MODEL_FEATURES = BASE_PANEL_FEATURES + DERIVED_FEATURES + TIME_SERIES_FEATURES

print(f"BASE_PANEL_FEATURES = {len(BASE_PANEL_FEATURES):,}")
print(f"TIME_SERIES_FEATURES = {len(TIME_SERIES_FEATURES):,}")
print(f"MODEL_FEATURES      = {len(MODEL_FEATURES):,}")
display(pd.DataFrame({"feature": MODEL_FEATURES})) if display else print(MODEL_FEATURES)


# %% [markdown] cell 8
# ## 3. DuckDB 로딩 함수
# `target_spread = target_date의 actual_grid_price - target_date의 national_actual_price`를 만들고,
# feature는 `feature_date = target_date - PREDICTION_HORIZON_DAYS`와 그 이전 lag/rolling 값에서 가져옵니다.
# `national_actual_price`는 target_date의 주유소 수 가중 전국 평균으로 계산합니다.
# 

# %% cell 9


def history_sql_exprs() -> List[str]:
    exprs: List[str] = []
    for d in SPREAD_LAG_DAYS:
        exprs.append(
            f"LAG(spread_target, {d}) OVER (PARTITION BY grid_id ORDER BY target_date) AS spread_lag_{d}d"
        )
    for d in PRICE_LAG_DAYS:
        if d <= SEQUENCE_LENGTH_DAYS:
            exprs.append(
                f"LAG(actual_grid_price, {d}) OVER (PARTITION BY grid_id ORDER BY target_date) AS actual_grid_price_lag_{d}d"
            )
    for d in COUNT_LAG_DAYS:
        if d <= SEQUENCE_LENGTH_DAYS:
            exprs.append(
                f"LAG(station_weight, {d}) OVER (PARTITION BY grid_id ORDER BY target_date) AS station_weight_lag_{d}d"
            )
    for w in ROLLING_WINDOWS:
        if w <= SEQUENCE_LENGTH_DAYS:
            frame = f"PARTITION BY grid_id ORDER BY target_date ROWS BETWEEN {w} PRECEDING AND 1 PRECEDING"
            exprs.extend(
                [
                    f"COUNT(spread_target) OVER ({frame}) AS spread_hist_count_{w}d",
                    f"1.0 - (COUNT(spread_target) OVER ({frame}) / {float(w)}) AS spread_missing_rate_{w}d",
                    f"AVG(spread_target) OVER ({frame}) AS spread_roll{w}_mean",
                    f"STDDEV_SAMP(spread_target) OVER ({frame}) AS spread_roll{w}_std",
                    f"MIN(spread_target) OVER ({frame}) AS spread_roll{w}_min",
                    f"MAX(spread_target) OVER ({frame}) AS spread_roll{w}_max",
                    f"AVG(actual_grid_price) OVER ({frame}) AS actual_grid_price_roll{w}_mean",
                    f"STDDEV_SAMP(actual_grid_price) OVER ({frame}) AS actual_grid_price_roll{w}_std",
                ]
            )
    return exprs


def feature_sql_exprs() -> List[str]:
    exprs: List[str] = []
    for col in BASE_PANEL_FEATURES:
        exprs.append(f"CAST(p.{qid(col)} AS DOUBLE) AS {qid(col)}")

    exprs.extend(
        [
            "EXTRACT(year FROM t.target_date)::DOUBLE AS calendar_year",
            "EXTRACT(month FROM t.target_date)::DOUBLE AS calendar_month",
            "EXTRACT(dayofweek FROM t.target_date)::DOUBLE AS calendar_dayofweek",
            "EXTRACT(doy FROM t.target_date)::DOUBLE AS calendar_dayofyear",
            "CASE WHEN EXTRACT(dayofweek FROM t.target_date) IN (0, 6) THEN 1.0 ELSE 0.0 END AS calendar_is_weekend",
            "(sin(2 * pi() * EXTRACT(month FROM t.target_date) / 12.0))::DOUBLE AS calendar_month_sin",
            "(cos(2 * pi() * EXTRACT(month FROM t.target_date) / 12.0))::DOUBLE AS calendar_month_cos",
            "(sin(2 * pi() * EXTRACT(doy FROM t.target_date) / 366.0))::DOUBLE AS calendar_dayofyear_sin",
            "(cos(2 * pi() * EXTRACT(doy FROM t.target_date) / 366.0))::DOUBLE AS calendar_dayofyear_cos",
            "CAST(t.national_actual_price AS DOUBLE) AS national_price_anchor",
        ]
    )

    if "official_price_source_date" in ALL_COLUMNS:
        exprs.extend(
            [
                "date_diff('day', CAST(p.official_price_source_date AS DATE), t.target_date)::DOUBLE AS official_price_age_days",
                "EXTRACT(year FROM CAST(p.official_price_source_date AS DATE))::DOUBLE AS official_price_source_year",
            ]
        )
    else:
        exprs.extend(
            [
                "NULL::DOUBLE AS official_price_age_days",
                "NULL::DOUBLE AS official_price_source_year",
            ]
        )

    for col in SPREAD_LAG_FEATURES + PRICE_LAG_FEATURES + COUNT_LAG_FEATURES + ROLLING_FEATURES:
        exprs.append(f"CAST(t.{qid(col)} AS DOUBLE) AS {qid(col)}")

    exprs.extend(
        [
            "(CAST(t.spread_lag_1d AS DOUBLE) - CAST(t.spread_lag_7d AS DOUBLE)) AS spread_trend_1d_7d",
            "(CAST(t.spread_roll7_mean AS DOUBLE) - CAST(t.spread_roll28_mean AS DOUBLE)) AS spread_trend_roll7_roll28",
            "(CAST(t.actual_grid_price_lag_1d AS DOUBLE) - CAST(t.actual_grid_price_lag_7d AS DOUBLE)) AS actual_price_trend_1d_7d",
        ]
    )
    return exprs


def sample_predicate(per_mille: int, salt: str) -> str:
    per_mille = int(per_mille)
    if per_mille >= 1000:
        return "TRUE"
    if per_mille <= 0:
        raise ValueError("per_mille은 1~1000이어야 합니다.")
    return (
        "(hash(CAST(t.grid_id AS VARCHAR) || '|' || CAST(t.target_date AS VARCHAR) || '|' || "
        f"{qstr(salt)}) % 1000) < {per_mille}"
    )


def date_conditions(
    date_start: Optional[pd.Timestamp],
    date_end: Optional[pd.Timestamp],
    force_pre_2026: bool,
    exclude_policy_periods: bool = False,
) -> List[str]:
    conds: List[str] = []
    if date_start is not None:
        conds.append(f"t.target_date >= {sql_date(date_start)}")
    if date_end is not None:
        conds.append(f"t.target_date <= {sql_date(date_end)}")
    if force_pre_2026:
        conds.append(f"t.target_date < {sql_date(TEST_START)}")
    if exclude_policy_periods:
        conds.append(policy_exclusion_condition("t.target_date"))
    return conds


def estimate_rows(
    cfg: FuelConfig,
    date_start: Optional[pd.Timestamp] = None,
    date_end: Optional[pd.Timestamp] = None,
    force_pre_2026: bool = False,
    exclude_policy_periods: bool = False,
) -> int:
    conds = date_conditions(date_start, date_end, force_pre_2026, exclude_policy_periods)
    where_sql = " AND ".join(conds)
    return int(
        con.execute(
            f"""
            WITH raw AS (
                SELECT CAST(date AS DATE) AS date_key, *
                FROM {panel_sql()}
            ),
            target_rows AS (
                SELECT
                    date_key AS target_date,
                    date_key - INTERVAL {PREDICTION_HORIZON_DAYS} DAY AS feature_date,
                    grid_id
                FROM raw
                WHERE {qid(cfg.target_col)} IS NOT NULL
                  AND CAST({qid(cfg.station_count_col)} AS DOUBLE) > 0
            ),
            feature_rows AS (
                SELECT date_key, grid_id
                FROM raw
            )
            SELECT COUNT(*) AS n
            FROM target_rows t
            INNER JOIN feature_rows p
                ON p.grid_id = t.grid_id
               AND p.date_key = t.feature_date
            WHERE {where_sql if where_sql else "TRUE"}
            """
        ).fetchone()[0]
    )


def effective_per_mille(total_rows: int, requested_per_mille: int, max_rows: Optional[int]) -> int:
    if max_rows is None or max_rows <= 0:
        return min(int(requested_per_mille), 1000)
    if total_rows <= 0:
        return min(int(requested_per_mille), 1000)
    cap_per_mille = max(1, int(math.floor(max_rows * 1000 / total_rows)))
    return min(int(requested_per_mille), cap_per_mille, 1000)


def load_model_frame(
    cfg: FuelConfig,
    date_start: Optional[pd.Timestamp],
    date_end: Optional[pd.Timestamp],
    sample_per_mille: int,
    sample_salt: str,
    max_rows: Optional[int],
    force_pre_2026: bool,
    label: str,
    exclude_policy_periods: bool = False,
) -> pd.DataFrame:
    if exclude_policy_periods:
        raw_total_rows = estimate_rows(cfg, date_start, date_end, force_pre_2026, False)
        total_rows = estimate_rows(cfg, date_start, date_end, force_pre_2026, True)
        policy_excluded_rows = max(raw_total_rows - total_rows, 0)
    else:
        total_rows = estimate_rows(cfg, date_start, date_end, force_pre_2026, False)
        policy_excluded_rows = 0
    actual_per_mille = effective_per_mille(total_rows, sample_per_mille, max_rows)
    conds = date_conditions(date_start, date_end, force_pre_2026, exclude_policy_periods)
    conds.append(sample_predicate(actual_per_mille, sample_salt))
    where_sql = " AND ".join(conds) if conds else "TRUE"
    feature_exprs = ",\n            ".join(feature_sql_exprs())
    history_exprs = ",\n                ".join(history_sql_exprs())

    print(
        f"[LOAD] {cfg.label} {label}: eligible_total={total_rows:,}, "
        f"policy_excluded={policy_excluded_rows:,}, sample={actual_per_mille}/1000, max_rows={max_rows}"
    )

    df = con.execute(
        f"""
        WITH raw AS (
            SELECT
                CAST(date AS DATE) AS date_key,
                *
            FROM {panel_sql()}
        ),
        target_rows AS (
            SELECT
                date_key AS target_date,
                date_key - INTERVAL {PREDICTION_HORIZON_DAYS} DAY AS feature_date,
                grid_id,
                CAST({qid(cfg.target_col)} AS DOUBLE) AS actual_grid_price,
                CAST({qid(cfg.station_count_col)} AS DOUBLE) AS station_weight
            FROM raw
            WHERE {qid(cfg.target_col)} IS NOT NULL
              AND CAST({qid(cfg.station_count_col)} AS DOUBLE) > 0
        ),
        anchor AS (
            SELECT
                target_date,
                SUM(actual_grid_price * station_weight) / NULLIF(SUM(station_weight), 0) AS national_actual_price,
                SUM(station_weight) AS national_station_weight
            FROM target_rows
            GROUP BY target_date
        ),
        spread_all AS (
            SELECT
                t.target_date,
                t.feature_date,
                t.grid_id,
                t.actual_grid_price,
                t.station_weight,
                CAST(a.national_actual_price AS DOUBLE) AS national_actual_price,
                CAST(a.national_station_weight AS DOUBLE) AS national_station_weight,
                t.actual_grid_price - CAST(a.national_actual_price AS DOUBLE) AS spread_target
            FROM target_rows t
            INNER JOIN anchor a
                ON a.target_date = t.target_date
        ),
        history AS (
            SELECT
                s.*,
                {history_exprs}
            FROM spread_all s
        ),
        feature_rows AS (
            SELECT *
            FROM raw
        )
        SELECT
            t.target_date AS date,
            t.feature_date AS feature_date,
            t.grid_id,
            t.actual_grid_price,
            t.station_weight,
            t.national_actual_price,
            t.national_station_weight,
            t.spread_target,
            {feature_exprs}
        FROM history t
        INNER JOIN feature_rows p
            ON p.grid_id = t.grid_id
           AND p.date_key = t.feature_date
        WHERE {where_sql}
        """
    ).df()

    if max_rows and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=RANDOM_SEED).sort_values(["date", "grid_id"]).reset_index(drop=True)

    df["date"] = ensure_date(df["date"])
    df["feature_date"] = ensure_date(df["feature_date"])
    if force_pre_2026 and (df["date"] >= TEST_START).any():
        bad_min = df.loc[df["date"] >= TEST_START, "date"].min()
        raise AssertionError(f"{label}에 2026 test 행이 섞였습니다: {bad_min}")
    expected_delta = (df["date"] - df["feature_date"]).dt.days
    if len(df) and not expected_delta.eq(PREDICTION_HORIZON_DAYS).all():
        raise AssertionError("feature_date와 target_date의 horizon이 설정값과 다릅니다.")

    for col in MODEL_FEATURES + ["actual_grid_price", "station_weight", "national_actual_price", "spread_target"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    selected_pct = (len(df) / total_rows * 100.0) if total_rows else 0.0
    print(
        f"[LOAD DONE] {cfg.label} {label}: rows={len(df):,}/{total_rows:,} ({selected_pct:.2f}%), "
        f"target_date={df['date'].min().date() if len(df) else None}~{df['date'].max().date() if len(df) else None}"
    )
    return df


# %% [markdown] cell 10
# ## 4. 외부 전국 적정가격 파일(optional)
# 원문 코드처럼 `정책적용_v2` 또는 `적정가격대선정_v2` 파일이 있으면 test의 전국 기준가격으로 사용합니다.
# 없으면 `grid.parquet`에서 계산한 전국 실제 평균을 기준값으로 사용합니다.
# 

# %% cell 11


def find_column(columns: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    columns = list(columns)
    exact = {str(c).strip(): c for c in columns}
    lowered = {str(c).strip().lower(): c for c in columns}
    for cand in candidates:
        key = str(cand).strip()
        if key in exact:
            return exact[key]
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def load_external_fair_table(cfg: FuelConfig) -> Optional[pd.DataFrame]:
    candidates = [
        ROOT_DIR / "정책적용_v2" / cfg.policy_subdir / cfg.policy_file,
        ROOT_DIR / "적정가격대선정_v2" / cfg.step2_file,
        REPO_ROOT / "data-analysis" / "05_policy_application" / "outputs" / cfg.policy_subdir / cfg.policy_file,
        REPO_ROOT / "data-analysis" / "04_fair_price_model" / "outputs" / cfg.step2_file,
    ]
    source = first_existing(candidates)
    if source is None:
        print(f"[FAIR ANCHOR] {cfg.label}: 외부 전국 적정가격 파일 없음 -> panel 전국 평균 사용")
        return None

    raw = read_csv_flexible(source)
    date_col = find_column(raw.columns, ["date", "날짜", "일자", "기준일"])
    if date_col is None:
        print(f"[FAIR ANCHOR] {cfg.label}: 날짜 컬럼 없음({source}) -> panel 전국 평균 사용")
        return None

    center_col = find_column(
        raw.columns,
        [
            "적정가격_정책적용_원L",
            "national_fair_center",
            "pred_gross",
            "predicted_price",
            "fair_price",
            "center",
            "yhat",
        ],
    )
    lower_col = find_column(
        raw.columns,
        [
            "적정범위_정책적용_하한_원L",
            "national_fair_lower",
            "band_low",
            "pred_lower",
            "lower",
            "yhat_lower",
        ],
    )
    upper_col = find_column(
        raw.columns,
        [
            "적정범위_정책적용_상한_원L",
            "national_fair_upper",
            "band_high",
            "pred_upper",
            "upper",
            "yhat_upper",
        ],
    )
    if center_col is None:
        print(f"[FAIR ANCHOR] {cfg.label}: 적정가격 center 컬럼 없음({source}) -> panel 전국 평균 사용")
        return None

    keep = [date_col, center_col] + [c for c in [lower_col, upper_col] if c is not None]
    out = raw[keep].copy()
    rename = {date_col: "date", center_col: "national_fair_center"}
    if lower_col:
        rename[lower_col] = "national_fair_lower"
    if upper_col:
        rename[upper_col] = "national_fair_upper"
    out = out.rename(columns=rename)
    out["date"] = ensure_date(out["date"])
    for col in ["national_fair_center", "national_fair_lower", "national_fair_upper"]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["date", "national_fair_center"]).drop_duplicates("date").sort_values("date")
    print(f"[FAIR ANCHOR] {cfg.label}: {source} rows={len(out):,}")
    return out


def attach_fair_anchor_for_prediction(df: pd.DataFrame, fair_table: Optional[pd.DataFrame]) -> pd.DataFrame:
    out = df.copy()
    out["date"] = ensure_date(out["date"])
    if fair_table is not None and len(fair_table):
        out = out.merge(fair_table, on="date", how="left")
    else:
        out["national_fair_center"] = np.nan
        out["national_fair_lower"] = np.nan
        out["national_fair_upper"] = np.nan

    out["national_fair_center"] = pd.to_numeric(out["national_fair_center"], errors="coerce")
    out["national_fair_lower"] = pd.to_numeric(out["national_fair_lower"], errors="coerce")
    out["national_fair_upper"] = pd.to_numeric(out["national_fair_upper"], errors="coerce")
    out["national_fair_center"] = out["national_fair_center"].fillna(out["national_actual_price"])

    # 모델은 학습 때 national_actual_price를 anchor feature로 봤고,
    # test fair-price 예측 때는 외부 national_fair_center가 있으면 그 값을 넣습니다.
    out["national_price_anchor"] = out["national_fair_center"]
    return out


# %% [markdown] cell 12
# ## 5. LightGBM 학습/검증 함수
# 

# %% cell 13
LGBM_PARAM_CANDIDATES: List[Dict[str, Any]] = [
    {
        "learning_rate": 0.045,
        "num_leaves": 127,
        "min_child_samples": 80,
        "subsample": 0.90,
        "colsample_bytree": 0.90,
        "reg_alpha": 0.05,
        "reg_lambda": 0.40,
        "n_estimators": 3500,
    },
    {
        "learning_rate": 0.035,
        "num_leaves": 255,
        "min_child_samples": 120,
        "subsample": 0.88,
        "colsample_bytree": 0.85,
        "reg_alpha": 0.10,
        "reg_lambda": 0.70,
        "n_estimators": 4500,
    },
    {
        "learning_rate": 0.030,
        "num_leaves": 511,
        "min_child_samples": 180,
        "subsample": 0.85,
        "colsample_bytree": 0.82,
        "reg_alpha": 0.20,
        "reg_lambda": 1.00,
        "n_estimators": 5500,
    },
]

EARLY_STOPPING_ROUNDS = 150


def make_lgbm_params(candidate: Dict[str, Any], device_type: str) -> Dict[str, Any]:
    params = {
        "objective": "regression",
        "metric": "l1",
        "boosting_type": "gbdt",
        "random_state": RANDOM_SEED,
        "n_jobs": -1,
        "verbosity": -1,
        "max_bin": 255,
        **candidate,
    }
    if device_type == "gpu":
        params["device_type"] = "gpu"
        params["gpu_use_dp"] = False
    else:
        params["device_type"] = "cpu"
    return params


def fit_lgbm_with_fallback(
    params: Dict[str, Any],
    train_df: pd.DataFrame,
    valid_df: Optional[pd.DataFrame],
    features: List[str],
    label: str,
) -> Tuple[lgb.LGBMRegressor, str]:
    X_tr = train_df[features]
    y_tr = train_df["spread_target"]
    w_tr = train_df["station_weight"].clip(lower=1)

    devices = ["gpu", "cpu"] if USE_LGBM_GPU else ["cpu"]
    last_error: Optional[Exception] = None
    for device in devices:
        model = lgb.LGBMRegressor(**make_lgbm_params(params, device))
        try:
            if valid_df is not None and len(valid_df):
                X_va = valid_df[features]
                y_va = valid_df["spread_target"]
                w_va = valid_df["station_weight"].clip(lower=1)
                model.fit(
                    X_tr,
                    y_tr,
                    sample_weight=w_tr,
                    eval_set=[(X_va, y_va)],
                    eval_sample_weight=[w_va],
                    callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS), lgb.log_evaluation(100)],
                )
            else:
                model.fit(X_tr, y_tr, sample_weight=w_tr)
            print(f"[MODEL] {label}: trained with device={device}")
            return model, device
        except Exception as exc:
            last_error = exc
            print(f"[WARN] {label}: LightGBM device={device} failed: {type(exc).__name__}: {exc}")
            if device == "cpu":
                raise
    raise RuntimeError(f"LightGBM 학습 실패: {last_error}")


def predict_spread(model: lgb.LGBMRegressor, df: pd.DataFrame, features: List[str]) -> np.ndarray:
    best_iter = getattr(model, "best_iteration_", None)
    if best_iter and best_iter > 0:
        return model.predict(df[features], num_iteration=best_iter)
    return model.predict(df[features])


def evaluate_prediction_frame(df: pd.DataFrame, period: str) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "period": period,
        "rows": int(len(df)),
        "date_min": str(df["date"].min().date()) if len(df) else None,
        "date_max": str(df["date"].max().date()) if len(df) else None,
        "station_weight_sum": float(df["station_weight"].sum()) if len(df) else 0.0,
    }
    row.update(regression_metric_row(df["actual_grid_price"], df["pred_grid_price"], df["station_weight"], "price"))
    row.update(regression_metric_row(df["spread_target"], df["pred_spread"], df["station_weight"], "spread"))
    return row


def evaluate_baselines(train_df: pd.DataFrame, valid_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    zero = valid_df[["date", "station_weight", "national_actual_price", "actual_grid_price", "spread_target"]].copy()
    zero["pred_spread"] = 0.0
    zero["pred_grid_price"] = zero["national_actual_price"]
    rows.append({"model_name": "baseline_national_anchor", **evaluate_prediction_frame(zero, "validation")})

    grid_mean = train_df.groupby("grid_id")["spread_target"].mean()
    global_mean = float(train_df["spread_target"].mean())
    gm = valid_df[["date", "grid_id", "station_weight", "national_actual_price", "actual_grid_price", "spread_target"]].copy()
    gm["pred_spread_raw"] = gm["grid_id"].map(grid_mean).fillna(global_mean)
    gm["pred_spread"] = recenter_spread_by_date(gm, "pred_spread_raw", "station_weight")
    gm["pred_grid_price"] = gm["national_actual_price"] + gm["pred_spread"]
    rows.append({"model_name": "baseline_grid_mean_spread", **evaluate_prediction_frame(gm, "validation")})

    return pd.DataFrame(rows)


def evaluate_lgbm_candidate(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    features: List[str],
    params: Dict[str, Any],
    candidate_id: int,
) -> Tuple[pd.DataFrame, lgb.LGBMRegressor, str]:
    label = f"candidate_{candidate_id}"
    start = time.time()
    model, device = fit_lgbm_with_fallback(params, train_df, valid_df, features, label)

    pred = valid_df[["date", "station_weight", "national_actual_price", "actual_grid_price", "spread_target"]].copy()
    pred["pred_spread_raw"] = predict_spread(model, valid_df, features)
    pred["pred_spread"] = recenter_spread_by_date(pred, "pred_spread_raw", "station_weight")
    pred["pred_grid_price"] = pred["national_actual_price"] + pred["pred_spread"]

    row = {
        "model_name": f"lgbm_{label}",
        "device": device,
        "best_iteration": int(getattr(model, "best_iteration_", 0) or 0),
        "fit_seconds": round(time.time() - start, 2),
        "params_json": json.dumps(params, ensure_ascii=False, sort_keys=True),
        **evaluate_prediction_frame(pred, "validation"),
    }
    return pd.DataFrame([row]), model, device


def compute_feature_importance(model: lgb.LGBMRegressor, features: List[str]) -> pd.DataFrame:
    booster = model.booster_
    return (
        pd.DataFrame(
            {
                "feature": features,
                "importance_gain": booster.feature_importance(importance_type="gain"),
                "importance_split": booster.feature_importance(importance_type="split"),
            }
        )
        .sort_values(["importance_gain", "importance_split"], ascending=[False, False])
        .reset_index(drop=True)
    )



# %% [markdown] cell 14
# ## 6. 선택형 딥러닝 후보 모델
# 다음날 예측에는 최근 흐름을 보전하는 입력이 필요합니다.
# 이 후보 모델은 최근 28일 spread sequence를 두 채널(`value`, `observed_mask`)로 넣고,
# temporal CNN, LSTM, static MLP를 결합합니다.
# - temporal CNN: 최근 며칠의 국소 패턴과 급변을 포착합니다.
# - LSTM: 28일 lookback의 순서 정보를 보전합니다.
# - static MLP: 격자 좌표, 시설/주유소 영향, 전국 anchor, rolling feature를 함께 사용합니다.
# - 결측: sequence 값은 0으로 채우되 mask 채널을 별도 제공하고, static feature는 train median으로 대체합니다.
# 

# %% cell 15

SEQUENCE_VALUE_COLUMNS = [f"spread_lag_{d}d" for d in range(SEQUENCE_LENGTH_DAYS, 0, -1)]
SEQUENCE_STATIC_FEATURES = [c for c in MODEL_FEATURES if c not in set(SPREAD_LAG_FEATURES)]


def _sample_sequence_frame(df: pd.DataFrame, max_rows: int, salt: str) -> pd.DataFrame:
    if max_rows and len(df) > max_rows:
        return df.sample(n=max_rows, random_state=abs(hash(salt)) % (2**32)).sort_values(["date", "grid_id"]).reset_index(drop=True)
    return df.reset_index(drop=True)


def _fit_sequence_preprocess(train_df: pd.DataFrame, static_features: List[str]) -> Dict[str, Any]:
    seq_raw = train_df[SEQUENCE_VALUE_COLUMNS].apply(pd.to_numeric, errors="coerce").to_numpy(dtype="float32")
    seq_mean = float(np.nanmean(seq_raw)) if np.isfinite(seq_raw).any() else 0.0
    seq_std = float(np.nanstd(seq_raw)) if np.isfinite(seq_raw).any() else 1.0
    if not np.isfinite(seq_std) or seq_std < 1e-6:
        seq_std = 1.0

    static = train_df[static_features].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    static_median = static.median(numeric_only=True).fillna(0.0)
    static_filled = static.fillna(static_median)
    static_mean = static_filled.mean(numeric_only=True).fillna(0.0)
    static_std = static_filled.std(numeric_only=True).replace(0, 1.0).fillna(1.0)

    y = pd.to_numeric(train_df["spread_target"], errors="coerce").to_numpy(dtype="float32")
    y_mean = float(np.nanmean(y)) if np.isfinite(y).any() else 0.0
    y_std = float(np.nanstd(y)) if np.isfinite(y).any() else 1.0
    if not np.isfinite(y_std) or y_std < 1e-6:
        y_std = 1.0

    return {
        "sequence_value_columns": SEQUENCE_VALUE_COLUMNS,
        "static_features": static_features,
        "seq_mean": seq_mean,
        "seq_std": seq_std,
        "static_median": static_median.to_dict(),
        "static_mean": static_mean.to_dict(),
        "static_std": static_std.to_dict(),
        "y_mean": y_mean,
        "y_std": y_std,
    }


def _sequence_arrays(
    df: pd.DataFrame,
    prep: Dict[str, Any],
    include_target: bool,
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
    seq_cols = prep["sequence_value_columns"]
    static_features = prep["static_features"]

    seq_raw = df[seq_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype="float32")
    seq_mask = np.isfinite(seq_raw).astype("float32")
    seq_scaled = (seq_raw - float(prep["seq_mean"])) / float(prep["seq_std"])
    seq_scaled = np.where(np.isfinite(seq_scaled), seq_scaled, 0.0).astype("float32")
    seq = np.stack([seq_scaled, seq_mask], axis=-1)

    static = df[static_features].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    med = pd.Series(prep["static_median"], dtype="float64")
    mean = pd.Series(prep["static_mean"], dtype="float64")
    std = pd.Series(prep["static_std"], dtype="float64").replace(0, 1.0)
    static = static.fillna(med)
    static = ((static - mean) / std).replace([np.inf, -np.inf], 0).fillna(0.0)
    static_arr = static.to_numpy(dtype="float32")

    y_arr: Optional[np.ndarray] = None
    w_arr: Optional[np.ndarray] = None
    if include_target:
        y = pd.to_numeric(df["spread_target"], errors="coerce").to_numpy(dtype="float32")
        y_arr = ((y - float(prep["y_mean"])) / float(prep["y_std"])).astype("float32")
        w = pd.to_numeric(df["station_weight"], errors="coerce").fillna(0).clip(lower=0).to_numpy(dtype="float32")
        w_mean = float(np.nanmean(w[w > 0])) if np.any(w > 0) else 1.0
        w_arr = np.where(np.isfinite(w) & (w > 0), w / w_mean, 0.0).astype("float32")

    return seq, static_arr, y_arr, w_arr


def _make_torch_sequence_model(
    input_channels: int,
    static_dim: int,
    seq_to_y_scale: float,
    seq_to_y_shift: float,
):
    import torch
    import torch.nn as nn

    class HybridSequenceRegressor(nn.Module):
        def __init__(self, input_channels: int, static_dim: int, seq_to_y_scale: float, seq_to_y_shift: float):
            super().__init__()
            self.register_buffer("seq_to_y_scale", torch.tensor(float(seq_to_y_scale), dtype=torch.float32))
            self.register_buffer("seq_to_y_shift", torch.tensor(float(seq_to_y_shift), dtype=torch.float32))
            self.temporal_cnn = nn.Sequential(
                nn.Conv1d(input_channels, 48, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.Dropout(0.10),
                nn.Conv1d(48, 64, kernel_size=5, padding=2),
                nn.ReLU(),
                nn.AdaptiveAvgPool1d(1),
            )
            self.lstm = nn.LSTM(
                input_size=input_channels,
                hidden_size=64,
                num_layers=2,
                dropout=0.15,
                batch_first=True,
                bidirectional=True,
            )
            self.static_net = nn.Sequential(
                nn.Linear(static_dim, 128),
                nn.LayerNorm(128),
                nn.ReLU(),
                nn.Dropout(0.15),
                nn.Linear(128, 64),
                nn.ReLU(),
            )
            self.head = nn.Sequential(
                nn.Linear(64 + 128 + 64, 128),
                nn.ReLU(),
                nn.Dropout(0.15),
                nn.Linear(128, 1),
            )

        def forward(self, seq, static):
            cnn_x = seq.transpose(1, 2)
            cnn_out = self.temporal_cnn(cnn_x).squeeze(-1)
            _, (h_n, _) = self.lstm(seq)
            lstm_out = torch.cat([h_n[-2], h_n[-1]], dim=1)
            static_out = self.static_net(static)
            residual = self.head(torch.cat([cnn_out, lstm_out, static_out], dim=1)).squeeze(1)
            if not SEQUENCE_RESIDUAL_FROM_LAG1:
                return residual
            lag1_value = seq[:, -1, 0]
            lag1_mask = seq[:, -1, 1]
            base = lag1_value * self.seq_to_y_scale + self.seq_to_y_shift
            base = base * lag1_mask
            return base + residual

    return HybridSequenceRegressor(
        input_channels=input_channels,
        static_dim=static_dim,
        seq_to_y_scale=seq_to_y_scale,
        seq_to_y_shift=seq_to_y_shift,
    )


def _predict_sequence_wrapper(wrapper: Dict[str, Any], df: pd.DataFrame) -> np.ndarray:
    import torch
    from torch.utils.data import DataLoader, TensorDataset

    model = wrapper["model"]
    prep = wrapper["preprocess"]
    device = wrapper["device"]

    seq, static, _, _ = _sequence_arrays(df, prep, include_target=False)
    ds = TensorDataset(torch.from_numpy(seq), torch.from_numpy(static))
    loader = DataLoader(ds, batch_size=SEQUENCE_MODEL_BATCH_SIZE, shuffle=False)

    preds: List[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for xb_seq, xb_static in loader:
            raw = model(xb_seq.to(device), xb_static.to(device)).detach().cpu().numpy()
            preds.append(raw)
    scaled = np.concatenate(preds) if preds else np.array([], dtype="float32")
    return scaled * float(prep["y_std"]) + float(prep["y_mean"])


def train_sequence_candidate(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    cfg: FuelConfig,
    out_dir: Path,
    tag: str,
    reference_wmae: Optional[float] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[pd.DataFrame]]:
    if not RUN_SEQUENCE_MODEL:
        return None, None

    try:
        import torch
        import torch.nn.functional as F
        from torch.utils.data import DataLoader, TensorDataset
    except Exception as exc:
        print(f"[SEQUENCE] PyTorch 사용 불가 -> sequence 후보 skip: {type(exc).__name__}: {exc}")
        return None, None

    start = time.time()
    train_seq_df = _sample_sequence_frame(train_df, SEQUENCE_MODEL_MAX_TRAIN_ROWS, f"{cfg.fuel}_{tag}_seq_train")
    valid_seq_df = _sample_sequence_frame(valid_df, SEQUENCE_MODEL_MAX_VALID_ROWS, f"{cfg.fuel}_{tag}_seq_valid")

    prep = _fit_sequence_preprocess(train_seq_df, SEQUENCE_STATIC_FEATURES)
    x_seq, x_static, y, w = _sequence_arrays(train_seq_df, prep, include_target=True)

    device = "cuda" if (USE_GPU and torch.cuda.is_available()) else "cpu"
    seq_to_y_scale = float(prep["seq_std"]) / float(prep["y_std"])
    seq_to_y_shift = (float(prep["seq_mean"]) - float(prep["y_mean"])) / float(prep["y_std"])
    model = _make_torch_sequence_model(
        input_channels=x_seq.shape[-1],
        static_dim=x_static.shape[1],
        seq_to_y_scale=seq_to_y_scale,
        seq_to_y_shift=seq_to_y_shift,
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=SEQUENCE_MODEL_LR,
        weight_decay=SEQUENCE_MODEL_WEIGHT_DECAY,
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="min",
        factor=SEQUENCE_LR_REDUCE_FACTOR,
        patience=SEQUENCE_LR_PATIENCE,
        min_lr=SEQUENCE_MIN_LR,
    )

    ds = TensorDataset(
        torch.from_numpy(x_seq),
        torch.from_numpy(x_static),
        torch.from_numpy(y),
        torch.from_numpy(w),
    )
    loader = DataLoader(ds, batch_size=SEQUENCE_MODEL_BATCH_SIZE, shuffle=True, num_workers=0, pin_memory=(device == "cuda"))

    best_state = None
    best_mae = float("inf")
    patience_left = SEQUENCE_EARLY_STOPPING_PATIENCE
    history_rows: List[Dict[str, Any]] = []

    reference_text = f", reference_wmae={reference_wmae:.4f}" if reference_wmae is not None else ""
    print(
        f"[SEQUENCE] {cfg.label} {tag}: train={len(train_seq_df):,}, valid={len(valid_seq_df):,}, "
        f"device={device}, static_dim={x_static.shape[1]}, seq_len={x_seq.shape[1]}, "
        f"max_epochs={SEQUENCE_MODEL_EPOCHS}, early_stop_patience={SEQUENCE_EARLY_STOPPING_PATIENCE}, "
        f"lr_patience={SEQUENCE_LR_PATIENCE}, residual_from_lag1={SEQUENCE_RESIDUAL_FROM_LAG1}"
        f"{reference_text}"
    )

    for epoch in range(1, SEQUENCE_MODEL_EPOCHS + 1):
        epoch_start = time.time()
        model.train()
        train_loss_sum = 0.0
        train_weight_sum = 0.0
        for xb_seq, xb_static, yb, wb in loader:
            xb_seq = xb_seq.to(device)
            xb_static = xb_static.to(device)
            yb = yb.to(device)
            wb = wb.to(device).clip(min=0)

            optimizer.zero_grad(set_to_none=True)
            pred = model(xb_seq, xb_static)
            loss_vec = F.smooth_l1_loss(pred, yb, reduction="none")
            denom = wb.sum().clamp(min=1.0)
            loss = (loss_vec * wb).sum() / denom
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), SEQUENCE_GRAD_CLIP_NORM)
            optimizer.step()

            train_loss_sum += float((loss_vec.detach() * wb).sum().cpu())
            train_weight_sum += float(denom.detach().cpu())

        wrapper = {"model": model, "preprocess": prep, "device": device}
        valid_pred = valid_seq_df[["date", "station_weight", "national_actual_price", "actual_grid_price", "spread_target"]].copy()
        valid_pred["pred_spread_raw"] = _predict_sequence_wrapper(wrapper, valid_seq_df)
        valid_pred["pred_spread"] = recenter_spread_by_date(valid_pred, "pred_spread_raw", "station_weight")
        valid_pred["pred_grid_price"] = valid_pred["national_actual_price"] + valid_pred["pred_spread"]
        metrics = evaluate_prediction_frame(valid_pred, f"validation_{tag}_epoch_{epoch}")
        valid_mae = float(metrics["price_weighted_mae"])
        scheduler.step(valid_mae)
        current_lr = float(optimizer.param_groups[0]["lr"])

        row = {
            "model_name": f"hybrid_tcnn_lstm_{tag}",
            "epoch": epoch,
            "device": device,
            "learning_rate": current_lr,
            "reference_weighted_mae": reference_wmae,
            "train_weighted_huber_scaled": train_loss_sum / max(train_weight_sum, 1.0),
            "epoch_seconds": round(time.time() - epoch_start, 2),
            "fit_seconds": round(time.time() - start, 2),
            **metrics,
        }
        history_rows.append(row)

        stop_reason = None
        if valid_mae < best_mae - SEQUENCE_EARLY_STOPPING_MIN_DELTA:
            best_mae = valid_mae
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            patience_left = SEQUENCE_EARLY_STOPPING_PATIENCE
        else:
            patience_left -= 1
            if patience_left <= 0:
                stop_reason = (
                    f"no validation MAE improvement >= {SEQUENCE_EARLY_STOPPING_MIN_DELTA} "
                    f"for {SEQUENCE_EARLY_STOPPING_PATIENCE} epochs"
                )

        row["best_validation_weighted_mae_so_far"] = best_mae
        print(
            f"[SEQUENCE] epoch={epoch:02d}, train_loss={row['train_weighted_huber_scaled']:.5f}, "
            f"valid_wmae={valid_mae:.4f}, best={best_mae:.4f}, lr={current_lr:.6g}, "
            f"epoch_sec={row['epoch_seconds']:.2f}, total_min={row['fit_seconds'] / 60:.1f}, "
            f"patience_left={patience_left}"
        )

        if (
            stop_reason is None
            and reference_wmae is not None
            and np.isfinite(reference_wmae)
            and epoch >= SEQUENCE_MIN_EPOCHS_BEFORE_REFERENCE_ABORT
            and best_mae > reference_wmae * SEQUENCE_ABORT_WORSE_THAN_REFERENCE_RATIO
        ):
            stop_reason = (
                f"best sequence WMAE {best_mae:.4f} is still worse than reference "
                f"{reference_wmae:.4f} * {SEQUENCE_ABORT_WORSE_THAN_REFERENCE_RATIO:.2f}"
            )

        if stop_reason is not None:
            print(f"[SEQUENCE] early stop: {stop_reason}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    wrapper = {
        "kind": "sequence",
        "model": model,
        "preprocess": prep,
        "device": device,
        "best_validation_weighted_mae": best_mae,
        "reference_weighted_mae": reference_wmae,
        "architecture": "lag1_residual + temporal_cnn + bidirectional_lstm + static_mlp",
    }

    score_df = pd.DataFrame(history_rows)
    score_path = out_dir / f"{cfg.fuel}_sequence_{tag}_scores.csv"
    score_df.to_csv(score_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {score_path}")

    state_path = out_dir / "model" / f"{cfg.fuel}_sequence_{tag}_state.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "preprocess": prep,
            "architecture": wrapper["architecture"],
            "sequence_residual_from_lag1": SEQUENCE_RESIDUAL_FROM_LAG1,
            "input_channels": x_seq.shape[-1],
            "static_dim": x_static.shape[1],
        },
        state_path,
    )
    print(f"[SAVE] {state_path}")
    wrapper["state_path"] = str(state_path)
    wrapper["score_path"] = str(score_path)

    return wrapper, score_df


def predict_spread_from_selected_model(selected_model: Dict[str, Any], df: pd.DataFrame, features: List[str]) -> np.ndarray:
    if selected_model["kind"] == "sequence":
        return _predict_sequence_wrapper(selected_model["sequence_wrapper"], df)
    return predict_spread(selected_model["lgbm_model"], df, features)


# %% [markdown] cell 16
# ## 6. 유종별 학습, 2026 test 예측
# 

# %% cell 17


def eligible_daily_counts(cfg: FuelConfig) -> pd.DataFrame:
    conds = date_conditions(
        date_start=None,
        date_end=TEST_START - pd.Timedelta(days=1),
        force_pre_2026=True,
        exclude_policy_periods=EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID,
    )
    where_sql = " AND ".join(conds) if conds else "TRUE"
    daily = con.execute(
        f"""
        WITH raw AS (
            SELECT CAST(date AS DATE) AS date_key, *
            FROM {panel_sql()}
        ),
        target_rows AS (
            SELECT
                date_key AS target_date,
                date_key - INTERVAL {PREDICTION_HORIZON_DAYS} DAY AS feature_date,
                grid_id
            FROM raw
            WHERE {qid(cfg.target_col)} IS NOT NULL
              AND CAST({qid(cfg.station_count_col)} AS DOUBLE) > 0
        ),
        feature_rows AS (
            SELECT date_key, grid_id
            FROM raw
        )
        SELECT
            t.target_date AS date,
            COUNT(*) AS eligible_rows
        FROM target_rows t
        INNER JOIN feature_rows p
            ON p.grid_id = t.grid_id
           AND p.date_key = t.feature_date
        WHERE {where_sql}
        GROUP BY t.target_date
        ORDER BY t.target_date
        """
    ).df()
    if len(daily) == 0:
        raise RuntimeError(f"{cfg.label}: 정책기간 제외 후 train/validation 후보 날짜가 없습니다.")
    daily["date"] = ensure_date(daily["date"])
    daily["eligible_rows"] = pd.to_numeric(daily["eligible_rows"], errors="coerce").fillna(0).astype("int64")
    daily["cum_rows"] = daily["eligible_rows"].cumsum()
    return daily


def train_validation_split(cfg: FuelConfig) -> Dict[str, Any]:
    daily = eligible_daily_counts(cfg)
    total_rows = int(daily["eligible_rows"].sum())
    target_train_rows = max(1, int(math.floor(total_rows * TRAIN_VALID_TRAIN_RATIO)))
    split_idx = int(np.searchsorted(daily["cum_rows"].to_numpy(), target_train_rows, side="left"))
    split_idx = min(max(split_idx, 0), len(daily) - 1)
    train_end = pd.Timestamp(daily.iloc[split_idx]["date"])
    valid_start = train_end + pd.Timedelta(days=GAP_DAYS + 1)
    valid_end = TEST_START - pd.Timedelta(days=1)

    train_mask = daily["date"] <= train_end
    valid_mask = daily["date"] >= valid_start
    train_rows = int(daily.loc[train_mask, "eligible_rows"].sum())
    valid_rows = int(daily.loc[valid_mask, "eligible_rows"].sum())
    gap_rows = int(daily.loc[(daily["date"] > train_end) & (daily["date"] < valid_start), "eligible_rows"].sum())
    if train_rows == 0 or valid_rows == 0:
        raise RuntimeError(
            f"{cfg.label}: 7:3 split 생성 실패(train={train_rows:,}, validation={valid_rows:,}). "
            "정책기간 제외 범위 또는 ratio를 확인하세요."
        )

    train_dates = daily.loc[train_mask, "date"]
    valid_dates = daily.loc[valid_mask, "date"]
    usable_rows = train_rows + valid_rows
    return {
        "requested_train_ratio": TRAIN_VALID_TRAIN_RATIO,
        "actual_train_ratio_after_gap": train_rows / usable_rows if usable_rows else float("nan"),
        "actual_valid_ratio_after_gap": valid_rows / usable_rows if usable_rows else float("nan"),
        "train_end": train_end,
        "valid_start": valid_start,
        "valid_end": valid_end,
        "train_eligible_date_min": pd.Timestamp(train_dates.min()),
        "train_eligible_date_max": pd.Timestamp(train_dates.max()),
        "valid_eligible_date_min": pd.Timestamp(valid_dates.min()),
        "valid_eligible_date_max": pd.Timestamp(valid_dates.max()),
        "train_eligible_days": int(train_mask.sum()),
        "valid_eligible_days": int(valid_mask.sum()),
        "train_eligible_rows_full": train_rows,
        "valid_eligible_rows_full": valid_rows,
        "gap_eligible_rows": gap_rows,
        "eligible_rows_full": total_rows,
        "policy_exclusion_enabled": EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID,
    }


def month_ranges(start: pd.Timestamp, end: pd.Timestamp) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    ranges: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    cur = pd.Timestamp(start).replace(day=1)
    end = pd.Timestamp(end)
    while cur <= end:
        month_end = cur + pd.offsets.MonthEnd(0)
        ranges.append((max(cur, start), min(month_end, end)))
        cur = month_end + pd.Timedelta(days=1)
    return ranges


def get_test_date_range(cfg: FuelConfig) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    row = con.execute(
        f"""
        SELECT
            MIN(CAST(date AS DATE)) AS date_min,
            MAX(CAST(date AS DATE)) AS date_max
        FROM {panel_sql()}
        WHERE CAST(date AS DATE) >= {sql_date(TEST_START)}
          AND {qid(cfg.target_col)} IS NOT NULL
          AND CAST({qid(cfg.station_count_col)} AS DOUBLE) > 0
        """
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return pd.Timestamp(row[0]), pd.Timestamp(row[1])


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def write_combined_prediction_outputs(out_dir: Path, cfg: FuelConfig, parts: List[Path]) -> None:
    if not parts:
        return
    parts_sql = "[" + ", ".join(qstr(p) for p in parts) + "]"
    prediction_path = out_dir / f"{cfg.fuel}_test_predictions_2026.parquet"
    daily_path = out_dir / f"{cfg.fuel}_test_daily_summary_2026.csv"
    grid_path = out_dir / f"{cfg.fuel}_test_grid_summary_2026.csv"

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM read_parquet({parts_sql})
            ORDER BY date, grid_id
        ) TO {qstr(prediction_path)} (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

    con.execute(
        f"""
        COPY (
            SELECT
                date,
                COUNT(*) AS grid_rows,
                SUM(station_weight) AS station_weight_sum,
                AVG(actual_grid_price) AS actual_grid_price_mean_unweighted,
                SUM(actual_grid_price * station_weight) / NULLIF(SUM(station_weight), 0) AS actual_grid_price_mean_weighted,
                AVG(predicted_grid_fair_price) AS predicted_grid_fair_price_mean_unweighted,
                SUM(predicted_grid_fair_price * station_weight) / NULLIF(SUM(station_weight), 0) AS predicted_grid_fair_price_mean_weighted,
                AVG(predicted_spread) AS predicted_spread_mean_unweighted,
                SUM(predicted_spread * station_weight) / NULLIF(SUM(station_weight), 0) AS predicted_spread_mean_weighted,
                AVG(prediction_error_to_actual) AS error_mean_unweighted,
                SUM(prediction_error_to_actual * station_weight) / NULLIF(SUM(station_weight), 0) AS error_mean_weighted,
                SUM(ABS(prediction_error_to_actual) * station_weight) / NULLIF(SUM(station_weight), 0) AS weighted_mae_to_actual
            FROM read_parquet({parts_sql})
            GROUP BY date
            ORDER BY date
        ) TO {qstr(daily_path)} (HEADER, DELIMITER ',')
        """
    )

    con.execute(
        f"""
        COPY (
            SELECT
                grid_id,
                ANY_VALUE(cell_x) AS cell_x,
                ANY_VALUE(cell_y) AS cell_y,
                ANY_VALUE(center_lon) AS center_lon,
                ANY_VALUE(center_lat) AS center_lat,
                COUNT(*) AS days,
                AVG(actual_grid_price) AS actual_grid_price_mean,
                AVG(predicted_grid_fair_price) AS predicted_grid_fair_price_mean,
                AVG(prediction_error_to_actual) AS error_mean,
                AVG(ABS(prediction_error_to_actual)) AS mae_to_actual
            FROM read_parquet({parts_sql})
            GROUP BY grid_id
            ORDER BY mae_to_actual DESC
        ) TO {qstr(grid_path)} (HEADER, DELIMITER ',')
        """
    )

    print(f"[SAVE] {prediction_path}")
    print(f"[SAVE] {daily_path}")
    print(f"[SAVE] {grid_path}")


def predict_test_2026(
    cfg: FuelConfig,
    selected_model: Dict[str, Any],
    features: List[str],
    out_dir: Path,
    fair_table: Optional[pd.DataFrame],
) -> pd.DataFrame:
    test_range = get_test_date_range(cfg)
    if test_range is None:
        print(f"[TEST] {cfg.label}: 2026 test rows 없음")
        return pd.DataFrame()

    test_start, test_end = test_range
    parts_dir = out_dir / "test_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    parts: List[Path] = []
    metric_rows: List[Dict[str, Any]] = []

    for m_start, m_end in month_ranges(test_start, test_end):
        chunk = load_model_frame(
            cfg=cfg,
            date_start=m_start,
            date_end=m_end,
            sample_per_mille=1000,
            sample_salt=f"{cfg.fuel}_test_full",
            max_rows=None,
            force_pre_2026=False,
            label=f"test_{m_start:%Y_%m}",
        )
        if len(chunk) == 0:
            continue
        if (chunk["date"] < TEST_START).any():
            raise AssertionError("test chunk에 2025년 이전 행이 섞였습니다.")

        chunk = attach_fair_anchor_for_prediction(chunk, fair_table)
        chunk["predicted_spread_raw"] = predict_spread_from_selected_model(selected_model, chunk, features)
        chunk["predicted_spread"] = recenter_spread_by_date(chunk, "predicted_spread_raw", "station_weight")
        chunk["predicted_grid_fair_price"] = chunk["national_fair_center"] + chunk["predicted_spread"]
        chunk["predicted_grid_fair_lower"] = chunk["national_fair_lower"] + chunk["predicted_spread"]
        chunk["predicted_grid_fair_upper"] = chunk["national_fair_upper"] + chunk["predicted_spread"]
        chunk["prediction_error_to_actual"] = chunk["predicted_grid_fair_price"] - chunk["actual_grid_price"]
        chunk["pred_spread"] = chunk["predicted_spread"]
        chunk["pred_grid_price"] = chunk["predicted_grid_fair_price"]

        metric_rows.append(evaluate_prediction_frame(chunk, f"test_{m_start:%Y_%m}"))

        save_cols = [
            "date",
            "feature_date",
            "grid_id",
            "cell_x",
            "cell_y",
            "center_lon",
            "center_lat",
            "station_weight",
            "actual_grid_price",
            "national_actual_price",
            "national_fair_center",
            "national_fair_lower",
            "national_fair_upper",
            "spread_target",
            "predicted_spread_raw",
            "predicted_spread",
            "predicted_grid_fair_price",
            "predicted_grid_fair_lower",
            "predicted_grid_fair_upper",
            "prediction_error_to_actual",
        ]
        chunk["selected_model_kind"] = selected_model["kind"]
        save_cols.append("selected_model_kind")
        save_cols = [c for c in save_cols if c in chunk.columns]
        part_path = parts_dir / f"{cfg.fuel}_test_predictions_2026_{m_start:%Y_%m}.parquet"
        chunk[save_cols].to_parquet(part_path, index=False, compression="zstd")
        parts.append(part_path)
        print(f"[SAVE PART] {part_path} rows={len(chunk):,}")

        del chunk
        gc.collect()

    write_combined_prediction_outputs(out_dir, cfg, parts)

    metrics = pd.DataFrame(metric_rows)
    if len(metrics):
        all_test = con.execute(
            f"""
            SELECT
                'test_2026_all' AS period,
                COUNT(*) AS rows,
                MIN(date) AS date_min,
                MAX(date) AS date_max,
                SUM(station_weight) AS station_weight_sum,
                AVG(ABS(prediction_error_to_actual)) AS price_mae,
                SQRT(AVG(POWER(prediction_error_to_actual, 2))) AS price_rmse,
                SUM(ABS(prediction_error_to_actual) * station_weight) / NULLIF(SUM(station_weight), 0) AS price_weighted_mae,
                SQRT(SUM(POWER(prediction_error_to_actual, 2) * station_weight) / NULLIF(SUM(station_weight), 0)) AS price_weighted_rmse,
                AVG(ABS(spread_target - predicted_spread)) AS spread_mae,
                SQRT(AVG(POWER(spread_target - predicted_spread, 2))) AS spread_rmse,
                SUM(ABS(spread_target - predicted_spread) * station_weight) / NULLIF(SUM(station_weight), 0) AS spread_weighted_mae,
                SQRT(SUM(POWER(spread_target - predicted_spread, 2) * station_weight) / NULLIF(SUM(station_weight), 0)) AS spread_weighted_rmse
            FROM read_parquet({qstr(out_dir / f'{cfg.fuel}_test_predictions_2026.parquet')})
            """
        ).df()
        metrics = pd.concat([metrics, all_test], ignore_index=True, sort=False)

    metrics_path = out_dir / f"{cfg.fuel}_test_metrics_2026.csv"
    metrics.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {metrics_path}")
    return metrics


def run_one_fuel(cfg: FuelConfig) -> Dict[str, Any]:
    out_dir = OUTPUT_ROOT / cfg.fuel
    model_dir = out_dir / "model"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 120)
    print(f"[START] {cfg.label} model")
    print("=" * 120)

    split = train_validation_split(cfg)
    print(f"[SPLIT] policy excluded from train/validation = {split['policy_exclusion_enabled']}")
    print(
        f"[SPLIT] requested train/validation = "
        f"{TRAIN_VALID_TRAIN_RATIO:.0%}/{(1.0 - TRAIN_VALID_TRAIN_RATIO):.0%}"
    )
    print(
        f"[SPLIT] actual eligible rows after gap = "
        f"train {split['train_eligible_rows_full']:,} ({split['actual_train_ratio_after_gap']:.2%}) / "
        f"validation {split['valid_eligible_rows_full']:,} ({split['actual_valid_ratio_after_gap']:.2%}), "
        f"gap rows={split['gap_eligible_rows']:,}"
    )
    print(
        f"[SPLIT] train_tune eligible dates = "
        f"{split['train_eligible_date_min'].date()} ~ {split['train_eligible_date_max'].date()} "
        f"({split['train_eligible_days']:,} days)"
    )
    print(
        f"[SPLIT] validation eligible dates = "
        f"{split['valid_eligible_date_min'].date()} ~ {split['valid_eligible_date_max'].date()} "
        f"({split['valid_eligible_days']:,} days)"
    )
    print(f"[SPLIT] final_train < {TEST_START.date()} / test >= {TEST_START.date()}")

    train_tune = load_model_frame(
        cfg=cfg,
        date_start=None,
        date_end=split["train_end"],
        sample_per_mille=TRAIN_SAMPLE_PER_MILLE,
        sample_salt=f"{cfg.fuel}_train_tune",
        max_rows=MAX_TRAIN_TUNE_ROWS_PER_FUEL,
        force_pre_2026=True,
        label="train_tune",
        exclude_policy_periods=EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID,
    )
    valid = load_model_frame(
        cfg=cfg,
        date_start=split["valid_start"],
        date_end=split["valid_end"],
        sample_per_mille=VALID_SAMPLE_PER_MILLE,
        sample_salt=f"{cfg.fuel}_valid",
        max_rows=MAX_VALID_ROWS_PER_FUEL,
        force_pre_2026=True,
        label="validation",
        exclude_policy_periods=EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID,
    )

    if len(train_tune) == 0 or len(valid) == 0:
        raise RuntimeError(f"{cfg.label}: train 또는 validation 데이터가 비어 있습니다.")

    loaded_ratio = len(train_tune) / max(len(train_tune) + len(valid), 1)
    print(
        f"[SPLIT LOADED] {cfg.label}: train_tune={len(train_tune):,}, validation={len(valid):,}, "
        f"loaded_ratio={loaded_ratio:.2%}/{(1.0 - loaded_ratio):.2%}"
    )

    score_frames = [evaluate_baselines(train_tune, valid)]
    candidate_models: List[Tuple[float, lgb.LGBMRegressor, Dict[str, Any], str]] = []

    for idx, params in enumerate(LGBM_PARAM_CANDIDATES, start=1):
        score, model, device = evaluate_lgbm_candidate(train_tune, valid, MODEL_FEATURES, params, idx)
        score_frames.append(score)
        price_wmae = float(score["price_weighted_mae"].iloc[0])
        candidate_models.append((price_wmae, model, params, device))

    best_wmae, best_model, best_params, best_device = sorted(candidate_models, key=lambda x: x[0])[0]
    pre_sequence_scores = pd.concat(score_frames, ignore_index=True, sort=False)
    score_cols = [
        c
        for c in ["model_name", "device", "best_iteration", "price_weighted_mae", "spread_weighted_mae", "price_mae"]
        if c in pre_sequence_scores.columns
    ]
    print("[VALIDATION BEFORE SEQUENCE]")
    print(pre_sequence_scores.sort_values("price_weighted_mae")[score_cols].to_string(index=False))
    print(f"[BEST LGBM] {cfg.label}: weighted MAE={best_wmae:.4f}, device={best_device}, params={best_params}")

    sequence_valid_wrapper: Optional[Dict[str, Any]] = None
    sequence_validation_wmae = float("inf")
    sequence_scores = None
    if RUN_SEQUENCE_MODEL:
        sequence_reference_wmae = None if FINAL_MODEL_KIND == "sequence" else best_wmae
        sequence_valid_wrapper, sequence_scores = train_sequence_candidate(
            train_tune,
            valid,
            cfg,
            out_dir,
            "validation",
            reference_wmae=sequence_reference_wmae,
        )
        if sequence_scores is not None and len(sequence_scores):
            score_frames.append(sequence_scores)
            sequence_validation_wmae = float(sequence_scores["price_weighted_mae"].min())

    validation_scores = pd.concat(score_frames, ignore_index=True, sort=False)
    validation_scores_path = out_dir / f"{cfg.fuel}_validation_scores.csv"
    validation_scores.to_csv(validation_scores_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {validation_scores_path}")
    display(validation_scores.sort_values("price_weighted_mae")) if display else print(validation_scores)

    print(f"[BEST] {cfg.label}: weighted MAE={best_wmae:.4f}, device={best_device}, params={best_params}")
    if sequence_valid_wrapper is not None:
        print(f"[BEST] {cfg.label}: sequence validation weighted MAE={sequence_validation_wmae:.4f}")

    valid_pred = valid[["date", "feature_date", "grid_id", "station_weight", "national_actual_price", "actual_grid_price", "spread_target"]].copy()
    valid_pred["pred_spread_raw"] = predict_spread(best_model, valid, MODEL_FEATURES)
    valid_pred["pred_spread"] = recenter_spread_by_date(valid_pred, "pred_spread_raw", "station_weight")
    valid_pred["pred_grid_price"] = valid_pred["national_actual_price"] + valid_pred["pred_spread"]
    valid_pred.to_parquet(out_dir / f"{cfg.fuel}_validation_predictions.parquet", index=False, compression="zstd")

    del train_tune
    gc.collect()

    final_train = load_model_frame(
        cfg=cfg,
        date_start=None,
        date_end=TEST_START - pd.Timedelta(days=1),
        sample_per_mille=TRAIN_SAMPLE_PER_MILLE,
        sample_salt=f"{cfg.fuel}_final_train",
        max_rows=MAX_FINAL_TRAIN_ROWS_PER_FUEL,
        force_pre_2026=True,
        label="final_train_pre_2026",
        exclude_policy_periods=EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID,
    )

    final_params = dict(best_params)
    best_iter = int(getattr(best_model, "best_iteration_", 0) or 0)
    if best_iter > 0:
        final_params["n_estimators"] = max(800, int(best_iter * 1.20))

    center_model, final_device = fit_lgbm_with_fallback(final_params, final_train, None, MODEL_FEATURES, "final_model")
    importance = compute_feature_importance(center_model, MODEL_FEATURES)
    importance_path = out_dir / f"{cfg.fuel}_feature_importance.csv"
    importance.to_csv(importance_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {importance_path}")
    display(importance.head(30)) if display else print(importance.head(30))

    selected_model_kind = "lgbm"
    if FINAL_MODEL_KIND == "sequence":
        if sequence_valid_wrapper is None:
            print("[WARN] FINAL_MODEL_KIND=sequence 이지만 sequence 후보가 없어 LightGBM을 사용합니다.")
        else:
            selected_model_kind = "sequence"
    elif FINAL_MODEL_KIND == "auto":
        if sequence_valid_wrapper is not None and sequence_validation_wmae < best_wmae * 0.995:
            selected_model_kind = "sequence"

    selected_model: Dict[str, Any] = {
        "kind": selected_model_kind,
        "lgbm_model": center_model,
        "lgbm_validation_weighted_mae": best_wmae,
        "sequence_validation_weighted_mae": sequence_validation_wmae,
    }
    if selected_model_kind == "sequence" and sequence_valid_wrapper is not None:
        selected_model["sequence_wrapper"] = sequence_valid_wrapper

    print(f"[SELECTED MODEL] {cfg.label}: {selected_model_kind}")

    model_bundle = {
        "fuel": cfg.fuel,
        "label": cfg.label,
        "center_model": center_model,
        "selected_model_kind": selected_model_kind,
        "sequence_model_state_path": sequence_valid_wrapper.get("state_path") if sequence_valid_wrapper else None,
        "features": MODEL_FEATURES,
        "base_panel_features": BASE_PANEL_FEATURES,
        "derived_features": DERIVED_FEATURES,
        "time_series_features": TIME_SERIES_FEATURES,
        "use_lgbm_gpu": USE_LGBM_GPU,
        "use_sequence_gpu": USE_GPU,
        "boost_compute_cache_path": os.environ.get("BOOST_COMPUTE_CACHE_PATH"),
        "best_params": best_params,
        "final_params": final_params,
        "best_validation_weighted_mae": best_wmae,
        "sequence_validation_weighted_mae": sequence_validation_wmae,
        "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
        "train_validation_split": split,
        "policy_exclude_ranges": adjusted_policy_exclude_ranges(),
        "sequence_model_epochs": SEQUENCE_MODEL_EPOCHS,
        "sequence_early_stopping_patience": SEQUENCE_EARLY_STOPPING_PATIENCE,
        "sequence_early_stopping_min_delta": SEQUENCE_EARLY_STOPPING_MIN_DELTA,
        "sequence_lr_reduce_factor": SEQUENCE_LR_REDUCE_FACTOR,
        "sequence_lr_patience": SEQUENCE_LR_PATIENCE,
        "sequence_min_lr": SEQUENCE_MIN_LR,
        "sequence_residual_from_lag1": SEQUENCE_RESIDUAL_FROM_LAG1,
        "sequence_min_epochs_before_reference_abort": SEQUENCE_MIN_EPOCHS_BEFORE_REFERENCE_ABORT,
        "sequence_abort_worse_than_reference_ratio": SEQUENCE_ABORT_WORSE_THAN_REFERENCE_RATIO,
        "target_definition": "spread_target = actual_grid_price - national_actual_price",
        "prediction_definition": "predicted_grid_fair_price(target_date) = national_fair_center(target_date) + predicted_spread(target_date)",
        "recenter_rule": "date-level station-weighted mean(predicted_spread) is forced to zero",
        "test_guard": "target_date >= 2026-01-01 is test only and never used in training/tuning/final fit",
        "policy_exclusion_guard": "train_tune, validation, and final_train exclude configured policy periods before sampling",
        "feature_guard": "features are built from feature_date = target_date - prediction_horizon_days plus historical lags ending before target_date",
    }
    model_path = model_dir / f"{cfg.fuel}_grid_fair_model_bundle.joblib"
    joblib.dump(model_bundle, model_path)
    print(f"[SAVE] {model_path}")

    fair_table = load_external_fair_table(cfg)
    test_metrics = predict_test_2026(cfg, selected_model, MODEL_FEATURES, out_dir, fair_table)

    metadata = {
        "created_at": pd.Timestamp.now().isoformat(),
        "config": asdict(cfg),
        "grid_path": str(GRID_PATH),
        "output_dir": str(out_dir),
        "test_start": TEST_START_SQL,
        "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
        "train_valid_train_ratio_requested": TRAIN_VALID_TRAIN_RATIO,
        "gap_days": GAP_DAYS,
        "exclude_policy_periods_from_train_valid": EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID,
        "policy_exclude_buffer_before_days": POLICY_EXCLUDE_BUFFER_BEFORE_DAYS,
        "policy_exclude_buffer_after_days": POLICY_EXCLUDE_BUFFER_AFTER_DAYS,
        "policy_exclude_ranges": adjusted_policy_exclude_ranges(),
        "train_validation_split": split,
        "use_lgbm_gpu": USE_LGBM_GPU,
        "use_sequence_gpu": USE_GPU,
        "boost_compute_cache_path": os.environ.get("BOOST_COMPUTE_CACHE_PATH"),
        "train_sample_per_mille_requested": TRAIN_SAMPLE_PER_MILLE,
        "valid_sample_per_mille_requested": VALID_SAMPLE_PER_MILLE,
        "max_train_tune_rows_per_fuel": MAX_TRAIN_TUNE_ROWS_PER_FUEL,
        "max_final_train_rows_per_fuel": MAX_FINAL_TRAIN_ROWS_PER_FUEL,
        "max_valid_rows_per_fuel": MAX_VALID_ROWS_PER_FUEL,
        "features": MODEL_FEATURES,
        "time_series_features": TIME_SERIES_FEATURES,
        "selected_model_kind": selected_model_kind,
        "sequence_model_state_path": sequence_valid_wrapper.get("state_path") if sequence_valid_wrapper else None,
        "sequence_score_path": sequence_valid_wrapper.get("score_path") if sequence_valid_wrapper else None,
        "sequence_model_epochs": SEQUENCE_MODEL_EPOCHS,
        "sequence_early_stopping_patience": SEQUENCE_EARLY_STOPPING_PATIENCE,
        "sequence_early_stopping_min_delta": SEQUENCE_EARLY_STOPPING_MIN_DELTA,
        "sequence_lr_reduce_factor": SEQUENCE_LR_REDUCE_FACTOR,
        "sequence_lr_patience": SEQUENCE_LR_PATIENCE,
        "sequence_min_lr": SEQUENCE_MIN_LR,
        "sequence_residual_from_lag1": SEQUENCE_RESIDUAL_FROM_LAG1,
        "sequence_min_epochs_before_reference_abort": SEQUENCE_MIN_EPOCHS_BEFORE_REFERENCE_ABORT,
        "sequence_abort_worse_than_reference_ratio": SEQUENCE_ABORT_WORSE_THAN_REFERENCE_RATIO,
        "best_params": best_params,
        "final_params": final_params,
        "validation_scores_path": str(validation_scores_path),
        "feature_importance_path": str(importance_path),
        "model_path": str(model_path),
    }
    metadata_path = out_dir / f"{cfg.fuel}_model_metadata.json"
    save_json(metadata_path, metadata)
    print(f"[SAVE] {metadata_path}")

    del final_train, valid
    gc.collect()

    return {
        "fuel": cfg.fuel,
        "label": cfg.label,
        "best_validation_weighted_mae": best_wmae,
        "sequence_validation_weighted_mae": sequence_validation_wmae,
        "selected_model_kind": selected_model_kind,
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "test_metrics": test_metrics,
    }


# %% [markdown] cell 18
# ## 7. 전체 실행
# 아래 셀을 실행하면 지정된 유종(`RUN_FUELS`)에 대해 학습, 검증, 2026 test 예측을 순서대로 수행합니다.
# 

# %% cell 19
results: Dict[str, Any] = {}

for fuel_key in RUN_FUELS:
    results[fuel_key] = run_one_fuel(FUEL_CONFIG[fuel_key])

summary_rows = []
for fuel_key, result in results.items():
    metrics = result.get("test_metrics")
    test_wmae = np.nan
    if isinstance(metrics, pd.DataFrame) and len(metrics) and "period" in metrics.columns:
        rows = metrics[metrics["period"].astype(str).eq("test_2026_all")]
        if len(rows) and "price_weighted_mae" in rows.columns:
            test_wmae = rows["price_weighted_mae"].iloc[0]
    summary_rows.append(
        {
            "fuel": fuel_key,
            "label": result["label"],
            "selected_model_kind": result.get("selected_model_kind"),
            "best_validation_weighted_mae": result["best_validation_weighted_mae"],
            "sequence_validation_weighted_mae": result.get("sequence_validation_weighted_mae"),
            "test_2026_price_weighted_mae": test_wmae,
            "model_path": result["model_path"],
            "metadata_path": result["metadata_path"],
        }
    )

run_summary = pd.DataFrame(summary_rows)
summary_path = OUTPUT_ROOT / "model_run_summary.csv"
run_summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
print(f"[SAVE] {summary_path}")
display(run_summary) if display else print(run_summary)
