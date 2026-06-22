from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import torch


KST = timezone(timedelta(hours=9))

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE6_DIR = Path(__file__).resolve().parent
STAGE5_SCRIPT = REPO_ROOT / "ai-model" / "05_full_grid_prediction_for_web" / "predict_full_grid_for_web.py"
STAGE4_OUTPUT = REPO_ROOT / "ai-model" / "04_prediction_model_training" / "outputs"

DEFAULT_OUTPUT_DIR = STAGE6_DIR / "outputs"
DEFAULT_PRICE_ROOT = REPO_ROOT / "data-analysis" / "00_data_collection" / "outputs" / "gas_station_prices_by_region"
DEFAULT_STATION_POINTS = REPO_ROOT / "data-analysis" / "00_data_collection" / "outputs" / "derived_data" / "station_points.csv"

WEB_DIR_NAME = "web"
STATE_DIR_NAME = "inference_state"
STATE_FILE_NAME = "recent_model_input.parquet"
STATE_MANIFEST_NAME = "recent_model_input_manifest.json"
STATION_GRID_LOOKUP_NAME = "station_grid_lookup.csv"
SOURCE_NAME = "ai-model/06_web_operational_dataset_build/daily_operational_prediction.py"

SOURCE_CRS = "EPSG:4326"
WORK_CRS = "EPSG:5179"
CELL_SIZE_M = 500
SEQUENCE_LENGTH = 28

FUELS = {
    "gasoline": {
        "actual_col": "gasoline_price_mean",
        "station_count_col": "gasoline_station_count",
        "fair_target_col": "gasoline_grid_fair_price_target",
        "national_actual_col": "gasoline_national_actual_price_grid",
        "band_low_col": "gasoline_grid_fair_band_low_policy",
        "band_high_col": "gasoline_grid_fair_band_high_policy",
        "model_path": STAGE4_OUTPUT / "gasoline" / "model" / "gasoline_grid_fair_price_delta_lstm.pt",
    },
    "diesel": {
        "actual_col": "diesel_price_mean",
        "station_count_col": "diesel_station_count",
        "fair_target_col": "diesel_grid_fair_price_target",
        "national_actual_col": "diesel_national_actual_price_grid",
        "band_low_col": "diesel_grid_fair_band_low_policy",
        "band_high_col": "diesel_grid_fair_band_high_policy",
        "model_path": STAGE4_OUTPUT / "diesel" / "model" / "diesel_grid_fair_price_delta_lstm.pt",
    },
}

HISTORY_COLUMNS = [
    "date",
    "region",
    "fuel",
    "actual_price",
    "fair_price_policy",
    "band_low_policy",
    "band_high_policy",
    "gap_policy",
    "source",
]

TODAY_COLUMNS = [
    "region",
    "fuel",
    "actual_price",
    "fair_price_policy",
    "band_low_policy",
    "band_high_policy",
    "gap_policy",
    "judge_policy",
    "source_date",
    "station_count",
]

LATEST_GRID_COLUMNS = [
    "source_date",
    "feature_date",
    "fuel",
    "grid_id",
    "region",
    "cell_x",
    "cell_y",
    "center_lon",
    "center_lat",
    "station_count",
    "actual_price",
    "actual_price_basis",
    "fair_price_policy",
    "band_low_policy",
    "band_high_policy",
    "gap_policy",
    "judge_policy",
]


@dataclass(frozen=True)
class RunStats:
    status: str
    state_rows_before: int
    state_rows_after: int
    appended_state_rows: int
    prediction_rows: int
    target_date_min: str | None
    target_date_max: str | None
    latest_feature_date: str | None


def parse_date(value: str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def date_text(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).strftime("%Y-%m-%d")


def seconds_text(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] {path} rows={len(df):,} size={path.stat().st_size:,}")


def clean_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json_value(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(clean_json_value(payload), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"[SAVE] {path} size={path.stat().st_size:,}")


def relative_source(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def file_info(path: Path, repo_root: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": relative_source(path, repo_root), "exists": False}
    stat = path.stat()
    return {
        "path": relative_source(path, repo_root),
        "exists": True,
        "bytes": int(stat.st_size),
        "mb": round(stat.st_size / 1024 / 1024, 3),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, KST).isoformat(timespec="seconds"),
    }


def numeric_round(df: pd.DataFrame, digits: int) -> pd.DataFrame:
    out = df.copy()
    skip = {"date", "source_date", "feature_date", "region", "fuel", "judge_policy", "source", "grid_id", "actual_price_basis"}
    for col in out.columns:
        if col in skip:
            continue
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].round(digits)
    return out


def weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce").fillna(0)
    mask = v.notna() & w.gt(0)
    if mask.any():
        return float((v[mask] * w[mask]).sum() / w[mask].sum())
    if v.notna().any():
        return float(v.mean())
    return None


def judge(actual: pd.Series, low: pd.Series, high: pd.Series, pred: pd.Series) -> np.ndarray:
    return np.select(
        [
            pd.to_numeric(actual, errors="coerce") > pd.to_numeric(high, errors="coerce"),
            pd.to_numeric(actual, errors="coerce") < pd.to_numeric(low, errors="coerce"),
            pd.to_numeric(low, errors="coerce").notna() & pd.to_numeric(high, errors="coerce").notna(),
            pd.to_numeric(actual, errors="coerce") > pd.to_numeric(pred, errors="coerce"),
            pd.to_numeric(actual, errors="coerce") < pd.to_numeric(pred, errors="coerce"),
        ],
        ["비쌈", "쌈", "적정", "비쌈", "쌈"],
        default="적정",
    )


def import_stage5_module() -> Any:
    spec = importlib.util.spec_from_file_location("kff_stage5_prediction", STAGE5_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import stage 5 prediction module: {STAGE5_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["kff_stage5_prediction"] = module
    spec.loader.exec_module(module)
    return module


def load_state(state_path: Path) -> pd.DataFrame:
    if not state_path.exists():
        raise FileNotFoundError(
            f"Missing operational inference state: {state_path}\n"
            "Run AI 06 once from the local full target dataset, or commit the current recent_model_input.parquet."
        )
    state = pd.read_parquet(state_path)
    state["date"] = pd.to_datetime(state["date"], errors="coerce").dt.normalize()
    state = state.dropna(subset=["date", "grid_id"]).copy()
    return state


def save_state(state_path: Path, state: pd.DataFrame, state_days: int) -> None:
    work = state.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()
    work = work.dropna(subset=["date", "grid_id"])
    if not work.empty and state_days > 0:
        cutoff = work["date"].max() - pd.Timedelta(days=max(state_days - 1, 0))
        work = work[work["date"] >= cutoff].copy()
    work = work.sort_values(["date", "grid_id"]).drop_duplicates(["date", "grid_id"], keep="last")
    work["date"] = work["date"].dt.strftime("%Y-%m-%d")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    work.to_parquet(state_path, index=False, compression="zstd")
    print(f"[SAVE] {state_path} rows={len(work):,} size={state_path.stat().st_size:,}")


def latest_static_by_grid(state: pd.DataFrame) -> pd.DataFrame:
    work = state.sort_values("date").drop_duplicates("grid_id", keep="last").copy()
    return work


def build_station_grid_lookup(
    station_points_path: Path,
    state: pd.DataFrame,
    lookup_path: Path,
    force: bool,
) -> pd.DataFrame:
    if lookup_path.exists() and not force:
        lookup = read_csv(lookup_path)
        return lookup

    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError("pyproj is required to assign station points to 500m grid cells.") from exc

    if not station_points_path.exists():
        raise FileNotFoundError(f"Missing station point file: {station_points_path}")

    points = read_csv(station_points_path)
    required = {"station_id", "lon", "lat"}
    missing = sorted(required - set(points.columns))
    if missing:
        raise ValueError(f"station point file is missing columns: {missing}")

    work = points.copy()
    work["lon"] = pd.to_numeric(work["lon"], errors="coerce")
    work["lat"] = pd.to_numeric(work["lat"], errors="coerce")
    work = work.dropna(subset=["station_id", "lon", "lat"]).copy()

    transformer = Transformer.from_crs(SOURCE_CRS, WORK_CRS, always_xy=True)
    x_m, y_m = transformer.transform(work["lon"].to_numpy(dtype="float64"), work["lat"].to_numpy(dtype="float64"))
    work["cell_x"] = (np.floor(np.asarray(x_m) / CELL_SIZE_M).astype(np.int64) * CELL_SIZE_M).astype("int32")
    work["cell_y"] = (np.floor(np.asarray(y_m) / CELL_SIZE_M).astype(np.int64) * CELL_SIZE_M).astype("int32")

    grid_cols = ["grid_id", "cell_x", "cell_y", "center_lon", "center_lat"]
    grid_cells = (
        state[grid_cols]
        .dropna(subset=["grid_id", "cell_x", "cell_y"])
        .sort_values(["cell_x", "cell_y", "grid_id"])
        .drop_duplicates(["cell_x", "cell_y"], keep="last")
    )
    merged = work.merge(grid_cells, on=["cell_x", "cell_y"], how="inner")

    keep = ["station_id", "grid_id", "cell_x", "cell_y", "center_lon", "center_lat"]
    for col in ["source_region", "brand", "is_self"]:
        if col in merged.columns:
            keep.append(col)
    out = merged[keep].drop_duplicates("station_id").sort_values("station_id").reset_index(drop=True)
    write_csv(lookup_path, out)
    print(
        "[LOOKUP] station->grid "
        f"stations={len(points):,}, matched={len(out):,}, grids={out['grid_id'].nunique():,}"
    )
    return out


def station_price_files(price_root: Path, fuel: str) -> list[Path]:
    if not price_root.exists():
        return []
    files: list[Path] = []
    for region_dir in sorted([p for p in price_root.iterdir() if p.is_dir()]):
        direct = region_dir / f"{fuel}.csv"
        if direct.exists():
            files.append(direct)
        parts_dir = region_dir / f"{fuel}.parts"
        if parts_dir.exists():
            files.extend(sorted(parts_dir.glob("*.csv")))
    return files


def read_station_price_updates(
    price_root: Path,
    station_lookup: pd.DataFrame,
    min_source_date: pd.Timestamp,
    source_start_date: pd.Timestamp | None,
    source_end_date: pd.Timestamp | None,
) -> pd.DataFrame:
    station_ids = set(station_lookup["station_id"].astype(str))
    min_date = min_source_date
    if source_start_date is not None:
        min_date = max(min_date, source_start_date)

    frames: list[pd.DataFrame] = []
    for fuel in FUELS:
        files = station_price_files(price_root, fuel)
        if not files:
            print(f"[WARN] no station price files for {fuel}: {price_root}")
            continue
        for path in files:
            try:
                part = pd.read_csv(
                    path,
                    encoding="utf-8-sig",
                    usecols=lambda col: col == "date" or str(col) in station_ids,
                    low_memory=False,
                )
            except UnicodeDecodeError:
                part = pd.read_csv(
                    path,
                    encoding="cp949",
                    usecols=lambda col: col == "date" or str(col) in station_ids,
                    low_memory=False,
                )
            if "date" not in part.columns or len(part.columns) <= 1:
                continue
            part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
            mask = part["date"].notna() & (part["date"] >= min_date)
            if source_end_date is not None:
                mask &= part["date"] <= source_end_date
            part = part.loc[mask]
            if part.empty:
                continue
            long = part.melt(id_vars=["date"], var_name="station_id", value_name="price")
            long["price"] = pd.to_numeric(long["price"], errors="coerce")
            long = long.dropna(subset=["price"])
            long = long[long["price"] > 0].copy()
            if long.empty:
                continue
            long["fuel"] = fuel
            frames.append(long[["date", "fuel", "station_id", "price"]])

    if not frames:
        return pd.DataFrame(columns=["date", "fuel", "station_id", "price"])
    out = pd.concat(frames, ignore_index=True, sort=False)
    out["station_id"] = out["station_id"].astype(str)
    return out


def aggregate_station_prices(price_long: pd.DataFrame, station_lookup: pd.DataFrame, state: pd.DataFrame) -> pd.DataFrame:
    if price_long.empty:
        return pd.DataFrame(columns=state.columns)

    lookup_cols = ["station_id", "grid_id", "cell_x", "cell_y", "center_lon", "center_lat"]
    joined = price_long.merge(station_lookup[lookup_cols], on="station_id", how="inner")
    if joined.empty:
        return pd.DataFrame(columns=state.columns)

    frames: list[pd.DataFrame] = []
    for fuel, spec in FUELS.items():
        part = joined[joined["fuel"] == fuel].copy()
        if part.empty:
            continue
        agg = (
            part.groupby(["date", "grid_id"], observed=True)
            .agg(
                price_mean=("price", "mean"),
                station_count=("station_id", "nunique"),
                cell_x=("cell_x", "last"),
                cell_y=("cell_y", "last"),
                center_lon=("center_lon", "last"),
                center_lat=("center_lat", "last"),
            )
            .reset_index()
        )
        agg = agg.rename(
            columns={
                "price_mean": spec["actual_col"],
                "station_count": spec["station_count_col"],
            }
        )
        frames.append(agg)

    if not frames:
        return pd.DataFrame(columns=state.columns)

    combined = frames[0]
    for frame in frames[1:]:
        combined = combined.merge(frame, on=["date", "grid_id", "cell_x", "cell_y", "center_lon", "center_lat"], how="outer")

    static = latest_static_by_grid(state)
    static_cols = [col for col in static.columns if col not in set(combined.columns) | {"date"}]
    combined = combined.merge(static[["grid_id"] + static_cols], on="grid_id", how="left")

    for fuel, spec in FUELS.items():
        count_col = spec["station_count_col"]
        actual_col = spec["actual_col"]
        nat_col = spec["national_actual_col"]
        if count_col not in combined.columns:
            combined[count_col] = np.nan
        if actual_col not in combined.columns:
            combined[actual_col] = np.nan
        national = (
            combined.dropna(subset=[actual_col])
            .groupby("date", observed=True)
            .apply(lambda g: weighted_mean(g[actual_col], g[count_col]), include_groups=False)
            .rename(nat_col)
            .reset_index()
        )
        combined = combined.drop(columns=[nat_col], errors="ignore").merge(national, on="date", how="left")

    if "station_count_total" in combined.columns:
        gas_count = pd.to_numeric(combined.get("gasoline_station_count"), errors="coerce").fillna(0)
        diesel_count = pd.to_numeric(combined.get("diesel_station_count"), errors="coerce").fillna(0)
        combined["station_count_total"] = np.maximum(gas_count, diesel_count).astype("int32")

    for col in state.columns:
        if col not in combined.columns:
            combined[col] = np.nan
    out = combined[state.columns].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    return out.dropna(subset=["date", "grid_id"])


def update_state_from_station_prices(
    state: pd.DataFrame,
    state_path: Path,
    station_lookup: pd.DataFrame,
    price_root: Path,
    source_start_date: pd.Timestamp | None,
    source_end_date: pd.Timestamp | None,
    state_days: int,
    min_feature_coverage_ratio: float,
    source_backfill_days: int,
) -> tuple[pd.DataFrame, int]:
    if state.empty:
        raise ValueError("recent_model_input.parquet is empty")

    before_rows = len(state)
    state_max = state["date"].max()
    counts = state.groupby("date", observed=True)["grid_id"].count().sort_index()
    recent = counts.tail(14)
    baseline = float(recent.median()) if not recent.empty else float(counts.median())
    threshold = baseline * float(min_feature_coverage_ratio)
    backfill_floor = state_max - pd.Timedelta(days=max(source_backfill_days - 1, 0))
    incomplete_recent = counts[(counts.index >= backfill_floor) & (counts < threshold)]
    min_source_date = state_max + pd.Timedelta(days=1)
    if not incomplete_recent.empty:
        min_source_date = min(min_source_date, pd.Timestamp(incomplete_recent.index.min()).normalize())

    updates = read_station_price_updates(
        price_root=price_root,
        station_lookup=station_lookup,
        min_source_date=min_source_date,
        source_start_date=source_start_date,
        source_end_date=source_end_date,
    )
    if updates.empty:
        print(f"[STATE] no station price rows from {min_source_date:%Y-%m-%d} to update")
        return state, 0

    new_rows = aggregate_station_prices(updates, station_lookup, state)
    if new_rows.empty:
        print("[STATE] station updates did not match known operational grids")
        return state, 0

    new_counts = new_rows.groupby("date", observed=True)["grid_id"].nunique()
    old_counts = state[state["date"].isin(new_counts.index)].groupby("date", observed=True)["grid_id"].nunique()
    has_new_date = bool((new_counts.index > state_max).any())
    has_coverage_gain = any(int(count) > int(old_counts.get(day, 0)) for day, count in new_counts.items())
    if not has_new_date and not has_coverage_gain:
        print(
            "[STATE] recent incomplete dates checked; "
            "no new date or grid-coverage gain found"
        )
        return state, 0

    combined = pd.concat([state, new_rows], ignore_index=True, sort=False)
    combined = combined.sort_values(["date", "grid_id"]).drop_duplicates(["date", "grid_id"], keep="last")
    save_state(state_path, combined, state_days=state_days)
    refreshed = load_state(state_path)
    print(f"[STATE] appended_grid_days={len(refreshed) - before_rows:,}, new_source_rows={len(new_rows):,}")
    return refreshed, max(len(refreshed) - before_rows, 0)


def ensure_numeric(df: pd.DataFrame, cols: Iterable[str]) -> None:
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")


def model_sequence_length(bundle: Any) -> int:
    lengths = [len(cols) for cols in bundle.sequence_channels.values()]
    if not lengths or len(set(lengths)) != 1:
        raise ValueError(f"Invalid sequence channel shape: {bundle.sequence_channels}")
    return int(lengths[0])


def band_offsets(state: pd.DataFrame, spec: dict[str, Any]) -> tuple[float, float]:
    fair = pd.to_numeric(state.get(spec["fair_target_col"]), errors="coerce")
    low = pd.to_numeric(state.get(spec["band_low_col"]), errors="coerce")
    high = pd.to_numeric(state.get(spec["band_high_col"]), errors="coerce")
    low_offset = (fair - low).dropna()
    high_offset = (high - fair).dropna()
    return (
        float(low_offset.median()) if not low_offset.empty else 10.0,
        float(high_offset.median()) if not high_offset.empty else 20.0,
    )


def latest_complete_feature_date(state: pd.DataFrame, min_coverage_ratio: float) -> tuple[pd.Timestamp, dict[str, Any]]:
    counts = state.groupby("date", observed=True)["grid_id"].count().sort_index()
    if counts.empty:
        raise ValueError("Cannot infer a feature date from an empty state.")

    recent = counts.tail(14)
    baseline = float(recent.median()) if not recent.empty else float(counts.median())
    threshold = baseline * float(min_coverage_ratio)
    complete = counts[counts >= threshold]
    if complete.empty:
        complete = counts
    feature_date = pd.Timestamp(complete.index.max()).normalize()
    meta = {
        "latest_raw_feature_date": date_text(counts.index.max()),
        "latest_complete_feature_date": date_text(feature_date),
        "latest_raw_grid_rows": int(counts.iloc[-1]),
        "recent_median_grid_rows": baseline,
        "min_coverage_ratio": float(min_coverage_ratio),
        "min_required_grid_rows": threshold,
    }
    return feature_date, meta


def complete_feature_dates(state: pd.DataFrame, min_coverage_ratio: float) -> tuple[set[pd.Timestamp], dict[str, Any]]:
    counts = state.groupby("date", observed=True)["grid_id"].count().sort_index()
    if counts.empty:
        raise ValueError("Cannot infer complete feature dates from an empty state.")

    recent = counts.tail(14)
    baseline = float(recent.median()) if not recent.empty else float(counts.median())
    threshold = baseline * float(min_coverage_ratio)
    complete = counts[counts >= threshold]
    dates = {pd.Timestamp(value).normalize() for value in complete.index}
    meta = {
        "latest_raw_feature_date": date_text(counts.index.max()),
        "latest_raw_grid_rows": int(counts.iloc[-1]),
        "recent_median_grid_rows": baseline,
        "min_coverage_ratio": float(min_coverage_ratio),
        "min_required_grid_rows": threshold,
        "complete_feature_date_count": int(len(dates)),
    }
    if dates:
        meta["latest_complete_feature_date"] = date_text(max(dates))
    return dates, meta


def target_date_bounds(
    state: pd.DataFrame,
    web_history_path: Path,
    target_start_date: pd.Timestamp | None,
    target_end_date: pd.Timestamp | None,
    min_feature_coverage_ratio: float,
) -> tuple[pd.Timestamp, pd.Timestamp, dict[str, Any]]:
    safe_feature_end, coverage_meta = latest_complete_feature_date(state, min_feature_coverage_ratio)
    safe_target_end = safe_feature_end + pd.Timedelta(days=1)
    default_start = safe_target_end
    if web_history_path.exists():
        history = read_csv(web_history_path)
        if "date" in history.columns and not history.empty:
            max_history = pd.to_datetime(history["date"], errors="coerce").max()
            if pd.notna(max_history):
                max_history = pd.Timestamp(max_history).normalize()
                default_start = safe_target_end if max_history > safe_target_end else max_history + pd.Timedelta(days=1)

    start = target_start_date or default_start
    end = target_end_date or safe_target_end
    end = min(end, safe_target_end)
    coverage_meta["safe_target_end"] = date_text(safe_target_end)
    return start, end, coverage_meta


def build_feature_frame(
    state: pd.DataFrame,
    fuel: str,
    bundle: Any,
    target_start: pd.Timestamp,
    target_end: pd.Timestamp,
    allowed_feature_dates: set[pd.Timestamp],
) -> pd.DataFrame:
    spec = FUELS[fuel]
    seq_len = model_sequence_length(bundle)
    actual_col = spec["actual_col"]
    station_col = spec["station_count_col"]
    national_col = spec["national_actual_col"]
    fair_col = spec["fair_target_col"]
    low_col = spec["band_low_col"]
    high_col = spec["band_high_col"]

    keep_cols = set(
        ["date", "grid_id", "cell_x", "cell_y", "center_lon", "center_lat", actual_col, station_col, national_col, fair_col, low_col, high_col]
        + list(bundle.static_feature_columns)
    )
    keep_cols.discard("official_price_age_days")
    keep_cols.discard("official_price_source_year")
    keep_cols.add("official_price_source_date")
    work = state[[col for col in state.columns if col in keep_cols]].copy()
    ensure_numeric(work, [actual_col, station_col, national_col])
    work = work.dropna(subset=["date", "grid_id", actual_col, national_col])
    work = work[pd.to_numeric(work[station_col], errors="coerce").fillna(0) > 0].copy()
    if work.empty:
        return pd.DataFrame()

    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()
    work = work.dropna(subset=["date"]).sort_values(["grid_id", "date"]).reset_index(drop=True)
    work["spread_lag_1d"] = work[actual_col] - work[national_col]
    work["actual_price_lag_1d"] = work[actual_col]
    work["national_price_lag_1d"] = work[national_col]
    work["station_weight_lag_1d"] = work[station_col]

    grouped = work.groupby("grid_id", sort=False, observed=True)
    for d in range(1, seq_len + 1):
        cur_actual = grouped[actual_col].shift(d - 1)
        prev_actual = grouped[actual_col].shift(d)
        cur_national = grouped[national_col].shift(d - 1)
        prev_national = grouped[national_col].shift(d)
        cur_spread = grouped["spread_lag_1d"].shift(d - 1)
        prev_spread = grouped["spread_lag_1d"].shift(d)
        work[f"actual_grid_price_delta_lag_{d}d"] = cur_actual - prev_actual
        work[f"national_price_delta_lag_{d}d"] = cur_national - prev_national
        work[f"spread_delta_lag_{d}d"] = cur_spread - prev_spread

    work["history_start_date"] = grouped["date"].shift(seq_len)
    work["target_date"] = work["date"] + pd.Timedelta(days=1)
    span_ok = (work["date"] - work["history_start_date"]).dt.days == seq_len
    allowed = work["date"].isin(allowed_feature_dates)
    date_ok = (work["target_date"] >= target_start) & (work["target_date"] <= target_end) & allowed
    required_seq = [col for cols in bundle.sequence_channels.values() for col in cols]
    required_latest = list(bundle.latest_feature_columns)
    work = work[span_ok & date_ok].copy()
    if work.empty:
        return pd.DataFrame()
    work = work.dropna(subset=required_seq + required_latest)
    if work.empty:
        return pd.DataFrame()

    target_actual = state[["date", "grid_id", actual_col, station_col, national_col, fair_col, low_col, high_col]].copy()
    target_actual["date"] = pd.to_datetime(target_actual["date"], errors="coerce").dt.normalize()
    target_actual = target_actual.rename(
        columns={
            "date": "target_date",
            actual_col: "actual_grid_price_target_date",
            station_col: "station_weight_target_date",
            national_col: "national_actual_price_target_date",
            fair_col: "grid_fair_price_target",
            low_col: "grid_fair_band_low_policy",
            high_col: "grid_fair_band_high_policy",
        }
    )
    work = work.merge(target_actual, on=["target_date", "grid_id"], how="left")

    work["feature_date"] = work["date"]
    work["date"] = work["target_date"]
    has_target_actual = pd.to_numeric(work["actual_grid_price_target_date"], errors="coerce").notna()
    work["actual_grid_price"] = pd.to_numeric(work["actual_grid_price_target_date"], errors="coerce").where(
        has_target_actual, work["actual_price_lag_1d"]
    )
    work["station_weight"] = pd.to_numeric(work["station_weight_target_date"], errors="coerce").where(
        pd.to_numeric(work["station_weight_target_date"], errors="coerce").gt(0),
        work["station_weight_lag_1d"],
    )
    work["national_actual_price"] = pd.to_numeric(work["national_actual_price_target_date"], errors="coerce").where(
        pd.to_numeric(work["national_actual_price_target_date"], errors="coerce").notna(),
        work["national_price_lag_1d"],
    )
    work["actual_price_basis"] = np.where(has_target_actual, "target_date", "feature_date")

    source_date = pd.to_datetime(work["official_price_source_date"], errors="coerce") if "official_price_source_date" in work.columns else pd.NaT
    work["official_price_age_days"] = (work["feature_date"] - source_date).dt.days.astype("float64")
    work["official_price_source_year"] = source_date.dt.year.astype("float64")

    for col in bundle.static_feature_columns:
        if col not in work.columns:
            work[col] = np.nan

    return work


def add_operational_predictions(
    frame: pd.DataFrame,
    fuel: str,
    pred_delta: np.ndarray,
    state: pd.DataFrame,
    region_lookup: pd.DataFrame,
) -> pd.DataFrame:
    spec = FUELS[fuel]
    out = frame[
        [
            "date",
            "feature_date",
            "grid_id",
            "cell_x",
            "cell_y",
            "center_lon",
            "center_lat",
            "station_weight",
            "actual_grid_price",
            "actual_price_basis",
            "grid_fair_price_target",
            "grid_fair_band_low_policy",
            "grid_fair_band_high_policy",
        ]
    ].copy()
    out.insert(0, "fuel", fuel)
    out["pred_fair_price_delta"] = np.asarray(pred_delta, dtype="float64")
    out["fair_price_policy"] = pd.to_numeric(frame["actual_price_lag_1d"], errors="coerce") + out["pred_fair_price_delta"]

    low_offset, high_offset = band_offsets(state, spec)
    known_band = (
        pd.to_numeric(out["grid_fair_price_target"], errors="coerce").notna()
        & pd.to_numeric(out["grid_fair_band_low_policy"], errors="coerce").notna()
        & pd.to_numeric(out["grid_fair_band_high_policy"], errors="coerce").notna()
    )
    band_shift = out["fair_price_policy"] - pd.to_numeric(out["grid_fair_price_target"], errors="coerce")
    out["band_low_policy"] = np.where(
        known_band,
        pd.to_numeric(out["grid_fair_band_low_policy"], errors="coerce") + band_shift,
        out["fair_price_policy"] - low_offset,
    )
    out["band_high_policy"] = np.where(
        known_band,
        pd.to_numeric(out["grid_fair_band_high_policy"], errors="coerce") + band_shift,
        out["fair_price_policy"] + high_offset,
    )
    out["actual_price"] = pd.to_numeric(out["actual_grid_price"], errors="coerce")
    out["gap_policy"] = out["actual_price"] - out["fair_price_policy"]
    out["judge_policy"] = judge(out["actual_price"], out["band_low_policy"], out["band_high_policy"], out["fair_price_policy"])

    if not region_lookup.empty:
        out = out.merge(region_lookup[["grid_id", "region"]].drop_duplicates("grid_id"), on="grid_id", how="left")
    else:
        out["region"] = None
    out["region"] = out["region"].fillna("미분류")

    out = out.rename(columns={"date": "source_date", "station_weight": "station_count"})
    for col in LATEST_GRID_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    return out[LATEST_GRID_COLUMNS].copy()


def summarize_region(predictions: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS + ["judge_policy", "station_count"])

    rows: list[dict[str, Any]] = []
    group_cols = ["source_date", "region", "fuel"]
    for (source_date, region, fuel), part in predictions.groupby(group_cols, dropna=False, observed=True):
        weights = pd.to_numeric(part["station_count"], errors="coerce").fillna(0)
        row = {
            "date": date_text(source_date),
            "region": region if pd.notna(region) else "미분류",
            "fuel": fuel,
            "actual_price": weighted_mean(part["actual_price"], weights),
            "fair_price_policy": weighted_mean(part["fair_price_policy"], weights),
            "band_low_policy": weighted_mean(part["band_low_policy"], weights),
            "band_high_policy": weighted_mean(part["band_high_policy"], weights),
            "station_count": float(weights.sum()) if weights.notna().any() else None,
            "source": SOURCE_NAME,
        }
        row["gap_policy"] = None
        if row["actual_price"] is not None and row["fair_price_policy"] is not None:
            row["gap_policy"] = row["actual_price"] - row["fair_price_policy"]
        row["judge_policy"] = "적정"
        if row["actual_price"] is not None and row["band_high_policy"] is not None and row["actual_price"] > row["band_high_policy"]:
            row["judge_policy"] = "비쌈"
        elif row["actual_price"] is not None and row["band_low_policy"] is not None and row["actual_price"] < row["band_low_policy"]:
            row["judge_policy"] = "쌈"
        rows.append(row)

    return pd.DataFrame(rows).sort_values(["date", "region", "fuel"]).reset_index(drop=True)


def merge_history(web_dir: Path, region_summary: pd.DataFrame, history_years: int, round_digits: int) -> tuple[pd.DataFrame, Path]:
    path = web_dir / "web_price_history_region.csv"
    if path.exists():
        existing = read_csv(path)
    else:
        existing = pd.DataFrame(columns=HISTORY_COLUMNS)

    for col in HISTORY_COLUMNS:
        if col not in existing.columns:
            existing[col] = np.nan
        if col not in region_summary.columns:
            region_summary[col] = np.nan

    history_new = region_summary[HISTORY_COLUMNS].copy()
    combined = pd.concat([existing[HISTORY_COLUMNS], history_new], ignore_index=True, sort=False)
    combined["date"] = pd.to_datetime(combined["date"], errors="coerce").dt.normalize()
    combined = combined.dropna(subset=["date", "region", "fuel"])
    max_new_date = pd.to_datetime(history_new["date"], errors="coerce").max()
    if pd.notna(max_new_date):
        max_new_date = pd.Timestamp(max_new_date).normalize()
        combined = combined[~((combined["date"] > max_new_date) & (combined["source"] == SOURCE_NAME))].copy()
    combined = combined.sort_values(["date", "region", "fuel", "source"]).drop_duplicates(["date", "region", "fuel"], keep="last")
    if not combined.empty and history_years > 0:
        cutoff = combined["date"].max() - pd.DateOffset(years=history_years)
        combined = combined[combined["date"] >= cutoff].copy()
    combined["date"] = combined["date"].dt.strftime("%Y-%m-%d")
    combined = numeric_round(combined.sort_values(["date", "region", "fuel"]).reset_index(drop=True), round_digits)
    write_csv(path, combined)
    return combined, path


def write_today_files(
    web_dir: Path,
    history: pd.DataFrame,
    region_summary: pd.DataFrame,
    round_digits: int,
) -> tuple[pd.DataFrame, Path, Path | None]:
    today_path = web_dir / "web_region_today.csv"
    if not region_summary.empty:
        latest_date = pd.to_datetime(region_summary["date"], errors="coerce").max()
        today = region_summary[pd.to_datetime(region_summary["date"], errors="coerce") == latest_date].copy()
        today = today.rename(columns={"date": "source_date"})
    elif today_path.exists():
        today = read_csv(today_path)
    else:
        latest_date = pd.to_datetime(history["date"], errors="coerce").max()
        today = history[pd.to_datetime(history["date"], errors="coerce") == latest_date].copy()
        today = today.rename(columns={"date": "source_date"})

    for col in TODAY_COLUMNS:
        if col not in today.columns:
            today[col] = np.nan
    today = numeric_round(today[TODAY_COLUMNS].sort_values(["region", "fuel"]).reset_index(drop=True), round_digits)
    write_csv(today_path, today)

    national_path: Path | None = None
    if not today.empty:
        rows: list[dict[str, Any]] = []
        for fuel, part in today.groupby("fuel", dropna=False, observed=True):
            weights = pd.to_numeric(part["station_count"], errors="coerce").fillna(0)
            row = {"fuel": fuel, "source_date": part["source_date"].max()}
            for col in ["actual_price", "fair_price_policy", "band_low_policy", "band_high_policy", "gap_policy"]:
                row[col] = weighted_mean(part[col], weights)
            row["station_count"] = float(weights.sum()) if weights.notna().any() else None
            rows.append(row)
        national = numeric_round(pd.DataFrame(rows).sort_values("fuel").reset_index(drop=True), round_digits)
        national_path = web_dir / "web_national_today.csv"
        write_csv(national_path, national)

    return today, today_path, national_path


def write_latest_grid(web_dir: Path, predictions: pd.DataFrame, round_digits: int) -> Path | None:
    path = web_dir / "web_latest_grid_predictions.csv"
    if predictions.empty:
        return path if path.exists() else None
    latest_date = pd.to_datetime(predictions["source_date"], errors="coerce").max()
    latest = predictions[pd.to_datetime(predictions["source_date"], errors="coerce") == latest_date].copy()
    latest = latest[LATEST_GRID_COLUMNS].sort_values(["fuel", "region", "grid_id"]).reset_index(drop=True)
    latest["source_date"] = pd.to_datetime(latest["source_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    latest["feature_date"] = pd.to_datetime(latest["feature_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    latest = numeric_round(latest, round_digits)
    write_csv(path, latest)
    return path


def predict_operational(
    state: pd.DataFrame,
    web_dir: Path,
    device_name: str,
    batch_size: int,
    fuel_names: list[str],
    target_start_date: pd.Timestamp | None,
    target_end_date: pd.Timestamp | None,
    min_feature_coverage_ratio: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    stage5 = import_stage5_module()
    device = stage5.resolve_device(device_name)
    region_lookup_path = web_dir / "grid_region_lookup.csv"
    region_lookup = read_csv(region_lookup_path) if region_lookup_path.exists() else pd.DataFrame(columns=["grid_id", "region"])
    target_start, target_end, coverage_meta = target_date_bounds(
        state,
        web_dir / "web_price_history_region.csv",
        target_start_date,
        target_end_date,
        min_feature_coverage_ratio,
    )
    allowed_feature_dates, all_coverage_meta = complete_feature_dates(state, min_feature_coverage_ratio)
    coverage_meta.update(all_coverage_meta)

    if target_start > target_end:
        return pd.DataFrame(columns=LATEST_GRID_COLUMNS), {
            "status": "no_new_target_dates",
            "target_start": date_text(target_start),
            "target_end": date_text(target_end),
            "device": str(device),
            "coverage": coverage_meta,
        }

    frames: list[pd.DataFrame] = []
    fuel_stats: dict[str, Any] = {}
    for fuel in fuel_names:
        spec = FUELS[fuel]
        cfg = stage5.FuelConfig.from_name(fuel, spec["model_path"])
        bundle = stage5.load_model_bundle(cfg, device)
        frame = build_feature_frame(state, fuel, bundle, target_start, target_end, allowed_feature_dates)
        if frame.empty:
            fuel_stats[fuel] = {"feature_rows": 0, "prediction_rows": 0}
            continue
        pred = stage5.predict_delta(bundle, frame, device=device, batch_size=batch_size)
        out = add_operational_predictions(frame, fuel, pred, state, region_lookup)
        frames.append(out)
        fuel_stats[fuel] = {
            "feature_rows": int(len(frame)),
            "prediction_rows": int(len(out)),
            "target_date_min": date_text(out["source_date"].min()),
            "target_date_max": date_text(out["source_date"].max()),
        }
        print(
            f"[PREDICT] {fuel}: rows={len(out):,}, "
            f"target={fuel_stats[fuel]['target_date_min']}~{fuel_stats[fuel]['target_date_max']}, device={device}"
        )

    if not frames:
        return pd.DataFrame(columns=LATEST_GRID_COLUMNS), {
            "status": "no_predictable_rows",
            "target_start": date_text(target_start),
            "target_end": date_text(target_end),
            "device": str(device),
            "coverage": coverage_meta,
            "fuels": fuel_stats,
        }

    predictions = pd.concat(frames, ignore_index=True, sort=False)
    return predictions, {
        "status": "completed",
        "target_start": date_text(target_start),
        "target_end": date_text(target_end),
        "device": str(device),
        "coverage": coverage_meta,
        "fuels": fuel_stats,
    }


def write_state_manifest(
    repo_root: Path,
    state_path: Path,
    manifest_path: Path,
    state: pd.DataFrame,
    state_days: int,
    appended_rows: int,
    lookup_path: Path,
) -> None:
    payload = {
        "schema_version": "recent_model_input_state_v2",
        "status": "ready",
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "operational rolling inference state",
        "state_days": state_days,
        "date_min": date_text(state["date"].min()) if not state.empty else None,
        "date_max": date_text(state["date"].max()) if not state.empty else None,
        "rows": int(len(state)),
        "columns": list(state.columns),
        "last_update": {
            "appended_grid_day_rows": int(appended_rows),
            "station_grid_lookup": file_info(lookup_path, repo_root),
        },
        "files": {"recent_model_input": file_info(state_path, repo_root)},
        "use": (
            "Rolling 500m-grid model input state used by daily_operational_prediction.py. "
            "It intentionally replaces the local-only full grid_target.parquet in GitHub Actions."
        ),
    }
    save_json(manifest_path, payload)


def update_operational_manifest(
    repo_root: Path,
    output_dir: Path,
    stats: RunStats,
    prediction_meta: dict[str, Any],
    files: dict[str, Path | None],
) -> None:
    web_dir = output_dir / WEB_DIR_NAME
    payload = {
        "schema_version": "web_operational_dataset_v2",
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "as_of_date": stats.target_date_max,
        "source": SOURCE_NAME,
        "status": stats.status,
        "daily_prediction": {
            "state_rows_before": stats.state_rows_before,
            "state_rows_after": stats.state_rows_after,
            "appended_state_rows": stats.appended_state_rows,
            "prediction_rows": stats.prediction_rows,
            "target_date_min": stats.target_date_min,
            "target_date_max": stats.target_date_max,
            "latest_feature_date": stats.latest_feature_date,
            "model_meta": prediction_meta,
            "operational_limit": (
                "Daily predictions advance only as far as the latest available individual station price date plus one day. "
                "If station price files are not updated, the web output is rebuilt from the existing latest state."
            ),
        },
        "outputs": {
            "web_price_history_region": file_info(web_dir / "web_price_history_region.csv", repo_root),
            "web_region_today": file_info(web_dir / "web_region_today.csv", repo_root),
            "web_national_today": file_info(web_dir / "web_national_today.csv", repo_root),
            "web_latest_grid_predictions": file_info(web_dir / "web_latest_grid_predictions.csv", repo_root),
            "grid_region_lookup": file_info(web_dir / "grid_region_lookup.csv", repo_root),
            "station_grid_lookup": file_info(output_dir / STATE_DIR_NAME / STATION_GRID_LOOKUP_NAME, repo_root),
            "inference_state": {
                "manifest": file_info(output_dir / STATE_DIR_NAME / STATE_MANIFEST_NAME, repo_root),
                "data": file_info(output_dir / STATE_DIR_NAME / STATE_FILE_NAME, repo_root),
            },
        },
        "files_changed_this_run": {key: file_info(path, repo_root) if path else None for key, path in files.items()},
    }
    save_json(output_dir / "operational_dataset_manifest.json", payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the operational daily fair-price inference path from the compact AI 06 state. "
            "This does not require the local-only grid_target.parquet."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--station-price-root", type=Path, default=DEFAULT_PRICE_ROOT)
    parser.add_argument("--station-points", type=Path, default=DEFAULT_STATION_POINTS)
    parser.add_argument("--source-start-date", default="")
    parser.add_argument("--source-end-date", default="")
    parser.add_argument("--target-start-date", default="")
    parser.add_argument("--target-end-date", default="")
    parser.add_argument("--fuel", choices=["all", "gasoline", "diesel"], default="all")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--history-years", type=int, default=10)
    parser.add_argument("--state-days", type=int, default=45)
    parser.add_argument("--round-digits", type=int, default=3)
    parser.add_argument("--min-feature-coverage-ratio", type=float, default=0.80)
    parser.add_argument("--source-backfill-days", type=int, default=7)
    parser.add_argument("--force-station-grid-lookup", action="store_true")
    parser.add_argument("--skip-state-update", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start_time = time.time()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    web_dir = output_dir / WEB_DIR_NAME
    state_dir = output_dir / STATE_DIR_NAME
    state_path = state_dir / STATE_FILE_NAME
    state_manifest_path = state_dir / STATE_MANIFEST_NAME
    lookup_path = state_dir / STATION_GRID_LOOKUP_NAME
    fuel_names = ["gasoline", "diesel"] if args.fuel == "all" else [args.fuel]

    source_start = parse_date(args.source_start_date)
    source_end = parse_date(args.source_end_date)
    target_start = parse_date(args.target_start_date)
    target_end = parse_date(args.target_end_date)

    print("[CONFIG]")
    print(f"repo_root          = {repo_root}")
    print(f"state_path         = {state_path}")
    print(f"web_dir            = {web_dir}")
    print(f"station_price_root = {args.station_price_root.resolve()}")
    print(f"source_date_filter = {date_text(source_start)} ~ {date_text(source_end)}")
    print(f"target_date_filter = {date_text(target_start)} ~ {date_text(target_end)}")
    print(f"fuels              = {', '.join(fuel_names)}")
    print(f"device             = {args.device}")

    state = load_state(state_path)
    rows_before = len(state)
    lookup = build_station_grid_lookup(
        station_points_path=args.station_points.resolve(),
        state=state,
        lookup_path=lookup_path,
        force=args.force_station_grid_lookup,
    )

    appended_rows = 0
    if not args.skip_state_update:
        state, appended_rows = update_state_from_station_prices(
            state=state,
            state_path=state_path,
            station_lookup=lookup,
            price_root=args.station_price_root.resolve(),
            source_start_date=source_start,
            source_end_date=source_end,
            state_days=args.state_days,
            min_feature_coverage_ratio=args.min_feature_coverage_ratio,
            source_backfill_days=args.source_backfill_days,
        )

    predictions, prediction_meta = predict_operational(
        state=state,
        web_dir=web_dir,
        device_name=args.device,
        batch_size=args.batch_size,
        fuel_names=fuel_names,
        target_start_date=target_start,
        target_end_date=target_end,
        min_feature_coverage_ratio=args.min_feature_coverage_ratio,
    )

    files: dict[str, Path | None] = {}
    if predictions.empty:
        status = prediction_meta.get("status", "no_predictions")
        history_path = web_dir / "web_price_history_region.csv"
        today_path = web_dir / "web_region_today.csv"
        latest_grid_path = web_dir / "web_latest_grid_predictions.csv"
        national_path = web_dir / "web_national_today.csv"
        history = read_csv(history_path) if history_path.exists() else pd.DataFrame(columns=HISTORY_COLUMNS)
        today = read_csv(today_path) if today_path.exists() else pd.DataFrame(columns=TODAY_COLUMNS)
        files.update(
            {
                "web_price_history_region": history_path if history_path.exists() else None,
                "web_region_today": today_path if today_path.exists() else None,
                "web_national_today": national_path if national_path.exists() else None,
                "web_latest_grid_predictions": latest_grid_path if latest_grid_path.exists() else None,
            }
        )
    else:
        status = "completed"
        region_summary = summarize_region(predictions)
        history, history_path = merge_history(web_dir, region_summary, args.history_years, args.round_digits)
        today, today_path, national_path = write_today_files(web_dir, history, region_summary, args.round_digits)
        latest_grid_path = write_latest_grid(web_dir, predictions, args.round_digits)
        files.update(
            {
                "web_price_history_region": history_path,
                "web_region_today": today_path,
                "web_national_today": national_path,
                "web_latest_grid_predictions": latest_grid_path,
            }
        )

    write_state_manifest(
        repo_root=repo_root,
        state_path=state_path,
        manifest_path=state_manifest_path,
        state=state,
        state_days=args.state_days,
        appended_rows=appended_rows,
        lookup_path=lookup_path,
    )

    target_min = date_text(predictions["source_date"].min()) if not predictions.empty else None
    target_max = date_text(predictions["source_date"].max()) if not predictions.empty else None
    if target_max is None and not today.empty and "source_date" in today.columns:
        target_max = date_text(pd.to_datetime(today["source_date"], errors="coerce").max())
    stats = RunStats(
        status=status,
        state_rows_before=rows_before,
        state_rows_after=len(state),
        appended_state_rows=appended_rows,
        prediction_rows=int(len(predictions)),
        target_date_min=target_min,
        target_date_max=target_max,
        latest_feature_date=date_text(state["date"].max()) if not state.empty else None,
    )
    update_operational_manifest(repo_root, output_dir, stats, prediction_meta, files)

    print(
        "[DONE] "
        f"status={stats.status}, predictions={stats.prediction_rows:,}, "
        f"state={stats.state_rows_before:,}->{stats.state_rows_after:,}, "
        f"elapsed={seconds_text(time.time() - start_time)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
