from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.validation import make_valid


VWORLD_WFS_URL = "https://api.vworld.kr/ned/wfs/getIndvdLandPriceWFS"
VWORLD_WFS_DOC_URL = "https://www.vworld.kr/dtna/dtna_apiSvcFc_s001.do?apiNum=24"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
)

CELL_SIZE_M = 500
DEFAULT_SNAPSHOT_DATE = "20260526"

# Official VWorld WFS sample bbox.
# EPSG:4326 bbox order for VWorld WFS is ymin,xmin,ymax,xmax.
DEFAULT_SAMPLE_BBOX_4326 = (
    37.5666502857805,
    127.31259030366,
    37.5689495688305,
    127.316674702516,
)


def fetch_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def get_vworld_key(use_doc_preview_key: bool = True) -> str:
    key = os.getenv("VWORLD_KEY", "").strip()
    if key:
        return key

    if not use_doc_preview_key:
        raise RuntimeError("VWORLD_KEY is required when --no-doc-preview-key is used.")

    html = fetch_text(VWORLD_WFS_DOC_URL, timeout=30)
    match = re.search(r'name\s*:\s*"key"\s*,\s*value\s*:\s*"([^"]+)"', html)
    if not match:
        raise RuntimeError(
            "VWORLD_KEY is not set and the official WFS preview key was not found."
        )
    return match.group(1)


def bbox_4326_to_5179(bbox_4326: tuple[float, float, float, float]) -> str:
    ymin, xmin, ymax, xmax = bbox_4326
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5179", always_xy=True)
    x1, y1 = transformer.transform(xmin, ymin)
    x2, y2 = transformer.transform(xmax, ymax)
    return f"{min(x1, x2)},{min(y1, y2)},{max(x1, x2)},{max(y1, y2)},EPSG:5179"


def normalize_bbox_5179(value: str) -> str:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) == 4:
        parts.append("EPSG:5179")
    if len(parts) != 5 or parts[-1].upper() != "EPSG:5179":
        raise ValueError(f"Expected minx,miny,maxx,maxy,EPSG:5179 bbox: {value}")
    float(parts[0])
    float(parts[1])
    float(parts[2])
    float(parts[3])
    return ",".join(parts)


def load_bbox_5179_file(path: Path) -> list[str]:
    bboxes: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        if "minx" in sample.lower() and "maxx" in sample.lower():
            reader = csv.DictReader(f)
            for row in reader:
                bboxes.append(
                    normalize_bbox_5179(
                        f"{row['minx']},{row['miny']},{row['maxx']},{row['maxy']},EPSG:5179"
                    )
                )
        else:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                bboxes.append(normalize_bbox_5179(line))
    if not bboxes:
        raise RuntimeError(f"No bbox rows found: {path}")
    return bboxes


def request_wfs_bbox_json(
    bbox_5179: str,
    key: str,
    domain: str,
    max_features: int,
    timeout: int = 90,
) -> dict:
    params = {
        "typename": "dt_d150",
        "bbox": bbox_5179,
        "maxFeatures": str(max_features),
        "resultType": "results",
        "srsName": "EPSG:5179",
        "output": "json",
        "key": key,
        "domain": domain,
    }
    query = urllib.parse.urlencode(params, safe="$,:-/")
    req = urllib.request.Request(
        f"{VWORLD_WFS_URL}?{query}",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Referer": VWORLD_WFS_DOC_URL,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"WFS did not return JSON: {text[:500]}") from exc


def download_features(
    bboxes_5179: Iterable[str],
    key: str,
    domain: str,
    max_features: int,
    sleep_sec: float,
) -> list[dict]:
    features_by_pnu: dict[str, dict] = {}

    for idx, bbox_5179 in enumerate(bboxes_5179, start=1):
        data = request_wfs_bbox_json(
            bbox_5179=bbox_5179,
            key=key,
            domain=domain,
            max_features=max_features,
        )
        features = data.get("features") or []
        total = data.get("totalFeatures")
        returned = data.get("numberReturned", len(features))
        print(
            f"[bbox {idx}] totalFeatures={total} numberReturned={returned} "
            f"features={len(features)} bbox={bbox_5179}",
            flush=True,
        )

        if total and int(total) > max_features:
            raise RuntimeError(
                "WFS result hit maxFeatures. Split the bbox into smaller tiles: "
                f"totalFeatures={total}, maxFeatures={max_features}, bbox={bbox_5179}"
            )

        for feature in features:
            props = feature.get("properties") or {}
            pnu = str(props.get("pnu") or feature.get("id") or "")
            if pnu:
                features_by_pnu[pnu] = feature

        if sleep_sec > 0:
            time.sleep(sleep_sec)

    return list(features_by_pnu.values())


def cell_floor(value: float) -> int:
    return int(math.floor(value / CELL_SIZE_M) * CELL_SIZE_M)


def iter_grid_cells(minx: float, miny: float, maxx: float, maxy: float):
    start_x = cell_floor(minx)
    end_x = cell_floor(maxx)
    start_y = cell_floor(miny)
    end_y = cell_floor(maxy)
    for cell_x in range(start_x, end_x + CELL_SIZE_M, CELL_SIZE_M):
        for cell_y in range(start_y, end_y + CELL_SIZE_M, CELL_SIZE_M):
            yield cell_x, cell_y


def aggregate_features_to_grid(features: list[dict], snapshot_date: str) -> list[dict]:
    weighted_price_sum: dict[tuple[int, int], float] = defaultdict(float)
    area_sum: dict[tuple[int, int], float] = defaultdict(float)

    for feature in features:
        props = feature.get("properties") or {}
        price = props.get("pblntf_pclnd")
        if price is None:
            continue

        geom = make_valid(shape(feature["geometry"]))
        if geom.is_empty:
            continue

        for cell_x, cell_y in iter_grid_cells(*geom.bounds):
            grid = box(cell_x, cell_y, cell_x + CELL_SIZE_M, cell_y + CELL_SIZE_M)
            overlap_area = geom.intersection(grid).area
            if overlap_area <= 0:
                continue

            key = (cell_x, cell_y)
            weighted_price_sum[key] += float(price) * overlap_area
            area_sum[key] += overlap_area

    price_col = f"p_{snapshot_date}"
    rows = []
    for (cell_x, cell_y), total_area in sorted(area_sum.items()):
        if total_area <= 0:
            continue
        rows.append(
            {
                "grid_id": f"G500_{cell_x // CELL_SIZE_M}_{cell_y // CELL_SIZE_M}",
                "cell_x": cell_x,
                "cell_y": cell_y,
                price_col: weighted_price_sum[(cell_x, cell_y)] / total_area,
            }
        )
    return rows


def validate_grid_rows(rows: list[dict], snapshot_date: str) -> None:
    price_col = f"p_{snapshot_date}"
    required = {"grid_id", "cell_x", "cell_y", price_col}
    if not rows:
        raise RuntimeError("No grid rows were produced.")
    if set(rows[0]) != required:
        raise RuntimeError(f"Unexpected columns: {list(rows[0])}")

    seen = set()
    for row in rows:
        key = (row["cell_x"], row["cell_y"])
        if key in seen:
            raise RuntimeError(f"Duplicate grid cell: {key}")
        seen.add(key)
        expected_grid_id = (
            f"G500_{int(row['cell_x']) // CELL_SIZE_M}_"
            f"{int(row['cell_y']) // CELL_SIZE_M}"
        )
        if row["grid_id"] != expected_grid_id:
            raise RuntimeError(f"Invalid grid_id for {key}: {row['grid_id']}")
        float(row[price_col])


def write_grid_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def append_rows_to_base_csv(base_csv: Path, new_rows: list[dict], output_csv: Path) -> None:
    if not new_rows:
        raise RuntimeError("No new rows to append.")

    price_cols = [c for c in new_rows[0] if c.startswith("p_")]
    if len(price_cols) != 1:
        raise RuntimeError(f"Expected exactly one p_ column in new rows: {price_cols}")
    price_col = price_cols[0]

    price_by_cell = {
        (int(row["cell_x"]), int(row["cell_y"])): row[price_col]
        for row in new_rows
    }

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with base_csv.open("r", newline="", encoding="utf-8-sig") as src:
        reader = csv.DictReader(src)
        if not reader.fieldnames:
            raise RuntimeError(f"Base CSV has no header: {base_csv}")
        if "cell_x" not in reader.fieldnames or "cell_y" not in reader.fieldnames:
            raise RuntimeError("Base CSV must contain cell_x and cell_y columns.")
        if price_col in reader.fieldnames:
            raise RuntimeError(f"Base CSV already has column: {price_col}")

        fieldnames = list(reader.fieldnames) + [price_col]
        with output_csv.open("w", newline="", encoding="utf-8-sig") as dst:
            writer = csv.DictWriter(dst, fieldnames=fieldnames)
            writer.writeheader()
            matched = 0
            total = 0
            for row in reader:
                total += 1
                key = (int(float(row["cell_x"])), int(float(row["cell_y"])))
                value = price_by_cell.get(key)
                row[price_col] = "" if value is None else value
                if value is not None:
                    matched += 1
                writer.writerow(row)

    print(
        f"[append csv] base_rows={total} matched_new_rows={matched} "
        f"unmatched_new_rows={len(price_by_cell) - matched}",
        flush=True,
    )


def parse_bbox_4326(value: str) -> tuple[float, float, float, float]:
    parts = [float(p.strip()) for p in value.split(",") if p.strip()]
    if len(parts) != 4:
        raise ValueError("Expected ymin,xmin,ymax,xmax for --bbox4326")
    return tuple(parts)  # type: ignore[return-value]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download VWorld official land price WFS features and aggregate them "
            "to the project 500m grid CSV format."
        )
    )
    parser.add_argument(
        "--snapshot-date",
        default=DEFAULT_SNAPSHOT_DATE,
        help="Snapshot date used in the output p_YYYYMMDD column.",
    )
    parser.add_argument(
        "--output",
        default=f"official_land_price_wfs_grid_{DEFAULT_SNAPSHOT_DATE}.csv",
        help="Output CSV path.",
    )
    parser.add_argument(
        "--base-csv",
        default=None,
        help=(
            "Optional existing project 공시지가.csv. When supplied, the new p_YYYYMMDD "
            "column is left-joined by cell_x/cell_y and written to --output."
        ),
    )
    parser.add_argument(
        "--bbox4326",
        default=None,
        help="Single VWorld EPSG:4326 bbox as ymin,xmin,ymax,xmax.",
    )
    parser.add_argument(
        "--bbox5179",
        default=None,
        help="Single EPSG:5179 bbox as minx,miny,maxx,maxy[,EPSG:5179].",
    )
    parser.add_argument(
        "--bbox5179-file",
        default=None,
        help="CSV/text file containing EPSG:5179 tile bboxes.",
    )
    parser.add_argument("--max-features", type=int, default=1000)
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    parser.add_argument("--domain", default=os.getenv("VWORLD_DOMAIN", "api.vworld.kr"))
    parser.add_argument(
        "--no-doc-preview-key",
        action="store_true",
        help="Require VWORLD_KEY instead of reading the public preview key from VWorld docs.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    snapshot_date = re.sub(r"[^0-9]", "", args.snapshot_date)
    if len(snapshot_date) != 8:
        raise ValueError("--snapshot-date must resolve to YYYYMMDD")

    bboxes: list[str] = []
    if args.bbox5179_file:
        bboxes.extend(load_bbox_5179_file(Path(args.bbox5179_file)))
    if args.bbox5179:
        bboxes.append(normalize_bbox_5179(args.bbox5179))
    if args.bbox4326:
        bboxes.append(bbox_4326_to_5179(parse_bbox_4326(args.bbox4326)))
    if not bboxes:
        bboxes.append(bbox_4326_to_5179(DEFAULT_SAMPLE_BBOX_4326))

    key = get_vworld_key(use_doc_preview_key=not args.no_doc_preview_key)
    features = download_features(
        bboxes_5179=bboxes,
        key=key,
        domain=args.domain,
        max_features=args.max_features,
        sleep_sec=args.sleep_sec,
    )
    print(f"[download done] unique_features={len(features)}", flush=True)

    rows = aggregate_features_to_grid(features, snapshot_date=snapshot_date)
    validate_grid_rows(rows, snapshot_date=snapshot_date)
    output_path = Path(args.output)
    if args.base_csv:
        append_rows_to_base_csv(Path(args.base_csv), rows, output_path)
    else:
        write_grid_csv(output_path, rows)

    print(f"[grid csv] path={output_path.resolve()}", flush=True)
    print(f"[grid csv] rows={len(rows)} columns={list(rows[0])}", flush=True)
    print("[preview]")
    for row in rows[:10]:
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
