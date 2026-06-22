from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


KST = timezone(timedelta(hours=9))

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGE5_OUTPUT_DIR = REPO_ROOT / "ai-model" / "05_full_grid_prediction_for_web" / "outputs"
DEFAULT_TARGET_DATASET = REPO_ROOT / "ai-model" / "03_target_dataset_build" / "outputs" / "grid_target.parquet"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"

WEB_DIR_NAME = "web"
INFERENCE_STATE_DIR_NAME = "inference_state"
LATEST_GRID_FILENAME = "web_latest_grid_predictions.csv"

FUEL_CONFIGS = {
    "gasoline": {
        "actual_col": "gasoline_price_mean",
        "station_count_col": "gasoline_station_count",
        "fair_target_col": "gasoline_grid_fair_price_target",
        "national_actual_col": "gasoline_national_actual_price_grid",
        "band_low_col": "gasoline_grid_fair_band_low_policy",
        "band_high_col": "gasoline_grid_fair_band_high_policy",
        "model_metadata": REPO_ROOT
        / "ai-model"
        / "04_prediction_model_training"
        / "outputs"
        / "gasoline"
        / "gasoline_model_metadata.json",
    },
    "diesel": {
        "actual_col": "diesel_price_mean",
        "station_count_col": "diesel_station_count",
        "fair_target_col": "diesel_grid_fair_price_target",
        "national_actual_col": "diesel_national_actual_price_grid",
        "band_low_col": "diesel_grid_fair_band_low_policy",
        "band_high_col": "diesel_grid_fair_band_high_policy",
        "model_metadata": REPO_ROOT
        / "ai-model"
        / "04_prediction_model_training"
        / "outputs"
        / "diesel"
        / "diesel_model_metadata.json",
    },
}

STANDARD_HISTORY_COLUMNS = [
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

STANDARD_TODAY_COLUMNS = [
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


def qstr(value: Any) -> str:
    return "'" + str(value).replace("\\", "/").replace("'", "''") + "'"


def qid(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


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


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"[SAVE] {path} size={path.stat().st_size:,}")


def file_info(path: Path, repo_root: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    try:
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel = str(path)
    return {
        "path": rel,
        "exists": True,
        "bytes": int(stat.st_size),
        "mb": round(stat.st_size / 1024 / 1024, 3),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, KST).isoformat(timespec="seconds"),
    }


def relative_source(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def numeric_round(df: pd.DataFrame, digits: int) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in {"date", "source_date", "region", "fuel", "judge_policy", "source", "grid_id"}:
            continue
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].round(digits)
    return out


def source_web_history(stage5_dir: Path) -> tuple[pd.DataFrame, Path]:
    web_history = stage5_dir / "web_price_history_region.csv"
    if web_history.exists():
        df = read_csv(web_history)
        return df, web_history

    frames: list[pd.DataFrame] = []
    for fuel in FUEL_CONFIGS:
        path = stage5_dir / fuel / f"{fuel}_region_daily_summary.csv"
        if not path.exists():
            continue
        part = read_csv(path)
        rename = {
            "station_weight_sum": "station_count",
        }
        part = part.rename(columns=rename)
        frames.append(part)

    if not frames:
        raise FileNotFoundError(
            "No stage 5 web history source found. Expected web_price_history_region.csv "
            "or {fuel}/{fuel}_region_daily_summary.csv under stage 5 outputs."
        )

    df = pd.concat(frames, ignore_index=True, sort=False)
    df["source"] = "ai-model/05_full_grid_prediction_for_web/predict_full_grid_for_web.py"
    return df, stage5_dir


def build_web_history(
    repo_root: Path,
    stage5_dir: Path,
    web_dir: Path,
    as_of_date: str | None,
    history_years: int,
    round_digits: int,
) -> tuple[pd.DataFrame, Path]:
    df, source_path = source_web_history(stage5_dir)
    missing = [col for col in STANDARD_HISTORY_COLUMNS if col not in df.columns]
    for col in missing:
        df[col] = None

    work = df[STANDARD_HISTORY_COLUMNS].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date"])
    if as_of_date:
        resolved_as_of = pd.Timestamp(as_of_date)
    else:
        resolved_as_of = work["date"].max()

    work = work[work["date"] <= resolved_as_of]
    if history_years > 0:
        cutoff = resolved_as_of - pd.DateOffset(years=history_years)
        work = work[work["date"] >= cutoff]

    work["date"] = work["date"].dt.strftime("%Y-%m-%d")
    work = numeric_round(work.sort_values(["date", "region", "fuel"]).reset_index(drop=True), round_digits)
    work["source"] = relative_source(source_path, repo_root)

    out_path = web_dir / "web_price_history_region.csv"
    write_csv(out_path, work)
    return work, out_path


def build_web_today(
    repo_root: Path,
    stage5_dir: Path,
    web_history: pd.DataFrame,
    web_dir: Path,
    as_of_date: str | None,
    round_digits: int,
) -> tuple[pd.DataFrame, Path]:
    today_path = stage5_dir / "web_region_today.csv"
    if today_path.exists():
        today = read_csv(today_path)
        source_path = today_path
    else:
        history = web_history.copy()
        history["date"] = pd.to_datetime(history["date"], errors="coerce")
        if as_of_date:
            history = history[history["date"] <= pd.Timestamp(as_of_date)]
        idx = history.sort_values("date").groupby(["region", "fuel"], dropna=False).tail(1).index
        today = history.loc[idx].copy().rename(columns={"date": "source_date"})
        today["station_count"] = None
        today["judge_policy"] = None
        source_path = web_dir / "web_price_history_region.csv"

    for col in STANDARD_TODAY_COLUMNS:
        if col not in today.columns:
            today[col] = None

    today = today[STANDARD_TODAY_COLUMNS].copy()
    today["source_date"] = pd.to_datetime(today["source_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if as_of_date:
        today = today[pd.to_datetime(today["source_date"], errors="coerce") <= pd.Timestamp(as_of_date)]
        idx = today.sort_values("source_date").groupby(["region", "fuel"], dropna=False).tail(1).index
        today = today.loc[idx]

    today = numeric_round(today.sort_values(["region", "fuel"]).reset_index(drop=True), round_digits)
    out_path = web_dir / "web_region_today.csv"
    write_csv(out_path, today)

    today["source"] = relative_source(source_path, repo_root)
    return today, out_path


def build_latest_grid(stage5_dir: Path, web_dir: Path, round_digits: int) -> Path | None:
    frames: list[pd.DataFrame] = []
    for fuel in FUEL_CONFIGS:
        path = stage5_dir / fuel / f"{fuel}_latest_grid_predictions.csv"
        if not path.exists():
            continue
        part = read_csv(path)
        if "fuel" not in part.columns:
            part["fuel"] = fuel
        rename = {
            "date": "source_date",
            "station_weight": "station_count",
            "actual_grid_price": "actual_price",
            "pred_grid_fair_price": "fair_price_policy",
            "pred_band_low_policy": "band_low_policy",
            "pred_band_high_policy": "band_high_policy",
            "actual_gap_to_pred_fair": "gap_policy",
            "pred_judge_policy": "judge_policy",
        }
        part = part.rename(columns=rename)
        keep = [
            "source_date",
            "fuel",
            "grid_id",
            "region",
            "cell_x",
            "cell_y",
            "center_lon",
            "center_lat",
            "station_count",
            "actual_price",
            "fair_price_policy",
            "band_low_policy",
            "band_high_policy",
            "gap_policy",
            "judge_policy",
        ]
        for col in keep:
            if col not in part.columns:
                part[col] = None
        frames.append(part[keep].copy())

    if not frames:
        return None

    out = pd.concat(frames, ignore_index=True, sort=False)
    out["source_date"] = pd.to_datetime(out["source_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = numeric_round(out.sort_values(["fuel", "region", "grid_id"]).reset_index(drop=True), round_digits)
    out_path = web_dir / LATEST_GRID_FILENAME
    write_csv(out_path, out)
    return out_path


def copy_region_lookup(stage5_dir: Path, web_dir: Path) -> Path | None:
    src = stage5_dir / "grid_region_lookup.csv"
    if not src.exists():
        return None
    df = read_csv(src)
    out_path = web_dir / "grid_region_lookup.csv"
    write_csv(out_path, df)
    return out_path


def build_national_today(today: pd.DataFrame, web_dir: Path, round_digits: int) -> Path | None:
    if today.empty:
        return None

    rows: list[dict[str, Any]] = []
    for fuel, part in today.groupby("fuel", dropna=False):
        weights = pd.to_numeric(part.get("station_count"), errors="coerce").fillna(0)
        row: dict[str, Any] = {"fuel": fuel, "source_date": part["source_date"].max()}
        for col in ["actual_price", "fair_price_policy", "band_low_policy", "band_high_policy", "gap_policy"]:
            values = pd.to_numeric(part[col], errors="coerce")
            mask = values.notna() & weights.gt(0)
            if mask.any():
                row[col] = float((values[mask] * weights[mask]).sum() / weights[mask].sum())
            else:
                row[col] = float(values.mean()) if values.notna().any() else None
        row["station_count"] = float(weights.sum()) if weights.notna().any() else None
        rows.append(row)

    out = numeric_round(pd.DataFrame(rows).sort_values("fuel").reset_index(drop=True), round_digits)
    out_path = web_dir / "web_national_today.csv"
    write_csv(out_path, out)
    return out_path


def schema_columns(con: duckdb.DuckDBPyConnection, parquet_path: Path) -> set[str]:
    df = con.execute(f"DESCRIBE SELECT * FROM read_parquet({qstr(parquet_path)})").df()
    return set(df["column_name"].astype(str))


def load_model_static_columns() -> set[str]:
    cols: set[str] = set()
    for cfg in FUEL_CONFIGS.values():
        path = cfg["model_metadata"]
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        cols.update(payload.get("static_feature_columns", []))
        cols.update(payload.get("latest_feature_columns", []))
    cols.discard("official_price_age_days")
    cols.discard("official_price_source_year")
    cols.add("official_price_source_date")
    return cols


def required_target_columns(all_columns: set[str]) -> list[str]:
    required = {
        "date",
        "grid_id",
        "cell_x",
        "cell_y",
        "center_lon",
        "center_lat",
    }
    required.update(load_model_static_columns())
    for cfg in FUEL_CONFIGS.values():
        required.update(
            [
                cfg["actual_col"],
                cfg["station_count_col"],
                cfg["fair_target_col"],
                cfg["national_actual_col"],
                cfg["band_low_col"],
                cfg["band_high_col"],
            ]
        )
    return sorted(col for col in required if col in all_columns)


def build_inference_state(
    repo_root: Path,
    target_dataset: Path,
    output_dir: Path,
    as_of_date: str | None,
    state_days: int,
    max_git_file_mb: float,
) -> dict[str, Any]:
    state_dir = output_dir / INFERENCE_STATE_DIR_NAME
    state_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = state_dir / "recent_model_input_manifest.json"

    if not target_dataset.exists():
        payload = {
            "status": "skipped",
            "reason": "target dataset is missing",
            "target_dataset": str(target_dataset),
            "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        }
        save_json(manifest_path, payload)
        return {"manifest": manifest_path, "data": None, "status": "skipped"}

    con = duckdb.connect(database=":memory:")
    con.execute("SET preserve_insertion_order=false")
    all_columns = schema_columns(con, target_dataset)
    cols = required_target_columns(all_columns)
    if "date" not in cols or "grid_id" not in cols:
        raise RuntimeError("target dataset must contain date and grid_id columns")

    if as_of_date:
        state_end = pd.Timestamp(as_of_date)
    else:
        row = con.execute(
            f"SELECT MAX(CAST(date AS DATE)) FROM read_parquet({qstr(target_dataset)})"
        ).fetchone()
        state_end = pd.Timestamp(row[0])

    state_start = state_end - pd.Timedelta(days=max(state_days - 1, 0))
    select_sql = ", ".join(qid(col) for col in cols)
    out_path = state_dir / "recent_model_input.parquet"

    con.execute(
        f"""
        COPY (
            SELECT {select_sql}
            FROM read_parquet({qstr(target_dataset)})
            WHERE CAST(date AS DATE) BETWEEN DATE {qstr(state_start.strftime('%Y-%m-%d'))}
                                      AND DATE {qstr(state_end.strftime('%Y-%m-%d'))}
            ORDER BY date, grid_id
        ) TO {qstr(out_path)} (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    count, date_min, date_max = con.execute(
        f"""
        SELECT COUNT(*), MIN(CAST(date AS DATE)), MAX(CAST(date AS DATE))
        FROM read_parquet({qstr(out_path)})
        """
    ).fetchone()

    info = file_info(out_path, repo_root)
    status = "ready"
    warning = None
    if info["mb"] > max_git_file_mb:
        status = "too_large_for_git"
        warning = (
            f"recent_model_input.parquet is {info['mb']} MB. "
            f"Reduce --state-days or keep this file out of git."
        )
        print(f"[WARN] {warning}")

    payload = {
        "schema_version": "recent_model_input_state_v1",
        "status": status,
        "warning": warning,
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": relative_source(target_dataset, repo_root),
        "state_days": state_days,
        "date_min": str(date_min) if date_min is not None else None,
        "date_max": str(date_max) if date_max is not None else None,
        "rows": int(count),
        "columns": cols,
        "files": {"recent_model_input": info},
        "use": (
            "This is a compact recent panel for operational inference experiments. "
            "The full historical grid_target.parquet remains a local-only training/build artifact."
        ),
    }
    save_json(manifest_path, payload)
    print(f"[SAVE] {out_path} rows={count:,} size={out_path.stat().st_size:,}")
    return {"manifest": manifest_path, "data": out_path, "status": status}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=REPO_ROOT)
    parser.add_argument("--stage5-output-dir", default=DEFAULT_STAGE5_OUTPUT_DIR)
    parser.add_argument("--target-dataset", default=DEFAULT_TARGET_DATASET)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--as-of-date", default="")
    parser.add_argument("--history-years", type=int, default=10)
    parser.add_argument("--state-days", type=int, default=35)
    parser.add_argument("--round-digits", type=int, default=3)
    parser.add_argument("--max-git-file-mb", type=float, default=95.0)
    parser.add_argument("--skip-inference-state", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    stage5_dir = Path(args.stage5_output_dir).resolve()
    target_dataset = Path(args.target_dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    web_dir = output_dir / WEB_DIR_NAME
    as_of_date = args.as_of_date.strip() or None

    print("[CONFIG]")
    print(f"repo_root         = {repo_root}")
    print(f"stage5_output_dir = {stage5_dir}")
    print(f"target_dataset    = {target_dataset}")
    print(f"output_dir        = {output_dir}")
    print(f"history_years     = {args.history_years}")
    print(f"state_days        = {args.state_days}")

    history, history_path = build_web_history(
        repo_root=repo_root,
        stage5_dir=stage5_dir,
        web_dir=web_dir,
        as_of_date=as_of_date,
        history_years=args.history_years,
        round_digits=args.round_digits,
    )
    today, today_path = build_web_today(
        repo_root=repo_root,
        stage5_dir=stage5_dir,
        web_history=history,
        web_dir=web_dir,
        as_of_date=as_of_date,
        round_digits=args.round_digits,
    )
    national_path = build_national_today(today, web_dir, args.round_digits)
    latest_grid_path = build_latest_grid(stage5_dir, web_dir, args.round_digits)
    region_lookup_path = copy_region_lookup(stage5_dir, web_dir)

    inference_state: dict[str, Any] | None = None
    if not args.skip_inference_state:
        inference_state = build_inference_state(
            repo_root=repo_root,
            target_dataset=target_dataset,
            output_dir=output_dir,
            as_of_date=as_of_date,
            state_days=args.state_days,
            max_git_file_mb=args.max_git_file_mb,
        )

    manifest = {
        "schema_version": "web_operational_dataset_v1",
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
        "history_years": args.history_years,
        "as_of_date": today["source_date"].dropna().max() if "source_date" in today.columns and not today.empty else None,
        "source_stage5_output_dir": relative_source(stage5_dir, repo_root),
        "outputs": {
            "web_price_history_region": file_info(history_path, repo_root),
            "web_region_today": file_info(today_path, repo_root),
            "web_national_today": file_info(national_path, repo_root) if national_path else None,
            "web_latest_grid_predictions": file_info(latest_grid_path, repo_root) if latest_grid_path else None,
            "grid_region_lookup": file_info(region_lookup_path, repo_root) if region_lookup_path else None,
            "inference_state": None
            if inference_state is None
            else {
                "status": inference_state.get("status"),
                "manifest": file_info(inference_state["manifest"], repo_root),
                "data": file_info(inference_state["data"], repo_root) if inference_state.get("data") else None,
            },
        },
        "row_counts": {
            "history": int(len(history)),
            "today": int(len(today)),
            "regions": int(today["region"].nunique()) if "region" in today.columns else 0,
            "fuels": sorted(str(x) for x in today["fuel"].dropna().unique()) if "fuel" in today.columns else [],
        },
    }
    manifest_path = output_dir / "operational_dataset_manifest.json"
    save_json(manifest_path, manifest)
    print("[DONE]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
