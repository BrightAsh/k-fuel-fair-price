# 01. Derived Features

AI 모델 학습 전에 필요한 파생 CSV를 만드는 단계입니다.

## 실행 파일

- `02_derived_features.ipynb`
- 동일 코드 원본: `02_derived_features.py`

## 입력 경로

```python
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
DERIVED_DATA_PATH = DATA_COLLECTION_PATH + "derived_data/"
```

수동 시설 데이터는 아래 경로를 기준으로 둡니다.

```text
DATA_COLLECTION_PATH/z_pa_facility/final/facility_data.csv
```

## 주요 산출물

```text
DATA_COLLECTION_PATH/derived_data/data_readiness_summary.csv
DATA_COLLECTION_PATH/derived_data/national_daily_features.csv
DATA_COLLECTION_PATH/derived_data/station_price_manifest.csv
DATA_COLLECTION_PATH/derived_data/station_location_history.csv
DATA_COLLECTION_PATH/derived_data/station_attribute_history.csv
DATA_COLLECTION_PATH/derived_data/station_latest_profile.csv
DATA_COLLECTION_PATH/derived_data/facility_points.csv
DATA_COLLECTION_PATH/derived_data/facility_location_data_final.csv
DATA_COLLECTION_PATH/derived_data/official_land_price_grid.csv
DATA_COLLECTION_PATH/derived_data/official_land_price_snapshots.csv
DATA_COLLECTION_PATH/derived_data/derived_outputs_summary.csv
```

## 확인 사항

- 필요한 수집 산출물이 `data collection/{dataset}/final/`에 있는지 확인합니다.
- 주유소 가격/메타데이터의 기간, station 수, 위경도 결측을 확인합니다.
- 시설 데이터는 `z_pa_facility` 기준으로 정리합니다.
- 공시지가는 `official_land_price/final/`의 grid/snapshot 형식을 확인합니다.
