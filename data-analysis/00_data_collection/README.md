# 00. Data Collection Readiness

## 목적

`00_data_collection.ipynb`는 원천 데이터를 직접 수집하거나 변환하는 단계가 아니라, 뒤 단계가 사용할 원천 데이터 파일이 정해진 위치와 이름 규칙에 맞게 준비되어 있는지 점검하는 준비 단계입니다. 이 노트북은 Google Drive의 `data collection/` 아래에 있는 수집 결과를 검사하고, 수집 현황을 manifest로 남긴 뒤, 정책 수기 데이터 폴더를 보장합니다.

노트북 구조는 markdown 1개, code 3개, 총 167줄입니다. 저장된 출력 셀은 없으므로, 레포에는 별도 CSV 산출물이 없습니다.

## 경로 설정

노트북은 Colab 기준으로 아래 경로를 사용합니다.

| 변수 | 의미 |
|---|---|
| `ROOT_PATH` | 프로젝트 루트. 예: `/content/drive/MyDrive/.../산업부/` |
| `DATA_COLLECTION_PATH` | 원천 수집 데이터 위치. `ROOT_PATH + "data collection/"` |
| `PROCESSED_PATH` | 01 전처리 산출물 위치. `ROOT_PATH + "preprocessed_data/"` |
| `MANIFEST_DIR` | 원천 데이터 점검 manifest 저장 위치. `data collection/_manifests/` |

`PROCESSED_PATH`와 `MANIFEST_DIR`는 없으면 생성합니다.

## 점검 로직

핵심 함수는 다음 세 가지입니다.

| 함수 | 역할 |
|---|---|
| `latest_under(base, pattern)` | 지정 폴더에서 패턴에 맞는 최신 파일을 찾습니다. |
| `first_existing(paths)` | 후보 경로 중 실제 존재하는 첫 파일을 반환합니다. |
| `ensure_manual_dataset_folders(dataset_name)` | 수기 입력 데이터셋의 `raw`, `final`, `logs` 폴더를 보장합니다. |

원천 파일 점검은 `SPECS` 리스트를 기준으로 수행합니다. 각 spec은 `name`, `dataset`, `required_for`, `required`, `src`, `expected` 등을 가지고, 발견 여부와 예상 경로를 manifest에 기록합니다.

## 필수 입력 데이터셋

01 전처리에 반드시 필요한 입력은 다음 10개입니다.

| name | dataset | 파일 패턴 또는 위치 | 다음 단계 |
|---|---|---|---|
| `crude` | `crude` | `crude/final/crude_*.csv` | 01 |
| `retail_avg` | `retail_avg` | `retail_avg/final/retail_avg_*.csv` | 01 |
| `brand_gasoline` | `brand_price` | `brand_price/final/brand_gasoline_*.csv` | 01 |
| `brand_diesel` | `brand_price` | `brand_price/final/brand_diesel_*.csv` | 01 |
| `fx_usdkrw` | `fx_usdkrw` | `fx_usdkrw/final/fx_usdkrw_*.csv` | 01 |
| `intl_products` | `intl_products` | `intl_products/final/intl_products_*.csv` | 01 |
| `intl_product_diesel_0001` | `intl_products` | `intl_products/final/intl_product_diesel(0.001)_*.csv` | 01 |
| `gasoline_tax_trend` | `fuel_tax_trend` | `fuel_tax_trend/final/gasoline_tax_trend_*.xls` | 01 |
| `diesel_tax_trend` | `fuel_tax_trend` | `fuel_tax_trend/final/diesel_tax_trend_*.xls` | 01 |
| `refinery_weekly_supply` | `refinery_weekly_supply` | `refinery_weekly_supply/final/refinery_weekly_supply_prices_by_product_*.csv` | 01 |

05 정책 적용에 필요한 수기 정책 파일도 필수로 점검합니다.

| name | dataset | 고정 위치 | 다음 단계 |
|---|---|---|---|
| `korea_fuel_tax_price_policies` | `z_pa_policy` | `z_pa_policy/final/korea_fuel_tax_price_policies.csv` | 05 |

다음 두 데이터셋은 manifest에는 남기지만, 현재 01~05 분석 파이프라인에는 사용하지 않는 선택 입력입니다.

| name | dataset | 비고 |
|---|---|---|
| `official_land_price` | `official_land_price` | 현재 data-analysis 01~05에서는 미사용 |
| `facility_data` | `z_pa_facility` | 현재 data-analysis 01~05에서는 미사용 |

## 산출물

레포 안에는 00 단계의 CSV 산출물이 없습니다. Colab 실행 시 Drive에는 아래 파일이 생성됩니다.

| 산출물 | 설명 |
|---|---|
| `data collection/_manifests/data_analysis_input_manifest.csv` | 원천 파일별 발견 여부, 실제 경로, 예상 경로, 필수 여부를 기록한 점검표 |
| `data collection/z_pa_policy/raw/` | 수기 정책 원자료 보관 폴더 |
| `data collection/z_pa_policy/final/` | `korea_fuel_tax_price_policies.csv` 저장 위치 |
| `data collection/z_pa_policy/logs/` | 수기 정책 데이터 처리 로그용 폴더 |

## 다음 단계와의 연결

00 단계가 성공하면 01 전처리는 원유, 국제제품가, 환율, 국내 주유소 평균가, 브랜드별 가격, 유류세, 정유사 주간 공급가격을 모두 읽을 수 있습니다. 또한 05 정책 적용은 `korea_fuel_tax_price_policies.csv`를 읽어 유류세 인하율과 정유사 최고가격제 정책을 수치로 반영할 수 있습니다.

이 단계의 핵심 산출물은 분석 데이터 자체가 아니라 "원천 데이터가 준비되어 있다"는 실행 가능성 확인입니다.
