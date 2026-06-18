# Page Data Contract

`page`는 대용량 원천/모델 파일을 직접 공개하지 않고, 아래 JSON 파일만 읽습니다.

```text
page/public/data/latest/site_manifest.json
page/public/data/latest/national_today.json
page/public/data/latest/region_today.json
page/public/data/latest/station_search_index.json
page/public/data/latest/price_history.json
page/public/data/latest/training_data_coverage.json
page/public/data/latest/external_data_status.json
page/public/assets/korea-provinces.geojson
```

## Source Inputs

현재 파악된 파이프라인 기준 핵심 입력은 다음입니다.

### 전국 적정가격/정책 적용

```text
data-analysis/05_policy_application/outputs/휘발유/일별_정책적용_데이터_휘발유.csv
data-analysis/05_policy_application/outputs/경유/일별_정책적용_데이터_경유.csv
```

주요 컬럼:

```text
date 또는 날짜
국내유가_원L
적정가격_미정책_원L
적정범위_미정책_하한_원L
적정범위_미정책_상한_원L
적정가격_정책적용_원L
적정범위_정책적용_하한_원L
적정범위_정책적용_상한_원L
정책효과_원L
정책적용_inside
정책적용_above
정책적용_below
```

### 지역별 요약

아직 최종 지역별 적정가격 산출물 계약은 확정 전입니다.

임시 입력:

```text
page/manual_inputs/region_today.csv
```

필수 컬럼:

```text
as_of_date,region,fuel,actual_price,fair_price_policy,band_low_policy,band_high_policy,gap_policy,judge_policy
```

`fuel` 값은 `gasoline`, `diesel`을 사용합니다.

향후 AI 모델 03 결과가 확정되면 아래 중 하나를 기준으로 자동 생성합니다.

```text
ai-model/03_prediction_model_design/outputs/gasoline/gasoline_test_predictions_2026.parquet
ai-model/03_prediction_model_design/outputs/diesel/diesel_test_predictions_2026.parquet
```

또는 모델 학습 완료 후 생성될 지역 집계 CSV:

```text
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_region_daily_summary.csv
```

### 주유소 검색

임시 입력:

```text
page/manual_inputs/station_search_index.csv
```

필수 컬럼:

```text
station_id,name,brand,region,address,lon,lat,gasoline_price,diesel_price,judge_policy
```

### 수동/강제 수집 가격 이력

비어 있는 날짜를 강제 수집으로 보강할 때 사용합니다.

```text
page/manual_inputs/price_history.csv
```

필수 컬럼:

```text
date,region,fuel,actual_price,fair_price_policy,band_low_policy,band_high_policy,gap_policy
```

이 파일은 `page/public/data/latest/price_history.json`과 `date + region + fuel` 기준으로 병합됩니다. 따라서 기존 이력은 유지되고, 같은 키의 행은 새 값으로 교체됩니다.

향후에는 아래 AI 01/02 산출물과 AI 03 예측 결과를 결합해 생성합니다.

```text
data-analysis/00_data_collection/outputs/derived_data/station_latest_profile.csv
data-analysis/00_data_collection/outputs/derived_data/station_points.csv
ROOT_PATH/그리드/grid.parquet
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_test_predictions_2026.parquet
```

### AI 학습 데이터 지도

`데이터 현황` 탭은 연결 상태 목록이 아니라 AI 학습에 사용한 데이터의 지역별 분포를 대한민국 지도 히트맵으로 보여줍니다.

수동/중간 입력:

```text
page/manual_inputs/training_data_coverage.csv
```

필수 컬럼:

```text
dataset,date,region,value,unit,label
```

기본 `dataset` 값:

```text
grid_panel_rows          # AI 02 최종 grid.parquet의 시도·날짜별 행 수
station_count            # 주유소 입력 수
facility_count           # 시설 영향력 입력 수
land_price_grid_count    # 공시지가 격자 수
```

`date`가 있으면 페이지에서 날짜를 선택할 수 있고, 날짜가 없는 snapshot 데이터는 전체값으로 표시합니다.

## Output JSON

### `site_manifest.json`

```json
{
  "schema_version": "page_data_v1",
  "as_of_date": "2026-06-09",
  "generated_at": "2026-06-10T03:00:00+09:00",
  "freshness": "fresh",
  "files": ["national_today.json", "region_today.json", "station_search_index.json", "price_history.json", "training_data_coverage.json", "external_data_status.json"],
  "assets": ["korea-provinces.geojson"]
}
```

`files`에는 기간별 그래프와 다운로드에 쓰는 `price_history.json`도 포함될 수 있습니다.

### `national_today.json`

```json
{
  "schema_version": "national_today_v1",
  "as_of_date": "2026-06-09",
  "generated_at": "2026-06-10T03:00:00+09:00",
  "freshness": "fresh",
  "fuels": {
    "gasoline": {
      "label": "휘발유",
      "actual_price": 2009.98,
      "actual_delta_1d": 1.2,
      "fair_price_policy": 1886.91,
      "band_low_policy": 1873.12,
      "band_high_policy": 1901.02,
      "gap_policy": 123.07,
      "judge_policy": "비쌈",
      "policy_effect": 123.07
    }
  },
  "policies": [
    {
      "title": "유류세 인하 반영",
      "status": "정책 효과 반영",
      "period": "분석 산출물 기준",
      "gasoline_effect": 123.07,
      "diesel_effect": 145.41,
      "note": "전국 적정가격 산식에 반영된 정책효과입니다."
    }
  ]
}
```

### `region_today.json`

배열입니다. 각 행은 한 지역이고, fuel별 값을 중첩 객체로 둡니다.

```json
[
  {
    "region": "서울",
    "gasoline": {
      "actual_price": 2078.0,
      "fair_price_policy": 1934.0,
      "gap_policy": 144.0,
      "judge_policy": "비쌈"
    },
    "diesel": {
      "actual_price": 2059.0,
      "fair_price_policy": 1906.0,
      "gap_policy": 153.0,
      "judge_policy": "비쌈"
    }
  }
]
```

### `station_search_index.json`

검색/주변 주유소 기능에 쓰는 공개 인덱스입니다. `station_search_index.csv`에 들어온 행 전체를 변환하므로, 주변 주유소 탭은 선택 반경 안의 모든 행을 거리순으로 표시합니다. 단, GitHub Pages에 공개되는 파일이므로 내부용 원천 컬럼은 넣지 않습니다.

```json
[
  {
    "station_id": "A0000001",
    "name": "주유소명",
    "brand": "SK에너지",
    "region": "서울",
    "address": "서울 ...",
    "lon": 127.0,
    "lat": 37.5,
    "gasoline_price": 2010.0,
    "diesel_price": 1980.0,
    "judge_policy": "적정"
  }
]
```

### `price_history.json`

기간별 그래프와 가격 요약 CSV 다운로드에 사용합니다. 현재 자동 생성은 전국 일별 정책 적용 데이터 기준이며, 지역별 시계열이 확정되면 같은 스키마에서 `region` 값을 시도명으로 확장합니다.

```json
[
  {
    "date": "2026-06-09",
    "region": "전국",
    "fuel": "gasoline",
    "actual_price": 2009.98,
    "fair_price_policy": 2373.07,
    "band_low_policy": 2363.23,
    "band_high_policy": 2395.36,
    "gap_policy": -363.09,
    "source": "data-analysis/05_policy_application/outputs/휘발유/일별_정책적용_데이터_휘발유.csv"
  }
]
```

자동화가 다시 실행될 때 기존 `price_history.json`을 읽어 새 행과 병합합니다. 이 구조 때문에 모델 완성 이후 날짜를 지정해 과거 빈 구간을 강제 수집해도 기존 날짜가 삭제되지 않습니다.

### `training_data_coverage.json`

`데이터 현황` 탭의 지도 히트맵에 사용합니다.

```json
{
  "schema_version": "training_data_coverage_v1",
  "generated_at": "2026-06-18T03:00:00+09:00",
  "source": "page/manual_inputs/training_data_coverage.csv",
  "datasets": [
    {
      "id": "grid_panel_rows",
      "label": "AI 학습 격자 패널 행 수",
      "unit": "행",
      "status": "connected",
      "rows": 340,
      "date_min": "2026-06-01",
      "date_max": "2026-06-10",
      "path": "ROOT_PATH/그리드/grid.parquet",
      "note": "AI 02 최종 grid.parquet를 시도·날짜별로 집계한 값입니다."
    }
  ],
  "rows": [
    {
      "dataset": "grid_panel_rows",
      "date": "2026-06-10",
      "region": "서울",
      "value": 123456,
      "unit": "행",
      "label": null
    }
  ]
}
```

### `external_data_status.json`

웹 내부 점검용 데이터 연결 상태입니다. 현재 사용자 화면의 `데이터 현황` 탭은 `training_data_coverage.json`을 우선 사용합니다.

```json
{
  "schema_version": "external_data_status_v1",
  "generated_at": "2026-06-18T03:00:00+09:00",
  "datasets": [
    {
      "id": "station_search_index",
      "label": "주유소 검색/주변",
      "status": "connected",
      "rows": 5000,
      "date_min": "2026-06-09",
      "date_max": "2026-06-09",
      "path": "page/manual_inputs/station_search_index.csv",
      "note": "검색 탭과 주변 주유소 탭에 사용합니다."
    }
  ]
}
```

## Freshness Rule

`as_of_date`가 현재 한국 날짜 기준 어제 또는 오늘이면 `fresh`, 그보다 오래되면 `stale`로 표시합니다.
