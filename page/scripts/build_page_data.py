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
    },
    "diesel": {
        "label": "경유",
        "policy_csv": Path("data-analysis/05_policy_application/outputs/경유/일별_정책적용_데이터_경유.csv"),
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


def build_external_data_status(repo_root: Path, output_dir: Path, national: dict[str, Any], region: list[dict[str, Any]], stations: list[dict[str, Any]], history: list[dict[str, Any]]) -> dict[str, Any]:
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    history_min, history_max = history_extent(history)
    national_date = national.get("as_of_date")
    station_input = repo_root / "page/manual_inputs/station_search_index.csv"
    region_input = repo_root / "page/manual_inputs/region_today.csv"
    manual_history_input = repo_root / "page/manual_inputs/price_history.csv"
    ai_gasoline_dir = repo_root / "ai-model/03_prediction_model_design/outputs/gasoline"
    ai_diesel_dir = repo_root / "ai-model/03_prediction_model_design/outputs/diesel"
    ai_exists = ai_gasoline_dir.exists() or ai_diesel_dir.exists()

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
                "status": "connected" if region_input.exists() and region else "waiting",
                "rows": len(region),
                "date_min": national_date,
                "date_max": national_date,
                "path": "page/manual_inputs/region_today.csv",
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
                "rows": 0,
                "date_min": None,
                "date_max": None,
                "path": "ai-model/03_prediction_model_design/outputs/{fuel}/",
                "note": "학습 완료 후 지역/주유소 적정가격과 예측 이력을 생성합니다.",
            },
        ],
    }


def build_region(repo_root: Path) -> list[dict[str, Any]]:
    path = repo_root / "page/manual_inputs/region_today.csv"
    if not path.exists():
        return []

    df = read_csv(path)
    rows: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        region = str(row.get("region", "")).strip()
        fuel = str(row.get("fuel", "")).strip()
        if not region or fuel not in FUEL_CONFIG:
            continue
        rows.setdefault(region, {"region": region})
        rows[region][fuel] = {
            "actual_price": to_float(row.get("actual_price")),
            "fair_price_policy": to_float(row.get("fair_price_policy")),
            "band_low_policy": to_float(row.get("band_low_policy")),
            "band_high_policy": to_float(row.get("band_high_policy")),
            "gap_policy": to_float(row.get("gap_policy")),
            "judge_policy": row.get("judge_policy") if pd.notna(row.get("judge_policy")) else None,
        }
    return list(rows.values())


def build_station_index(repo_root: Path, limit: int = 5000) -> list[dict[str, Any]]:
    path = repo_root / "page/manual_inputs/station_search_index.csv"
    if not path.exists():
        return []

    df = read_csv(path).head(limit)
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
            "external_data_status.json",
        ],
        "assets": [
            "korea-provinces.geojson",
        ],
        "source": {
            "national": "data-analysis/05_policy_application/outputs",
            "region": "page/manual_inputs/region_today.csv" if region else None,
            "station": "page/manual_inputs/station_search_index.csv" if stations else None,
        },
    }

    write_json(output_dir / "national_today.json", national)
    write_json(output_dir / "region_today.json", region)
    write_json(output_dir / "station_search_index.json", stations)
    write_json(output_dir / "price_history.json", history)
    write_json(output_dir / "external_data_status.json", external_status)
    write_json(output_dir / "site_manifest.json", manifest)

    print(f"[SAVE] {output_dir}")
    print(f"[INFO] as_of_date={manifest['as_of_date']} freshness={manifest['freshness']}")
    print(f"[INFO] regions={len(region):,} stations={len(stations):,}")
    print(f"[INFO] history={len(history):,}")


if __name__ == "__main__":
    main()
