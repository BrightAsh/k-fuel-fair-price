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

아래 파일을 넣어주세요.

```text
page/public/assets/korea-map.png
```

지도 이미지는 첫 화면 지역별 패널에 사용합니다. 나중에 인터랙티브 지도까지 가려면 아래 파일을 추가합니다.

```text
page/public/assets/korea-regions.geojson
```

## Manual Data Until AI 03 Is Final

AI 03 최종 결과 포맷이 확정되기 전까지는 아래 파일을 수동으로 넣으면 페이지에 지역/주유소 정보를 표시할 수 있습니다.

```text
page/manual_inputs/region_today.csv
page/manual_inputs/station_search_index.csv
```

### `region_today.csv`

```text
as_of_date,region,fuel,actual_price,fair_price_policy,band_low_policy,band_high_policy,gap_policy,judge_policy
```

### `station_search_index.csv`

```text
station_id,name,brand,region,address,lon,lat,gasoline_price,diesel_price,judge_policy
```

## AI Model Outputs To Confirm

AI 모델 학습이 끝나면 아래 경로와 컬럼을 확인해야 합니다.

```text
ROOT_PATH/그리드/grid.parquet
ai-model/03_prediction_model_design/outputs/gasoline/gasoline_test_predictions_2026.parquet
ai-model/03_prediction_model_design/outputs/diesel/diesel_test_predictions_2026.parquet
ai-model/03_prediction_model_design/outputs/model_run_summary.csv
```

특히 `grid.parquet`는 Colab Drive에 있고, 03 코드는 repo 내부 `ai-model/02_spatial_grid_build/outputs/grid.parquet`를 기대합니다. 자동화 전 이 경로 연결 방식을 확정해야 합니다.

