# AI Model 04 예측 모델 설계 및 학습

이 단계는 기존 8번 파일입니다. AI Model 03에서 생성한 격자 패널을 진단하고, 격자 단위 적정가격 예측 모델을 학습합니다.

웹 자동화에서는 이 노트북을 매일 재학습하는 것이 아닙니다. 이 단계는 모델 제작 및 산출물 생성용이고, 실제 웹서비스 자동화에서는 여기서 생성된 model bundle과 추론 결과 파일을 가져와 사용합니다.

## Notebook

- `04_prediction_model_design.ipynb`

## Inputs

주요 입력은 AI Model 03 산출물과 Data Analysis 1~5번 산출물입니다.

```text
ROOT_PATH/그리드/data_1/grid_station_daily_panel_500m_plus_facility_plus_geo.parquet
ROOT_PATH/그리드/data_1/grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet
PROCESSED_PATH/분석용_일별_통합데이터.csv
ROOT_PATH/적정가격대선정_v2/gasoline_production_predictions_full_calendar.csv
ROOT_PATH/적정가격대선정_v2/diesel_production_predictions_full_calendar.csv
ROOT_PATH/정책적용_v2/휘발유/일별_정책적용_데이터_휘발유.csv
ROOT_PATH/정책적용_v2/경유/일별_정책적용_데이터_경유.csv
ROOT_PATH/정책적용_v2/정유사_최고가격제_점검/정유사_최고가격제_점검_휘발유.csv
ROOT_PATH/정책적용_v2/정유사_최고가격제_점검/정유사_최고가격제_점검_경유.csv
```

공시지가 feature를 모델에 쓸지 여부는 04번 정리 시 명시적으로 결정해야 합니다.

## Outputs

```text
panel_diagnostic_report_for_chatgpt.txt
gasoline/model/gasoline_grid_fair_model_bundle.joblib
gasoline/gasoline_grid_fair_predictions_2025_2026.parquet
gasoline/gasoline_grid_fair_daily_summary_2025_2026.csv
diesel/model/diesel_grid_fair_model_bundle.joblib
diesel/diesel_grid_fair_predictions_2025_2026.parquet
diesel/diesel_grid_fair_daily_summary_2025_2026.csv
```
