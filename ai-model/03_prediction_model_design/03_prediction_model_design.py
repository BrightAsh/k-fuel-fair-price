from __future__ import annotations

import gc
import json
import math
import os
import random
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from torch.utils.data import DataLoader, TensorDataset

warnings.filterwarnings("ignore")


# =============================================================================
# Local fixed configuration
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE3_DIR = Path(__file__).resolve().parent
GRID_PATH = REPO_ROOT / "ai-model" / "02_spatial_grid_build" / "outputs" / "grid.parquet"
OUTPUT_ROOT = STAGE3_DIR / "outputs"
INTERMEDIATE_DATA_DIR = OUTPUT_ROOT / "intermediate_data"
CACHE_DATASET_VERSION = "stage03_spread_delta_lstm_v1"

TEST_START = pd.Timestamp("2026-01-01")
PREDICTION_HORIZON_DAYS = 1

RUN_FUELS = ("gasoline", "diesel")
RANDOM_SEED = 20260616

TRAIN_VALID_TRAIN_RATIO = 0.70
GAP_DAYS = 7

SEQUENCE_LENGTH_DAYS = 28
SEQUENCE_REQUIRED_HISTORY_DAYS = SEQUENCE_LENGTH_DAYS + 1

TARGET_COLUMN = "spread_delta_target"
MODEL_TARGET_MODE = "spread_delta"

TRAIN_SAMPLE_PER_MILLE = 100
VALID_SAMPLE_PER_MILLE = 100
MAX_TRAIN_ROWS_PER_FUEL = 3_000_000
MAX_VALID_ROWS_PER_FUEL = 1_300_000
MAX_FINAL_TRAIN_ROWS_PER_FUEL = 4_500_000

SEQUENCE_MAX_TRAIN_ROWS = 3_000_000
SEQUENCE_MAX_VALID_ROWS = 1_300_000
SEQUENCE_MAX_FINAL_ROWS = 4_500_000

MODEL_EPOCHS = 1000
MODEL_BATCH_SIZE = 8192
MODEL_LEARNING_RATE = 0.0025
MODEL_WEIGHT_DECAY = 0.0001
MODEL_GRAD_CLIP_NORM = 1.0
EARLY_STOPPING_PATIENCE = 30
EARLY_STOPPING_MIN_DELTA = 0.001
LR_REDUCE_PATIENCE = 8
LR_REDUCE_FACTOR = 0.5
MIN_LEARNING_RATE = 0.00001
FINAL_EXTRA_EPOCHS = 5
FINAL_MAX_EPOCHS = 200

USE_CUDA = torch.cuda.is_available()
DEVICE = torch.device("cuda" if USE_CUDA else "cpu")

if USE_CUDA:
    torch.backends.cudnn.benchmark = True

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)
if USE_CUDA:
    torch.cuda.manual_seed_all(RANDOM_SEED)


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


@dataclass(frozen=True)
class FuelConfig:
    fuel: str
    label: str
    target_col: str
    station_count_col: str


FUEL_CONFIG: Dict[str, FuelConfig] = {
    "gasoline": FuelConfig(
        fuel="gasoline",
        label="gasoline",
        target_col="gasoline_price_mean",
        station_count_col="gasoline_station_count",
    ),
    "diesel": FuelConfig(
        fuel="diesel",
        label="diesel",
        target_col="diesel_price_mean",
        station_count_col="diesel_station_count",
    ),
}


SEQUENCE_CHANNELS = {
    "spread_delta": [f"spread_delta_lag_{d}d" for d in range(SEQUENCE_LENGTH_DAYS, 0, -1)],
    "actual_price_delta": [f"actual_grid_price_delta_lag_{d}d" for d in range(SEQUENCE_LENGTH_DAYS, 0, -1)],
    "national_price_delta": [f"national_price_delta_lag_{d}d" for d in range(SEQUENCE_LENGTH_DAYS, 0, -1)],
    "station_weight": [f"station_weight_lag_{d}d" for d in range(SEQUENCE_LENGTH_DAYS, 0, -1)],
}
MODEL_INPUT_COLUMNS = [col for cols in SEQUENCE_CHANNELS.values() for col in cols]
OUTPUT_PANEL_COLUMNS = ["cell_x", "cell_y", "center_lon", "center_lat"]


# =============================================================================
# Utility
# =============================================================================


def qid(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def qstr(value: Any) -> str:
    return "'" + str(value).replace("\\", "/").replace("'", "''") + "'"


def sql_date(value: pd.Timestamp | str) -> str:
    return f"DATE {qstr(pd.Timestamp(value).strftime('%Y-%m-%d'))}"


def ensure_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.floor("D")


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


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
    row.update(regression_metric_row(df[TARGET_COLUMN], df["pred_spread_delta"], df["station_weight"], "delta"))
    return row


def sample_frame(df: pd.DataFrame, max_rows: int, salt: str) -> pd.DataFrame:
    if max_rows and len(df) > max_rows:
        seed = abs(hash((salt, RANDOM_SEED))) % (2**32)
        return df.sample(n=max_rows, random_state=seed).sort_values(["date", "grid_id"]).reset_index(drop=True)
    return df.reset_index(drop=True)


def seconds_text(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60:.1f}m"


# =============================================================================
# DuckDB data frame builder
# =============================================================================


if not GRID_PATH.exists():
    raise FileNotFoundError(f"grid.parquet not found: {GRID_PATH}")

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
INTERMEDIATE_DATA_DIR.mkdir(parents=True, exist_ok=True)

con = duckdb.connect(database=":memory:")
con.execute(f"PRAGMA threads={max(os.cpu_count() or 2, 2)}")


def panel_sql() -> str:
    return f"read_parquet({qstr(GRID_PATH)})"


schema_df = con.execute(f"DESCRIBE SELECT * FROM {panel_sql()} LIMIT 0").df()
ALL_COLUMNS = set(schema_df["column_name"].astype(str))


def policy_membership_condition(date_expr: str) -> str:
    pieces = [
        f"({date_expr} BETWEEN {sql_date(start)} AND {sql_date(end)})"
        for start, end, _label in POLICY_EXCLUDE_RANGES
    ]
    return "(" + " OR ".join(pieces) + ")" if pieces else "FALSE"


def policy_exclusion_condition(date_expr: str) -> str:
    return "NOT " + policy_membership_condition(date_expr)


def history_sql_exprs() -> List[str]:
    exprs: List[str] = []
    sequence_frame = (
        f"PARTITION BY grid_id ORDER BY target_date "
        f"ROWS BETWEEN {SEQUENCE_REQUIRED_HISTORY_DAYS} PRECEDING AND 1 PRECEDING"
    )
    exprs.extend(
        [
            f"COUNT(spread_target) OVER ({sequence_frame}) AS sequence_hist_count",
            (
                f"SUM(CASE WHEN {policy_membership_condition('target_date')} THEN 1 ELSE 0 END) "
                f"OVER ({sequence_frame}) AS sequence_policy_days"
            ),
            (
                f"date_diff('day', "
                f"LAG(target_date, {SEQUENCE_REQUIRED_HISTORY_DAYS}) OVER (PARTITION BY grid_id ORDER BY target_date), "
                f"target_date) AS sequence_calendar_span"
            ),
            "LAG(spread_target, 1) OVER (PARTITION BY grid_id ORDER BY target_date) AS spread_lag_1d",
        ]
    )
    for d in range(1, SEQUENCE_LENGTH_DAYS + 1):
        exprs.extend(
            [
                (
                    f"(LAG(spread_target, {d}) OVER (PARTITION BY grid_id ORDER BY target_date) - "
                    f"LAG(spread_target, {d + 1}) OVER (PARTITION BY grid_id ORDER BY target_date)) "
                    f"AS spread_delta_lag_{d}d"
                ),
                (
                    f"(LAG(actual_grid_price, {d}) OVER (PARTITION BY grid_id ORDER BY target_date) - "
                    f"LAG(actual_grid_price, {d + 1}) OVER (PARTITION BY grid_id ORDER BY target_date)) "
                    f"AS actual_grid_price_delta_lag_{d}d"
                ),
                (
                    f"(LAG(national_actual_price, {d}) OVER (PARTITION BY grid_id ORDER BY target_date) - "
                    f"LAG(national_actual_price, {d + 1}) OVER (PARTITION BY grid_id ORDER BY target_date)) "
                    f"AS national_price_delta_lag_{d}d"
                ),
                (
                    f"LAG(station_weight, {d}) OVER (PARTITION BY grid_id ORDER BY target_date) "
                    f"AS station_weight_lag_{d}d"
                ),
            ]
        )
    return exprs


def output_panel_exprs() -> List[str]:
    exprs: List[str] = []
    for col in OUTPUT_PANEL_COLUMNS:
        if col in ALL_COLUMNS:
            exprs.append(f"p.{qid(col)} AS {qid(col)}")
        else:
            exprs.append(f"NULL AS {qid(col)}")
    return exprs


def selected_column_exprs() -> List[str]:
    exprs = [
        "t.target_date AS date",
        "t.feature_date AS feature_date",
        "t.grid_id",
        "t.actual_grid_price",
        "t.station_weight",
        "t.national_actual_price",
        "t.spread_target",
        "(CAST(t.spread_target AS DOUBLE) - CAST(t.spread_lag_1d AS DOUBLE)) AS spread_delta_target",
        "CAST(t.spread_lag_1d AS DOUBLE) AS spread_lag_1d",
        "CAST(t.sequence_hist_count AS DOUBLE) AS sequence_hist_count",
        "CAST(t.sequence_policy_days AS DOUBLE) AS sequence_policy_days",
        "CAST(t.sequence_calendar_span AS DOUBLE) AS sequence_calendar_span",
    ]
    exprs.extend([f"CAST(t.{qid(col)} AS DOUBLE) AS {qid(col)}" for col in MODEL_INPUT_COLUMNS])
    exprs.extend(output_panel_exprs())
    return exprs


def base_date_conditions(
    date_start: Optional[pd.Timestamp],
    date_end: Optional[pd.Timestamp],
    force_pre_2026: bool,
    exclude_target_policy: bool,
) -> List[str]:
    conds: List[str] = []
    if date_start is not None:
        conds.append(f"t.target_date >= {sql_date(date_start)}")
    if date_end is not None:
        conds.append(f"t.target_date <= {sql_date(date_end)}")
    if force_pre_2026:
        conds.append(f"t.target_date < {sql_date(TEST_START)}")
    if exclude_target_policy:
        conds.append(policy_exclusion_condition("t.target_date"))
    return conds


def sequence_quality_conditions(exclude_history_policy: bool) -> List[str]:
    conds = [
        f"t.sequence_hist_count = {SEQUENCE_REQUIRED_HISTORY_DAYS}",
        f"t.sequence_calendar_span = {SEQUENCE_REQUIRED_HISTORY_DAYS}",
        "t.spread_lag_1d IS NOT NULL",
    ]
    conds.extend([f"t.{qid(col)} IS NOT NULL" for col in MODEL_INPUT_COLUMNS])
    if exclude_history_policy:
        conds.append("COALESCE(t.sequence_policy_days, 999999) = 0")
    return conds


def sample_predicate(per_mille: int, salt: str) -> str:
    per_mille = int(per_mille)
    if per_mille >= 1000:
        return "TRUE"
    if per_mille <= 0:
        raise ValueError("per_mille must be between 1 and 1000")
    return (
        "(hash(CAST(t.grid_id AS VARCHAR) || '|' || CAST(t.target_date AS VARCHAR) || '|' || "
        f"{qstr(salt)}) % 1000) < {per_mille}"
    )


def effective_per_mille(total_rows: int, requested_per_mille: int, max_rows: Optional[int]) -> int:
    if not max_rows or total_rows <= max_rows:
        return min(int(requested_per_mille), 1000)
    cap = max(1, int(math.floor(max_rows * 1000 / total_rows)))
    return min(int(requested_per_mille), cap, 1000)


def model_frame_query(cfg: FuelConfig, select_sql: str, where_sql: str, group_sql: str = "") -> str:
    history_exprs = ",\n                ".join(history_sql_exprs())
    return f"""
        WITH raw AS (
            SELECT CAST(date AS DATE) AS date_key, *
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
                SUM(actual_grid_price * station_weight) / NULLIF(SUM(station_weight), 0) AS national_actual_price
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
            {select_sql}
        FROM history t
        INNER JOIN feature_rows p
            ON p.grid_id = t.grid_id
           AND p.date_key = t.feature_date
        WHERE {where_sql}
        {group_sql}
    """


def estimate_rows(
    cfg: FuelConfig,
    date_start: Optional[pd.Timestamp],
    date_end: Optional[pd.Timestamp],
    force_pre_2026: bool,
    exclude_target_policy: bool,
    exclude_history_policy: bool,
) -> int:
    conds = base_date_conditions(date_start, date_end, force_pre_2026, exclude_target_policy)
    conds.extend(sequence_quality_conditions(exclude_history_policy))
    query = model_frame_query(cfg, "COUNT(*) AS n", " AND ".join(conds))
    return int(con.execute(query).fetchone()[0])


def cache_date(value: Optional[pd.Timestamp]) -> Optional[str]:
    if value is None:
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def cache_safe(value: Any) -> str:
    text = "none" if value is None else str(value)
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)


def grid_file_signature() -> Dict[str, Any]:
    stat = GRID_PATH.stat()
    return {
        "path": str(GRID_PATH.resolve()),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def normalized_policy_ranges() -> List[List[str]]:
    return [[str(start), str(end), str(label)] for start, end, label in POLICY_EXCLUDE_RANGES]


def frame_cache_conditions(
    cfg: FuelConfig,
    date_start: Optional[pd.Timestamp],
    date_end: Optional[pd.Timestamp],
    sample_per_mille: int,
    sample_salt: str,
    max_rows: Optional[int],
    force_pre_2026: bool,
    exclude_target_policy: bool,
    exclude_history_policy: bool,
    label: str,
) -> Dict[str, Any]:
    return {
        "dataset_version": CACHE_DATASET_VERSION,
        "fuel": cfg.fuel,
        "target_col": cfg.target_col,
        "station_count_col": cfg.station_count_col,
        "label": label,
        "date_start": cache_date(date_start),
        "date_end": cache_date(date_end),
        "sample_per_mille_requested": int(sample_per_mille),
        "sample_salt": sample_salt,
        "max_rows": int(max_rows) if max_rows is not None else None,
        "force_pre_2026": bool(force_pre_2026),
        "exclude_target_policy": bool(exclude_target_policy),
        "exclude_history_policy": bool(exclude_history_policy),
        "test_start": cache_date(TEST_START),
        "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
        "train_valid_train_ratio": TRAIN_VALID_TRAIN_RATIO,
        "gap_days": GAP_DAYS,
        "sequence_length_days": SEQUENCE_LENGTH_DAYS,
        "sequence_required_history_days": SEQUENCE_REQUIRED_HISTORY_DAYS,
        "target_column": TARGET_COLUMN,
        "model_target_mode": MODEL_TARGET_MODE,
        "model_input_columns": MODEL_INPUT_COLUMNS,
        "sequence_channels": SEQUENCE_CHANNELS,
        "policy_exclude_ranges": normalized_policy_ranges(),
        "random_seed": RANDOM_SEED,
        "grid_file": grid_file_signature(),
    }


def frame_cache_metadata(
    conditions: Dict[str, Any],
    total_rows: int,
    actual_per_mille: int,
    cached_rows: int,
) -> Dict[str, Any]:
    return {
        "conditions": conditions,
        "stats": {
            "eligible_total_rows": int(total_rows),
            "sample_per_mille_actual": int(actual_per_mille),
            "cached_rows": int(cached_rows),
            "created_at": pd.Timestamp.now().isoformat(),
        },
    }


def frame_cache_paths(cfg: FuelConfig, label: str) -> Tuple[Path, Path]:
    cache_dir = INTERMEDIATE_DATA_DIR / cfg.fuel
    stem = cache_safe(label)
    return cache_dir / f"{stem}.parquet", cache_dir / f"{stem}.metadata.json"


def load_cached_frame(cache_path: Path, meta_path: Path, expected_conditions: Dict[str, Any]) -> Optional[pd.DataFrame]:
    if not cache_path.exists() or not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            stored_meta = json.load(f)
    except Exception as exc:
        print(f"[CACHE MISS] metadata read failed: {meta_path} ({type(exc).__name__}: {exc})")
        return None
    if stored_meta.get("conditions") != expected_conditions:
        print(f"[CACHE MISS] conditions changed: {cache_path}")
        return None

    start = time.time()
    df = pd.read_parquet(cache_path)
    df["date"] = ensure_date(df["date"])
    df["feature_date"] = ensure_date(df["feature_date"])
    print(f"[CACHE HIT] {cache_path} rows={len(df):,}, read={seconds_text(time.time() - start)}")
    return df


def save_cached_frame(df: pd.DataFrame, cache_path: Path, meta_path: Path, metadata: Dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    df.to_parquet(cache_path, index=False, compression="zstd")
    save_json(meta_path, metadata)
    print(f"[CACHE SAVE] {cache_path} rows={len(df):,}, write={seconds_text(time.time() - start)}")


def daily_counts_cache_conditions(cfg: FuelConfig) -> Dict[str, Any]:
    return {
        "dataset_version": CACHE_DATASET_VERSION,
        "fuel": cfg.fuel,
        "target_col": cfg.target_col,
        "station_count_col": cfg.station_count_col,
        "test_start": cache_date(TEST_START),
        "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
        "sequence_length_days": SEQUENCE_LENGTH_DAYS,
        "sequence_required_history_days": SEQUENCE_REQUIRED_HISTORY_DAYS,
        "model_input_columns": MODEL_INPUT_COLUMNS,
        "sequence_channels": SEQUENCE_CHANNELS,
        "policy_exclude_ranges": normalized_policy_ranges(),
        "grid_file": grid_file_signature(),
    }


def daily_counts_cache_paths(cfg: FuelConfig) -> Tuple[Path, Path]:
    cache_dir = INTERMEDIATE_DATA_DIR / cfg.fuel
    return cache_dir / "eligible_daily_counts.parquet", cache_dir / "eligible_daily_counts.metadata.json"


def load_cached_daily_counts(cfg: FuelConfig, expected_conditions: Dict[str, Any]) -> Optional[pd.DataFrame]:
    cache_path, meta_path = daily_counts_cache_paths(cfg)
    if not cache_path.exists() or not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            stored_meta = json.load(f)
    except Exception as exc:
        print(f"[CACHE MISS] daily count metadata read failed: {meta_path} ({type(exc).__name__}: {exc})")
        return None
    if stored_meta.get("conditions") != expected_conditions:
        print(f"[CACHE MISS] daily count conditions changed: {cache_path}")
        return None

    start = time.time()
    daily = pd.read_parquet(cache_path)
    daily["date"] = ensure_date(daily["date"])
    daily["eligible_rows"] = pd.to_numeric(daily["eligible_rows"], errors="coerce").fillna(0).astype("int64")
    daily["cum_rows"] = daily["eligible_rows"].cumsum()
    print(f"[CACHE HIT] {cache_path} rows={len(daily):,}, read={seconds_text(time.time() - start)}")
    return daily


def save_cached_daily_counts(cfg: FuelConfig, daily: pd.DataFrame, conditions: Dict[str, Any]) -> None:
    cache_path, meta_path = daily_counts_cache_paths(cfg)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    daily.to_parquet(cache_path, index=False, compression="zstd")
    save_json(
        meta_path,
        {
            "conditions": conditions,
            "stats": {
                "days": int(len(daily)),
                "eligible_total_rows": int(daily["eligible_rows"].sum()),
                "created_at": pd.Timestamp.now().isoformat(),
            },
        },
    )
    print(f"[CACHE SAVE] {cache_path} rows={len(daily):,}, write={seconds_text(time.time() - start)}")


def load_model_frame(
    cfg: FuelConfig,
    date_start: Optional[pd.Timestamp],
    date_end: Optional[pd.Timestamp],
    sample_per_mille: int,
    sample_salt: str,
    max_rows: Optional[int],
    force_pre_2026: bool,
    exclude_target_policy: bool,
    exclude_history_policy: bool,
    label: str,
) -> pd.DataFrame:
    cache_conditions = frame_cache_conditions(
        cfg=cfg,
        date_start=date_start,
        date_end=date_end,
        sample_per_mille=sample_per_mille,
        sample_salt=sample_salt,
        max_rows=max_rows,
        force_pre_2026=force_pre_2026,
        exclude_target_policy=exclude_target_policy,
        exclude_history_policy=exclude_history_policy,
        label=label,
    )
    cache_path, meta_path = frame_cache_paths(cfg, label)
    cached = load_cached_frame(cache_path, meta_path, cache_conditions)
    if cached is not None:
        return cached

    total_rows = estimate_rows(
        cfg,
        date_start=date_start,
        date_end=date_end,
        force_pre_2026=force_pre_2026,
        exclude_target_policy=exclude_target_policy,
        exclude_history_policy=exclude_history_policy,
    )
    actual_per_mille = effective_per_mille(total_rows, sample_per_mille, max_rows)
    conds = base_date_conditions(date_start, date_end, force_pre_2026, exclude_target_policy)
    conds.extend(sequence_quality_conditions(exclude_history_policy))
    conds.append(sample_predicate(actual_per_mille, sample_salt))

    print(
        f"[LOAD] {cfg.label} {label}: eligible={total_rows:,}, "
        f"sample={actual_per_mille}/1000, max_rows={max_rows}"
    )

    query = model_frame_query(cfg, ",\n            ".join(selected_column_exprs()), " AND ".join(conds))
    df = con.execute(query).df()

    if max_rows and len(df) > max_rows:
        df = sample_frame(df, max_rows, f"{cfg.fuel}_{label}_post_sample")

    df["date"] = ensure_date(df["date"])
    df["feature_date"] = ensure_date(df["feature_date"])
    expected_delta = (df["date"] - df["feature_date"]).dt.days
    if len(df) and not expected_delta.eq(PREDICTION_HORIZON_DAYS).all():
        raise AssertionError("feature_date and target_date horizon mismatch")
    if force_pre_2026 and (df["date"] >= TEST_START).any():
        bad_min = df.loc[df["date"] >= TEST_START, "date"].min()
        raise AssertionError(f"pre-2026 frame contains test rows: {bad_min}")

    numeric_cols = [
        "actual_grid_price",
        "station_weight",
        "national_actual_price",
        "spread_target",
        "spread_delta_target",
        "spread_lag_1d",
        "sequence_hist_count",
        "sequence_policy_days",
        "sequence_calendar_span",
        *MODEL_INPUT_COLUMNS,
        *[c for c in OUTPUT_PANEL_COLUMNS if c in df.columns],
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    required = [TARGET_COLUMN, "spread_lag_1d", *MODEL_INPUT_COLUMNS]
    before = len(df)
    df = df.dropna(subset=[c for c in required if c in df.columns]).sort_values(["date", "grid_id"]).reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        print(f"[LOAD FILTER] {cfg.label} {label}: dropped_null_required={dropped:,}")

    pct = (len(df) / total_rows * 100.0) if total_rows else 0.0
    print(
        f"[LOAD DONE] {cfg.label} {label}: rows={len(df):,}/{total_rows:,} ({pct:.2f}%), "
        f"target_date={df['date'].min().date() if len(df) else None}~{df['date'].max().date() if len(df) else None}"
    )
    cache_meta = frame_cache_metadata(
        conditions=cache_conditions,
        total_rows=total_rows,
        actual_per_mille=actual_per_mille,
        cached_rows=len(df),
    )
    save_cached_frame(df, cache_path, meta_path, cache_meta)
    return df


def eligible_daily_counts(cfg: FuelConfig) -> pd.DataFrame:
    cache_conditions = daily_counts_cache_conditions(cfg)
    cached = load_cached_daily_counts(cfg, cache_conditions)
    if cached is not None:
        return cached

    conds = base_date_conditions(
        date_start=None,
        date_end=TEST_START - pd.Timedelta(days=1),
        force_pre_2026=True,
        exclude_target_policy=True,
    )
    conds.extend(sequence_quality_conditions(exclude_history_policy=True))
    query = model_frame_query(
        cfg,
        "t.target_date AS date,\n            COUNT(*) AS eligible_rows",
        " AND ".join(conds),
        "GROUP BY t.target_date ORDER BY t.target_date",
    )
    daily = con.execute(query).df()
    if len(daily) == 0:
        raise RuntimeError(f"{cfg.label}: no eligible train/validation rows after policy/history filters")
    daily["date"] = ensure_date(daily["date"])
    daily["eligible_rows"] = pd.to_numeric(daily["eligible_rows"], errors="coerce").fillna(0).astype("int64")
    daily["cum_rows"] = daily["eligible_rows"].cumsum()
    save_cached_daily_counts(cfg, daily, cache_conditions)
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
        raise RuntimeError(f"{cfg.label}: failed to make train/validation split")

    usable = train_rows + valid_rows
    return {
        "requested_train_ratio": TRAIN_VALID_TRAIN_RATIO,
        "actual_train_ratio_after_gap": train_rows / usable,
        "actual_valid_ratio_after_gap": valid_rows / usable,
        "train_end": train_end,
        "valid_start": valid_start,
        "valid_end": valid_end,
        "train_eligible_date_min": pd.Timestamp(daily.loc[train_mask, "date"].min()),
        "train_eligible_date_max": pd.Timestamp(daily.loc[train_mask, "date"].max()),
        "valid_eligible_date_min": pd.Timestamp(daily.loc[valid_mask, "date"].min()),
        "valid_eligible_date_max": pd.Timestamp(daily.loc[valid_mask, "date"].max()),
        "train_eligible_days": int(train_mask.sum()),
        "valid_eligible_days": int(valid_mask.sum()),
        "train_eligible_rows_full": train_rows,
        "valid_eligible_rows_full": valid_rows,
        "gap_eligible_rows": gap_rows,
        "eligible_rows_full": total_rows,
    }


# =============================================================================
# Sequence model
# =============================================================================


class SpreadDeltaLstm(nn.Module):
    def __init__(self, input_size: int, hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.20):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
            bidirectional=True,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size * 2, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h_n, _) = self.lstm(x)
        h = torch.cat([h_n[-2], h_n[-1]], dim=1)
        return self.head(h).squeeze(1)


def fit_preprocess(df: pd.DataFrame) -> Dict[str, Any]:
    seq = raw_sequence_array(df)
    seq_mean = np.nanmean(seq, axis=(0, 1)).astype("float32")
    seq_std = np.nanstd(seq, axis=(0, 1)).astype("float32")
    seq_std = np.where(np.isfinite(seq_std) & (seq_std > 1e-6), seq_std, 1.0).astype("float32")

    y = pd.to_numeric(df[TARGET_COLUMN], errors="coerce").to_numpy(dtype="float32")
    y_mean = float(np.nanmean(y)) if np.isfinite(y).any() else 0.0
    y_std = float(np.nanstd(y)) if np.isfinite(y).any() else 1.0
    if not np.isfinite(y_std) or y_std < 1e-6:
        y_std = 1.0

    return {
        "channel_names": list(SEQUENCE_CHANNELS.keys()),
        "sequence_channels": SEQUENCE_CHANNELS,
        "seq_mean": seq_mean.tolist(),
        "seq_std": seq_std.tolist(),
        "y_mean": y_mean,
        "y_std": y_std,
    }


def raw_sequence_array(df: pd.DataFrame) -> np.ndarray:
    channel_arrays = []
    for cols in SEQUENCE_CHANNELS.values():
        channel_arrays.append(df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype="float32"))
    return np.stack(channel_arrays, axis=-1)


def sequence_arrays(
    df: pd.DataFrame,
    prep: Dict[str, Any],
    include_target: bool,
) -> Tuple[np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
    seq = raw_sequence_array(df)
    mean = np.asarray(prep["seq_mean"], dtype="float32").reshape(1, 1, -1)
    std = np.asarray(prep["seq_std"], dtype="float32").reshape(1, 1, -1)
    seq = ((seq - mean) / std).astype("float32")
    seq = np.where(np.isfinite(seq), seq, 0.0).astype("float32")

    y_arr: Optional[np.ndarray] = None
    w_arr: Optional[np.ndarray] = None
    if include_target:
        y = pd.to_numeric(df[TARGET_COLUMN], errors="coerce").to_numpy(dtype="float32")
        y_arr = ((y - float(prep["y_mean"])) / float(prep["y_std"])).astype("float32")
        w = pd.to_numeric(df["station_weight"], errors="coerce").fillna(0).clip(lower=0).to_numpy(dtype="float32")
        w_mean = float(np.nanmean(w[w > 0])) if np.any(w > 0) else 1.0
        w_arr = np.where(np.isfinite(w) & (w > 0), w / w_mean, 0.0).astype("float32")
    return seq, y_arr, w_arr


def make_loader(
    df: pd.DataFrame,
    prep: Dict[str, Any],
    batch_size: int,
    shuffle: bool,
    include_target: bool,
) -> DataLoader:
    seq, y, w = sequence_arrays(df, prep, include_target=include_target)
    if include_target:
        assert y is not None and w is not None
        ds = TensorDataset(torch.from_numpy(seq), torch.from_numpy(y), torch.from_numpy(w))
    else:
        ds = TensorDataset(torch.from_numpy(seq))
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle, num_workers=0, pin_memory=USE_CUDA)


def predict_delta(wrapper: Dict[str, Any], df: pd.DataFrame) -> np.ndarray:
    model: SpreadDeltaLstm = wrapper["model"]
    prep = wrapper["preprocess"]
    loader = make_loader(df, prep, MODEL_BATCH_SIZE, shuffle=False, include_target=False)

    preds: List[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for (xb,) in loader:
            raw = model(xb.to(DEVICE)).detach().cpu().numpy()
            preds.append(raw)
    scaled = np.concatenate(preds) if preds else np.array([], dtype="float32")
    return scaled * float(prep["y_std"]) + float(prep["y_mean"])


def prediction_frame(df: pd.DataFrame, pred_delta: np.ndarray) -> pd.DataFrame:
    out_cols = [
        "date",
        "feature_date",
        "grid_id",
        "station_weight",
        "actual_grid_price",
        "national_actual_price",
        "spread_target",
        TARGET_COLUMN,
        "spread_lag_1d",
        *[c for c in OUTPUT_PANEL_COLUMNS if c in df.columns],
    ]
    out = df[out_cols].copy()
    out["pred_spread_delta"] = np.asarray(pred_delta, dtype=float)
    out["pred_spread_raw"] = pd.to_numeric(out["spread_lag_1d"], errors="coerce") + out["pred_spread_delta"]
    out["pred_spread"] = recenter_spread_by_date(out, "pred_spread_raw", "station_weight")
    out["pred_grid_price"] = out["national_actual_price"] + out["pred_spread"]
    out["prediction_error_to_actual"] = out["pred_grid_price"] - out["actual_grid_price"]
    return out


def baseline_scores(train_df: pd.DataFrame, valid_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    zero_spread = valid_df[["date", "station_weight", "national_actual_price", "actual_grid_price", "spread_target", TARGET_COLUMN]].copy()
    zero_spread["pred_spread_delta"] = -pd.to_numeric(valid_df["spread_lag_1d"], errors="coerce")
    zero_spread["pred_spread"] = 0.0
    zero_spread["pred_grid_price"] = zero_spread["national_actual_price"]
    rows.append({"model_name": "baseline_national_average", **evaluate_prediction_frame(zero_spread, "validation")})

    lag1 = valid_df[
        ["date", "station_weight", "national_actual_price", "actual_grid_price", "spread_target", TARGET_COLUMN, "spread_lag_1d"]
    ].copy()
    lag1["pred_spread_delta"] = 0.0
    lag1["pred_spread_raw"] = pd.to_numeric(lag1["spread_lag_1d"], errors="coerce")
    lag1["pred_spread"] = recenter_spread_by_date(lag1, "pred_spread_raw", "station_weight")
    lag1["pred_grid_price"] = lag1["national_actual_price"] + lag1["pred_spread"]
    rows.append({"model_name": "baseline_lag1_delta0", **evaluate_prediction_frame(lag1, "validation")})

    train_delta_mean = float(np.average(train_df[TARGET_COLUMN], weights=train_df["station_weight"].clip(lower=1)))
    mean_delta = valid_df[
        ["date", "station_weight", "national_actual_price", "actual_grid_price", "spread_target", TARGET_COLUMN, "spread_lag_1d"]
    ].copy()
    mean_delta["pred_spread_delta"] = train_delta_mean
    mean_delta["pred_spread_raw"] = pd.to_numeric(mean_delta["spread_lag_1d"], errors="coerce") + train_delta_mean
    mean_delta["pred_spread"] = recenter_spread_by_date(mean_delta, "pred_spread_raw", "station_weight")
    mean_delta["pred_grid_price"] = mean_delta["national_actual_price"] + mean_delta["pred_spread"]
    rows.append({"model_name": "baseline_train_mean_delta", **evaluate_prediction_frame(mean_delta, "validation")})

    return pd.DataFrame(rows)


def train_with_validation(
    train_df: pd.DataFrame,
    valid_df: pd.DataFrame,
    cfg: FuelConfig,
    out_dir: Path,
) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame, int]:
    train_model_df = sample_frame(train_df, SEQUENCE_MAX_TRAIN_ROWS, f"{cfg.fuel}_train_model")
    valid_model_df = sample_frame(valid_df, SEQUENCE_MAX_VALID_ROWS, f"{cfg.fuel}_valid_model")
    prep = fit_preprocess(train_model_df)

    model = SpreadDeltaLstm(input_size=len(SEQUENCE_CHANNELS)).to(DEVICE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=MODEL_LEARNING_RATE, weight_decay=MODEL_WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="min",
        factor=LR_REDUCE_FACTOR,
        patience=LR_REDUCE_PATIENCE,
        min_lr=MIN_LEARNING_RATE,
    )
    loader = make_loader(train_model_df, prep, MODEL_BATCH_SIZE, shuffle=True, include_target=True)

    print(
        f"[MODEL] {cfg.label}: train_rows={len(train_model_df):,}, valid_rows={len(valid_model_df):,}, "
        f"device={DEVICE}, seq_len={SEQUENCE_LENGTH_DAYS}, channels={len(SEQUENCE_CHANNELS)}, "
        f"epochs={MODEL_EPOCHS}, batch={MODEL_BATCH_SIZE}"
    )

    start = time.time()
    best_state: Optional[Dict[str, torch.Tensor]] = None
    best_wmae = float("inf")
    best_epoch = 0
    patience_left = EARLY_STOPPING_PATIENCE
    history: List[Dict[str, Any]] = []

    for epoch in range(1, MODEL_EPOCHS + 1):
        epoch_start = time.time()
        model.train()
        train_loss_sum = 0.0
        train_weight_sum = 0.0

        for xb, yb, wb in loader:
            xb = xb.to(DEVICE)
            yb = yb.to(DEVICE)
            wb = wb.to(DEVICE).clip(min=0)

            optimizer.zero_grad(set_to_none=True)
            pred = model(xb)
            loss_vec = F.smooth_l1_loss(pred, yb, reduction="none")
            denom = wb.sum().clamp(min=1.0)
            loss = (loss_vec * wb).sum() / denom
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), MODEL_GRAD_CLIP_NORM)
            optimizer.step()

            train_loss_sum += float((loss_vec.detach() * wb).sum().cpu())
            train_weight_sum += float(denom.detach().cpu())

        wrapper = {"model": model, "preprocess": prep}
        valid_pred = prediction_frame(valid_model_df, predict_delta(wrapper, valid_model_df))
        metrics = evaluate_prediction_frame(valid_pred, f"validation_epoch_{epoch}")
        valid_wmae = float(metrics["price_weighted_mae"])
        scheduler.step(valid_wmae)
        current_lr = float(optimizer.param_groups[0]["lr"])

        improved = valid_wmae < best_wmae - EARLY_STOPPING_MIN_DELTA
        if improved:
            best_wmae = valid_wmae
            best_epoch = epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            patience_left = EARLY_STOPPING_PATIENCE
        else:
            patience_left -= 1

        row = {
            "model_name": "lstm_spread_delta",
            "epoch": epoch,
            "device": str(DEVICE),
            "learning_rate": current_lr,
            "train_weighted_huber_scaled": train_loss_sum / max(train_weight_sum, 1.0),
            "epoch_seconds": round(time.time() - epoch_start, 2),
            "fit_seconds": round(time.time() - start, 2),
            "best_validation_weighted_mae_so_far": best_wmae,
            "best_epoch_so_far": best_epoch,
            **metrics,
        }
        history.append(row)

        print(
            f"[EPOCH] {cfg.label} {epoch:04d}: "
            f"train_loss={row['train_weighted_huber_scaled']:.5f}, "
            f"valid_wmae={valid_wmae:.4f}, best={best_wmae:.4f}@{best_epoch}, "
            f"lr={current_lr:.6g}, epoch={seconds_text(row['epoch_seconds'])}, "
            f"total={seconds_text(row['fit_seconds'])}, patience_left={patience_left}"
        )

        if patience_left <= 0:
            print(f"[EARLY STOP] {cfg.label}: no improvement for {EARLY_STOPPING_PATIENCE} epochs")
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    wrapper = {"model": model, "preprocess": prep}
    valid_full_pred = prediction_frame(valid_df, predict_delta(wrapper, valid_df))
    full_metrics = evaluate_prediction_frame(valid_full_pred, "validation_full_best_model")
    history_df = pd.DataFrame(history)
    history_path = out_dir / f"{cfg.fuel}_training_history.csv"
    history_df.to_csv(history_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {history_path}")

    validation_model_scores = pd.DataFrame(
        [
            {
                "model_name": "lstm_spread_delta",
                "best_epoch": best_epoch,
                "device": str(DEVICE),
                **full_metrics,
            }
        ]
    )
    return wrapper, history_df, validation_model_scores, max(best_epoch, 1)


def train_final_model(final_df: pd.DataFrame, cfg: FuelConfig, epochs: int, model_path: Path) -> Dict[str, Any]:
    final_model_df = sample_frame(final_df, SEQUENCE_MAX_FINAL_ROWS, f"{cfg.fuel}_final_model")
    prep = fit_preprocess(final_model_df)
    model = SpreadDeltaLstm(input_size=len(SEQUENCE_CHANNELS)).to(DEVICE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=MODEL_LEARNING_RATE, weight_decay=MODEL_WEIGHT_DECAY)
    loader = make_loader(final_model_df, prep, MODEL_BATCH_SIZE, shuffle=True, include_target=True)

    final_epochs = max(1, min(int(epochs) + FINAL_EXTRA_EPOCHS, FINAL_MAX_EPOCHS))
    print(
        f"[FINAL TRAIN] {cfg.label}: rows={len(final_model_df):,}, epochs={final_epochs}, "
        f"source_best_epoch={epochs}, device={DEVICE}"
    )
    start = time.time()
    for epoch in range(1, final_epochs + 1):
        epoch_start = time.time()
        model.train()
        train_loss_sum = 0.0
        train_weight_sum = 0.0
        for xb, yb, wb in loader:
            xb = xb.to(DEVICE)
            yb = yb.to(DEVICE)
            wb = wb.to(DEVICE).clip(min=0)

            optimizer.zero_grad(set_to_none=True)
            pred = model(xb)
            loss_vec = F.smooth_l1_loss(pred, yb, reduction="none")
            denom = wb.sum().clamp(min=1.0)
            loss = (loss_vec * wb).sum() / denom
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), MODEL_GRAD_CLIP_NORM)
            optimizer.step()

            train_loss_sum += float((loss_vec.detach() * wb).sum().cpu())
            train_weight_sum += float(denom.detach().cpu())

        print(
            f"[FINAL EPOCH] {cfg.label} {epoch:04d}/{final_epochs}: "
            f"train_loss={train_loss_sum / max(train_weight_sum, 1.0):.5f}, "
            f"epoch={seconds_text(time.time() - epoch_start)}, total={seconds_text(time.time() - start)}"
        )

    wrapper = {"model": model, "preprocess": prep}
    model_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_class": "SpreadDeltaLstm",
            "model_config": {
                "input_size": len(SEQUENCE_CHANNELS),
                "sequence_length_days": SEQUENCE_LENGTH_DAYS,
                "target_column": TARGET_COLUMN,
                "target_mode": MODEL_TARGET_MODE,
            },
            "preprocess": prep,
            "fuel_config": asdict(cfg),
            "policy_exclude_ranges": POLICY_EXCLUDE_RANGES,
            "test_start": str(TEST_START.date()),
            "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
        },
        model_path,
    )
    print(f"[SAVE] {model_path}")
    return wrapper


# =============================================================================
# Test prediction outputs
# =============================================================================


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
                AVG(pred_grid_price) AS pred_grid_price_mean_unweighted,
                SUM(pred_grid_price * station_weight) / NULLIF(SUM(station_weight), 0) AS pred_grid_price_mean_weighted,
                AVG(pred_spread) AS pred_spread_mean_unweighted,
                SUM(pred_spread * station_weight) / NULLIF(SUM(station_weight), 0) AS pred_spread_mean_weighted,
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
                AVG(pred_grid_price) AS pred_grid_price_mean,
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


def predict_test_2026(cfg: FuelConfig, wrapper: Dict[str, Any], out_dir: Path) -> pd.DataFrame:
    test_range = get_test_date_range(cfg)
    if test_range is None:
        print(f"[TEST] {cfg.label}: no 2026 rows")
        return pd.DataFrame()

    parts_dir = out_dir / "test_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: List[Path] = []
    metric_rows: List[Dict[str, Any]] = []

    for m_start, m_end in month_ranges(*test_range):
        chunk = load_model_frame(
            cfg=cfg,
            date_start=m_start,
            date_end=m_end,
            sample_per_mille=1000,
            sample_salt=f"{cfg.fuel}_test_full",
            max_rows=None,
            force_pre_2026=False,
            exclude_target_policy=False,
            exclude_history_policy=False,
            label=f"test_{m_start:%Y_%m}",
        )
        if len(chunk) == 0:
            continue
        if (chunk["date"] < TEST_START).any():
            raise AssertionError("test frame contains pre-2026 rows")

        pred = prediction_frame(chunk, predict_delta(wrapper, chunk))
        metric_rows.append(evaluate_prediction_frame(pred, f"test_{m_start:%Y_%m}"))

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
            "spread_target",
            TARGET_COLUMN,
            "spread_lag_1d",
            "pred_spread_delta",
            "pred_spread_raw",
            "pred_spread",
            "pred_grid_price",
            "prediction_error_to_actual",
        ]
        save_cols = [c for c in save_cols if c in pred.columns]
        part_path = parts_dir / f"{cfg.fuel}_test_predictions_2026_{m_start:%Y_%m}.parquet"
        pred[save_cols].to_parquet(part_path, index=False, compression="zstd")
        parts.append(part_path)
        print(f"[SAVE PART] {part_path} rows={len(pred):,}")

        del chunk, pred
        gc.collect()

    write_combined_prediction_outputs(out_dir, cfg, parts)

    metrics = pd.DataFrame(metric_rows)
    if len(metrics) and parts:
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
                AVG(ABS(spread_target - pred_spread)) AS spread_mae,
                SQRT(AVG(POWER(spread_target - pred_spread, 2))) AS spread_rmse,
                SUM(ABS(spread_target - pred_spread) * station_weight) / NULLIF(SUM(station_weight), 0) AS spread_weighted_mae,
                SQRT(SUM(POWER(spread_target - pred_spread, 2) * station_weight) / NULLIF(SUM(station_weight), 0)) AS spread_weighted_rmse,
                AVG(ABS(spread_delta_target - pred_spread_delta)) AS delta_mae,
                SQRT(AVG(POWER(spread_delta_target - pred_spread_delta, 2))) AS delta_rmse,
                SUM(ABS(spread_delta_target - pred_spread_delta) * station_weight) / NULLIF(SUM(station_weight), 0) AS delta_weighted_mae,
                SQRT(SUM(POWER(spread_delta_target - pred_spread_delta, 2) * station_weight) / NULLIF(SUM(station_weight), 0)) AS delta_weighted_rmse
            FROM read_parquet({qstr(out_dir / f'{cfg.fuel}_test_predictions_2026.parquet')})
            """
        ).df()
        metrics = pd.concat([metrics, all_test], ignore_index=True, sort=False)

    metrics_path = out_dir / f"{cfg.fuel}_test_metrics_2026.csv"
    metrics.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {metrics_path}")
    return metrics


# =============================================================================
# Main pipeline
# =============================================================================


def run_one_fuel(cfg: FuelConfig) -> Dict[str, Any]:
    out_dir = OUTPUT_ROOT / cfg.fuel
    model_dir = out_dir / "model"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 120)
    print(f"[START] {cfg.label} model")
    print("=" * 120)

    split = train_validation_split(cfg)
    print(
        f"[SPLIT] train={split['train_eligible_rows_full']:,} "
        f"({split['actual_train_ratio_after_gap']:.2%}) / "
        f"validation={split['valid_eligible_rows_full']:,} "
        f"({split['actual_valid_ratio_after_gap']:.2%}), gap_rows={split['gap_eligible_rows']:,}"
    )
    print(
        f"[SPLIT] train dates={split['train_eligible_date_min'].date()}~{split['train_eligible_date_max'].date()}, "
        f"validation dates={split['valid_eligible_date_min'].date()}~{split['valid_eligible_date_max'].date()}"
    )
    print("[SPLIT] train/validation/final_train exclude target policy dates and policy dates inside 29-day input history")
    print(f"[SPLIT] final_train target_date < {TEST_START.date()} / test target_date >= {TEST_START.date()}")

    train_df = load_model_frame(
        cfg=cfg,
        date_start=None,
        date_end=split["train_end"],
        sample_per_mille=TRAIN_SAMPLE_PER_MILLE,
        sample_salt=f"{cfg.fuel}_train",
        max_rows=MAX_TRAIN_ROWS_PER_FUEL,
        force_pre_2026=True,
        exclude_target_policy=True,
        exclude_history_policy=True,
        label="train",
    )
    valid_df = load_model_frame(
        cfg=cfg,
        date_start=split["valid_start"],
        date_end=split["valid_end"],
        sample_per_mille=VALID_SAMPLE_PER_MILLE,
        sample_salt=f"{cfg.fuel}_valid",
        max_rows=MAX_VALID_ROWS_PER_FUEL,
        force_pre_2026=True,
        exclude_target_policy=True,
        exclude_history_policy=True,
        label="validation",
    )
    if len(train_df) == 0 or len(valid_df) == 0:
        raise RuntimeError(f"{cfg.label}: train or validation frame is empty")

    baseline_df = baseline_scores(train_df, valid_df)
    wrapper, history_df, model_score_df, best_epoch = train_with_validation(train_df, valid_df, cfg, out_dir)
    validation_scores = pd.concat([baseline_df, model_score_df], ignore_index=True, sort=False)
    validation_scores_path = out_dir / f"{cfg.fuel}_validation_scores.csv"
    validation_scores.to_csv(validation_scores_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {validation_scores_path}")
    print(validation_scores.sort_values("price_weighted_mae")[["model_name", "price_weighted_mae", "delta_weighted_mae"]].to_string(index=False))

    valid_pred = prediction_frame(valid_df, predict_delta(wrapper, valid_df))
    valid_pred_path = out_dir / f"{cfg.fuel}_validation_predictions.parquet"
    valid_pred.to_parquet(valid_pred_path, index=False, compression="zstd")
    print(f"[SAVE] {valid_pred_path}")

    del train_df
    gc.collect()

    final_df = load_model_frame(
        cfg=cfg,
        date_start=None,
        date_end=TEST_START - pd.Timedelta(days=1),
        sample_per_mille=TRAIN_SAMPLE_PER_MILLE,
        sample_salt=f"{cfg.fuel}_final_train",
        max_rows=MAX_FINAL_TRAIN_ROWS_PER_FUEL,
        force_pre_2026=True,
        exclude_target_policy=True,
        exclude_history_policy=True,
        label="final_train_pre_2026",
    )
    model_path = model_dir / f"{cfg.fuel}_spread_delta_lstm.pt"
    final_wrapper = train_final_model(final_df, cfg, best_epoch, model_path)

    test_metrics = predict_test_2026(cfg, final_wrapper, out_dir)

    metadata = {
        "created_at": pd.Timestamp.now().isoformat(),
        "config": asdict(cfg),
        "grid_path": str(GRID_PATH),
        "output_dir": str(out_dir),
        "model_path": str(model_path),
        "test_start": str(TEST_START.date()),
        "prediction_horizon_days": PREDICTION_HORIZON_DAYS,
        "target_definition": "spread_delta_target = spread_target - spread_lag_1d",
        "prediction_definition": "pred_spread = spread_lag_1d + predicted_spread_delta; pred_grid_price = national_actual_price + pred_spread",
        "train_valid_train_ratio_requested": TRAIN_VALID_TRAIN_RATIO,
        "gap_days": GAP_DAYS,
        "policy_exclude_ranges": POLICY_EXCLUDE_RANGES,
        "train_validation_split": split,
        "sequence_length_days": SEQUENCE_LENGTH_DAYS,
        "sequence_required_history_days": SEQUENCE_REQUIRED_HISTORY_DAYS,
        "sequence_channels": SEQUENCE_CHANNELS,
        "device": str(DEVICE),
        "model_epochs": MODEL_EPOCHS,
        "best_epoch": best_epoch,
        "batch_size": MODEL_BATCH_SIZE,
        "learning_rate": MODEL_LEARNING_RATE,
        "early_stopping_patience": EARLY_STOPPING_PATIENCE,
        "early_stopping_min_delta": EARLY_STOPPING_MIN_DELTA,
        "validation_scores_path": str(validation_scores_path),
        "validation_predictions_path": str(valid_pred_path),
        "training_history_path": str(out_dir / f"{cfg.fuel}_training_history.csv"),
    }
    metadata_path = out_dir / f"{cfg.fuel}_model_metadata.json"
    save_json(metadata_path, metadata)
    print(f"[SAVE] {metadata_path}")

    summary = {
        "fuel": cfg.fuel,
        "label": cfg.label,
        "best_epoch": best_epoch,
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "validation_best_price_weighted_mae": float(model_score_df["price_weighted_mae"].iloc[0]),
        "test_2026_price_weighted_mae": float(
            test_metrics.loc[test_metrics["period"].astype(str).eq("test_2026_all"), "price_weighted_mae"].iloc[0]
        )
        if isinstance(test_metrics, pd.DataFrame)
        and len(test_metrics)
        and "period" in test_metrics.columns
        and test_metrics["period"].astype(str).eq("test_2026_all").any()
        else float("nan"),
    }

    del valid_df, valid_pred, final_df
    gc.collect()
    if USE_CUDA:
        torch.cuda.empty_cache()
    return summary


def main() -> None:
    print("[CONFIG]")
    print(f"REPO_ROOT                  = {REPO_ROOT}")
    print(f"GRID_PATH                  = {GRID_PATH}")
    print(f"OUTPUT_ROOT                = {OUTPUT_ROOT}")
    print(f"TEST_START                 = {TEST_START.date()}")
    print(f"PREDICTION_HORIZON_DAYS    = {PREDICTION_HORIZON_DAYS}")
    print(f"TARGET_COLUMN              = {TARGET_COLUMN}")
    print(f"RUN_FUELS                  = {', '.join(RUN_FUELS)}")
    print(f"DEVICE                     = {DEVICE}")
    print(f"MODEL_INPUT_CHANNELS       = {list(SEQUENCE_CHANNELS.keys())}")
    print(f"TRAIN/VALID SAMPLE         = {TRAIN_SAMPLE_PER_MILLE}/1000, {VALID_SAMPLE_PER_MILLE}/1000")
    print(f"MAX TRAIN/VALID ROWS       = {MAX_TRAIN_ROWS_PER_FUEL:,}, {MAX_VALID_ROWS_PER_FUEL:,}")
    print(f"MAX FINAL TRAIN ROWS       = {MAX_FINAL_TRAIN_ROWS_PER_FUEL:,}")

    overview = con.execute(
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
    print("[PANEL OVERVIEW]")
    print(overview.to_string(index=False))

    summaries = []
    for fuel_key in RUN_FUELS:
        summaries.append(run_one_fuel(FUEL_CONFIG[fuel_key]))

    summary_df = pd.DataFrame(summaries)
    summary_path = OUTPUT_ROOT / "model_run_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print("\n[SUMMARY]")
    print(summary_df.to_string(index=False))
    print(f"[SAVE] {summary_path}")


if __name__ == "__main__":
    main()
