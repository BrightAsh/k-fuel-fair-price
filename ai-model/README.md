# AI Model

이 폴더는 기존 6~8번을 AI 모델 파이프라인으로 다시 정리한 영역입니다.

```text
01_data_collection/          # 기존 6번
02_spatial_grid_build/       # 기존 7번
03_prediction_model_design/  # 기존 8번
```

## Stage Responsibility

| 단계 | 역할 | 핵심 산출물 |
|---|---|---|
| 01 데이터 수집 및 1차 전처리 | 외부 원천 데이터 수집, 기존 파일 정리, 지역별 주유소 가격/메타데이터와 시설 목록/좌표 파일 준비 | `ROOT_PATH/data collection/...` |
| 02 데이터 격자화 및 feature 생성 | 주유소/시설/공시지가를 500m 격자에 결합하고 AI feature 생성 | `ROOT_PATH/그리드/data_1/*.parquet` |
| 03 예측 모델 설계 및 학습 | 격자 패널과 분석 결과를 결합해 적정가격 예측 모델 학습/예측 | model bundle, prediction parquet/csv |

## Path Contract

AI Model 01의 기준 산출 경로는 다음입니다.

```python
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
```

AI Model 02는 원칙적으로 아래 파일들을 입력으로 사용합니다.

```text
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/gasoline.csv
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/diesel.csv
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/metadata.json
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/metadata__latlon.json
DATA_COLLECTION_PATH/facility/final/facility_data.csv
DATA_COLLECTION_PATH/facility/final/facility_location_data_final.csv
DATA_COLLECTION_PATH/official_land_price/final/공시지가.csv
```

원문 코드에는 `PROCESSED_PATH/additional_data/...`를 읽는 부분이 남아 있을 수 있습니다. 이 경로는 원문 로직을 이해하기 위한 참고 경로이고, 새 구조에서는 위 `DATA_COLLECTION_PATH` 기준으로 맞춰 실행해야 합니다.

## Feature Location

시설 영향력과 주유소 개수 영향력은 AI Model 01에서 계산하지 않습니다.

- AI Model 01: 시설 목록, 시설 좌표, 주유소 가격, 주유소 위치 메타데이터 준비
- AI Model 02: `station_count_total`, `gasoline_station_count`, `diesel_station_count`, `station_neighbor_influence`, `facility_*_count`, `storage_influence`, `agency_influence`, `factory_influence` 생성
- AI Model 03: 위 feature를 모델 입력 후보로 사용
