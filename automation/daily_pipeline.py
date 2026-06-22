from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


KST = timezone(timedelta(hours=9))

REQUIRED_COLLECTIONS = [
    {
        "name": "crude",
        "dataset": "crude",
        "pattern": "crude_*.csv",
        "required_for": "data-analysis/01",
        "collector": None,
    },
    {
        "name": "retail_avg",
        "dataset": "retail_avg",
        "pattern": "retail_avg_*.csv",
        "required_for": "data-analysis/01",
        "collector": None,
    },
    {
        "name": "brand_gasoline",
        "dataset": "brand_price",
        "pattern": "brand_gasoline_*.csv",
        "required_for": "data-analysis/01",
        "collector": None,
    },
    {
        "name": "brand_diesel",
        "dataset": "brand_price",
        "pattern": "brand_diesel_*.csv",
        "required_for": "data-analysis/01",
        "collector": None,
    },
    {
        "name": "fx_usdkrw",
        "dataset": "fx_usdkrw",
        "pattern": "fx_usdkrw_*.csv",
        "required_for": "data-analysis/01",
        "collector": "bok_ecos",
    },
    {
        "name": "intl_products",
        "dataset": "intl_products",
        "pattern": "intl_products_*.csv",
        "required_for": "data-analysis/01",
        "collector": None,
    },
    {
        "name": "intl_product_diesel_0001",
        "dataset": "intl_products",
        "pattern": "intl_product_diesel(0.001)_*.csv",
        "required_for": "data-analysis/01",
        "collector": None,
    },
    {
        "name": "gasoline_tax_trend",
        "dataset": "fuel_tax_trend",
        "pattern": "gasoline_tax_trend_*.xls",
        "required_for": "data-analysis/01",
        "collector": None,
    },
    {
        "name": "diesel_tax_trend",
        "dataset": "fuel_tax_trend",
        "pattern": "diesel_tax_trend_*.xls",
        "required_for": "data-analysis/01",
        "collector": None,
    },
    {
        "name": "refinery_weekly_supply",
        "dataset": "refinery_weekly_supply",
        "pattern": "refinery_weekly_supply_prices_by_product_*.csv",
        "required_for": "data-analysis/01",
        "collector": None,
    },
    {
        "name": "korea_fuel_tax_price_policies",
        "dataset": "z_pa_policy",
        "pattern": "korea_fuel_tax_price_policies.csv",
        "required_for": "data-analysis/05",
        "collector": "manual",
    },
]

DATE_COLUMNS = ["date", "기간", "구분", "변환", "날짜", "일자"]


@dataclass
class StepResult:
    name: str
    status: str
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def today_kst() -> date:
    return datetime.now(KST).date()


def parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    if len(text) >= 8 and text[:8].isdigit():
        try:
            return datetime.strptime(text[:8], "%Y%m%d").date()
        except ValueError:
            pass
    if "년" in text and "월" in text and "일" in text:
        compact = (
            text.replace("년", "-")
            .replace("월", "-")
            .replace("일", "")
            .replace(" ", "")
        )
        try:
            return datetime.strptime(compact, "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def date_to_str(value: date | None) -> str | None:
    return value.isoformat() if value else None


def latest_file(base: Path, pattern: str) -> Path | None:
    if not base.exists():
        return None
    files = [p for p in base.glob(pattern) if p.is_file()]
    if not files:
        return None
    return sorted(files, key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)[0]


def sniff_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                rows = [dict(row) for row in reader]
                return list(reader.fieldnames or []), rows
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return [], []


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def find_date_column(fieldnames: list[str]) -> str | None:
    normalized = {field.strip().lstrip("\ufeff"): field for field in fieldnames}
    for candidate in DATE_COLUMNS:
        if candidate in normalized:
            return normalized[candidate]
    return fieldnames[0] if fieldnames else None


def csv_date_range(path: Path) -> tuple[date | None, date | None, int]:
    fieldnames, rows = sniff_csv(path)
    date_col = find_date_column(fieldnames)
    min_date: date | None = None
    max_date: date | None = None
    count = 0
    if not date_col:
        return None, None, len(rows)
    for row in rows:
        parsed = parse_date(row.get(date_col))
        if parsed is None:
            continue
        count += 1
        min_date = parsed if min_date is None or parsed < min_date else min_date
        max_date = parsed if max_date is None or parsed > max_date else max_date
    return min_date, max_date, count


def inspect_collection(repo_root: Path) -> list[StepResult]:
    outputs = repo_root / "data-analysis" / "00_data_collection" / "outputs"
    results: list[StepResult] = []
    for spec in REQUIRED_COLLECTIONS:
        path = latest_file(outputs / spec["dataset"], spec["pattern"])
        if path is None:
            results.append(
                StepResult(
                    name=f"inspect:{spec['name']}",
                    status="missing",
                    detail=f"{spec['dataset']}/{spec['pattern']}",
                )
            )
            continue
        if path.suffix.lower() == ".csv":
            min_dt, max_dt, dated_rows = csv_date_range(path)
            data = {
                "path": str(path.relative_to(repo_root)),
                "date_min": date_to_str(min_dt),
                "date_max": date_to_str(max_dt),
                "dated_rows": dated_rows,
            }
        else:
            data = {"path": str(path.relative_to(repo_root))}
        results.append(StepResult(name=f"inspect:{spec['name']}", status="available", data=data))
    return results


def merge_csv_by_date(existing_path: Path, incoming_path: Path) -> dict[str, Any]:
    existing_fields, existing_rows = sniff_csv(existing_path)
    incoming_fields, incoming_rows = sniff_csv(incoming_path)
    if not existing_fields:
        raise ValueError(f"empty existing csv: {existing_path}")
    if not incoming_fields:
        raise ValueError(f"empty incoming csv: {incoming_path}")

    date_col = find_date_column(existing_fields)
    incoming_date_col = find_date_column(incoming_fields)
    if not date_col or not incoming_date_col:
        raise ValueError(f"date column not found: {existing_path} / {incoming_path}")

    merged_fields = list(dict.fromkeys(existing_fields + incoming_fields))
    by_date: dict[str, dict[str, Any]] = {}
    for row in existing_rows:
        parsed = parse_date(row.get(date_col))
        key = parsed.isoformat() if parsed else str(row.get(date_col, "")).strip()
        if key:
            by_date[key] = row
    before = len(by_date)

    incoming_count = 0
    for row in incoming_rows:
        parsed = parse_date(row.get(incoming_date_col))
        key = parsed.isoformat() if parsed else str(row.get(incoming_date_col, "")).strip()
        if not key:
            continue
        if incoming_date_col != date_col:
            row[date_col] = row.get(incoming_date_col, "")
        by_date[key] = row
        incoming_count += 1

    ordered_rows = [by_date[key] for key in sorted(by_date)]
    write_csv(existing_path, merged_fields, ordered_rows)
    min_dt, max_dt, dated_rows = csv_date_range(existing_path)
    return {
        "existing_before_unique_dates": before,
        "incoming_rows": incoming_count,
        "after_rows": len(ordered_rows),
        "date_min": date_to_str(min_dt),
        "date_max": date_to_str(max_dt),
        "dated_rows": dated_rows,
        "path": str(existing_path),
    }


def merge_incoming_files(repo_root: Path) -> list[StepResult]:
    outputs = repo_root / "data-analysis" / "00_data_collection" / "outputs"
    incoming_root = repo_root / "automation" / "incoming"
    results: list[StepResult] = []
    if not incoming_root.exists():
        return [StepResult("merge_incoming", "skipped", "automation/incoming does not exist")]

    for spec in REQUIRED_COLLECTIONS:
        existing = latest_file(outputs / spec["dataset"], spec["pattern"])
        incoming_dir = incoming_root / spec["dataset"]
        if existing is None or not incoming_dir.exists():
            continue
        incoming_files = sorted(incoming_dir.glob(spec["pattern"]))
        for incoming in incoming_files:
            if existing.suffix.lower() != ".csv" or incoming.suffix.lower() != ".csv":
                results.append(
                    StepResult(
                        f"merge:{spec['name']}",
                        "skipped",
                        f"non-csv merge is not automatic: {incoming}",
                    )
                )
                continue
            try:
                data = merge_csv_by_date(existing, incoming)
                results.append(StepResult(f"merge:{spec['name']}", "merged", data=data))
            except Exception as exc:
                results.append(StepResult(f"merge:{spec['name']}", "failed", repr(exc)))
    if not results:
        results.append(StepResult("merge_incoming", "skipped", "no matching incoming files"))
    return results


def run_command(name: str, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> StepResult:
    try:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=merged_env,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        status = "completed" if completed.returncode == 0 else "failed"
        return StepResult(
            name,
            status,
            data={"returncode": completed.returncode, "output_tail": completed.stdout[-6000:]},
        )
    except FileNotFoundError as exc:
        return StepResult(name, "skipped", f"command not found: {exc}")


def run_collection(repo_root: Path, enabled: bool, start_date: date, end_date: date) -> StepResult:
    if not enabled:
        return StepResult("collect", "skipped", "disabled")
    if start_date > end_date:
        return StepResult(
            "collect",
            "skipped",
            "already up to date",
            {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        )
    script = repo_root / "automation" / "collect_sources.py"
    if not script.exists():
        return StepResult("collect", "skipped", "automation/collect_sources.py missing")
    return run_command(
        "collect",
        [
            sys.executable,
            str(script),
            "--repo-root",
            str(repo_root),
            "--start-date",
            start_date.isoformat(),
            "--end-date",
            end_date.isoformat(),
        ],
        repo_root,
    )


def run_preprocessing(repo_root: Path, enabled: bool) -> StepResult:
    if not enabled:
        return StepResult("preprocess", "skipped", "disabled")
    script = repo_root / "automation" / "preprocess_sources.py"
    if not script.exists():
        return StepResult("preprocess", "skipped", "automation/preprocess_sources.py missing")
    return run_command(
        "preprocess",
        [sys.executable, str(script), "--repo-root", str(repo_root)],
        repo_root,
    )


def run_page_build(repo_root: Path, enabled: bool, as_of_date: date | None) -> StepResult:
    if not enabled:
        return StepResult("page_build", "skipped", "disabled")
    script = repo_root / "page" / "scripts" / "build_page_data.py"
    cmd = [sys.executable, str(script)]
    if as_of_date:
        cmd.extend(["--as-of-date", as_of_date.isoformat()])
    return run_command("page_build", cmd, repo_root)


def path_signature(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size": int(stat.st_size),
        "mtime": datetime.fromtimestamp(stat.st_mtime, KST).isoformat(timespec="seconds"),
    }


def run_ai_target_dataset(repo_root: Path, enabled: bool) -> StepResult:
    if not enabled:
        return StepResult("ai_target_dataset", "skipped", "disabled")

    script = repo_root / "ai-model" / "03_target_dataset_build" / "03_target_dataset_build.py"
    grid_path = repo_root / "ai-model" / "02_spatial_grid_build" / "outputs" / "grid.parquet"
    target_path = repo_root / "ai-model" / "03_target_dataset_build" / "outputs" / "grid_target.parquet"

    if not script.exists():
        return StepResult("ai_target_dataset", "skipped", "ai-model/03_target_dataset_build/03_target_dataset_build.py missing")
    if not grid_path.exists():
        status = "skipped" if target_path.exists() else "waiting"
        detail = "AI 02 grid.parquet is missing; using existing grid_target if available."
        return StepResult(
            "ai_target_dataset",
            status,
            detail,
            {"grid": path_signature(grid_path), "target_dataset": path_signature(target_path)},
        )

    result = run_command("ai_target_dataset", [sys.executable, str(script)], repo_root)
    result.data.update({"grid": path_signature(grid_path), "target_dataset": path_signature(target_path)})
    return result


def run_ai_full_grid_prediction(repo_root: Path, enabled: bool, start_date: date, end_date: date) -> StepResult:
    if not enabled:
        return StepResult("ai_full_grid_prediction", "skipped", "disabled")

    script = repo_root / "ai-model" / "05_full_grid_prediction_for_web" / "predict_full_grid_for_web.py"
    target_dataset = repo_root / "ai-model" / "03_target_dataset_build" / "outputs" / "grid_target.parquet"
    output_dir = repo_root / "ai-model" / "05_full_grid_prediction_for_web" / "outputs"
    gasoline_model = repo_root / "ai-model" / "04_prediction_model_training" / "outputs" / "gasoline" / "model" / "gasoline_grid_fair_price_delta_lstm.pt"
    diesel_model = repo_root / "ai-model" / "04_prediction_model_training" / "outputs" / "diesel" / "model" / "diesel_grid_fair_price_delta_lstm.pt"

    required = [script, target_dataset, gasoline_model, diesel_model]
    missing = [path for path in required if not path.exists()]
    if missing:
        return StepResult(
            "ai_full_grid_prediction",
            "waiting",
            "required AI prediction inputs are missing",
            {"missing": [str(path) for path in missing], "output_dir": str(output_dir)},
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(script),
        "--target-dataset",
        str(target_dataset),
        "--output-dir",
        str(output_dir),
        "--fuel",
        "all",
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
        "--device",
        os.environ.get("KFF_AI_DEVICE", "cpu"),
    ]
    batch_size = os.environ.get("KFF_AI_BATCH_SIZE")
    if batch_size:
        cmd.extend(["--batch-size", batch_size])
    threads = os.environ.get("KFF_AI_THREADS")
    if threads:
        cmd.extend(["--threads", threads])

    result = run_command("ai_full_grid_prediction", cmd, repo_root)
    result.data.update(
        {
            "target_dataset": path_signature(target_dataset),
            "web_region_today": path_signature(output_dir / "web_region_today.csv"),
            "web_price_history_region": path_signature(output_dir / "web_price_history_region.csv"),
        }
    )
    return result


def run_ai_daily_operational_prediction(repo_root: Path, enabled: bool, start_date: date, end_date: date) -> StepResult:
    if not enabled:
        return StepResult("ai_daily_operational_prediction", "skipped", "disabled")

    script = repo_root / "ai-model" / "06_web_operational_dataset_build" / "daily_operational_prediction.py"
    state_path = repo_root / "ai-model" / "06_web_operational_dataset_build" / "outputs" / "inference_state" / "recent_model_input.parquet"
    gasoline_model = repo_root / "ai-model" / "04_prediction_model_training" / "outputs" / "gasoline" / "model" / "gasoline_grid_fair_price_delta_lstm.pt"
    diesel_model = repo_root / "ai-model" / "04_prediction_model_training" / "outputs" / "diesel" / "model" / "diesel_grid_fair_price_delta_lstm.pt"
    station_points = repo_root / "data-analysis" / "00_data_collection" / "outputs" / "derived_data" / "station_points.csv"

    required = [script, state_path, gasoline_model, diesel_model, station_points]
    missing = [path for path in required if not path.exists()]
    if missing:
        return StepResult(
            "ai_daily_operational_prediction",
            "waiting",
            "required operational AI inputs are missing",
            {"missing": [str(path) for path in missing]},
        )

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--source-end-date",
        end_date.isoformat(),
        "--device",
        os.environ.get("KFF_AI_DEVICE", "cpu"),
        "--history-years",
        os.environ.get("KFF_WEB_HISTORY_YEARS", "10"),
        "--state-days",
        os.environ.get("KFF_INFERENCE_STATE_DAYS", "45"),
        "--min-feature-coverage-ratio",
        os.environ.get("KFF_MIN_FEATURE_COVERAGE_RATIO", "0.80"),
    ]
    batch_size = os.environ.get("KFF_AI_BATCH_SIZE")
    if batch_size:
        cmd.extend(["--batch-size", batch_size])
    fuel = os.environ.get("KFF_AI_FUEL")
    if fuel in {"gasoline", "diesel"}:
        cmd.extend(["--fuel", fuel])

    result = run_command("ai_daily_operational_prediction", cmd, repo_root)
    stage6_output = repo_root / "ai-model" / "06_web_operational_dataset_build" / "outputs"
    web_output = stage6_output / "web"
    result.data.update(
        {
            "recent_model_input": path_signature(state_path),
            "web_region_today": path_signature(web_output / "web_region_today.csv"),
            "web_price_history_region": path_signature(web_output / "web_price_history_region.csv"),
            "manifest": path_signature(stage6_output / "operational_dataset_manifest.json"),
        }
    )
    return result


def run_ai_operational_dataset(repo_root: Path, enabled: bool) -> StepResult:
    if not enabled:
        return StepResult("ai_operational_dataset", "skipped", "disabled")

    script = repo_root / "ai-model" / "06_web_operational_dataset_build" / "06_web_operational_dataset_build.py"
    stage5_output = repo_root / "ai-model" / "05_full_grid_prediction_for_web" / "outputs"
    stage6_output = repo_root / "ai-model" / "06_web_operational_dataset_build" / "outputs"
    stage5_history = stage5_output / "web_price_history_region.csv"
    stage5_today = stage5_output / "web_region_today.csv"
    stage6_history = stage6_output / "web" / "web_price_history_region.csv"
    stage6_today = stage6_output / "web" / "web_region_today.csv"

    if not script.exists():
        return StepResult("ai_operational_dataset", "skipped", "ai-model/06_web_operational_dataset_build/06_web_operational_dataset_build.py missing")

    if not (stage5_history.exists() and stage5_today.exists()):
        if stage6_history.exists() and stage6_today.exists():
            return StepResult(
                "ai_operational_dataset",
                "skipped",
                "stage 5 outputs are missing; using existing stage 06 operational data",
                {
                    "web_region_today": path_signature(stage6_today),
                    "web_price_history_region": path_signature(stage6_history),
                },
            )
        return StepResult(
            "ai_operational_dataset",
            "waiting",
            "stage 5 web outputs are missing",
            {
                "stage5_web_region_today": path_signature(stage5_today),
                "stage5_web_price_history_region": path_signature(stage5_history),
            },
        )

    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--history-years",
        os.environ.get("KFF_WEB_HISTORY_YEARS", "10"),
        "--state-days",
        os.environ.get("KFF_INFERENCE_STATE_DAYS", "35"),
    ]
    if os.environ.get("KFF_SKIP_INFERENCE_STATE", "").lower() in {"1", "true", "yes"}:
        cmd.append("--skip-inference-state")

    result = run_command("ai_operational_dataset", cmd, repo_root)
    result.data.update(
        {
            "web_region_today": path_signature(stage6_today),
            "web_price_history_region": path_signature(stage6_history),
            "manifest": path_signature(stage6_output / "operational_dataset_manifest.json"),
        }
    )
    return result


def run_ai_pipeline(repo_root: Path, enabled: bool, start_date: date, end_date: date) -> list[StepResult]:
    if not enabled:
        return [StepResult("ai_pipeline", "skipped", "disabled")]
    run_full_ai = os.environ.get("KFF_RUN_FULL_AI", "").lower() in {"1", "true", "yes"}
    if not run_full_ai:
        return [
            StepResult("ai_target_dataset", "skipped", "daily automation uses committed operational inference state"),
            StepResult("ai_full_grid_prediction", "skipped", "daily automation uses committed operational inference state"),
            run_ai_daily_operational_prediction(repo_root, True, start_date, end_date),
        ]
    results = [run_ai_target_dataset(repo_root, True)]
    full_result = run_ai_full_grid_prediction(repo_root, True, start_date, end_date)
    results.append(full_result)
    if full_result.status == "completed":
        results.append(run_ai_operational_dataset(repo_root, True))
    else:
        results.append(run_ai_daily_operational_prediction(repo_root, True, start_date, end_date))
    return results


def run_ai_placeholders(repo_root: Path) -> list[StepResult]:
    return run_ai_pipeline(repo_root, True, today_kst() - timedelta(days=1), today_kst() - timedelta(days=1))

def write_report(repo_root: Path, steps: list[StepResult], start_date: date, end_date: date) -> Path:
    report_dir = repo_root / "automation" / "logs"
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "daily_pipeline_report_v1",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "steps": [asdict(step) for step in steps],
    }
    latest = report_dir / "latest_pipeline_report.json"
    stamped = report_dir / f"pipeline_report_{end_date.isoformat()}.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    stamped.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return latest


def infer_start_date(repo_root: Path, fallback_end: date) -> date:
    latest_dates: list[date] = []
    for result in inspect_collection(repo_root):
        max_text = result.data.get("date_max")
        parsed = parse_date(max_text)
        if parsed:
            latest_dates.append(parsed)
    if not latest_dates:
        return fallback_end
    return min(latest_dates) + timedelta(days=1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--skip-collection", action="store_true")
    parser.add_argument("--run-preprocessing", action="store_true")
    parser.add_argument("--build-page", action="store_true")
    parser.add_argument("--run-ai", action="store_true")
    parser.add_argument("--include-ai-placeholders", action="store_true", help="Deprecated alias for --run-ai")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    end_date = parse_date(args.end_date) if args.end_date else today_kst() - timedelta(days=1)
    if end_date is None:
        raise ValueError(f"invalid --end-date: {args.end_date}")
    start_date = parse_date(args.start_date) if args.start_date else infer_start_date(repo_root, end_date)
    if start_date is None:
        raise ValueError(f"invalid --start-date: {args.start_date}")

    steps: list[StepResult] = []
    steps.extend(inspect_collection(repo_root))
    if args.skip_collection:
        steps.append(StepResult("collect", "skipped", "disabled"))
    else:
        steps.append(run_collection(repo_root, True, start_date, end_date))
    steps.extend(merge_incoming_files(repo_root))
    steps.append(run_preprocessing(repo_root, args.run_preprocessing))
    if args.run_ai or args.include_ai_placeholders:
        steps.extend(run_ai_pipeline(repo_root, True, start_date, end_date))
    steps.append(run_page_build(repo_root, args.build_page, end_date))
    report_path = write_report(repo_root, steps, start_date, end_date)

    print(f"[PIPELINE] report={report_path}")
    for step in steps:
        print(f"[{step.status}] {step.name} {step.detail}")
        if step.status == "failed":
            output_tail = step.data.get("output_tail")
            if output_tail:
                print(f"[{step.name} output_tail]")
                print(output_tail)

    failed = [step for step in steps if step.status == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
