# AI Model

전국 평균 유가 분석 결과를 주유소/격자 단위 예측 문제로 확장하는 폴더입니다. 데이터 수집 실행 노트북은 이 폴더에서 제거했고, 현재 AI 모델 단계는 `data collection/`의 수집 산출물과 `data-analysis` 산출물을 입력으로 사용합니다.

## 단계 구조

| 단계 | 폴더 | 역할 | 주요 산출물 |
|---|---|---|---|
| 01 | `01_derived_features/` | 격자화 전 데이터 준비. 주유소 좌표/속성 이력, 시설 좌표, 공시지가 격자, 전국 land grid 생성 | `data collection/derived_data/*.csv`, `korea_land_grid_500m.parquet` |
| 02 | `02_spatial_grid_build/` | 01 산출물과 주유소 가격 원자료를 결합해 최종 일별 500m 격자 패널 생성 | `ROOT_PATH/그리드/grid.parquet` |
| 03 | `03_target_dataset_build/` | `data-analysis/05`의 전국 적정가격을 격자별 spread와 결합해 target dataset 생성 | `outputs/grid_target.parquet` |
| 04 | `04_prediction_model_training/` | 03 target dataset으로 격자별 적정가격 예측 LSTM 학습/test | validation/test 예측, checkpoint, 최종 모델 |

## 입력 경로 원칙

AI Model 단계도 원천 수집 산출물은 `ROOT_PATH/data collection/`을 기준으로 읽습니다.

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
DERIVED_DATA_PATH = DATA_COLLECTION_PATH + "derived_data/"
```

수동 수집 데이터는 `z_pa_` 접두어 폴더에 둡니다.

```text
data collection/z_pa_facility/final/facility_data.csv
data collection/z_pa_policy/final/korea_fuel_tax_price_policies.csv
```

대용량 주유소 가격 원자료는 아래 구조를 기대합니다. 이 데이터는 용량 때문에 Git에 올리지 않아도 되며, Colab Drive의 `data collection/` 안에 있으면 됩니다.

```text
data collection/gas_station_prices_by_region/final/{region}/gasoline.csv
data collection/gas_station_prices_by_region/final/{region}/diesel.csv
data collection/gas_station_prices_by_region/final/{region}/metadata__latlon.json
```

## 단계 간 데이터 흐름

```text
data collection/gas_station_prices_by_region
data collection/z_pa_facility
data collection/official_land_price
        |
        v
01_derived_features
        |
        v
data collection/derived_data/
        |
        v
02_spatial_grid_build
        |
        v
ROOT_PATH/그리드/grid.parquet
        |
        v
03_target_dataset_build
        |
        v
ai-model/03_target_dataset_build/outputs/grid_target.parquet
        |
        v
04_prediction_model_training
```

## 현재 확인된 실행 결과

AI 01 노트북 최종 출력 기준입니다.

| 산출물 | 행 | 열 | 비고 |
|---|---:|---:|---|
| `national_daily_features.csv` | 6,736 | 21 | 2008-01-01 ~ 2026-06-10 |
| `station_location_history.csv` | 28,171 | 9 | 주유소 위치 이력 |
| `station_attribute_history.csv` | 153,625 | 8 | 브랜드/셀프 여부 등 속성 이력 |
| `station_latest_profile.csv` | 28,828 | 17 | 최신 주유소 프로필. 좌표 결측 포함 |
| `station_points.csv` | 27,830 | 11 | 유효 좌표 주유소 포인트 |
| `facility_points.csv` | 797 | 12 | 시설 원자료 좌표 결과. 좌표 결측 포함 |
| `facility_location_data_final.csv` | 740 | 4 | 유효 좌표 시설 포인트 |
| `official_land_price_grid.csv` | 396,185 | 12 | 공시지가 snapshot별 500m 격자 |
| `korea_land_grid_500m.parquet` | 별도 parquet | - | 전국 500m land grid |

AI 01 좌표 QC 결과는 다음과 같습니다.

| 구분 | 전체 행 | lon/lat 결측 | 숫자 좌표 범위 이탈 | 유효 좌표 |
|---|---:|---:|---:|---:|
| 주유소 | 28,828 | 415 | 0 | 28,413 |
| 시설 | 797 | 57 | 0 | 740 |

주유소 유효 좌표 28,413행은 최신 프로필 기준이며, `station_points.csv`는 같은 `station_id` 중복을 제거해 27,830행으로 저장됩니다.

AI 02 노트북 최종 출력 기준 `grid.parquet` 요약입니다.

| 파일 | 크기 | 행 | 격자 수 | 기간 |
|---|---:|---:|---:|---|
| `ROOT_PATH/그리드/grid.parquet` | 1,893.63 MB | 63,800,291 | 12,338 | 2008-04-15 ~ 2026-06-11 |

## 주의할 점

- 기존 원본 코드의 `DATA_PATH`, `preprocessed_data/additional_data` 참조는 과거 구조입니다. 새 구조에서는 `data collection/{dataset}/final/` 또는 `data collection/derived_data/` 기준으로 읽습니다.
- 01 단계에서 좌표가 비어 있는 주유소/시설은 숫자 좌표가 잘못된 것이 아니라 lon/lat 자체가 없는 경우입니다.
- 02 단계의 최종 산출물은 `grid.parquet` 하나입니다. 중간 parquet는 `/content/kff_spatial_grid_build_tmp`에 만들고 마지막에 삭제합니다.
- 03 단계는 `grid.parquet`을 덮어쓰지 않고 별도 `grid_target.parquet`을 만듭니다.
- 04 단계는 `grid_target.parquet`을 읽어 학습하며, 2026년 이후 데이터는 학습에 사용하지 않고 test로만 사용합니다.

## 하위 README

| 문서 | 내용 |
|---|---|
| `01_derived_features/README.md` | 01 입력 파일, 좌표 보강 방식, 산출물별 역할, QC 결과 |
| `02_spatial_grid_build/README.md` | 02 최종 격자 패널 생성 로직, 스키마, 최종 출력 |
| `03_target_dataset_build/README.md` | 03 target dataset 정의, 공식, 입력/출력 |
| `04_prediction_model_training/README.md` | 04 학습 데이터 정의, split, cache, 모델 설계, 산출물 |
