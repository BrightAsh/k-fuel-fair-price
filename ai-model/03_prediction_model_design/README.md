# 03. Prediction Model Design

격자 패널과 data-analysis 산출물을 결합해 격자 단위 적정가격 예측 모델을 설계하는 단계입니다.

## 실행 파일

- `04_prediction_model_design.ipynb`

## 주요 입력

```text
ROOT_PATH/그리드data_1/grid_station_daily_panel_500m_plus_facility_plus_geo.parquet
ROOT_PATH/그리드data_1/grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet
PROCESSED_PATH/분석용_일별_통합데이터.csv
ROOT_PATH/적정가격대선정_v2/gasoline_production_predictions_full_calendar.csv
ROOT_PATH/적정가격대선정_v2/diesel_production_predictions_full_calendar.csv
ROOT_PATH/정책적용_v2/휘발유/일별_정책적용_데이터_휘발유.csv
ROOT_PATH/정책적용_v2/경유/일별_정책적용_데이터_경유.csv
ROOT_PATH/정책적용_v2/정유사_최고가격제_점검/정유사_최고가격제_점검_휘발유.csv
ROOT_PATH/정책적용_v2/정유사_최고가격제_점검/정유사_최고가격제_점검_경유.csv
```

## 주요 산출물

```text
panel_diagnostic_report_for_chatgpt.txt
gasoline/model/gasoline_grid_fair_model_bundle.joblib
gasoline/gasoline_grid_fair_predictions_2025_2026.parquet
gasoline/gasoline_grid_fair_daily_summary_2025_2026.csv
diesel/model/diesel_grid_fair_model_bundle.joblib
diesel/diesel_grid_fair_predictions_2025_2026.parquet
diesel/diesel_grid_fair_daily_summary_2025_2026.csv
```

공시지가 feature를 모델 입력으로 사용할지 여부는 이 단계에서 명시적으로 결정합니다.
