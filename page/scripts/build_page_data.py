from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


KST = timezone(timedelta(hours=9))

FUEL_CONFIG = {
    "gasoline": {
        "label": "휘발유",
        "policy_csv": Path("data-analysis/05_policy_application/outputs/휘발유/일별_정책적용_데이터_휘발유.csv"),
        "preprocessed_actual_col": "보통휘발유_평균",
    },
    "diesel": {
        "label": "경유",
        "policy_csv": Path("data-analysis/05_policy_application/outputs/경유/일별_정책적용_데이터_경유.csv"),
        "preprocessed_actual_col": "자동차용경유_평균",
    },
}

PREPROCESSED_DAILY_PATH = Path("data-analysis/01_data_preprocessing/outputs/분석용일별통합데이터.csv")
AI_WEB_OUTPUT_DIR = Path("ai-model/05_full_grid_prediction_for_web/outputs")

TRAINING_COVERAGE_DATASETS = {
    "grid_panel_rows": {
        "label": "AI 학습 격자 패널 행 수",
        "unit": "행",
        "path": "ROOT_PATH/그리드/grid.parquet",
        "note": "AI 02 최종 grid.parquet를 시도·날짜별로 집계한 값입니다.",
    },
    "station_count": {
        "label": "주유소 입력 수",
        "unit": "개",
        "path": "data-analysis/00_data_collection/outputs/derived_data/station_points.csv",
        "note": "AI 01 주유소 좌표/프로필 산출물을 시도별로 집계한 값입니다.",
    },
    "facility_count": {
        "label": "시설 영향력 입력 수",
        "unit": "개",
        "path": "data-analysis/00_data_collection/outputs/derived_data/facility_points.csv",
        "note": "AI 01 시설 좌표 산출물을 시도별로 집계한 값입니다.",
    },
    "land_price_grid_count": {
        "label": "공시지가 격자 수",
        "unit": "격자",
        "path": "data-analysis/00_data_collection/outputs/derived_data/official_land_price_grid.csv",
        "note": "공시지가 500m 격자 산출물을 시도·날짜별로 집계한 값입니다.",
    },
}


def read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    columns = {str(col).strip(): col for col in df.columns}
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
    return None


def to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except Exception:
        return None

def weighted_average(values: pd.Series, weights: pd.Series) -> float | None:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce").fillna(0)
    mask = v.notna() & w.gt(0)
    if not mask.any():
        return to_float(v.mean())
    return float((v[mask] * w[mask]).sum() / w[mask].sum())


def judge_from_prices(actual: float | None, low: float | None, high: float | None, fair: float | None = None) -> str | None:
    if actual is None:
        return None
    if high is not None and actual > high:
        return "비쌈"
    if low is not None and actual < low:
        return "저렴"
    if low is not None and high is not None:
        return "적정"
    if fair is not None and actual > fair:
        return "비쌈"
    if fair is not None and actual < fair:
        return "저렴"
    return "적정"


def ai_web_path(repo_root: Path, filename: str) -> Path:
    return repo_root / AI_WEB_OUTPUT_DIR / filename


def read_ai_web_csv(repo_root: Path, filename: str, as_of_date: str | None = None) -> pd.DataFrame | None:
    path = ai_web_path(repo_root, filename)
    if not path.exists():
        return None
    df = read_csv(path)
    date_col = "date" if "date" in df.columns else "source_date" if "source_date" in df.columns else None
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).sort_values(date_col)
        if as_of_date:
            df = df[df[date_col] <= pd.Timestamp(as_of_date)]
    return df


def build_ai_national(repo_root: Path, as_of_date: str | None) -> dict[str, Any] | None:
    df = read_ai_web_csv(repo_root, "web_region_today.csv", as_of_date)
    if df is None or df.empty:
        return None

    date_col = "source_date" if "source_date" in df.columns else "date" if "date" in df.columns else None
    if date_col:
        latest_date = df[date_col].max()
        df = df[df[date_col] == latest_date]
        resolved_date = pd.Timestamp(latest_date).strftime("%Y-%m-%d")
    else:
        resolved_date = as_of_date

    fuels: dict[str, Any] = {}
    for fuel, cfg in FUEL_CONFIG.items():
        part = df[df["fuel"].astype(str).str.strip() == fuel].copy() if "fuel" in df.columns else pd.DataFrame()
        if part.empty:
            continue
        weights = part["station_count"] if "station_count" in part.columns else pd.Series([1] * len(part), index=part.index)
        actual = weighted_average(part.get("actual_price", pd.Series(dtype=float)), weights)
        fair = weighted_average(part.get("fair_price_policy", pd.Series(dtype=float)), weights)
        low = weighted_average(part.get("band_low_policy", pd.Series(dtype=float)), weights)
        high = weighted_average(part.get("band_high_policy", pd.Series(dtype=float)), weights)
        fuels[fuel] = {
            "label": cfg["label"],
            "actual_price": actual,
            "actual_delta_1d": None,
            "fair_price_policy": fair,
            "band_low_policy": low,
            "band_high_policy": high,
            "gap_policy": actual - fair if actual is not None and fair is not None else None,
            "judge_policy": judge_from_prices(actual, low, high, fair),
            "policy_effect": None,
            "source": str(AI_WEB_OUTPUT_DIR / "web_region_today.csv"),
        }

    if not fuels:
        return None

    freshness = "fresh"
    if resolved_date:
        age_days = (datetime.now(KST).date() - pd.Timestamp(resolved_date).date()).days
        freshness = "fresh" if age_days <= 1 else "stale"

    return {
        "schema_version": "national_today_v1",
        "as_of_date": resolved_date,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "freshness": freshness,
        "fuels": fuels,
        "policies": [],
        "errors": {},
        "source": "ai-model/05_full_grid_prediction_for_web/outputs/web_region_today.csv",
    }

def judge_from_row(row: pd.Series) -> str | None:
    inside_col = next((col for col in row.index if str(col).strip() == "정책적용_inside"), None)
    above_col = next((col for col in row.index if str(col).strip() == "정책적용_above"), None)
    below_col = next((col for col in row.index if str(col).strip() == "정책적용_below"), None)
    judge_col = next((col for col in row.index if str(col).strip() in ("정책적용_판정", "judge_policy")), None)

    if judge_col and pd.notna(row[judge_col]):
        return str(row[judge_col])
    if inside_col and bool(row.get(inside_col)):
        return "적정"
    if above_col and bool(row.get(above_col)):
        return "비쌈"
    if below_col and bool(row.get(below_col)):
        return "저렴"
    return None


def latest_row(df: pd.DataFrame, as_of_date: str | None) -> pd.Series:
    date_col = find_col(df, ["date", "날짜", "일자"])
    if date_col is None:
        raise ValueError(f"date column not found: {list(df.columns)}")

    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col)
    if as_of_date:
        work = work[work[date_col] <= pd.Timestamp(as_of_date)]
    if len(work) == 0:
        raise ValueError("no rows available for requested as_of_date")
    return work.iloc[-1]


def previous_row(df: pd.DataFrame, current_date: pd.Timestamp) -> pd.Series | None:
    date_col = find_col(df, ["date", "날짜", "일자"])
    if date_col is None:
        return None
    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col)
    work = work[work[date_col] < current_date]
    if len(work) == 0:
        return None
    return work.iloc[-1]


def load_preprocessed_daily(repo_root: Path, as_of_date: str | None) -> pd.DataFrame | None:
    path = repo_root / PREPROCESSED_DAILY_PATH
    if not path.exists():
        return None

    df = read_csv(path)
    date_col = find_col(df, ["date", "날짜", "일자"])
    if date_col is None:
        return None

    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col)
    if as_of_date:
        work = work[work[date_col] <= pd.Timestamp(as_of_date)]
    return work if len(work) else None


def add_preprocessed_national_history(
    repo_root: Path,
    as_of_date: str | None,
    by_key: dict[tuple[str, str, str], dict[str, Any]],
) -> None:
    work = load_preprocessed_daily(repo_root, as_of_date)
    if work is None:
        return

    date_col = find_col(work, ["date", "날짜", "일자"])
    if date_col is None:
        return

    for fuel, cfg in FUEL_CONFIG.items():
        actual_col = find_col(work, [cfg["preprocessed_actual_col"]])
        if actual_col is None:
            continue

        for _, row in work.iterrows():
            actual = to_float(row.get(actual_col))
            if actual is None:
                continue

            item = {
                "date": pd.Timestamp(row[date_col]).strftime("%Y-%m-%d"),
                "region": "전국",
                "fuel": fuel,
                "actual_price": actual,
                "fair_price_policy": None,
                "band_low_policy": None,
                "band_high_policy": None,
                "gap_policy": None,
                "source": str(PREPROCESSED_DAILY_PATH),
            }
            by_key[(item["date"], item["region"], item["fuel"])] = item


def extract_national_fuel(repo_root: Path, fuel: str, as_of_date: str | None) -> tuple[str, dict[str, Any]]:
    cfg = FUEL_CONFIG[fuel]
    path = repo_root / cfg["policy_csv"]
    if not path.exists():
        raise FileNotFoundError(path)

    df = read_csv(path)
    row = latest_row(df, as_of_date)
    date_col = find_col(df, ["date", "날짜", "일자"])
    current_date = pd.Timestamp(row[date_col])
    prev = previous_row(df, current_date)

    actual_col = find_col(df, ["국내유가_원L", "actual_price", "actual_gross_full"])
    fair_col = find_col(df, ["적정가격_정책적용_원L", "fair_price_policy"])
    low_col = find_col(df, ["적정범위_정책적용_하한_원L", "band_low_policy"])
    high_col = find_col(df, ["적정범위_정책적용_상한_원L", "band_high_policy"])
    effect_col = find_col(df, ["정책효과_원L", "policy_effect"])

    actual = to_float(row.get(actual_col)) if actual_col else None
    fair = to_float(row.get(fair_col)) if fair_col else None
    prev_actual = to_float(prev.get(actual_col)) if prev is not None and actual_col else None

    payload = {
        "label": cfg["label"],
        "actual_price": actual,
        "actual_delta_1d": actual - prev_actual if actual is not None and prev_actual is not None else None,
        "fair_price_policy": fair,
        "band_low_policy": to_float(row.get(low_col)) if low_col else None,
        "band_high_policy": to_float(row.get(high_col)) if high_col else None,
        "gap_policy": actual - fair if actual is not None and fair is not None else None,
        "judge_policy": judge_from_row(row),
        "policy_effect": to_float(row.get(effect_col)) if effect_col else None,
    }
    return current_date.strftime("%Y-%m-%d"), payload


def build_national(repo_root: Path, as_of_date: str | None) -> dict[str, Any]:
    ai_national = build_ai_national(repo_root, as_of_date)
    if ai_national is not None:
        return ai_national
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    fuels: dict[str, Any] = {}
    dates: list[str] = []
    errors: dict[str, str] = {}

    for fuel in FUEL_CONFIG:
        try:
            dt, payload = extract_national_fuel(repo_root, fuel, as_of_date)
            dates.append(dt)
            fuels[fuel] = payload
        except Exception as exc:
            errors[fuel] = str(exc)

    resolved_date = min(dates) if dates else as_of_date
    freshness = "fresh"
    if resolved_date:
        today_kst = datetime.now(KST).date()
        age_days = (today_kst - pd.Timestamp(resolved_date).date()).days
        freshness = "fresh" if age_days <= 1 else "stale"

    return {
        "schema_version": "national_today_v1",
        "as_of_date": resolved_date,
        "generated_at": generated_at,
        "freshness": freshness,
        "fuels": fuels,
        "policies": [],
        "errors": errors,
    }


def build_price_history(repo_root: Path, as_of_date: str | None) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    cutoff = pd.Timestamp(as_of_date) if as_of_date else None

    add_preprocessed_national_history(repo_root, as_of_date, by_key)

    for fuel, cfg in FUEL_CONFIG.items():
        path = repo_root / cfg["policy_csv"]
        if not path.exists():
            continue

        df = read_csv(path)
        date_col = find_col(df, ["date", "날짜", "일자"])
        actual_col = find_col(df, ["국내유가_원L", "actual_price", "actual_gross_full"])
        fair_col = find_col(df, ["적정가격_정책적용_원L", "fair_price_policy"])
        low_col = find_col(df, ["적정범위_정책적용_하한_원L", "band_low_policy"])
        high_col = find_col(df, ["적정범위_정책적용_상한_원L", "band_high_policy"])

        if date_col is None:
            continue

        work = df.copy()
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work = work.dropna(subset=[date_col]).sort_values(date_col)
        if cutoff is not None:
            work = work[work[date_col] <= cutoff]

        for _, row in work.iterrows():
            actual = to_float(row.get(actual_col)) if actual_col else None
            fair = to_float(row.get(fair_col)) if fair_col else None
            item = {
                "date": pd.Timestamp(row[date_col]).strftime("%Y-%m-%d"),
                "region": "전국",
                "fuel": fuel,
                "actual_price": actual,
                "fair_price_policy": fair,
                "band_low_policy": to_float(row.get(low_col)) if low_col else None,
                "band_high_policy": to_float(row.get(high_col)) if high_col else None,
                "gap_policy": actual - fair if actual is not None and fair is not None else None,
                "source": str(cfg["policy_csv"]),
            }
            by_key[(item["date"], item["region"], item["fuel"])] = item

    manual_path = repo_root / "page/manual_inputs/price_history.csv"
    if manual_path.exists():
        df = read_csv(manual_path)
        for _, row in df.iterrows():
            date = pd.to_datetime(row.get("date") or row.get("as_of_date"), errors="coerce")
            if pd.isna(date):
                continue
            if cutoff is not None and date > cutoff:
                continue
            fuel = str(row.get("fuel", "")).strip()
            if fuel not in FUEL_CONFIG:
                continue
            region = str(row.get("region", "전국")).strip() or "전국"
            actual = to_float(row.get("actual_price"))
            fair = to_float(row.get("fair_price_policy"))
            gap = to_float(row.get("gap_policy")) if pd.notna(row.get("gap_policy")) else None
            if gap is None and actual is not None and fair is not None:
                gap = actual - fair
            item = {
                "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                "region": region,
                "fuel": fuel,
                "actual_price": actual,
                "fair_price_policy": fair,
                "band_low_policy": to_float(row.get("band_low_policy")),
                "band_high_policy": to_float(row.get("band_high_policy")),
                "gap_policy": gap,
                "source": "page/manual_inputs/price_history.csv",
            }
            by_key[(item["date"], item["region"], item["fuel"])] = item

    ai_history = read_ai_web_csv(repo_root, "web_price_history_region.csv", as_of_date)
    if ai_history is not None and not ai_history.empty:
        for _, row in ai_history.iterrows():
            date = pd.to_datetime(row.get("date"), errors="coerce")
            if pd.isna(date):
                continue
            fuel = str(row.get("fuel", "")).strip()
            region = str(row.get("region", "")).strip()
            if not region or fuel not in FUEL_CONFIG:
                continue
            actual = to_float(row.get("actual_price"))
            fair = to_float(row.get("fair_price_policy"))
            gap = to_float(row.get("gap_policy"))
            if gap is None and actual is not None and fair is not None:
                gap = actual - fair
            item = {
                "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                "region": region,
                "fuel": fuel,
                "actual_price": actual,
                "fair_price_policy": fair,
                "band_low_policy": to_float(row.get("band_low_policy")),
                "band_high_policy": to_float(row.get("band_high_policy")),
                "gap_policy": gap,
                "source": "ai-model/05_full_grid_prediction_for_web/outputs/web_price_history_region.csv",
            }
            by_key[(item["date"], item["region"], item["fuel"])] = item

    return sorted(by_key.values(), key=lambda item: (item["date"], item["region"], item["fuel"]))


def merge_history(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in existing + incoming:
        date = str(row.get("date") or row.get("as_of_date") or "").strip()
        region = str(row.get("region") or "전국").strip()
        fuel = str(row.get("fuel") or "").strip()
        if not date or not region or fuel not in FUEL_CONFIG:
            continue
        by_key[(date, region, fuel)] = {**row, "date": date, "region": region, "fuel": fuel}
    return sorted(by_key.values(), key=lambda item: (item["date"], item["region"], item["fuel"]))


def json_row_count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return len(data)
    return None


def csv_row_count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return len(read_csv(path))
    except Exception:
        return None


def history_extent(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    dates = sorted(str(row.get("date", "")) for row in rows if row.get("date"))
    if not dates:
        return None, None
    return dates[0], dates[-1]


def build_training_data_coverage(repo_root: Path) -> dict[str, Any]:
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    path = repo_root / "page/manual_inputs/training_data_coverage.csv"
    rows: list[dict[str, Any]] = []

    if path.exists():
        df = read_csv(path)
        for _, row in df.iterrows():
            dataset = str(row.get("dataset", "")).strip()
            region = str(row.get("region", "")).strip()
            value = to_float(row.get("value"))
            if not dataset or not region or value is None:
                continue
            date_raw = row.get("date")
            date = ""
            if date_raw is not None and not pd.isna(date_raw) and str(date_raw).strip():
                parsed_date = pd.to_datetime(date_raw, errors="coerce")
                if not pd.isna(parsed_date):
                    date = pd.Timestamp(parsed_date).strftime("%Y-%m-%d")
            rows.append({
                "dataset": dataset,
                "date": date,
                "region": region,
                "value": value,
                "unit": row.get("unit") if pd.notna(row.get("unit")) else TRAINING_COVERAGE_DATASETS.get(dataset, {}).get("unit"),
                "label": row.get("label") if pd.notna(row.get("label")) else None,
            })

    rows_by_dataset: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_dataset.setdefault(row["dataset"], []).append(row)

    datasets: list[dict[str, Any]] = []
    for dataset, cfg in TRAINING_COVERAGE_DATASETS.items():
        dataset_rows = rows_by_dataset.get(dataset, [])
        dates = sorted({row["date"] for row in dataset_rows if row.get("date")})
        datasets.append({
            "id": dataset,
            "label": cfg["label"],
            "unit": cfg["unit"],
            "status": "connected" if dataset_rows else "waiting",
            "rows": len(dataset_rows),
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "path": cfg["path"],
            "note": cfg["note"],
        })

    for dataset in sorted(set(rows_by_dataset) - set(TRAINING_COVERAGE_DATASETS)):
        dataset_rows = rows_by_dataset[dataset]
        dates = sorted({row["date"] for row in dataset_rows if row.get("date")})
        datasets.append({
            "id": dataset,
            "label": dataset,
            "unit": dataset_rows[0].get("unit"),
            "status": "connected",
            "rows": len(dataset_rows),
            "date_min": dates[0] if dates else None,
            "date_max": dates[-1] if dates else None,
            "path": "page/manual_inputs/training_data_coverage.csv",
            "note": "수동 입력된 AI 학습 데이터 커버리지입니다.",
        })

    return {
        "schema_version": "training_data_coverage_v1",
        "generated_at": generated_at,
        "source": "page/manual_inputs/training_data_coverage.csv" if path.exists() else None,
        "datasets": datasets,
        "rows": sorted(rows, key=lambda item: (item["dataset"], item.get("date") or "", item["region"])),
    }


def build_external_data_status(repo_root: Path, output_dir: Path, national: dict[str, Any], region: list[dict[str, Any]], stations: list[dict[str, Any]], history: list[dict[str, Any]]) -> dict[str, Any]:
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    history_min, history_max = history_extent(history)
    national_date = national.get("as_of_date")
    station_input = repo_root / "page/manual_inputs/station_search_index.csv"
    region_input = repo_root / "page/manual_inputs/region_today.csv"
    manual_history_input = repo_root / "page/manual_inputs/price_history.csv"
    ai_output_dir = repo_root / AI_WEB_OUTPUT_DIR
    ai_today_input = ai_output_dir / "web_region_today.csv"
    ai_history_input = ai_output_dir / "web_price_history_region.csv"
    ai_exists = ai_today_input.exists() or ai_history_input.exists()

    return {
        "schema_version": "external_data_status_v1",
        "generated_at": generated_at,
        "datasets": [
            {
                "id": "national_today",
                "label": "전국 가격 요약",
                "status": "connected" if national.get("fuels") else "waiting",
                "rows": len(national.get("fuels", {})),
                "date_min": national_date,
                "date_max": national_date,
                "path": "data-analysis/05_policy_application/outputs/{fuel}/일별_정책적용_데이터_{fuel}.csv",
                "note": "전국 실제가격과 정책 적용 적정가격을 만드는 핵심 데이터입니다.",
            },
            {
                "id": "price_history",
                "label": "기간별 가격 추이",
                "status": "connected" if history else "waiting",
                "rows": len(history),
                "date_min": history_min,
                "date_max": history_max,
                "path": "page/public/data/latest/price_history.json",
                "note": "자동 갱신 시 기존 파일과 병합해 날짜별 이력을 누적합니다.",
            },
            {
                "id": "region_today",
                "label": "지역별 요약",
                "status": "connected" if (ai_today_input.exists() or region_input.exists()) and region else "waiting",
                "rows": len(region),
                "date_min": national_date,
                "date_max": national_date,
                "path": "ai-model/05_full_grid_prediction_for_web/outputs/web_region_today.csv" if ai_today_input.exists() else "page/manual_inputs/region_today.csv",
                "note": "AI 모델 완료 전까지 수동 입력합니다.",
            },
            {
                "id": "station_search_index",
                "label": "주유소 검색/주변",
                "status": "connected" if station_input.exists() and stations else "waiting",
                "rows": len(stations),
                "date_min": national_date,
                "date_max": national_date,
                "path": "page/manual_inputs/station_search_index.csv",
                "note": "주유소명, 주소, 좌표, 현재가를 담는 공개 검색 인덱스입니다.",
            },
            {
                "id": "manual_price_history",
                "label": "수동 가격 이력",
                "status": "connected" if manual_history_input.exists() else "waiting",
                "rows": csv_row_count(manual_history_input) or 0,
                "date_min": None,
                "date_max": None,
                "path": "page/manual_inputs/price_history.csv",
                "note": "비어 있는 기간을 수동/강제 수집 결과로 보강할 때 사용합니다.",
            },
            {
                "id": "ai_model_outputs",
                "label": "AI 적정가격 모델",
                "status": "connected" if ai_exists else "waiting",
                "rows": (csv_row_count(ai_today_input) or 0) + (csv_row_count(ai_history_input) or 0),
                "date_min": None,
                "date_max": None,
                "path": "ai-model/05_full_grid_prediction_for_web/outputs/",
                "note": "학습 완료 후 지역/주유소 적정가격과 예측 이력을 생성합니다.",
            },
        ],
    }


def build_region(repo_root: Path) -> list[dict[str, Any]]:
    ai_path = ai_web_path(repo_root, "web_region_today.csv")
    manual_path = repo_root / "page/manual_inputs/region_today.csv"
    path = ai_path if ai_path.exists() else manual_path
    if not path.exists():
        return []

    df = read_csv(path)
    rows: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        region = str(row.get("region", "")).strip()
        fuel = str(row.get("fuel", "")).strip()
        if not region or fuel not in FUEL_CONFIG:
            continue
        actual = to_float(row.get("actual_price"))
        fair = to_float(row.get("fair_price_policy"))
        low = to_float(row.get("band_low_policy"))
        high = to_float(row.get("band_high_policy"))
        source_date_value = row.get("source_date") if pd.notna(row.get("source_date")) else row.get("date") if pd.notna(row.get("date")) else None
        source_date = None if source_date_value is None else pd.Timestamp(source_date_value).strftime("%Y-%m-%d")
        rows.setdefault(region, {"region": region})
        rows[region][fuel] = {
            "actual_price": actual,
            "fair_price_policy": fair,
            "band_low_policy": low,
            "band_high_policy": high,
            "gap_policy": to_float(row.get("gap_policy")) if pd.notna(row.get("gap_policy")) else (actual - fair if actual is not None and fair is not None else None),
            "judge_policy": row.get("judge_policy") if pd.notna(row.get("judge_policy")) else judge_from_prices(actual, low, high, fair),
            "source_date": source_date,
            "station_count": to_float(row.get("station_count")),
            "source": str(path.relative_to(repo_root)),
        }
    return list(rows.values())

def build_station_index(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / "page/manual_inputs/station_search_index.csv"
    if not path.exists():
        return []

    df = read_csv(path)
    out = []
    for _, row in df.iterrows():
        out.append({
            "station_id": row.get("station_id"),
            "name": row.get("name"),
            "brand": row.get("brand"),
            "region": row.get("region"),
            "address": row.get("address"),
            "lon": to_float(row.get("lon")),
            "lat": to_float(row.get("lat")),
            "gasoline_price": to_float(row.get("gasoline_price")),
            "diesel_price": to_float(row.get("diesel_price")),
            "judge_policy": row.get("judge_policy") if pd.notna(row.get("judge_policy")) else None,
        })
    return out


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--as-of-date", default=None)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else repo_root / "page/public/data/latest"

    national = build_national(repo_root, args.as_of_date)
    region = build_region(repo_root)
    stations = build_station_index(repo_root)
    history = build_price_history(repo_root, args.as_of_date)
    existing_history_path = output_dir / "price_history.json"
    if existing_history_path.exists():
        try:
            existing_history = json.loads(existing_history_path.read_text(encoding="utf-8"))
            if isinstance(existing_history, list):
                history = merge_history(existing_history, history)
        except Exception:
            pass
    training_coverage = build_training_data_coverage(repo_root)
    external_status = build_external_data_status(repo_root, output_dir, national, region, stations, history)

    manifest = {
        "schema_version": "page_data_v1",
        "as_of_date": national.get("as_of_date"),
        "generated_at": national.get("generated_at"),
        "freshness": national.get("freshness"),
        "files": [
            "national_today.json",
            "region_today.json",
            "station_search_index.json",
            "price_history.json",
            "training_data_coverage.json",
            "external_data_status.json",
        ],
        "assets": [
            "korea-provinces.geojson",
        ],
        "source": {
            "national": "data-analysis/05_policy_application/outputs + data-analysis/01_data_preprocessing/outputs",
            "region": "ai-model/05_full_grid_prediction_for_web/outputs/web_region_today.csv" if (repo_root / AI_WEB_OUTPUT_DIR / "web_region_today.csv").exists() else "page/manual_inputs/region_today.csv" if region else None,
            "station": "page/manual_inputs/station_search_index.csv" if stations else None,
        },
    }

    write_json(output_dir / "national_today.json", national)
    write_json(output_dir / "region_today.json", region)
    write_json(output_dir / "station_search_index.json", stations)
    write_json(output_dir / "price_history.json", history)
    write_json(output_dir / "training_data_coverage.json", training_coverage)
    write_json(output_dir / "external_data_status.json", external_status)
    write_json(output_dir / "site_manifest.json", manifest)

    print(f"[SAVE] {output_dir}")
    print(f"[INFO] as_of_date={manifest['as_of_date']} freshness={manifest['freshness']}")
    print(f"[INFO] regions={len(region):,} stations={len(stations):,}")
    print(f"[INFO] history={len(history):,}")


if __name__ == "__main__":
    main()
