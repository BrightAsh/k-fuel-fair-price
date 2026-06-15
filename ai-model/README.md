# AI Model

이 폴더는 기존 6~8번을 AI 모델 파이프라인으로 다시 정리한 영역입니다. 새 흐름은 4단계입니다.

```text
01_data_collection/          # 기존 6번: 자동 수집 및 1차 전처리
02_derived_features/         # 신규: 격자화 전 파생 변수/파생 데이터 CSV 생성
03_spatial_grid_build/       # 기존 7번: 500m 격자화
04_prediction_model_design/  # 기존 8번: 예측 모델 설계 및 학습
```

## Stage Responsibility

| 단계 | 역할 | 핵심 산출물 |
|---|---|---|
| 01 데이터 수집 및 1차 전처리 | 외부 원천 데이터 수집, 지역별 주유소 가격/메타데이터, 시설/공시지가 원자료 준비 | `ROOT_PATH/data collection/{dataset}/...` |
| 02 파생 변수/파생 데이터 추가 | 01 산출물을 격자화 전 표준 CSV로 정리, 좌표/컬럼/기간 검증, 시설 좌표 보강 | `ROOT_PATH/data collection/derived_data/*.csv` |
| 03 데이터 격자화 | 02 산출물과 지도 데이터를 사용해 500m grid panel 및 공간 feature 생성 | `ROOT_PATH/그리드/data_1/*.parquet` |
| 04 예측 모델 설계 및 학습 | 격자 패널과 Data Analysis 결과를 결합해 적정가격 예측 모델 학습/예측 | model bundle, prediction parquet/csv |

## Path Contract

공통 경로는 다음입니다.

```python
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
DERIVED_DATA_PATH = DATA_COLLECTION_PATH + "derived_data/"
```

AI Model 02는 다음 CSV들을 만듭니다.

```text
DERIVED_DATA_PATH/data_readiness_summary.csv
DERIVED_DATA_PATH/national_daily_features.csv
DERIVED_DATA_PATH/station_price_manifest.csv
DERIVED_DATA_PATH/station_location_history.csv
DERIVED_DATA_PATH/station_attribute_history.csv
DERIVED_DATA_PATH/station_latest_profile.csv
DERIVED_DATA_PATH/facility_points.csv
DERIVED_DATA_PATH/facility_location_data_final.csv
DERIVED_DATA_PATH/official_land_price_grid.csv
DERIVED_DATA_PATH/official_land_price_snapshots.csv
DERIVED_DATA_PATH/derived_outputs_summary.csv
```

AI Model 03은 원칙적으로 위 `DERIVED_DATA_PATH` 산출물을 입력으로 사용하도록 맞춥니다.

## Feature Location

- AI Model 01: 원자료 수집/1차 전처리
- AI Model 02: 격자화 전 파생 CSV, 좌표 보강, 입력 검증
- AI Model 03: `station_count_total`, `gasoline_station_count`, `diesel_station_count`, `station_neighbor_influence`, `facility_*_count`, `storage_influence`, `agency_influence`, `factory_influence`, `official_land_price` 생성
- AI Model 04: 위 feature를 모델 입력 후보로 사용
