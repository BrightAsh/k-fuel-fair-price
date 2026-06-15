# Data Analysis

이 폴더는 수집 산출물을 이용해 전국 단위 유가 분석을 수행하는 파이프라인입니다.

## 단계

```text
00_data_collection/         # 수집 산출물 점검, 수동 수집 폴더 생성, manifest 저장
01_data_preprocessing/      # 수집 산출물 -> 일별 통합 데이터 생성
02_benchmark_selection/     # 국제 가격 benchmark 선택
03_lag_analysis/            # 국내 가격 반영 시차 분석
04_fair_price_model/        # 정책 미반영 적정 가격 분석
05_policy_application/      # 정책 효과 적용 및 최고가격제 점검
```

## 경로 원칙

원천 입력은 `ROOT_PATH/data collection/` 아래 수집 산출물만 사용합니다. `ROOT_PATH/data/`로 표준 복사본을 만들거나 fallback으로 읽지 않습니다.

```python
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
```

수동 수집 데이터는 폴더명 앞에 `z_pa_`를 붙입니다. 현재 data-analysis에서 추가로 필요한 수동 수집 파일은 정책 이력입니다.

```text
DATA_COLLECTION_PATH/z_pa_policy/final/korea_fuel_tax_price_policies.csv
```

00번은 이 파일이 없으면 아래 폴더만 생성합니다.

```text
DATA_COLLECTION_PATH/z_pa_policy/raw/
DATA_COLLECTION_PATH/z_pa_policy/final/
DATA_COLLECTION_PATH/z_pa_policy/logs/
```

## 현재 필요한 데이터

01번 전처리 필수 입력은 아래 10개 수집 산출물입니다.

- `crude/final/crude_*.csv`
- `retail_avg/final/retail_avg_*.csv`
- `brand_price/final/brand_gasoline_*.csv`
- `brand_price/final/brand_diesel_*.csv`
- `fx_usdkrw/final/fx_usdkrw_*.csv`
- `intl_products/final/intl_products_*.csv`
- `intl_products/final/intl_product_diesel(0.001)_*.csv`
- `fuel_tax_trend/final/gasoline_tax_trend_*.xls`
- `fuel_tax_trend/final/diesel_tax_trend_*.xls`
- `refinery_weekly_supply/final/refinery_weekly_supply_prices_by_product_*.csv`

05번 정책 적용 필수 입력 중 정책 이력 파일은 현재 수동 수집 대상입니다.

## 쓰지 않는 9개 폴더 데이터

현재 9개 수집 폴더 중 `official_land_price`와 `z_pa_facility`는 data-analysis 01~05번에서 직접 사용하지 않습니다. 이 둘은 AI Model의 격자/공간 feature 단계에서 사용하는 쪽으로 보는 것이 맞습니다.
