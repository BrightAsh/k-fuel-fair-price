from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


KST = timezone(timedelta(hours=9))
NATIONAL_REGION = "\uc804\uad6d"
UNCLASSIFIED_REGION = "\ubbf8\ubd84\ub958"

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
AI_WEB_OUTPUT_DIRS = [
    Path("ai-model/06_web_operational_dataset_build/outputs/web"),
    Path("ai-model/05_full_grid_prediction_for_web/outputs"),
]
DISTRICT_ASSET_PATH = Path("page/public/assets/korea-districts.geojson")
DISTRICT_REGION_BY_PREFIX = {
    "11": "\uc11c\uc6b8",
    "21": "\ubd80\uc0b0",
    "22": "\ub300\uad6c",
    "23": "\uc778\ucc9c",
    "24": "\uad11\uc8fc",
    "25": "\ub300\uc804",
    "26": "\uc6b8\uc0b0",
    "29": "\uc138\uc885",
    "31": "\uacbd\uae30",
    "32": "\uac15\uc6d0",
    "33": "\ucda9\ubd81",
    "34": "\ucda9\ub0a8",
    "35": "\uc804\ubd81",
    "36": "\uc804\ub0a8",
    "37": "\uacbd\ubd81",
    "38": "\uacbd\ub0a8",
    "39": "\uc81c\uc8fc",
}

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


def to_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def clean_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): clean_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json_value(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return clean_json_value(value.item())
        except Exception:
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def weighted_average(values: pd.Series, weights: pd.Series) -> float | None:
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce").fillna(0)
    mask = v.notna() & w.gt(0)
    if not mask.any():
        return to_float(v.mean())
    return float((v[mask] * w[mask]).sum() / w[mask].sum())


def aggregation_weights(part: pd.DataFrame) -> tuple[pd.Series, float | None]:
    if "station_count" in part.columns:
        raw = pd.to_numeric(part["station_count"], errors="coerce").fillna(0)
        if raw.gt(0).any():
            return raw, float(raw.sum())
    return pd.Series(1.0, index=part.index), None


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
    for rel_dir in AI_WEB_OUTPUT_DIRS:
        path = repo_root / rel_dir / filename
        if path.exists():
            return path
    return repo_root / AI_WEB_OUTPUT_DIRS[0] / filename


def ai_web_source(repo_root: Path, filename: str) -> str:
    path = ai_web_path(repo_root, filename)
    try:
        return str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


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


def build_policy_items(repo_root: Path, as_of_date: str | None) -> list[dict[str, Any]]:
    path = repo_root / "page/manual_inputs/policies.csv"
    if not path.exists():
        return []

    df = read_csv(path)
    as_of_ts = pd.Timestamp(as_of_date) if as_of_date else None
    policies: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        start = to_text(row.get("start_date"))
        end = to_text(row.get("end_date"))
        if as_of_ts is not None:
            if start and pd.Timestamp(start) > as_of_ts:
                continue
            if end and pd.Timestamp(end) < as_of_ts:
                continue

        item = {
            "title": to_text(row.get("title")),
            "status": to_text(row.get("status")),
            "period": to_text(row.get("period")),
            "note": to_text(row.get("note")),
            "gasoline_effect": to_float(row.get("gasoline_effect")),
            "diesel_effect": to_float(row.get("diesel_effect")),
            "gasoline_effect_label": to_text(row.get("gasoline_effect_label")),
            "diesel_effect_label": to_text(row.get("diesel_effect_label")),
            "effect_label": to_text(row.get("effect_label")),
            "source_url": to_text(row.get("source_url")),
            "source": "page/manual_inputs/policies.csv",
        }
        if item["title"]:
            policies.append(item)

    return policies


def build_ai_national(repo_root: Path, as_of_date: str | None) -> dict[str, Any] | None:
    df = read_ai_web_csv(repo_root, "web_region_today.csv", as_of_date)
    if df is None or df.empty:
        return None
    source = ai_web_source(repo_root, "web_region_today.csv")

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
            "source": source,
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
        "policies": build_policy_items(repo_root, resolved_date),
        "errors": {},
        "source": source,
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
                "region": NATIONAL_REGION,
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
        "policies": build_policy_items(repo_root, resolved_date),
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
                "region": NATIONAL_REGION,
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
    ai_history_available = ai_web_path(repo_root, "web_price_history_region.csv").exists()
    if manual_path.exists() and not ai_history_available:
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
            region = str(row.get("region", NATIONAL_REGION)).strip() or NATIONAL_REGION
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
        ai_history_source = ai_web_source(repo_root, "web_price_history_region.csv")
        work = ai_history.copy()
        work["date"] = pd.to_datetime(work.get("date"), errors="coerce")
        work["fuel"] = work.get("fuel", "").astype(str).str.strip()
        work["region"] = work.get("region", "").astype(str).str.strip()
        work = work.dropna(subset=["date"])
        work = work[work["fuel"].isin(FUEL_CONFIG) & work["region"].ne("")]
        for col in ["actual_price", "fair_price_policy", "band_low_policy", "band_high_policy", "gap_policy", "station_count"]:
            if col not in work.columns:
                work[col] = pd.NA
            work[col] = pd.to_numeric(work[col], errors="coerce")
        work["gap_policy"] = work["gap_policy"].where(
            work["gap_policy"].notna(),
            work["actual_price"] - work["fair_price_policy"],
        )
        work["date"] = work["date"].dt.strftime("%Y-%m-%d")
        work["source"] = ai_history_source
        regional_work = work[work["region"].ne(NATIONAL_REGION)].copy()
        keep = [
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
        for item in regional_work[keep].where(pd.notna(regional_work[keep]), None).to_dict("records"):
            by_key[(item["date"], item["region"], item["fuel"])] = item

        national_work = regional_work[regional_work["region"].ne(UNCLASSIFIED_REGION)].copy()
        for (date, fuel), part in national_work.groupby(["date", "fuel"], sort=True):
            weights, _ = aggregation_weights(part)
            actual = weighted_average(part["actual_price"], weights)
            fair = weighted_average(part["fair_price_policy"], weights)
            low = weighted_average(part["band_low_policy"], weights)
            high = weighted_average(part["band_high_policy"], weights)
            item = {
                "date": date,
                "region": NATIONAL_REGION,
                "fuel": fuel,
                "actual_price": actual,
                "fair_price_policy": fair,
                "band_low_policy": low,
                "band_high_policy": high,
                "gap_policy": actual - fair if actual is not None and fair is not None else None,
                "source": f"{ai_history_source}#regional_average",
            }
            by_key[(item["date"], item["region"], item["fuel"])] = item

    return sorted(by_key.values(), key=lambda item: (item["date"], item["region"], item["fuel"]))


def merge_history(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in existing + incoming:
        date = str(row.get("date") or row.get("as_of_date") or "").strip()
        region = str(row.get("region") or NATIONAL_REGION).strip()
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


def trim_history(rows: list[dict[str, Any]], as_of_date: str | None, history_years: int) -> list[dict[str, Any]]:
    if history_years <= 0 or not rows:
        return rows

    dates = [pd.to_datetime(row.get("date"), errors="coerce") for row in rows]
    valid_dates = [date for date in dates if not pd.isna(date)]
    if not valid_dates:
        return rows

    end = pd.Timestamp(as_of_date) if as_of_date else max(valid_dates)
    start = end - pd.DateOffset(years=history_years)
    out = []
    for row, parsed in zip(rows, dates):
        if pd.isna(parsed):
            continue
        if start <= parsed <= end:
            out.append(row)
    return sorted(out, key=lambda item: (item["date"], item["region"], item["fuel"]))


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


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    if len(ring) < 3:
        return False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        intersects = (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_polygon(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon or not point_in_ring(lon, lat, polygon[0]):
        return False
    return not any(point_in_ring(lon, lat, hole) for hole in polygon[1:])


def point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    if geometry.get("type") == "Polygon":
        return point_in_polygon(lon, lat, geometry.get("coordinates", []))
    if geometry.get("type") == "MultiPolygon":
        return any(point_in_polygon(lon, lat, polygon) for polygon in geometry.get("coordinates", []))
    return False


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    coords: list[list[float]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list) and len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            coords.append(value)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(geometry.get("coordinates", []))
    if not coords:
        return (0.0, 0.0, 0.0, 0.0)
    lons = [float(point[0]) for point in coords]
    lats = [float(point[1]) for point in coords]
    return (min(lons), min(lats), max(lons), max(lats))


def load_district_features(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / DISTRICT_ASSET_PATH
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    features: list[dict[str, Any]] = []
    for feature in data.get("features", []):
        props = feature.setdefault("properties", {})
        code = str(props.get("code") or "")
        region = props.get("region") or DISTRICT_REGION_BY_PREFIX.get(code[:2])
        name = to_text(props.get("name"))
        if not code or not region or not name:
            continue
        feature["_bbox"] = geometry_bbox(feature.get("geometry", {}))
        props["region"] = region
        props["name"] = name
        features.append(feature)
    return features


def assign_district(lon: float | None, lat: float | None, region: str | None, features_by_region: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    if lon is None or lat is None or not region:
        return None
    for feature in features_by_region.get(region, []):
        min_lon, min_lat, max_lon, max_lat = feature.get("_bbox", (0.0, 0.0, 0.0, 0.0))
        if lon < min_lon or lon > max_lon or lat < min_lat or lat > max_lat:
            continue
        if point_in_geometry(lon, lat, feature.get("geometry", {})):
            return feature.get("properties", {})
    return None


def build_district_detail(repo_root: Path, as_of_date: str | None) -> dict[str, Any]:
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    features = load_district_features(repo_root)
    features_by_region: dict[str, list[dict[str, Any]]] = {}
    for feature in features:
        features_by_region.setdefault(str(feature["properties"]["region"]), []).append(feature)

    latest_grid = read_ai_web_csv(repo_root, "web_latest_grid_predictions.csv", as_of_date)
    source = ai_web_source(repo_root, "web_latest_grid_predictions.csv")
    if latest_grid is None or latest_grid.empty or not features:
        return {
            "schema_version": "district_detail_v1",
            "generated_at": generated_at,
            "as_of_date": as_of_date,
            "source": source,
            "districts": [],
            "grids": [],
        }

    work = latest_grid.copy()
    date_col = "source_date" if "source_date" in work.columns else "date" if "date" in work.columns else None
    if date_col:
        latest_date = work[date_col].max()
        work = work[work[date_col] == latest_date]
        resolved_date = pd.Timestamp(latest_date).strftime("%Y-%m-%d")
    else:
        resolved_date = as_of_date

    district_codes: list[str | None] = []
    district_names: list[str | None] = []
    for _, row in work.iterrows():
        district = assign_district(
            to_float(row.get("center_lon")),
            to_float(row.get("center_lat")),
            to_text(row.get("region")),
            features_by_region,
        )
        district_codes.append(to_text(district.get("code")) if district else None)
        district_names.append(to_text(district.get("name")) if district else None)

    work["district_code"] = district_codes
    work["district_name"] = district_names
    mapped = work.dropna(subset=["district_code", "district_name"]).copy()

    grids: list[dict[str, Any]] = []
    for _, row in mapped.iterrows():
        actual = to_float(row.get("actual_price"))
        fair = to_float(row.get("fair_price_policy"))
        low = to_float(row.get("band_low_policy"))
        high = to_float(row.get("band_high_policy"))
        grids.append({
            "source_date": resolved_date,
            "feature_date": pd.Timestamp(row.get("feature_date")).strftime("%Y-%m-%d") if pd.notna(row.get("feature_date")) else None,
            "fuel": to_text(row.get("fuel")),
            "grid_id": to_text(row.get("grid_id")),
            "region": to_text(row.get("region")),
            "district_code": to_text(row.get("district_code")),
            "district_name": to_text(row.get("district_name")),
            "center_lon": to_float(row.get("center_lon")),
            "center_lat": to_float(row.get("center_lat")),
            "station_count": to_float(row.get("station_count")),
            "actual_price": actual,
            "fair_price_policy": fair,
            "band_low_policy": low,
            "band_high_policy": high,
            "gap_policy": to_float(row.get("gap_policy")) if pd.notna(row.get("gap_policy")) else (actual - fair if actual is not None and fair is not None else None),
            "judge_policy": to_text(row.get("judge_policy")) or judge_from_prices(actual, low, high, fair),
            "source": source,
        })

    district_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for feature in features:
        props = feature["properties"]
        key = (str(props["region"]), str(props["code"]))
        district_rows[key] = {
            "region": props["region"],
            "district_code": props["code"],
            "district_name": props["name"],
        }

    if not mapped.empty:
        for (region, code, name, fuel), part in mapped.groupby(["region", "district_code", "district_name", "fuel"], sort=True):
            weights = pd.to_numeric(part.get("station_count", pd.Series(dtype=float)), errors="coerce").fillna(0)
            if not weights.gt(0).any():
                weights = pd.Series(1.0, index=part.index)
            actual = weighted_average(part.get("actual_price", pd.Series(dtype=float)), weights)
            fair = weighted_average(part.get("fair_price_policy", pd.Series(dtype=float)), weights)
            low = weighted_average(part.get("band_low_policy", pd.Series(dtype=float)), weights)
            high = weighted_average(part.get("band_high_policy", pd.Series(dtype=float)), weights)
            key = (str(region), str(code))
            district_rows.setdefault(key, {"region": region, "district_code": code, "district_name": name})
            district_rows[key][fuel] = {
                "actual_price": actual,
                "fair_price_policy": fair,
                "band_low_policy": low,
                "band_high_policy": high,
                "gap_policy": actual - fair if actual is not None and fair is not None else None,
                "judge_policy": judge_from_prices(actual, low, high, fair),
                "source_date": resolved_date,
                "station_count": to_float(weights.sum()),
                "grid_count": int(len(part)),
                "source": source,
            }

    return {
        "schema_version": "district_detail_v1",
        "generated_at": generated_at,
        "as_of_date": resolved_date,
        "source": source,
        "districts": sorted(district_rows.values(), key=lambda item: (str(item.get("region")), str(item.get("district_name")))),
        "grids": sorted(grids, key=lambda item: (str(item.get("region")), str(item.get("district_name")), str(item.get("fuel")), str(item.get("grid_id")))),
    }


def build_external_data_status(
    repo_root: Path,
    output_dir: Path,
    national: dict[str, Any],
    region: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    history: list[dict[str, Any]],
    district_detail: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    history_min, history_max = history_extent(history)
    national_date = national.get("as_of_date")
    station_input = repo_root / "page/manual_inputs/station_search_index.csv"
    region_input = repo_root / "page/manual_inputs/region_today.csv"
    manual_history_input = repo_root / "page/manual_inputs/price_history.csv"
    ai_today_input = ai_web_path(repo_root, "web_region_today.csv")
    ai_history_input = ai_web_path(repo_root, "web_price_history_region.csv")
    ai_exists = ai_today_input.exists() or ai_history_input.exists()
    ai_today_source = ai_web_source(repo_root, "web_region_today.csv")
    ai_history_source = ai_web_source(repo_root, "web_price_history_region.csv")

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
                "path": ai_today_source if ai_today_input.exists() else "page/manual_inputs/region_today.csv",
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
                "id": "district_detail",
                "label": "시군구 상세 지도",
                "status": "connected" if district_detail.get("districts") else "waiting",
                "rows": len(district_detail.get("districts", [])),
                "date_min": district_detail.get("as_of_date"),
                "date_max": district_detail.get("as_of_date"),
                "path": "page/public/data/latest/district_detail.json",
                "note": "시도 클릭 후 시군구 경계, 가격 요약, 격자 상세를 표시하는 데이터입니다.",
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
                "path": ai_history_source if ai_history_input.exists() else ai_today_source,
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
            "source": str(path.relative_to(repo_root)).replace("\\", "/"),
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
            "station_id": to_text(row.get("station_id")),
            "name": to_text(row.get("name")),
            "brand": to_text(row.get("brand")),
            "region": to_text(row.get("region")),
            "address": to_text(row.get("address")),
            "lon": to_float(row.get("lon")),
            "lat": to_float(row.get("lat")),
            "gasoline_price": to_float(row.get("gasoline_price")),
            "diesel_price": to_float(row.get("diesel_price")),
            "judge_policy": to_text(row.get("judge_policy")),
        })
    return out


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_obj = clean_json_value(obj)
    path.write_text(
        json.dumps(clean_obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--as-of-date", default=None)
    parser.add_argument("--history-years", type=int, default=10)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else repo_root / "page/public/data/latest"

    national = build_national(repo_root, args.as_of_date)
    resolved_as_of_date = args.as_of_date or national.get("as_of_date")
    region = build_region(repo_root)
    stations = build_station_index(repo_root)
    district_detail = build_district_detail(repo_root, resolved_as_of_date)
    history = build_price_history(repo_root, resolved_as_of_date)
    existing_history_path = output_dir / "price_history.json"
    ai_history_path = ai_web_path(repo_root, "web_price_history_region.csv")
    if existing_history_path.exists() and not ai_history_path.exists():
        try:
            existing_history = json.loads(existing_history_path.read_text(encoding="utf-8"))
            if isinstance(existing_history, list):
                history = merge_history(existing_history, history)
        except Exception:
            pass
    history = trim_history(history, resolved_as_of_date, args.history_years)
    training_coverage = build_training_data_coverage(repo_root)
    external_status = build_external_data_status(repo_root, output_dir, national, region, stations, history, district_detail)
    ai_region_source = ai_web_source(repo_root, "web_region_today.csv")
    ai_region_path = ai_web_path(repo_root, "web_region_today.csv")

    manifest = {
        "schema_version": "page_data_v1",
        "as_of_date": national.get("as_of_date"),
        "generated_at": national.get("generated_at"),
        "freshness": national.get("freshness"),
        "files": [
            "national_today.json",
            "region_today.json",
            "district_detail.json",
            "station_search_index.json",
            "price_history.json",
            "training_data_coverage.json",
            "external_data_status.json",
        ],
        "assets": [
            "korea-provinces.geojson",
            "korea-districts.geojson",
        ],
        "source": {
            "national": "data-analysis/05_policy_application/outputs + data-analysis/01_data_preprocessing/outputs",
            "region": ai_region_source if ai_region_path.exists() else "page/manual_inputs/region_today.csv" if region else None,
            "station": "page/manual_inputs/station_search_index.csv" if stations else None,
        },
    }

    write_json(output_dir / "national_today.json", national)
    write_json(output_dir / "region_today.json", region)
    write_json(output_dir / "district_detail.json", district_detail)
    write_json(output_dir / "station_search_index.json", stations)
    write_json(output_dir / "price_history.json", history)
    write_json(output_dir / "training_data_coverage.json", training_coverage)
    write_json(output_dir / "external_data_status.json", external_status)
    write_json(output_dir / "site_manifest.json", manifest)

    print(f"[SAVE] {output_dir}")
    print(f"[INFO] as_of_date={manifest['as_of_date']} freshness={manifest['freshness']}")
    print(f"[INFO] regions={len(region):,} stations={len(stations):,}")
    print(f"[INFO] districts={len(district_detail.get('districts', [])):,} district_grids={len(district_detail.get('grids', [])):,}")
    print(f"[INFO] history={len(history):,}")


if __name__ == "__main__":
    main()
