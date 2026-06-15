# 01. 데이터 전처리

이 단계는 국제 원유/석유제품 가격, 환율, 국내 평균 소매가, 브랜드별 가격, 유류세 추이, 정유사 주간 공급가격을 하나의 일별 분석용 통합 데이터로 만듭니다.

현재 구조에서는 03 시차 분석, 04 적정 가격 분석, 05 정책 적용이 이 통합 데이터를 공통 입력으로 사용하므로 01번 전처리 단계가 필요합니다.

## 기본 루트

```python
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
```

01번은 `DATA_COLLECTION_PATH/{dataset}/final/` 아래 최신 수집 산출물을 직접 읽습니다. `ROOT_PATH/data/` 표준 복사본은 만들거나 읽지 않습니다.

## 입력 데이터

| 입력 | 실제 읽는 위치 | 주요 컬럼 |
| --- | --- | --- |
| 원유 가격 | `data collection/crude/final/crude_*.csv` | `기간`, `Dubai`, `Brent`, `WTI` |
| 국내 평균 소매가 | `data collection/retail_avg/final/retail_avg_*.csv` | `구분`, `보통휘발유`, `자동차용경유` |
| 휘발유 브랜드 가격 | `data collection/brand_price/final/brand_gasoline_*.csv` | `구분`, `정유사평균`, `SK에너지`, `GS칼텍스`, `HD현대오일뱅크`, `S-OIL`, `알뜰주유소`, `(알뜰-자영)`, `자가상표` |
| 경유 브랜드 가격 | `data collection/brand_price/final/brand_diesel_*.csv` | `구분`, `정유사평균`, `SK에너지`, `GS칼텍스`, `HD현대오일뱅크`, `S-OIL`, `알뜰주유소`, `(알뜰-자영)`, `자가상표` |
| 원/달러 환율 | `data collection/fx_usdkrw/final/fx_usdkrw_*.csv` | `변환`, `원자료` |
| 국제 석유제품 가격 | `data collection/intl_products/final/intl_products_*.csv` | `기간`, `휘발유(95RON)`, `휘발유(92RON)`, `등유`, `경유(0.001%)`, `경유(0.05%)`, `고유황중유(180cst/3.5%)`, `나프타` |
| 초저유황 경유 보완 | `data collection/intl_products/final/intl_product_diesel(0.001)_*.csv` | `기간`, `경유(0.001%)` |
| 휘발유 유류세 추이 | `data collection/fuel_tax_trend/final/gasoline_tax_trend_*.xls` | `변동일자`, `개별소비세`, `교통에너지환경세`, `교육세`, `주행세`, `합계`, `판매부과금` |
| 경유 유류세 추이 | `data collection/fuel_tax_trend/final/diesel_tax_trend_*.xls` | `변동일자`, `개별소비세`, `교통에너지환경세`, `교육세`, `주행세`, `합계`, `판매부과금` |
| 정유사 주간 공급가격 | `data collection/refinery_weekly_supply/final/refinery_weekly_supply_prices_by_product_*.csv` | `구분`, `보통휘발유`, `자동차용경유` |

## 처리 내용

1. 날짜 컬럼을 `date`로 통일합니다.
2. 국제 원유/제품 가격과 환율을 일별 calendar에 맞추고 비영업일 구간은 forward fill합니다.
3. 국제 가격의 `USD/bbl` 값을 `KRW/L`로 환산합니다.
4. 국내 평균가, 브랜드가, 유류세, 정유사 주간 공급가격을 일별 기준으로 결합합니다.
5. 최종 통합 데이터를 `PROCESSED_PATH`에 저장합니다.

환산식은 아래와 같습니다.

```text
KRW/L = USD/bbl price * USDKRW / 158.987294928
```

## 산출물

```text
{PROCESSED_PATH}/분석용_일별_통합데이터.csv
```

인코딩은 `utf-8-sig`입니다.
