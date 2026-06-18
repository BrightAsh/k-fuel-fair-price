# 00. Data Collection

`00_data_collection.ipynb`는 data-analysis와 ai-model이 함께 사용하는 원천 데이터를 수집하는 단계입니다.

과거 `analysis-modeling/06_external_data_collection`에 있던 운영 자동수집 로직을 현재 구조에 맞게 `data-analysis/00_data_collection`으로 옮겼습니다. 기존 점검용 노트북은 `00_input_contract_check.ipynb`로 보존했습니다.

## 주요 입력

자동 수집에 필요한 secret은 다음과 같습니다.

| secret | 용도 |
|---|---|
| `BOK_ECOS_API_KEY` | ECOS 원/달러 환율 |
| `VWORLD_API_KEY` | 공시지가 WFS 또는 공간 보조 수집 |

OPINET 전국 단위 데이터는 현재 코드에서 OPINET CSV/HTML 다운로드 URL을 사용합니다. 따라서 현재 자동수집 경로에서는 OPINET key가 필요하지 않습니다.

좌표 보강은 ai-model 01 단계에서 처리하며, 그 단계에서는 `GEOCODER_TOKEN`, `KAKAO_REST_API_KEY`, `NAVER_MAPS_CLIENT_ID`, `NAVER_MAPS_CLIENT_SECRET`, `VWORLD_API_KEY`를 사용할 수 있습니다.

## 수집 대상

| dataset | 산출물 예시 | 다음 단계 |
|---|---|---|
| `crude` | `crude_YYYYMMDD_YYYYMMDD.csv` | 01 전처리 |
| `retail_avg` | `retail_avg_YYYYMMDD_YYYYMMDD.csv` | 01 전처리 |
| `brand_price` | `brand_gasoline_*.csv`, `brand_diesel_*.csv` | 01 전처리 |
| `fx_usdkrw` | `fx_usdkrw_YYYYMMDD_YYYYMMDD.csv` | 01 전처리 |
| `intl_products` | `intl_products_*.csv`, `intl_product_diesel(0.001)_*.csv` | 01 전처리 |
| `fuel_tax_trend` | `gasoline_tax_trend_*.xls`, `diesel_tax_trend_*.xls` | 01 전처리 |
| `refinery_weekly_supply` | `refinery_weekly_supply_prices_by_product_*.csv` | 01 전처리 |
| `gas_station_prices_by_region` | `{region}/gasoline.csv`, `{region}/diesel.csv` | ai-model 02 |

주유소 지역별 가격 다운로드는 Selenium/브라우저 다운로드 방식이라 GitHub Actions 기본 실행에서는 끕니다. 수동으로 돌릴 때 `KFF_RUN_STATION_DOWNLOAD=true`를 설정하면 실행할 수 있습니다.

## 산출물 위치

현재 레포 기준 최종 사용 파일은 아래에 둡니다.

```text
data-analysis/00_data_collection/outputs/{dataset}/
```

복구된 수집 노트북은 과거 호환을 위해 `{dataset}/raw`, `{dataset}/final` snapshot도 만들 수 있습니다. 마지막 정리 셀에서 최신 final 파일을 01 전처리가 읽는 `outputs/{dataset}/` 바로 아래로 복사합니다.

## 점검 노트북

`00_input_contract_check.ipynb`는 실제 수집 없이 필요한 산출물 존재 여부만 확인합니다. 수집이 끝난 뒤 입력 계약 확인용으로 사용합니다.
