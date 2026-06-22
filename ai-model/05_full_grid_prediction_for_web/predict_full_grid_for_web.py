from __future__ import annotations

import argparse
import calendar
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE5_DIR = Path(__file__).resolve().parent
STAGE4_DIR = REPO_ROOT / "ai-model" / "04_prediction_model_training"

DEFAULT_TARGET_DATASET = REPO_ROOT / "ai-model" / "03_target_dataset_build" / "outputs" / "grid_target.parquet"
DEFAULT_OUTPUT_DIR = STAGE5_DIR / "outputs"
DEFAULT_GEOJSON = REPO_ROOT / "page" / "public" / "assets" / "korea-provinces.geojson"

MODEL_NAME = "hybrid_grid_fair_price_delta_lstm"
TARGET_COLUMN = "fair_price_delta_target"
PREDICTED_TARGET_COLUMN = "pred_fair_price_delta"
PREDICTION_HORIZON_DAYS = 1
SEQUENCE_REQUIRED_HISTORY_DAYS = 29

FUEL_CONFIGS = {
    "gasoline": {
        "fuel": "gasoline",
        "label": "휘발유",
        "actual_col": "gasoline_price_mean",
        "station_count_col": "gasoline_station_count",
        "fair_target_col": "gasoline_grid_fair_price_target",
        "national_actual_col": "gasoline_national_actual_price_grid",
        "band_low_col": "gasoline_grid_fair_band_low_policy",
        "band_high_col": "gasoline_grid_fair_band_high_policy",
        "model_path": STAGE4_DIR / "outputs" / "gasoline" / "model" / "gasoline_grid_fair_price_delta_lstm.pt",
    },
    "diesel": {
        "fuel": "diesel",
        "label": "경유",
        "actual_col": "diesel_price_mean",
        "station_count_col": "diesel_station_count",
        "fair_target_col": "diesel_grid_fair_price_target",
        "national_actual_col": "diesel_national_actual_price_grid",
        "band_low_col": "diesel_grid_fair_band_low_policy",
        "band_high_col": "diesel_grid_fair_band_high_policy",
        "model_path": STAGE4_DIR / "outputs" / "diesel" / "model" / "diesel_grid_fair_price_delta_lstm.pt",
    },
}

REGION_SHORT_NAMES = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라북도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주특별자치도": "제주",
}


@dataclass(frozen=True)
class FuelConfig:
    fuel: str
    label: str
    actual_col: str
    station_count_col: str
    fair_target_col: str
    national_actual_col: str
    band_low_col: str
    band_high_col: str
    model_path: Path

    @classmethod
    def from_name(cls, fuel: str, model_path: Path | None = None) -> "FuelConfig":
        spec = dict(FUEL_CONFIGS[fuel])
        if model_path is not None:
            spec["model_path"] = model_path
        return cls(**spec)


@dataclass
class ModelBundle:
    fuel: str
    model: "PriceDeltaHybridLstm"
    preprocess: dict[str, Any]
    sequence_channels: dict[str, list[str]]
    latest_feature_columns: list[str]
    static_feature_columns: list[str]
    model_path: Path
    payload: dict[str, Any]


class PriceDeltaHybridLstm(nn.Module):
    def __init__(
        self,
        sequence_input_size: int,
        latest_input_size: int,
        static_input_size: int,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.20,
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=sequence_input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
            bidirectional=True,
        )
        self.latest_net = nn.Sequential(
            nn.Linear(latest_input_size, 32),
            nn.LayerNorm(32),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.static_net = nn.Sequential(
            nn.Linear(static_input_size, 32),
            nn.LayerNorm(32),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size * 2 + 64, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, seq: torch.Tensor, latest: torch.Tensor, static: torch.Tensor) -> torch.Tensor:
        _, (h_n, _) = self.lstm(seq)
        h = torch.cat([h_n[-2], h_n[-1]], dim=1)
        latest_h = self.latest_net(latest)
        static_h = self.static_net(static)
        return self.head(torch.cat([h, latest_h, static_h], dim=1)).squeeze(1)


def qid(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def qstr(value: Any) -> str:
    return "'" + str(value).replace("\\", "/").replace("'", "''") + "'"


def sql_date(value: str | pd.Timestamp) -> str:
    return f"DATE {qstr(pd.Timestamp(value).strftime('%Y-%m-%d'))}"


def seconds_text(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run AI 04 grid fair-price models over the full AI 03 grid_target.parquet "
            "and write location-attached outputs for web use."
        )
    )
    parser.add_argument("--target-dataset", type=Path, default=DEFAULT_TARGET_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    parser.add_argument("--fuel", choices=["all", "gasoline", "diesel"], default="all")
    parser.add_argument("--gasoline-model", type=Path, default=FUEL_CONFIGS["gasoline"]["model_path"])
    parser.add_argument("--diesel-model", type=Path, default=FUEL_CONFIGS["diesel"]["model_path"])
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--threads", type=int, default=max(os.cpu_count() or 2, 2))
    parser.add_argument("--limit-per-chunk", type=int, default=None, help="Debug only: cap rows per month chunk.")
    parser.add_argument("--no-region", action="store_true", help="Skip GeoJSON region attachment.")
    parser.add_argument("--force-region-lookup", action="store_true", help="Rebuild grid_id to region lookup.")
    return parser.parse_args()


def selected_fuels(args: argparse.Namespace) -> list[FuelConfig]:
    model_overrides = {
        "gasoline": args.gasoline_model,
        "diesel": args.diesel_model,
    }
    names = ["gasoline", "diesel"] if args.fuel == "all" else [args.fuel]
    return [FuelConfig.from_name(name, model_overrides[name]) for name in names]


def resolve_device(value: str) -> torch.device:
    if value == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda requested, but CUDA is not available.")
        return torch.device("cuda")
    if value == "cpu":
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def torch_load(path: Path, device: torch.device) -> dict[str, Any]:
    try:
        payload = torch.load(path, map_location=device, weights_only=False)
    except TypeError:
        payload = torch.load(path, map_location=device)
    if not isinstance(payload, dict) or "model_state_dict" not in payload:
        raise ValueError(f"Unexpected model payload: {path}")
    return payload


def load_model_bundle(cfg: FuelConfig, device: torch.device) -> ModelBundle:
    if not cfg.model_path.exists():
        raise FileNotFoundError(f"Missing model file for {cfg.fuel}: {cfg.model_path}")

    payload = torch_load(cfg.model_path, device)
    preprocess = payload.get("preprocess")
    if not isinstance(preprocess, dict):
        raise ValueError(f"Missing preprocess block in model: {cfg.model_path}")

    model_config = payload.get("model_config", {})
    sequence_channels = (
        model_config.get("sequence_channels")
        or preprocess.get("sequence_channels")
        or {}
    )
    latest_cols = (
        model_config.get("latest_feature_columns")
        or preprocess.get("latest_feature_columns")
        or []
    )
    static_cols = (
        model_config.get("static_feature_columns")
        or preprocess.get("static_feature_columns")
        or []
    )

    model = PriceDeltaHybridLstm(
        sequence_input_size=int(model_config.get("sequence_input_size", len(sequence_channels))),
        latest_input_size=int(model_config.get("latest_input_size", len(latest_cols))),
        static_input_size=int(model_config.get("static_input_size", len(static_cols))),
        hidden_size=int(model_config.get("hidden_size", 128)),
        num_layers=int(model_config.get("num_layers", 2)),
        dropout=float(model_config.get("dropout", 0.20)),
    ).to(device)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()

    return ModelBundle(
        fuel=cfg.fuel,
        model=model,
        preprocess=preprocess,
        sequence_channels={str(k): list(v) for k, v in sequence_channels.items()},
        latest_feature_columns=[str(c) for c in latest_cols],
        static_feature_columns=[str(c) for c in static_cols],
        model_path=cfg.model_path,
        payload=payload,
    )


def schema_columns(con: duckdb.DuckDBPyConnection, target_dataset: Path) -> list[str]:
    df = con.execute(f"DESCRIBE SELECT * FROM read_parquet({qstr(target_dataset)}) LIMIT 0").df()
    return df["column_name"].astype(str).tolist()


def history_sql_exprs(sequence_length: int) -> list[str]:
    exprs: list[str] = []
    frame = (
        "PARTITION BY grid_id ORDER BY target_date "
        f"ROWS BETWEEN {SEQUENCE_REQUIRED_HISTORY_DAYS} PRECEDING AND 1 PRECEDING"
    )
    exprs.extend(
        [
            f"COUNT(spread_target) OVER ({frame}) AS sequence_hist_count",
            (
                "date_diff('day', "
                f"LAG(target_date, {SEQUENCE_REQUIRED_HISTORY_DAYS}) "
                "OVER (PARTITION BY grid_id ORDER BY target_date), "
                "target_date) AS sequence_calendar_span"
            ),
            "LAG(spread_target, 1) OVER (PARTITION BY grid_id ORDER BY target_date) AS spread_lag_1d",
            "LAG(actual_grid_price, 1) OVER (PARTITION BY grid_id ORDER BY target_date) AS actual_price_lag_1d",
            "LAG(national_actual_price, 1) OVER (PARTITION BY grid_id ORDER BY target_date) AS national_price_lag_1d",
            "LAG(station_weight, 1) OVER (PARTITION BY grid_id ORDER BY target_date) AS station_weight_lag_1d",
        ]
    )
    for d in range(1, sequence_length + 1):
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
            ]
        )
    return exprs


def first_sequence_length(sequence_channels: dict[str, list[str]]) -> int:
    lengths = [len(cols) for cols in sequence_channels.values()]
    if not lengths or len(set(lengths)) != 1:
        raise ValueError(f"Invalid sequence channel shape: {sequence_channels}")
    return lengths[0]


def null_double(alias: str) -> str:
    return f"CAST(NULL AS DOUBLE) AS {qid(alias)}"


def static_feature_exprs(static_cols: list[str], all_columns: set[str]) -> list[str]:
    exprs: list[str] = []
    for col in static_cols:
        if col == "official_price_age_days":
            exprs.append(
                "CASE WHEN p.official_price_source_date IS NULL THEN NULL ELSE "
                "CAST(date_diff('day', CAST(p.official_price_source_date AS DATE), CAST(t.feature_date AS DATE)) AS DOUBLE) "
                "END AS official_price_age_days"
            )
        elif col == "official_price_source_year":
            exprs.append(
                "CASE WHEN p.official_price_source_date IS NULL THEN NULL ELSE "
                "CAST(year(CAST(p.official_price_source_date AS DATE)) AS DOUBLE) "
                "END AS official_price_source_year"
            )
        elif col in all_columns:
            exprs.append(f"CAST(p.{qid(col)} AS DOUBLE) AS {qid(col)}")
        else:
            exprs.append(null_double(col))
    return exprs


def selected_column_exprs(bundle: ModelBundle, all_columns: set[str]) -> list[str]:
    exprs = [
        "t.target_date AS date",
        "t.feature_date AS feature_date",
        "t.grid_id",
        "t.actual_grid_price",
        "t.grid_fair_price_target",
        "t.grid_fair_band_low_policy",
        "t.grid_fair_band_high_policy",
        "t.station_weight",
        "t.national_actual_price",
        "t.spread_target",
        "(CAST(t.grid_fair_price_target AS DOUBLE) - CAST(t.national_actual_price AS DOUBLE)) AS fair_spread_target",
        "(CAST(t.grid_fair_price_target AS DOUBLE) - CAST(t.actual_price_lag_1d AS DOUBLE)) AS fair_price_delta_target",
        "CAST(t.spread_lag_1d AS DOUBLE) AS spread_lag_1d",
        "CAST(t.actual_price_lag_1d AS DOUBLE) AS actual_price_lag_1d",
        "CAST(t.national_price_lag_1d AS DOUBLE) AS national_price_lag_1d",
        "CAST(t.station_weight_lag_1d AS DOUBLE) AS station_weight_lag_1d",
        "CAST(t.sequence_hist_count AS DOUBLE) AS sequence_hist_count",
        "CAST(t.sequence_calendar_span AS DOUBLE) AS sequence_calendar_span",
    ]
    for col in [c for cols in bundle.sequence_channels.values() for c in cols]:
        exprs.append(f"CAST(t.{qid(col)} AS DOUBLE) AS {qid(col)}")
    exprs.extend(static_feature_exprs(bundle.static_feature_columns, all_columns))
    for col in ["cell_x", "cell_y", "center_lon", "center_lat"]:
        if col in all_columns and col not in bundle.static_feature_columns:
            exprs.append(f"p.{qid(col)} AS {qid(col)}")
    return exprs


def sequence_quality_conditions(bundle: ModelBundle) -> list[str]:
    model_input_cols = [c for cols in bundle.sequence_channels.values() for c in cols]
    conds = [
        f"t.sequence_hist_count = {SEQUENCE_REQUIRED_HISTORY_DAYS}",
        f"t.sequence_calendar_span = {SEQUENCE_REQUIRED_HISTORY_DAYS}",
        "t.spread_lag_1d IS NOT NULL",
        "t.actual_price_lag_1d IS NOT NULL",
        "t.national_price_lag_1d IS NOT NULL",
        "t.station_weight_lag_1d IS NOT NULL",
    ]
    conds.extend([f"t.{qid(col)} IS NOT NULL" for col in model_input_cols])
    return conds


def date_conditions(start: str | None, end: str | None) -> list[str]:
    conds: list[str] = []
    if start:
        conds.append(f"t.target_date >= {sql_date(start)}")
    if end:
        conds.append(f"t.target_date <= {sql_date(end)}")
    return conds


def source_date_conditions(start: str | None, end: str | None) -> list[str]:
    conds: list[str] = []
    if start:
        source_start = pd.Timestamp(start) - pd.Timedelta(days=SEQUENCE_REQUIRED_HISTORY_DAYS)
        conds.append(f"CAST(date AS DATE) >= {sql_date(source_start)}")
    if end:
        conds.append(f"CAST(date AS DATE) <= {sql_date(end)}")
    return conds


def build_model_frame_query(
    target_dataset: Path,
    cfg: FuelConfig,
    bundle: ModelBundle,
    all_columns: set[str],
    start: str | None,
    end: str | None,
    limit: int | None,
) -> str:
    sequence_length = first_sequence_length(bundle.sequence_channels)
    history_exprs = ",\n                ".join(history_sql_exprs(sequence_length))
    select_sql = ",\n            ".join(selected_column_exprs(bundle, all_columns))
    where_sql = " AND\n              ".join(date_conditions(start, end) + sequence_quality_conditions(bundle))
    raw_conds = source_date_conditions(start, end)
    raw_where_sql = "\n            WHERE " + " AND ".join(raw_conds) if raw_conds else ""
    limit_sql = f"\n        ORDER BY date, grid_id\n        LIMIT {int(limit)}" if limit else ""

    band_low_expr = (
        f"CAST({qid(cfg.band_low_col)} AS DOUBLE) AS grid_fair_band_low_policy"
        if cfg.band_low_col in all_columns
        else null_double("grid_fair_band_low_policy")
    )
    band_high_expr = (
        f"CAST({qid(cfg.band_high_col)} AS DOUBLE) AS grid_fair_band_high_policy"
        if cfg.band_high_col in all_columns
        else null_double("grid_fair_band_high_policy")
    )

    return f"""
        WITH raw AS (
            SELECT CAST(date AS DATE) AS date_key, *
            FROM read_parquet({qstr(target_dataset)})
            {raw_where_sql}
        ),
        target_rows AS (
            SELECT
                date_key AS target_date,
                date_key - INTERVAL {PREDICTION_HORIZON_DAYS} DAY AS feature_date,
                grid_id,
                CAST({qid(cfg.actual_col)} AS DOUBLE) AS actual_grid_price,
                CAST({qid(cfg.fair_target_col)} AS DOUBLE) AS grid_fair_price_target,
                {band_low_expr},
                {band_high_expr},
                CAST({qid(cfg.station_count_col)} AS DOUBLE) AS station_weight,
                CAST({qid(cfg.national_actual_col)} AS DOUBLE) AS national_actual_price
            FROM raw
            WHERE {qid(cfg.actual_col)} IS NOT NULL
              AND {qid(cfg.fair_target_col)} IS NOT NULL
              AND {qid(cfg.national_actual_col)} IS NOT NULL
              AND CAST({qid(cfg.station_count_col)} AS DOUBLE) > 0
        ),
        spread_all AS (
            SELECT
                t.*,
                t.actual_grid_price - t.national_actual_price AS spread_target
            FROM target_rows t
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
        {limit_sql}
    """


def available_date_range(
    con: duckdb.DuckDBPyConnection,
    target_dataset: Path,
    cfg: FuelConfig,
    start: str | None,
    end: str | None,
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    conds = [
        f"{qid(cfg.actual_col)} IS NOT NULL",
        f"{qid(cfg.fair_target_col)} IS NOT NULL",
        f"{qid(cfg.national_actual_col)} IS NOT NULL",
        f"CAST({qid(cfg.station_count_col)} AS DOUBLE) > 0",
    ]
    if start:
        conds.append(f"CAST(date AS DATE) >= {sql_date(start)}")
    if end:
        conds.append(f"CAST(date AS DATE) <= {sql_date(end)}")
    cond_sql = " AND ".join(conds)
    row = con.execute(
        f"""
        SELECT MIN(CAST(date AS DATE)) AS date_min, MAX(CAST(date AS DATE)) AS date_max
        FROM read_parquet({qstr(target_dataset)})
        WHERE {cond_sql}
        """
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return pd.Timestamp(row[0]), pd.Timestamp(row[1])


def month_ranges(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    cur = pd.Timestamp(start).replace(day=1)
    while cur <= end:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        month_end = pd.Timestamp(year=cur.year, month=cur.month, day=last_day)
        ranges.append((max(cur, start), min(month_end, end)))
        cur = month_end + pd.Timedelta(days=1)
    return ranges


def ensure_numeric_frame(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
    return df


def raw_feature_array(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    if not cols:
        return np.zeros((len(df), 0), dtype="float32")
    ensure_numeric_frame(df, cols)
    return df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype="float32")


def raw_sequence_array(df: pd.DataFrame, sequence_channels: dict[str, list[str]]) -> np.ndarray:
    channel_arrays = []
    for cols in sequence_channels.values():
        channel_arrays.append(raw_feature_array(df, cols))
    return np.stack(channel_arrays, axis=-1)


def normalized_feature_array(df: pd.DataFrame, prep: dict[str, Any], key: str, cols: list[str]) -> np.ndarray:
    arr = raw_feature_array(df, cols)
    mean = np.asarray(prep[f"{key}_mean"], dtype="float32").reshape(1, -1)
    std = np.asarray(prep[f"{key}_std"], dtype="float32").reshape(1, -1)
    arr = ((arr - mean) / std).astype("float32")
    return np.where(np.isfinite(arr), arr, 0.0).astype("float32")


def inference_arrays(df: pd.DataFrame, bundle: ModelBundle) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    prep = bundle.preprocess
    seq = raw_sequence_array(df, bundle.sequence_channels)
    seq_mean = np.asarray(prep["seq_mean"], dtype="float32").reshape(1, 1, -1)
    seq_std = np.asarray(prep["seq_std"], dtype="float32").reshape(1, 1, -1)
    seq = ((seq - seq_mean) / seq_std).astype("float32")
    seq = np.where(np.isfinite(seq), seq, 0.0).astype("float32")
    latest = normalized_feature_array(df, prep, "latest", bundle.latest_feature_columns)
    static = normalized_feature_array(df, prep, "static", bundle.static_feature_columns)
    return seq, latest, static


def predict_delta(bundle: ModelBundle, df: pd.DataFrame, device: torch.device, batch_size: int) -> np.ndarray:
    seq, latest, static = inference_arrays(df, bundle)
    loader = DataLoader(
        TensorDataset(torch.from_numpy(seq), torch.from_numpy(latest), torch.from_numpy(static)),
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )

    preds: list[np.ndarray] = []
    bundle.model.eval()
    with torch.no_grad():
        for xb, latestb, staticb in loader:
            raw = bundle.model(xb.to(device), latestb.to(device), staticb.to(device)).detach().cpu().numpy()
            preds.append(raw)
    scaled = np.concatenate(preds) if preds else np.array([], dtype="float32")
    return scaled * float(bundle.preprocess["y_std"]) + float(bundle.preprocess["y_mean"])


def add_predictions(df: pd.DataFrame, cfg: FuelConfig, pred_delta: np.ndarray) -> pd.DataFrame:
    out_cols = [
        "date",
        "feature_date",
        "grid_id",
        "cell_x",
        "cell_y",
        "center_lon",
        "center_lat",
        "region",
        "station_weight",
        "actual_grid_price",
        "grid_fair_price_target",
        "grid_fair_band_low_policy",
        "grid_fair_band_high_policy",
        "national_actual_price",
        "spread_target",
        "fair_spread_target",
        TARGET_COLUMN,
        "spread_lag_1d",
        "actual_price_lag_1d",
        "national_price_lag_1d",
    ]
    keep = [col for col in out_cols if col in df.columns]
    out = df[keep].copy()
    if "region" not in out.columns:
        out["region"] = None
    out.insert(0, "fuel", cfg.fuel)
    out.insert(1, "fuel_label", cfg.label)
    out[PREDICTED_TARGET_COLUMN] = np.asarray(pred_delta, dtype=float)
    out["pred_grid_fair_price"] = pd.to_numeric(out["actual_price_lag_1d"], errors="coerce") + out[PREDICTED_TARGET_COLUMN]
    out["pred_fair_spread"] = out["pred_grid_fair_price"] - out["national_actual_price"]
    out["prediction_error_to_target"] = out["pred_grid_fair_price"] - out["grid_fair_price_target"]
    out["actual_gap_to_target_fair"] = out["actual_grid_price"] - out["grid_fair_price_target"]
    out["actual_gap_to_pred_fair"] = out["actual_grid_price"] - out["pred_grid_fair_price"]

    if {"grid_fair_band_low_policy", "grid_fair_band_high_policy", "grid_fair_price_target"}.issubset(out.columns):
        band_shift = out["pred_grid_fair_price"] - out["grid_fair_price_target"]
        out["pred_band_low_policy"] = out["grid_fair_band_low_policy"] + band_shift
        out["pred_band_high_policy"] = out["grid_fair_band_high_policy"] + band_shift
    else:
        out["pred_band_low_policy"] = np.nan
        out["pred_band_high_policy"] = np.nan

    actual = pd.to_numeric(out["actual_grid_price"], errors="coerce")
    low = pd.to_numeric(out["pred_band_low_policy"], errors="coerce")
    high = pd.to_numeric(out["pred_band_high_policy"], errors="coerce")
    pred = pd.to_numeric(out["pred_grid_fair_price"], errors="coerce")
    out["pred_judge_policy"] = np.select(
        [actual > high, actual < low, low.notna() & high.notna(), actual > pred, actual < pred],
        ["비쌈", "저렴", "적정", "비쌈", "저렴"],
        default="적정",
    )
    return out


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    x1, y1 = ring[0]
    for i in range(1, n + 1):
        x2, y2 = ring[i % n]
        crosses = (y1 > lat) != (y2 > lat)
        if crosses:
            x_at_lat = (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1
            if lon < x_at_lat:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def point_in_polygon(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon or not point_in_ring(lon, lat, polygon[0]):
        return False
    for hole in polygon[1:]:
        if point_in_ring(lon, lat, hole):
            return False
    return True


def geometry_polygons(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
    if not geometry:
        return []
    if geometry.get("type") == "Polygon":
        return [geometry.get("coordinates") or []]
    if geometry.get("type") == "MultiPolygon":
        return geometry.get("coordinates") or []
    return []


def polygon_bbox(polygons: list[list[list[list[float]]]]) -> tuple[float, float, float, float]:
    coords: list[list[float]] = []
    for poly in polygons:
        for ring in poly:
            coords.extend(ring)
    if not coords:
        return (math.nan, math.nan, math.nan, math.nan)
    xs = [float(p[0]) for p in coords]
    ys = [float(p[1]) for p in coords]
    return (min(xs), min(ys), max(xs), max(ys))


def load_region_features(geojson_path: Path) -> list[dict[str, Any]]:
    obj = json.loads(geojson_path.read_text(encoding="utf-8"))
    features = []
    for feature in obj.get("features", []):
        props = feature.get("properties", {})
        name = props.get("name") or props.get("NAME") or props.get("CTP_KOR_NM")
        region = REGION_SHORT_NAMES.get(str(name), str(name) if name else None)
        polygons = geometry_polygons(feature.get("geometry", {}))
        bbox = polygon_bbox(polygons)
        if region and polygons:
            features.append({"region": region, "bbox": bbox, "polygons": polygons})
    return features


def find_region(lon: Any, lat: Any, features: list[dict[str, Any]]) -> str | None:
    try:
        x = float(lon)
        y = float(lat)
    except Exception:
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    for feature in features:
        min_x, min_y, max_x, max_y = feature["bbox"]
        if x < min_x or x > max_x or y < min_y or y > max_y:
            continue
        for polygon in feature["polygons"]:
            if point_in_polygon(x, y, polygon):
                return feature["region"]
    return None


def build_region_lookup(
    con: duckdb.DuckDBPyConnection,
    target_dataset: Path,
    geojson_path: Path,
    lookup_path: Path,
    force: bool,
) -> pd.DataFrame:
    if lookup_path.exists() and not force:
        return pd.read_csv(lookup_path, encoding="utf-8-sig")
    if not geojson_path.exists():
        print(f"[WARN] GeoJSON not found; region will be skipped: {geojson_path}")
        return pd.DataFrame(columns=["grid_id", "region"])

    print("[REGION] building grid_id -> region lookup")
    features = load_region_features(geojson_path)
    grids = con.execute(
        f"""
        SELECT
            grid_id,
            MAX(CAST(center_lon AS DOUBLE)) AS center_lon,
            MAX(CAST(center_lat AS DOUBLE)) AS center_lat
        FROM read_parquet({qstr(target_dataset)})
        WHERE center_lon IS NOT NULL AND center_lat IS NOT NULL
        GROUP BY grid_id
        ORDER BY grid_id
        """
    ).df()
    grids["region"] = [find_region(lon, lat, features) for lon, lat in zip(grids["center_lon"], grids["center_lat"])]
    out = grids[["grid_id", "region"]].copy()
    lookup_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(lookup_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {lookup_path} rows={len(out):,}, matched={out['region'].notna().sum():,}")
    return out


def weighted_sql(expr: str, weight: str = "station_weight") -> str:
    return f"SUM({expr} * {weight}) / NULLIF(SUM({weight}), 0)"


def write_combined_outputs(con: duckdb.DuckDBPyConnection, out_dir: Path, cfg: FuelConfig, parts: list[Path], has_region: bool) -> dict[str, Path]:
    if not parts:
        return {}
    parts_sql = "[" + ", ".join(qstr(path) for path in parts) + "]"
    fuel_dir = out_dir / cfg.fuel
    full_path = fuel_dir / f"{cfg.fuel}_grid_fair_price_predictions_full.parquet"
    daily_path = fuel_dir / f"{cfg.fuel}_daily_summary.csv"
    grid_path = fuel_dir / f"{cfg.fuel}_grid_summary.csv"
    latest_grid_path = fuel_dir / f"{cfg.fuel}_latest_grid_predictions.csv"
    region_path = fuel_dir / f"{cfg.fuel}_region_daily_summary.csv"

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM read_parquet({parts_sql})
            ORDER BY date, grid_id
        ) TO {qstr(full_path)} (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

    con.execute(
        f"""
        COPY (
            SELECT
                date,
                fuel,
                fuel_label,
                COUNT(*) AS grid_rows,
                SUM(station_weight) AS station_weight_sum,
                AVG(actual_grid_price) AS actual_grid_price_mean_unweighted,
                {weighted_sql("actual_grid_price")} AS actual_grid_price_mean_weighted,
                AVG(pred_grid_fair_price) AS pred_grid_fair_price_mean_unweighted,
                {weighted_sql("pred_grid_fair_price")} AS pred_grid_fair_price_mean_weighted,
                AVG(pred_band_low_policy) AS pred_band_low_mean_unweighted,
                {weighted_sql("pred_band_low_policy")} AS pred_band_low_mean_weighted,
                AVG(pred_band_high_policy) AS pred_band_high_mean_unweighted,
                {weighted_sql("pred_band_high_policy")} AS pred_band_high_mean_weighted,
                AVG(actual_gap_to_pred_fair) AS gap_to_pred_fair_mean_unweighted,
                {weighted_sql("actual_gap_to_pred_fair")} AS gap_to_pred_fair_mean_weighted,
                AVG(grid_fair_price_target) AS target_fair_mean_unweighted,
                {weighted_sql("grid_fair_price_target")} AS target_fair_mean_weighted,
                AVG(prediction_error_to_target) AS prediction_error_to_target_mean_unweighted,
                {weighted_sql("prediction_error_to_target")} AS prediction_error_to_target_mean_weighted,
                SUM(ABS(prediction_error_to_target) * station_weight) / NULLIF(SUM(station_weight), 0) AS weighted_mae_to_target
            FROM read_parquet({parts_sql})
            GROUP BY date, fuel, fuel_label
            ORDER BY date
        ) TO {qstr(daily_path)} (HEADER, DELIMITER ',')
        """
    )

    con.execute(
        f"""
        COPY (
            SELECT
                grid_id,
                ANY_VALUE(fuel) AS fuel,
                ANY_VALUE(fuel_label) AS fuel_label,
                ANY_VALUE(region) AS region,
                ANY_VALUE(cell_x) AS cell_x,
                ANY_VALUE(cell_y) AS cell_y,
                ANY_VALUE(center_lon) AS center_lon,
                ANY_VALUE(center_lat) AS center_lat,
                COUNT(*) AS days,
                AVG(actual_grid_price) AS actual_grid_price_mean,
                AVG(pred_grid_fair_price) AS pred_grid_fair_price_mean,
                AVG(actual_gap_to_pred_fair) AS gap_to_pred_fair_mean,
                AVG(ABS(actual_gap_to_pred_fair)) AS abs_gap_to_pred_fair_mean
            FROM read_parquet({parts_sql})
            GROUP BY grid_id
            ORDER BY abs_gap_to_pred_fair_mean DESC
        ) TO {qstr(grid_path)} (HEADER, DELIMITER ',')
        """
    )

    con.execute(
        f"""
        COPY (
            WITH latest AS (
                SELECT MAX(date) AS max_date
                FROM read_parquet({parts_sql})
            )
            SELECT
                date,
                fuel,
                fuel_label,
                grid_id,
                region,
                cell_x,
                cell_y,
                center_lon,
                center_lat,
                station_weight,
                actual_grid_price,
                pred_grid_fair_price,
                pred_band_low_policy,
                pred_band_high_policy,
                actual_gap_to_pred_fair,
                pred_judge_policy
            FROM read_parquet({parts_sql}), latest
            WHERE date = latest.max_date
            ORDER BY region, grid_id
        ) TO {qstr(latest_grid_path)} (HEADER, DELIMITER ',')
        """
    )

    result = {
        "full": full_path,
        "daily": daily_path,
        "grid": grid_path,
        "latest_grid": latest_grid_path,
    }

    if has_region:
        con.execute(
            f"""
            COPY (
                SELECT
                    date,
                    COALESCE(region, '미분류') AS region,
                    fuel,
                    fuel_label,
                    COUNT(*) AS grid_rows,
                    SUM(station_weight) AS station_weight_sum,
                    {weighted_sql("actual_grid_price")} AS actual_price,
                    {weighted_sql("pred_grid_fair_price")} AS fair_price_policy,
                    {weighted_sql("pred_band_low_policy")} AS band_low_policy,
                    {weighted_sql("pred_band_high_policy")} AS band_high_policy,
                    {weighted_sql("actual_gap_to_pred_fair")} AS gap_policy,
                    CASE
                        WHEN {weighted_sql("actual_grid_price")} > {weighted_sql("pred_band_high_policy")} THEN '비쌈'
                        WHEN {weighted_sql("actual_grid_price")} < {weighted_sql("pred_band_low_policy")} THEN '저렴'
                        ELSE '적정'
                    END AS judge_policy
                FROM read_parquet({parts_sql})
                GROUP BY date, COALESCE(region, '미분류'), fuel, fuel_label
                ORDER BY date, region
            ) TO {qstr(region_path)} (HEADER, DELIMITER ',')
            """
        )
        result["region_daily"] = region_path

    for label, path in result.items():
        print(f"[SAVE] {label}: {path}")
    return result


def build_web_exports(out_dir: Path, fuel_outputs: dict[str, dict[str, Path]]) -> None:
    region_paths = [paths["region_daily"] for paths in fuel_outputs.values() if "region_daily" in paths]
    if not region_paths:
        return

    frames = [pd.read_csv(path, encoding="utf-8-sig") for path in region_paths]
    region_history = pd.concat(frames, ignore_index=True, sort=False)
    region_history["date"] = pd.to_datetime(region_history["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    web_history = region_history[
        [
            "date",
            "region",
            "fuel",
            "actual_price",
            "fair_price_policy",
            "band_low_policy",
            "band_high_policy",
            "gap_policy",
        ]
    ].copy()
    web_history["source"] = "ai-model/05_full_grid_prediction_for_web/predict_full_grid_for_web.py"

    latest_idx = region_history.sort_values("date").groupby(["region", "fuel"], dropna=False).tail(1).index
    web_today = region_history.loc[
        latest_idx,
        [
            "region",
            "fuel",
            "actual_price",
            "fair_price_policy",
            "band_low_policy",
            "band_high_policy",
            "gap_policy",
            "judge_policy",
            "date",
            "station_weight_sum",
        ],
    ].copy()
    web_today = web_today.rename(columns={"date": "source_date", "station_weight_sum": "station_count"})

    web_history_path = out_dir / "web_price_history_region.csv"
    web_today_path = out_dir / "web_region_today.csv"
    web_history.to_csv(web_history_path, index=False, encoding="utf-8-sig")
    web_today.to_csv(web_today_path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] web history: {web_history_path}")
    print(f"[SAVE] web today:   {web_today_path}")


def clean_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def save_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(clean_json_value(obj), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_one_fuel(
    con: duckdb.DuckDBPyConnection,
    target_dataset: Path,
    out_dir: Path,
    cfg: FuelConfig,
    bundle: ModelBundle,
    all_columns: set[str],
    args: argparse.Namespace,
    device: torch.device,
    region_lookup: pd.DataFrame | None,
) -> dict[str, Path]:
    date_range = available_date_range(con, target_dataset, cfg, args.start_date, args.end_date)
    if date_range is None:
        print(f"[SKIP] {cfg.fuel}: no available rows")
        return {}

    parts_dir = out_dir / cfg.fuel / "predictions_by_month"
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []

    print(f"[RUN] {cfg.fuel}: {date_range[0].date()} ~ {date_range[1].date()}, model={cfg.model_path}")
    start_time = time.time()
    for start, end in month_ranges(*date_range):
        chunk_start = time.time()
        query = build_model_frame_query(
            target_dataset=target_dataset,
            cfg=cfg,
            bundle=bundle,
            all_columns=all_columns,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            limit=args.limit_per_chunk,
        )
        chunk = con.execute(query).df()
        if chunk.empty:
            print(f"[CHUNK] {cfg.fuel} {start:%Y-%m}: no rows after sequence requirements")
            continue

        if region_lookup is not None and not region_lookup.empty:
            chunk = chunk.merge(region_lookup, on="grid_id", how="left")

        pred = predict_delta(bundle, chunk, device=device, batch_size=args.batch_size)
        out = add_predictions(chunk, cfg, pred)

        part_path = parts_dir / f"{start:%Y%m}.parquet"
        out.to_parquet(part_path, index=False, compression="zstd")
        parts.append(part_path)
        print(
            f"[CHUNK] {cfg.fuel} {start:%Y-%m}: rows={len(out):,}, "
            f"file={part_path.name}, elapsed={seconds_text(time.time() - chunk_start)}"
        )

        del chunk, pred, out

    outputs = write_combined_outputs(
        con=con,
        out_dir=out_dir,
        cfg=cfg,
        parts=parts,
        has_region=region_lookup is not None and not region_lookup.empty,
    )
    print(f"[DONE] {cfg.fuel}: elapsed={seconds_text(time.time() - start_time)}")
    return outputs


def main() -> int:
    args = parse_args()
    target_dataset = args.target_dataset.resolve()
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not target_dataset.exists():
        raise FileNotFoundError(
            "Missing AI 03 target dataset. Run/copy this first:\n"
            f"  {target_dataset}\n"
            "It is normally produced by ai-model/03_target_dataset_build/03_target_dataset_build.py."
        )

    for cfg in selected_fuels(args):
        if not cfg.model_path.exists():
            raise FileNotFoundError(f"Missing model for {cfg.fuel}: {cfg.model_path}")

    device = resolve_device(args.device)
    print("[CONFIG]")
    print(f"target_dataset = {target_dataset}")
    print(f"output_dir     = {out_dir}")
    print(f"device         = {device}")
    print(f"threads        = {args.threads}")

    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA threads={int(args.threads)}")
    con.execute("SET preserve_insertion_order=false")

    all_columns = set(schema_columns(con, target_dataset))
    region_lookup: pd.DataFrame | None = None
    if not args.no_region:
        region_lookup = build_region_lookup(
            con=con,
            target_dataset=target_dataset,
            geojson_path=args.geojson.resolve(),
            lookup_path=out_dir / "grid_region_lookup.csv",
            force=args.force_region_lookup,
        )

    fuel_outputs: dict[str, dict[str, Path]] = {}
    metadata: dict[str, Any] = {
        "created_at": pd.Timestamp.now().isoformat(),
        "script": str(Path(__file__).resolve()),
        "target_dataset": str(target_dataset),
        "output_dir": str(out_dir),
        "device": str(device),
        "fuels": [],
        "date_filter": {"start_date": args.start_date, "end_date": args.end_date},
        "region_lookup": None if region_lookup is None else str(out_dir / "grid_region_lookup.csv"),
    }

    for cfg in selected_fuels(args):
        bundle = load_model_bundle(cfg, device)
        outputs = run_one_fuel(
            con=con,
            target_dataset=target_dataset,
            out_dir=out_dir,
            cfg=cfg,
            bundle=bundle,
            all_columns=all_columns,
            args=args,
            device=device,
            region_lookup=region_lookup,
        )
        fuel_outputs[cfg.fuel] = outputs
        metadata["fuels"].append(
            {
                "fuel": cfg.fuel,
                "label": cfg.label,
                "model_path": str(cfg.model_path),
                "outputs": {key: str(path) for key, path in outputs.items()},
                "sequence_channels": bundle.sequence_channels,
                "latest_feature_columns": bundle.latest_feature_columns,
                "static_feature_columns": bundle.static_feature_columns,
            }
        )

    build_web_exports(out_dir, fuel_outputs)
    metadata_path = out_dir / "full_grid_prediction_metadata.json"
    save_json(metadata_path, metadata)
    print(f"[SAVE] metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
