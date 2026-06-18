from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import duckdb
import pandas as pd


# =============================================================================
# Local fixed configuration
# =============================================================================

REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE3_DIR = Path(__file__).resolve().parent

GRID_PATH = REPO_ROOT / "ai-model" / "02_spatial_grid_build" / "outputs" / "grid.parquet"
GASOLINE_POLICY_PATH = (
    REPO_ROOT
    / "data-analysis"
    / "05_policy_application"
    / "outputs"
    / "휘발유"
    / "일별_정책적용_데이터_휘발유.csv"
)
DIESEL_POLICY_PATH = (
    REPO_ROOT
    / "data-analysis"
    / "05_policy_application"
    / "outputs"
    / "경유"
    / "일별_정책적용_데이터_경유.csv"
)

OUTPUT_ROOT = STAGE3_DIR / "outputs"
NATIONAL_FAIR_PATH = OUTPUT_ROOT / "national_fair_prices.parquet"
TARGET_DATASET_PATH = OUTPUT_ROOT / "grid_target.parquet"
SUMMARY_CSV_PATH = OUTPUT_ROOT / "target_dataset_summary.csv"
METADATA_JSON_PATH = OUTPUT_ROOT / "target_dataset_metadata.json"


FUEL_SPECS = {
    "gasoline": {
        "label": "휘발유",
        "policy_path": GASOLINE_POLICY_PATH,
        "actual_col": "gasoline_price_mean",
        "station_count_col": "gasoline_station_count",
    },
    "diesel": {
        "label": "경유",
        "policy_path": DIESEL_POLICY_PATH,
        "actual_col": "diesel_price_mean",
        "station_count_col": "diesel_station_count",
    },
}


# =============================================================================
# Utility
# =============================================================================


def qstr(value: Any) -> str:
    return "'" + str(value).replace("\\", "/").replace("'", "''") + "'"


def sql_date(value: pd.Timestamp | str) -> str:
    return f"DATE {qstr(pd.Timestamp(value).strftime('%Y-%m-%d'))}"


def seconds_text(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60:.1f}m"


def save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def file_signature(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def require_files(paths: Iterable[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required input files:\n" + "\n".join(missing))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build grid-level fair price target dataset from AI 02 grid.parquet "
            "and data-analysis 05 policy-applied fair price outputs."
        )
    )
    parser.add_argument(
        "--smoke-limit",
        type=int,
        default=None,
        help=(
            "Write a small smoke-test parquet instead of the full target dataset. "
            "The smoke output is not used by stage 04."
        ),
    )
    parser.add_argument(
        "--smoke-start",
        type=str,
        default="2026-01-01",
        help="First date for --smoke-limit output.",
    )
    parser.add_argument(
        "--smoke-end",
        type=str,
        default="2026-01-31",
        help="Last date for --smoke-limit output.",
    )
    return parser.parse_args()


# =============================================================================
# National fair price table
# =============================================================================


def load_policy_output(fuel: str, spec: Dict[str, Any]) -> pd.DataFrame:
    path = Path(spec["policy_path"])
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.floor("D")

    renamed = pd.DataFrame(
        {
            "date": df["date"],
            f"{fuel}_national_actual_price_da": pd.to_numeric(df["국내유가_원L"], errors="coerce"),
            f"{fuel}_national_fair_price_no_policy": pd.to_numeric(df["적정가격_미정책_원L"], errors="coerce"),
            f"{fuel}_national_fair_band_low_no_policy": pd.to_numeric(df["적정범위_미정책_하한_원L"], errors="coerce"),
            f"{fuel}_national_fair_band_high_no_policy": pd.to_numeric(df["적정범위_미정책_상한_원L"], errors="coerce"),
            f"{fuel}_national_fair_price_policy": pd.to_numeric(df["적정가격_정책적용_원L"], errors="coerce"),
            f"{fuel}_national_fair_band_low_policy": pd.to_numeric(df["적정범위_정책적용_하한_원L"], errors="coerce"),
            f"{fuel}_national_fair_band_high_policy": pd.to_numeric(df["적정범위_정책적용_상한_원L"], errors="coerce"),
            f"{fuel}_policy_effect": pd.to_numeric(df["정책효과_원L"], errors="coerce"),
            f"{fuel}_policy_shift": pd.to_numeric(df["정책적용_시프트_원L"], errors="coerce"),
            f"{fuel}_policy_applied": df["정책적용여부_전체"].fillna(False).astype(bool),
            f"{fuel}_fair_price_available": pd.to_numeric(df["적정가격_정책적용_원L"], errors="coerce").notna(),
        }
    )
    return renamed.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def build_national_fair_prices() -> pd.DataFrame:
    national: Optional[pd.DataFrame] = None
    for fuel, spec in FUEL_SPECS.items():
        fuel_df = load_policy_output(fuel, spec)
        national = fuel_df if national is None else national.merge(fuel_df, on="date", how="outer")

    assert national is not None
    national = national.sort_values("date").reset_index(drop=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    national.to_parquet(NATIONAL_FAIR_PATH, index=False, compression="zstd")
    print(f"[SAVE] {NATIONAL_FAIR_PATH} rows={len(national):,}")
    return national


# =============================================================================
# Grid target dataset
# =============================================================================


def build_target_query(output_path: Path, smoke_limit: Optional[int], smoke_start: str, smoke_end: str) -> str:
    smoke_date_filter = ""
    smoke_limit_sql = ""
    if smoke_limit is not None:
        if smoke_limit <= 0:
            raise ValueError("--smoke-limit must be positive")
        smoke_date_filter = (
            f"WHERE CAST(date AS DATE) >= {sql_date(smoke_start)} "
            f"AND CAST(date AS DATE) <= {sql_date(smoke_end)}"
        )
        smoke_limit_sql = f"ORDER BY date, grid_id LIMIT {int(smoke_limit)}"

    fuel_exprs = []
    for fuel, spec in FUEL_SPECS.items():
        actual_col = spec["actual_col"]
        station_count_col = spec["station_count_col"]
        national_actual_grid = f"{fuel}_national_actual_price_grid"
        national_actual_da = f"{fuel}_national_actual_price_da"
        fair_policy = f"{fuel}_national_fair_price_policy"
        fair_no_policy = f"{fuel}_national_fair_price_no_policy"
        low_policy = f"{fuel}_national_fair_band_low_policy"
        high_policy = f"{fuel}_national_fair_band_high_policy"
        spread_col = f"{fuel}_actual_spread_grid"
        target_col = f"{fuel}_grid_fair_price_target"
        low_col = f"{fuel}_grid_fair_band_low_policy"
        high_col = f"{fuel}_grid_fair_band_high_policy"
        fair_gap_col = f"{fuel}_grid_fair_gap_to_actual"
        national_gap_col = f"{fuel}_national_gap_policy"
        actual_da_gap_col = f"{fuel}_national_actual_gap_grid_vs_da"
        target_no_policy_col = f"{fuel}_grid_fair_price_no_policy"

        valid_actual = (
            f"{actual_col} IS NOT NULL "
            f"AND CAST({station_count_col} AS DOUBLE) > 0 "
            f"AND {national_actual_grid} IS NOT NULL"
        )
        valid_target = f"{valid_actual} AND {fair_policy} IS NOT NULL"

        fuel_exprs.extend(
            [
                f"{national_actual_grid}",
                f"{national_actual_da}",
                (
                    f"CASE WHEN {national_actual_grid} IS NOT NULL AND {national_actual_da} IS NOT NULL "
                    f"THEN {national_actual_grid} - {national_actual_da} END AS {actual_da_gap_col}"
                ),
                f"{fair_no_policy}",
                f"{fair_policy}",
                f"{low_policy}",
                f"{high_policy}",
                (
                    f"CASE WHEN {national_actual_grid} IS NOT NULL AND {fair_policy} IS NOT NULL "
                    f"THEN {national_actual_grid} - {fair_policy} END AS {national_gap_col}"
                ),
                (
                    f"CASE WHEN {valid_actual} "
                    f"THEN CAST({actual_col} AS DOUBLE) - {national_actual_grid} END AS {spread_col}"
                ),
                (
                    f"CASE WHEN {valid_actual} AND {fair_no_policy} IS NOT NULL "
                    f"THEN {fair_no_policy} + (CAST({actual_col} AS DOUBLE) - {national_actual_grid}) "
                    f"END AS {target_no_policy_col}"
                ),
                (
                    f"CASE WHEN {valid_target} "
                    f"THEN {fair_policy} + (CAST({actual_col} AS DOUBLE) - {national_actual_grid}) "
                    f"END AS {target_col}"
                ),
                (
                    f"CASE WHEN {valid_actual} AND {low_policy} IS NOT NULL "
                    f"THEN {low_policy} + (CAST({actual_col} AS DOUBLE) - {national_actual_grid}) "
                    f"END AS {low_col}"
                ),
                (
                    f"CASE WHEN {valid_actual} AND {high_policy} IS NOT NULL "
                    f"THEN {high_policy} + (CAST({actual_col} AS DOUBLE) - {national_actual_grid}) "
                    f"END AS {high_col}"
                ),
                (
                    f"CASE WHEN {valid_target} "
                    f"THEN CAST({actual_col} AS DOUBLE) - "
                    f"({fair_policy} + (CAST({actual_col} AS DOUBLE) - {national_actual_grid})) "
                    f"END AS {fair_gap_col}"
                ),
            ]
        )

    fuel_expr_sql = ",\n                ".join(fuel_exprs)

    return f"""
        COPY (
            WITH grid_raw AS (
                SELECT CAST(date AS DATE) AS date, * EXCLUDE (date)
                FROM read_parquet({qstr(GRID_PATH)})
                {smoke_date_filter}
            ),
            anchor AS (
                SELECT
                    date,
                    SUM(
                        CASE
                            WHEN gasoline_price_mean IS NOT NULL
                             AND CAST(gasoline_station_count AS DOUBLE) > 0
                            THEN CAST(gasoline_price_mean AS DOUBLE) * CAST(gasoline_station_count AS DOUBLE)
                        END
                    ) / NULLIF(
                        SUM(
                            CASE
                                WHEN gasoline_price_mean IS NOT NULL
                                 AND CAST(gasoline_station_count AS DOUBLE) > 0
                                THEN CAST(gasoline_station_count AS DOUBLE)
                                ELSE 0
                            END
                        ),
                        0
                    ) AS gasoline_national_actual_price_grid,
                    SUM(
                        CASE
                            WHEN diesel_price_mean IS NOT NULL
                             AND CAST(diesel_station_count AS DOUBLE) > 0
                            THEN CAST(diesel_price_mean AS DOUBLE) * CAST(diesel_station_count AS DOUBLE)
                        END
                    ) / NULLIF(
                        SUM(
                            CASE
                                WHEN diesel_price_mean IS NOT NULL
                                 AND CAST(diesel_station_count AS DOUBLE) > 0
                                THEN CAST(diesel_station_count AS DOUBLE)
                                ELSE 0
                            END
                        ),
                        0
                    ) AS diesel_national_actual_price_grid
                FROM grid_raw
                GROUP BY date
            ),
            fair AS (
                SELECT CAST(date AS DATE) AS date, * EXCLUDE (date)
                FROM read_parquet({qstr(NATIONAL_FAIR_PATH)})
            ),
            joined AS (
                SELECT
                    g.*,
                    a.gasoline_national_actual_price_grid,
                    a.diesel_national_actual_price_grid,
                    f.* EXCLUDE (date)
                FROM grid_raw g
                LEFT JOIN anchor a
                    ON a.date = g.date
                LEFT JOIN fair f
                    ON f.date = g.date
            ),
            targeted AS (
                SELECT
                    *,
                    {fuel_expr_sql}
                FROM joined
            )
            SELECT
                *
            FROM targeted
            {smoke_limit_sql}
        )
        TO {qstr(output_path)} (FORMAT PARQUET, COMPRESSION ZSTD)
    """


def build_summary(con: duckdb.DuckDBPyConnection, output_path: Path) -> pd.DataFrame:
    summary = con.execute(
        f"""
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT grid_id) AS unique_grid_count,
            MIN(date) AS date_min,
            MAX(date) AS date_max,
            SUM(CASE WHEN gasoline_grid_fair_price_target IS NOT NULL THEN 1 ELSE 0 END) AS gasoline_target_rows,
            SUM(CASE WHEN diesel_grid_fair_price_target IS NOT NULL THEN 1 ELSE 0 END) AS diesel_target_rows,
            MIN(CASE WHEN gasoline_grid_fair_price_target IS NOT NULL THEN date END) AS gasoline_target_date_min,
            MAX(CASE WHEN gasoline_grid_fair_price_target IS NOT NULL THEN date END) AS gasoline_target_date_max,
            MIN(CASE WHEN diesel_grid_fair_price_target IS NOT NULL THEN date END) AS diesel_target_date_min,
            MAX(CASE WHEN diesel_grid_fair_price_target IS NOT NULL THEN date END) AS diesel_target_date_max,
            SUM(CASE WHEN date >= DATE '2026-01-01' AND gasoline_grid_fair_price_target IS NOT NULL THEN 1 ELSE 0 END) AS gasoline_target_2026_rows,
            SUM(CASE WHEN date >= DATE '2026-01-01' AND diesel_grid_fair_price_target IS NOT NULL THEN 1 ELSE 0 END) AS diesel_target_2026_rows,
            SUM(gasoline_grid_fair_price_target * CAST(gasoline_station_count AS DOUBLE))
                / NULLIF(SUM(CASE WHEN gasoline_grid_fair_price_target IS NOT NULL THEN CAST(gasoline_station_count AS DOUBLE) ELSE 0 END), 0)
                AS gasoline_target_weighted_mean,
            SUM(diesel_grid_fair_price_target * CAST(diesel_station_count AS DOUBLE))
                / NULLIF(SUM(CASE WHEN diesel_grid_fair_price_target IS NOT NULL THEN CAST(diesel_station_count AS DOUBLE) ELSE 0 END), 0)
                AS diesel_target_weighted_mean,
            AVG(gasoline_national_gap_policy) AS gasoline_national_gap_policy_mean,
            AVG(diesel_national_gap_policy) AS diesel_national_gap_policy_mean
        FROM read_parquet({qstr(output_path)})
        """
    ).df()
    return summary


def build_metadata(output_path: Path, summary: pd.DataFrame, smoke_limit: Optional[int]) -> Dict[str, Any]:
    return {
        "created_at": pd.Timestamp.now().isoformat(),
        "stage": "ai-model/03_target_dataset_build",
        "is_smoke_output": smoke_limit is not None,
        "inputs": {
            "grid": file_signature(GRID_PATH),
            "gasoline_policy_application": file_signature(GASOLINE_POLICY_PATH),
            "diesel_policy_application": file_signature(DIESEL_POLICY_PATH),
        },
        "outputs": {
            "national_fair_prices": str(NATIONAL_FAIR_PATH),
            "grid_target": str(output_path),
            "summary": str(SUMMARY_CSV_PATH),
        },
        "target_formula": {
            "national_gap_policy": "national_actual_price_grid(t) - national_fair_price_policy(t)",
            "grid_actual_spread": "grid_actual_price(t) - national_actual_price_grid(t)",
            "grid_fair_price_target": "national_fair_price_policy(t) + grid_actual_spread(t)",
            "stage04_target_delta": "fair_price_delta_target = grid_fair_price_target(t) - grid_actual_price(t-1)",
        },
        "target_columns": {
            "gasoline": {
                "level": "gasoline_grid_fair_price_target",
                "band_low": "gasoline_grid_fair_band_low_policy",
                "band_high": "gasoline_grid_fair_band_high_policy",
            },
            "diesel": {
                "level": "diesel_grid_fair_price_target",
                "band_low": "diesel_grid_fair_band_low_policy",
                "band_high": "diesel_grid_fair_band_high_policy",
            },
        },
        "summary": summary.to_dict(orient="records")[0] if len(summary) else {},
    }


def main() -> None:
    args = parse_args()
    output_path = TARGET_DATASET_PATH
    if args.smoke_limit is not None:
        output_path = OUTPUT_ROOT / "grid_target_smoke.parquet"

    require_files([GRID_PATH, GASOLINE_POLICY_PATH, DIESEL_POLICY_PATH])
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    print("[CONFIG]")
    print(f"REPO_ROOT                  = {REPO_ROOT}")
    print(f"GRID_PATH                  = {GRID_PATH}")
    print(f"GASOLINE_POLICY_PATH       = {GASOLINE_POLICY_PATH}")
    print(f"DIESEL_POLICY_PATH         = {DIESEL_POLICY_PATH}")
    print(f"OUTPUT_ROOT                = {OUTPUT_ROOT}")
    print(f"TARGET_DATASET_PATH        = {output_path}")
    if args.smoke_limit is not None:
        print(f"SMOKE                      = {args.smoke_start} ~ {args.smoke_end}, limit={args.smoke_limit:,}")

    start = time.time()
    national = build_national_fair_prices()
    print(
        "[NATIONAL FAIR] "
        f"rows={len(national):,}, date={national['date'].min().date()}~{national['date'].max().date()}"
    )

    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA threads={max(os.cpu_count() or 2, 2)}")
    con.execute("SET preserve_insertion_order=false")

    print("[BUILD] grid target dataset")
    con.execute(build_target_query(output_path, args.smoke_limit, args.smoke_start, args.smoke_end))
    print(f"[SAVE] {output_path}")

    summary = build_summary(con, output_path)
    summary.to_csv(SUMMARY_CSV_PATH, index=False, encoding="utf-8-sig")
    print("[SUMMARY]")
    print(summary.to_string(index=False))
    print(f"[SAVE] {SUMMARY_CSV_PATH}")

    metadata = build_metadata(output_path, summary, args.smoke_limit)
    save_json(METADATA_JSON_PATH, metadata)
    print(f"[SAVE] {METADATA_JSON_PATH}")
    print(f"[DONE] elapsed={seconds_text(time.time() - start)}")


if __name__ == "__main__":
    main()
