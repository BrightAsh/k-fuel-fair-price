# 01. Derived Features

AI 모델용 최종 격자 패널을 만들기 전, `data-analysis/00_data_collection/outputs/`의 수집 산출물을 격자화 가능한 형태로 정리하는 단계입니다. 이 단계는 직접 학습 데이터를 만들지 않고, 02 단계가 사용할 주유소/시설/공시지가/land grid 기반 입력을 생성합니다.

## 실행 파일

| 파일 | 역할 |
|---|---|
| `01_derived_features.ipynb` | Colab 실행용 노트북 |
| `01_derived_features.py` | 노트북과 같은 로직의 Python 코드 |

노트북 구조는 markdown 1개, code 12개입니다. 저장된 출력 기준으로 마지막 검증 셀에는 산출물 목록, 좌표 결측 QC, missing requirement 2건이 표시됩니다.

## 경로

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
DATA_COLLECTION_PATH = ROOT_PATH + "data-analysis/00_data_collection/outputs/"
DERIVED_DATA_PATH = DATA_COLLECTION_PATH + "derived_data/"
```

`DERIVED_DATA_PATH`는 없으면 생성합니다. 중간 실험 산출물은 저장하지 않고, 02 단계 이후에 실제로 쓰는 파일만 남기도록 정리했습니다.

## 필수 입력

| 입력 | 위치 | 용도 |
|---|---|---|
| 환율 | `fx_usdkrw/fx_usdkrw_*.csv` | 전국 일별 feature 후보 |
| 원유 | `crude/crude_*.csv` | 원유 가격 feature 후보 |
| 국제 제품가격 | `intl_products/intl_products_*.csv` | 국제 제품 가격 feature 후보 |
| 전국 평균 가격 | `retail_avg/retail_avg_*.csv` | 전국 일별 feature 후보 |
| 브랜드 가격 | `brand_price/brand_gasoline_*.csv`, `brand_diesel_*.csv` | 전국 일별 feature 후보 |
| 유류세 | `fuel_tax_trend/gasoline_tax_trend_*.xls`, `diesel_tax_trend_*.xls` | 전국 일별 feature 후보 |
| 정유사 주간 공급가격 | `refinery_weekly_supply/refinery_weekly_supply_prices_by_product_*.csv` | 전국 일별 feature 후보 |
| 주유소 가격/메타 | `gas_station_prices_by_region/{region}/gasoline.csv` 또는 `{fuel}.parts/`, `metadata.json` | 주유소 좌표, 가격 가능 일자, 속성 이력 |
| 수동 시설 | `z_pa_facility/facility_data.csv` | 시설 좌표/유형 |
| 공시지가 | `official_land_price/*.csv` 또는 `derived_data/official_land_price_grid.csv` | 500m 격자별 공시지가 snapshot |

`gas_station_prices_by_region` 중 GitHub 100MB 제한을 넘는 파일은 `{fuel}.parts/`로 열 기준 분할해 보관합니다.

## 좌표 보강 방식

좌표 보강은 기존 원문 코드에서 사용하던 GIMI9 주소 API를 1차 기준으로 사용합니다.

| Secret | 용도 |
|---|---|
| `GEOCODER_TOKEN` 또는 `GIMI9_GEOCODER_TOKEN` | GIMI9 주소 좌표 변환 |
| `KAKAO_REST_API_KEY` | GIMI9 실패 주소에 대한 보조 geocoder |
| `NAVER_MAPS_CLIENT_ID`, `NAVER_MAPS_CLIENT_SECRET` | GIMI9/Kakao 실패 주소에 대한 보조 geocoder |

보조 API는 기본 좌표를 무조건 대체하지 않습니다. GIMI9가 실패한 주소만 순차적으로 시도하고, Kakao/Naver 결과가 모두 있는 경우 두 좌표 간 거리가 500m를 넘으면 `needs_review=True`로 남깁니다. VWorld 함수는 코드에 남아 있지만, API 결과 저장 제한 이슈 때문에 기본 geocoder 목록에는 넣지 않았습니다.

## 처리 내용

### 1. 입력 준비 여부 확인

`INPUT_SPECS`에 정의한 자동/수동/대용량 입력을 확인합니다. 발견한 파일의 행 수, 컬럼, 날짜 범위는 노트북 출력에 표시합니다.

### 2. 전국 일별 feature 생성

자동 수집 파일 중 날짜 컬럼을 안정적으로 찾을 수 있는 파일만 일별 테이블로 표준화합니다. 최신 실행에서는 `crude`와 `intl_products`가 정상 표준화되었고, 일부 파일은 날짜 컬럼 구조가 달라 중간 파일 저장을 생략했습니다. 최종 `national_daily_features.csv`는 6,736행, 21열입니다.

### 3. 주유소 위치/속성 이력 생성

지역별 `metadata__latlon.json`과 가격 wide CSV를 읽어 다음을 만듭니다.

| 산출물 | 내용 |
|---|---|
| `station_location_history.csv` | `station_id`별 위치 이력 |
| `station_attribute_history.csv` | 브랜드, 셀프 여부 등 속성 이력 |
| `station_latest_profile.csv` | 최신 주유소 프로필. 좌표 결측/비정상 행도 포함 |
| `station_points.csv` | 유효 좌표만 남긴 주유소 포인트 |

같은 `station_id`가 여러 지역 폴더에 중복 등장해도 `station_points.csv`에는 1개 좌표만 남깁니다.
최신 실행에서는 좌표 유효 주유소 프로필 28,413행을 `station_id` 기준으로 정리해 최종 주유소 포인트 27,830행을 저장했습니다.

### 4. 시설 좌표 생성

`z_pa_facility/facility_data.csv`를 읽어 시설 유형을 표준화하고 주소 좌표를 보강합니다.

| 산출물 | 내용 |
|---|---|
| `facility_points.csv` | 전체 시설 좌표 결과. 좌표 결측 포함 |
| `facility_location_data_final.csv` | 유효 좌표만 남긴 시설 포인트. 02 단계의 시설 feature 입력 |

시설 유형은 02 단계에서 `storage`, `agency`, `factory` 중심으로 사용합니다.

### 5. 전국 500m land grid 생성

Natural Earth 경계와 주유소/시설 포인트 주변 patch grid를 합쳐 전국 500m 격자틀을 만듭니다. 독도 등 누락 방지를 위해 guard island를 추가합니다.

| 산출물 | 내용 |
|---|---|
| `korea_land_grid_500m.parquet` | 전국 land grid. 02 단계의 기본 격자 |

### 6. 공시지가 격자 생성

공시지가 원자료를 500m 격자에 맞춰 snapshot 컬럼으로 정리합니다.

| 산출물 | 내용 |
|---|---|
| `official_land_price_grid.csv` | `cell_x`, `cell_y`와 공시지가 snapshot 컬럼 |

최신 실행 기준 공시지가 snapshot은 `20160921`, `20171121`, `20181129`, `20190820`, `20200813`, `20211123`, `20220805`, `20231221`, `20240802`입니다.

## 최종 산출물

최신 노트북 출력 기준입니다.

| 파일 | 행 | 열 | 날짜 범위 또는 비고 |
|---|---:|---:|---|
| `national_daily_features.csv` | 6,736 | 21 | 2008-01-01 ~ 2026-06-10 |
| `station_location_history.csv` | 28,171 | 9 | 위치 이력 |
| `station_attribute_history.csv` | 153,625 | 8 | 속성 이력 |
| `station_latest_profile.csv` | 28,828 | 17 | 좌표 결측 포함 |
| `station_points.csv` | 27,830 | 11 | 유효 좌표 주유소 |
| `facility_points.csv` | 797 | 12 | 좌표 결측 포함 |
| `facility_location_data_final.csv` | 740 | 4 | 유효 좌표 시설 |
| `official_land_price_grid.csv` | 396,185 | 12 | 공시지가 격자 |
| `korea_land_grid_500m.parquet` | - | - | 전국 500m land grid |

## 좌표 QC 결과

| 구분 | 전체 행 | lon/lat 결측 | 숫자 좌표 범위 이탈 | 유효 좌표 |
|---|---:|---:|---:|---:|
| 주유소 | 28,828 | 415 | 0 | 28,413 |
| 시설 | 797 | 57 | 0 | 740 |

범위를 벗어난 숫자 좌표는 없습니다. 문제 행은 lon/lat 값 자체가 비어 있어 지도에 찍을 수 없는 행입니다.
주유소의 `valid_lonlat`은 최신 프로필 행 기준이고, `station_points.csv` 행 수는 같은 `station_id` 중복 제거 후 기준입니다.

## 02 단계와의 연결

02 단계가 직접 읽는 01 산출물은 다음입니다.

```text
data-analysis/00_data_collection/outputs/derived_data/korea_land_grid_500m.parquet
data-analysis/00_data_collection/outputs/derived_data/station_location_history.csv
data-analysis/00_data_collection/outputs/derived_data/station_attribute_history.csv
data-analysis/00_data_collection/outputs/derived_data/facility_points.csv
data-analysis/00_data_collection/outputs/derived_data/official_land_price_grid.csv
```

`station_latest_profile.csv`와 `facility_points.csv`는 결측 좌표까지 포함하는 품질 점검용 성격이 있고, 실제 격자 포인트로는 유효 좌표만 사용합니다.

## 확인 필요 항목

최신 실행의 `missing_requirements`는 2건입니다.

| collection_type | dataset | 상태 | 의미 |
|---|---|---|---|
| `large_collection_not_in_git` | `gas_station_prices_by_region` | `missing_coordinates` | 주유소 최신 프로필 415건의 좌표가 비어 있음 |
| `manual_z_pa` | `z_pa_facility` | `missing_coordinates` | 시설 57건의 좌표가 비어 있음 |

주소 자체가 없거나 API가 찾지 못한 행은 자동 보강만으로 해결되지 않을 수 있습니다. 이 경우 수동 보정 파일을 추가하거나 원천 주소를 보완해야 합니다.
