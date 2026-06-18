# Incoming Collection Files

이 폴더는 자동 수집기가 아직 연결되지 않은 데이터셋을 강제로 보강할 때 사용합니다.

추가 수집 파일을 아래 구조로 넣고 `Daily Data Pipeline` 워크플로를 수동 실행하면, CSV 파일은 날짜 컬럼 기준으로 기존 `data-analysis/00_data_collection/outputs/{dataset}/` 파일에 병합됩니다.

```text
automation/incoming/{dataset}/{same_filename_pattern}.csv
```

예시:

```text
automation/incoming/crude/crude_20260611_20260617.csv
automation/incoming/retail_avg/retail_avg_20260611_20260617.csv
automation/incoming/brand_price/brand_gasoline_20260611_20260617.csv
automation/incoming/brand_price/brand_diesel_20260611_20260617.csv
automation/incoming/fx_usdkrw/fx_usdkrw_20260611_20260617.csv
automation/incoming/intl_products/intl_products_20260611_20260617.csv
automation/incoming/intl_products/intl_product_diesel(0.001)_20260611_20260617.csv
automation/incoming/refinery_weekly_supply/refinery_weekly_supply_prices_by_product_20260611_20260617.csv
automation/incoming/z_pa_policy/korea_fuel_tax_price_policies.csv
```

`.xls` 파일은 자동 병합하지 않고 리포트에 skipped로 남깁니다. 해당 파일은 기존 outputs 파일을 교체하거나, 나중에 전용 병합 로직을 추가해야 합니다.
