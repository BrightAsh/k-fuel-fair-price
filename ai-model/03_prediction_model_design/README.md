# AI Model 03 예측 모델 설계 및 학습

이 단계는 기존 8번 파일입니다. AI Model 02에서 생성한 격자 패널을 진단하고, 격자 단위 적정가격 예측 모델을 학습합니다.

웹 자동화에서는 이 노트북을 매일 재학습하는 것이 아닙니다. 이 단계는 모델 제작 및 산출물 생성용이고, 실제 웹서비스 자동화에서는 여기서 생성된 model bundle과 추론 결과 파일을 가져와 사용합니다.

## Notebook

- `03_prediction_model_design.ipynb`

## Inputs

주요 입력은 AI Model 02 산출물과 Data Analysis 1~5번 산출물입니다.

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

원문 진단 셀은 공시지가가 결합된 `grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet`를 권고 경로로 출력했습니다. 실제 모델 설정 셀은 원문 그대로 `grid_station_daily_panel_500m_plus_facility_plus_geo.parquet`를 사용하는 부분이 있으므로, 공시지가 feature를 모델에 쓸지는 03번 정리 시 명시적으로 결정해야 합니다.

## Processing Flow

| 순서 | 처리 | 주요 내용 | 산출물 |
|---:|---|---|---|
| 0 | 최종 패널 진단 | parquet metadata, schema, 날짜/grid coverage, 결측률, target 분포, feature 후보 점검 | `panel_diagnostic_report_for_chatgpt.txt` |
| 1 | 설정 | 경로, 유종별 컬럼, 정책 파일, 학습 제외 정책기간, 가격 cap 후처리 옵션 정의 | 설정 변수 |
| 2 | 공통 함수 정의 | 날짜 처리, 정책 파일 로드, national anchor 생성, feature 후보 선택 | 함수 |
| 3 | 학습 샘플 생성 | grid panel과 national fair/actual 데이터를 병합하고 정책기간 제외, grid hash sampling 적용 | 학습 DataFrame |
| 4 | 모델 검증 | time fold 기반 LightGBM 후보와 baseline 비교 | `{fuel}_validation_scores_full_features.csv` |
| 5 | feature importance | native importance와 permutation importance 계산 | `{fuel}_feature_importance.csv` |
| 6 | 최종 모델 학습 | center model과 local residual quantile band model 학습 | `{fuel}_grid_fair_model_bundle.joblib` |
| 7 | 예측 저장 | 2025~2026 격자 단위 적정가격, 하단/상단 band, actual 대비 deviation 저장 | `{fuel}_grid_fair_predictions_2025_2026.parquet`, `{fuel}_grid_fair_daily_summary_2025_2026.csv` |
| 8 | 시각화 | 일별 band 그래프와 지도 이미지 저장 | `plots/*.png`, `plots/maps/*.png` |

## Confirmed Output From Original Cells

원문 출력 셀에서 확인된 참고값입니다.

| 항목 | 값 |
|---|---:|
| 최종 패널 파일 크기 | 1.7244 GB |
| parquet metadata row 수 | 63,863,732 |
| parquet metadata column 수 | 41 |
| row group 수 | 518 |
| 날짜 범위 | 2008-04-15 ~ 2026-04-07 |
| unique date 수 | 6,567 |
| unique grid 수 | 12,497 |
| duplicated date-grid key | 0 |

공시지가 결합 상태는 다음과 같습니다.

| 항목 | 값 |
|---|---:|
| `official_land_price` non-null rows | 33,759,224 |
| `official_land_price` null rows | 30,104,508 |
| 공시지가 평균 | 473,512.56 |
| 공시지가 중앙값 | 129,819.19 |
| 공시지가 source date 종류 | 9 |
| source date 범위 | 2016-09-21 ~ 2024-08-02 |

원문 실행의 final feature 수는 36개였고, 모델 검증 결과의 최상위 후보는 두 유종 모두 `lgbm_center_candidate_3`였습니다.

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
