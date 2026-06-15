# AI Model 01 데이터 수집 및 1차 전처리

이 단계는 기존 6번 파일입니다. 웹사이트 운영을 위한 자동 수집/수동 보강/1차 전처리 산출물을 `ROOT_PATH/data collection/` 아래에 정리합니다.

격자화와 영향력 feature 생성은 이 단계에서 하지 않습니다. 주유소 개수, 주유소 주변 영향력, 시설 영향력은 AI Model 02에서 생성합니다.

## Common Path

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
DATA_PATH = ROOT_PATH + "data/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
```

## Main Outputs

자동 수집/1차 전처리 결과는 데이터별로 `raw/`, `final/`, `logs/`를 분리합니다.

```text
DATA_COLLECTION_PATH/fx_usdkrw/final/fx_usdkrw_YYYYMMDD_YYYYMMDD.csv
DATA_COLLECTION_PATH/crude/final/crude_YYYYMMDD_YYYYMMDD.csv
DATA_COLLECTION_PATH/intl_products/final/intl_products_YYYYMMDD_YYYYMMDD.csv
DATA_COLLECTION_PATH/retail_avg/final/retail_avg_YYYYMMDD_YYYYMMDD.csv
DATA_COLLECTION_PATH/brand_price/final/brand_gasoline_YYYYMMDD_YYYYMMDD.csv
DATA_COLLECTION_PATH/brand_price/final/brand_diesel_YYYYMMDD_YYYYMMDD.csv
DATA_COLLECTION_PATH/fuel_tax_trend/final/gasoline_tax_trend_YYYYMMDD_YYYYMMDD.xls
DATA_COLLECTION_PATH/fuel_tax_trend/final/diesel_tax_trend_YYYYMMDD_YYYYMMDD.xls
DATA_COLLECTION_PATH/refinery_weekly_supply/final/refinery_weekly_supply_prices_by_product_YYYYMMDD_YYYYMMDD.csv
```

주유소/시설/공시지가는 AI Model 02 입력과 직접 연결됩니다.

```text
DATA_COLLECTION_PATH/gas_station_prices_by_region/raw/{region}/
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/gasoline.csv
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/diesel.csv
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/metadata.json
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/metadata__latlon.json

DATA_COLLECTION_PATH/facility/final/facility_data.csv
DATA_COLLECTION_PATH/facility/final/facility_location_data_final.csv

DATA_COLLECTION_PATH/official_land_price/final/공시지가.csv
```

## Facility Data

첨부된 `facility_data.csv`는 확인 결과 797행, 컬럼 `상표`, `구분`, `이름`, `주소` 형태입니다. 이는 시설 목록 파일입니다.

AI Model 02에서 시설 count/influence를 만들려면 좌표가 필요하므로, 최종적으로는 아래 형태의 좌표 포함 파일이 있어야 합니다.

```text
상표, 대상, 경도, 위도
```

원문 코드에서는 시설 목록을 만든 뒤 Google Maps 기반 좌표 보강을 통해 `1 facility_location_data_final.csv`를 만들고, AI Model 02에서 그 파일을 읽어 시설 feature를 생성했습니다. 새 구조에서는 같은 역할의 파일을 `DATA_COLLECTION_PATH/facility/final/facility_location_data_final.csv`로 관리합니다.

## Responsibility Boundary

| 항목 | AI Model 01에서 처리 | AI Model 02에서 처리 |
|---|---|---|
| 시설 목록 수집 | O | - |
| 시설 좌표 보강 | O | - |
| 시설 개수 feature | - | O |
| 시설 거리 감쇠 영향력 | - | O |
| 주유소 raw 수집 | O | - |
| 지역별 주유소 가격/메타데이터 정리 | O | - |
| 주유소 개수 feature | - | O |
| 주유소 주변 영향력 | - | O |
| 공시지가 파일 검증/결합 | - | O |

## Removed From This Stage

공시지가 격자 결합, 운영 자동수집 검토 메모, 산출물 계약 점검 셀은 01번 노트북 본문에서 제외하거나 별도 문서로 관리합니다. 공시지가 자체는 수동 파일로 준비하되, 형식 검증과 격자 패널 결합은 AI Model 02에서 수행합니다.
