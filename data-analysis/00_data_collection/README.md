# 00. Data Collection Readiness

이 단계는 `ROOT_PATH/data collection/` 아래 수집 산출물이 data-analysis 01~05번에서 필요한 입력 계약을 만족하는지 점검합니다.

중요한 원칙은 하나입니다. 수집 산출물을 `ROOT_PATH/data/`로 복사하지 않습니다. 01~05번은 필요한 경우 `data collection/{dataset}/final/`의 최신 산출물을 직접 읽습니다.

## 기본 루트

```python
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
```

00번 산출물은 아래 manifest입니다.

```text
{DATA_COLLECTION_PATH}/_manifests/data_analysis_input_manifest.csv
```

## 01~05번 필수 입력

| 이름 | 수집 산출물 위치 | 사용 단계 | 주요 컬럼 |
| --- | --- | --- | --- |
| `crude` | `data collection/crude/final/crude_*.csv` | 01 | `기간`, `Dubai`, `Brent`, `WTI` |
| `retail_avg` | `data collection/retail_avg/final/retail_avg_*.csv` | 01 | `구분`, `보통휘발유`, `자동차용경유` |
| `brand_gasoline` | `data collection/brand_price/final/brand_gasoline_*.csv` | 01 | `구분`, `정유사평균`, `SK에너지`, `GS칼텍스`, `HD현대오일뱅크`, `S-OIL`, `알뜰주유소`, `(알뜰-자영)`, `자가상표` |
| `brand_diesel` | `data collection/brand_price/final/brand_diesel_*.csv` | 01 | `구분`, `정유사평균`, `SK에너지`, `GS칼텍스`, `HD현대오일뱅크`, `S-OIL`, `알뜰주유소`, `(알뜰-자영)`, `자가상표` |
| `fx_usdkrw` | `data collection/fx_usdkrw/final/fx_usdkrw_*.csv` | 01 | `변환`, `원자료` |
| `intl_products` | `data collection/intl_products/final/intl_products_*.csv` | 01 | `기간`, `휘발유(95RON)`, `휘발유(92RON)`, `등유`, `경유(0.001%)`, `경유(0.05%)`, `고유황중유(180cst/3.5%)`, `나프타` |
| `intl_product_diesel_0001` | `data collection/intl_products/final/intl_product_diesel(0.001)_*.csv` | 01 | `기간`, `경유(0.001%)` |
| `gasoline_tax_trend` | `data collection/fuel_tax_trend/final/gasoline_tax_trend_*.xls` | 01 | `변동일자`, `개별소비세`, `교통에너지환경세`, `교육세`, `주행세`, `합계`, `판매부과금` |
| `diesel_tax_trend` | `data collection/fuel_tax_trend/final/diesel_tax_trend_*.xls` | 01 | `변동일자`, `개별소비세`, `교통에너지환경세`, `교육세`, `주행세`, `합계`, `판매부과금` |
| `refinery_weekly_supply` | `data collection/refinery_weekly_supply/final/refinery_weekly_supply_prices_by_product_*.csv` | 01 | `구분`, `보통휘발유`, `자동차용경유` |
| `korea_fuel_tax_price_policies` | `data collection/z_pa_policy/final/korea_fuel_tax_price_policies.csv` | 05 | 코드 기준 필요 컬럼: `정책명`, `시작일`, `종료일`, `유종`, `가격`, `카테고리` |

`korea_fuel_tax_price_policies.csv`는 현재 9개 수집 폴더에 없습니다. 수동 수집 대상입니다.

00번은 이 파일이 없을 때 아래 폴더만 만듭니다.

```text
DATA_COLLECTION_PATH/z_pa_policy/raw/
DATA_COLLECTION_PATH/z_pa_policy/final/
DATA_COLLECTION_PATH/z_pa_policy/logs/
```

파일을 `z_pa_policy/final/korea_fuel_tax_price_policies.csv`에 넣은 뒤 00번 또는 05번을 다시 실행하면 됩니다.

## 현재 9개 폴더 중 직접 쓰지 않는 데이터

`official_land_price/final/*.csv`와 `z_pa_facility/final/facility_data.csv`는 data-analysis 01~05번에서는 직접 사용하지 않습니다. 다만 AI Model의 격자/공간 feature 단계에서 필요할 수 있어 00번 manifest에는 참고용으로 포함합니다.
