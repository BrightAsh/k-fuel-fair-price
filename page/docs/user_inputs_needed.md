# User Inputs Needed

웹/자동화를 실제 운영 상태로 만들기 위해 사용자가 준비해야 하는 항목입니다.

## GitHub Settings

GitHub repo 설정에서 Pages를 활성화해야 합니다.

권장:

```text
Settings > Pages > Source = GitHub Actions
```

## GitHub Secrets

현재 초안 workflow는 secret 없이도 레포 산출물 기준 웹 JSON을 만들 수 있습니다.

다만 자동 수집까지 GitHub Actions에서 하려면 아래 secret이 필요할 수 있습니다.

```text
GIMI9_GEOCODER_TOKEN
KAKAO_REST_API_KEY
NAVER_MAPS_CLIENT_ID
NAVER_MAPS_CLIENT_SECRET
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
```

실제로 어떤 secret이 필요한지는 수집을 Actions로 옮기는 범위에 따라 달라집니다.

## Static Assets

지도 asset은 이미 repo에 포함되어 있습니다.

```text
page/public/assets/korea-provinces.geojson
```

첫 화면은 이 GeoJSON을 SVG로 그려 시도별 색상을 칠합니다. 더 최신 행정구역 경계가 필요할 때만 같은 스키마의 GeoJSON으로 교체하면 됩니다.

출처는 `southkorea/southkorea-maps`의 KOSTAT 2013 province GeoJSON입니다.

## Manual Data Until AI 03 Is Final

AI 03 최종 결과 포맷이 확정되기 전까지는 아래 파일을 수동으로 넣으면 페이지에 지역/주유소 정보를 표시할 수 있습니다.

```text
page/manual_inputs/region_today.csv
page/manual_inputs/station_search_index.csv
page/manual_inputs/price_history.csv
```

### `region_today.csv`

```text
as_of_date,region,fuel,actual_price,fair_price_policy,band_low_policy,band_high_policy,gap_policy,judge_policy
```

### `station_search_index.csv`

```text
station_id,name,brand,region,address,lon,lat,gasoline_price,diesel_price,judge_policy
```

### `price_history.csv`

가격 추이와 다운로드용 기간 데이터를 직접 보강할 때 넣습니다.

```text
date,region,fuel,actual_price,fair_price_policy,band_low_policy,band_high_policy,gap_policy
```

`page/public/data/latest/price_history.json`과 병합되므로 강제 수집으로 빈 날짜만 넣어도 기존 이력이 유지됩니다.

## AI Model Outputs To Confirm

AI 모델 학습이 끝나면 아래 경로와 컬럼을 확인해야 합니다.

```text
ROOT_PATH/그리드/grid.parquet
ai-model/03_prediction_model_design/outputs/gasoline/gasoline_test_predictions_2026.parquet
ai-model/03_prediction_model_design/outputs/diesel/diesel_test_predictions_2026.parquet
ai-model/03_prediction_model_design/outputs/model_run_summary.csv
```

특히 `grid.parquet`는 Colab Drive에 있고, 03 코드는 repo 내부 `ai-model/02_spatial_grid_build/outputs/grid.parquet`를 기대합니다. 자동화 전 이 경로 연결 방식을 확정해야 합니다.
