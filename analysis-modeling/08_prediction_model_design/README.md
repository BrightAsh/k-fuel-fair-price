# 08 Prediction Model Design

이 단계는 `07_spatial_grid_build`에서 생성한 격자 패널을 진단하고, 격자 단위 적정가격 예측 모델을 생성하는 단계입니다. 원본 Colab의 `5단계: 예측 모델 생성` 구간을 분리해 `08_prediction_model_design.ipynb`로 정리했습니다.

중요한 기준은 원본 로직 보존입니다. 이 노트북은 단계 분리와 Colab 단독 실행용 setup 셀만 추가했고, 원본 처리 셀 내부 로직은 수정하지 않았습니다. 코드상 문제가 발견되더라도 이 레포에서는 문서에만 기록하고, 실제 수정은 Colab 원본 작업 환경에서 직접 수행하는 방식으로 둡니다.

웹 자동화에서는 이 노트북을 매일 재학습하는 것이 아닙니다. 이 단계는 모델 제작 및 산출물 생성용이고, 실제 웹 페이지 자동화에서는 여기서 생성된 model bundle과 추론 결과 파일만 가져와 사용합니다.

## Notebook

- `08_prediction_model_design.ipynb`

노트북은 Colab에서 단독 실행할 수 있도록 Google Drive mount와 패키지 설치 셀을 포함합니다. 다른 사용자는 경로 설정 셀의 `ROOT_PATH`만 본인 경로로 수정하면 됩니다.

## Inputs

원본 코드 기준 필수 입력은 다음과 같습니다.

- `GRID_DIR/data_1/grid_station_daily_panel_500m_plus_facility_plus_geo.parquet`
- `preprocessed_data/분석용_일별_통합데이터.csv`
- `적정가격대선정_v2/gasoline_production_predictions_full_calendar.csv`
- `적정가격대선정_v2/diesel_production_predictions_full_calendar.csv`
- `정책적용_v2/휘발유/일별_정책적용_데이터_휘발유.csv`
- `정책적용_v2/경유/일별_정책적용_데이터_경유.csv`
- `정책적용_v2/정유사_최고가격제_점검/정유사_최고가격제_점검_휘발유.csv`
- `정책적용_v2/정유사_최고가격제_점검/정유사_최고가격제_점검_경유.csv`

원본 진단 셀은 공시지가가 결합된 `grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet`를 권고 경로로 출력합니다. 하지만 실제 모델 설정 셀은 원본 그대로 `grid_station_daily_panel_500m_plus_facility_plus_geo.parquet`를 사용합니다. 이 차이는 코드 수정 없이 문서에만 남깁니다.

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

아래는 원본 출력 셀에서 확인된 참고값입니다.

### Final Panel Diagnostic

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

Target 진단에서 원본 패널에는 가격 극단값이 확인되었습니다.

| 유종 | target non-null rows | target unique grids | 평균 | 최소 | p50 | p95 | 최대 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 휘발유 | 63,486,388 | 12,471 | 1662.92 | 3.0 | 1645.15 | 1997.28 | 3096.0 |
| 경유 | 63,757,542 | 12,486 | 1500.61 | 1.0 | 1481.30 | 1873.07 | 6190.0 |

이 README에는 관찰 사실만 기록합니다. 가격 필터나 원천 CSV 보정은 Colab 원본 작업 환경에서 직접 판단해 수정해야 합니다.

### Original Model Run Reference

원본 출력 기준 모델 검증 결과의 최상위 후보는 두 유종 모두 `lgbm_center_candidate_3`였습니다.

| 유종 | 학습 row | 학습 grid | 학습 기간 | best model | mean WMAE | mean WRMSE |
|---|---:|---:|---|---|---:|---:|
| 휘발유 | 1,624,388 | 477 | 2009-01-01 ~ 2021-11-11 | `lgbm_center_candidate_3` | 21.0622 | 29.1216 |
| 경유 | 1,630,720 | 476 | 2009-01-01 ~ 2021-11-11 | `lgbm_center_candidate_3` | 21.4798 | 30.2464 |

원본 실행의 final feature 수는 36개였습니다.

## Notes For Review

원본 출력에는 경유 시각화 셀에서 `diesel_grid_result is not defined` 오류가 남아 있었습니다. 셀 실행 순서 문제일 가능성이 있으므로, Colab에서 `diesel_grid_result = run_grid_fair_model_one_fuel("diesel")` 셀이 정상 실행된 뒤 시각화 셀을 실행하면 됩니다. 이 레포의 노트북 코드는 원본 로직을 보존하기 위해 해당 셀을 수정하지 않았습니다.

## Outputs Folder

이 폴더의 `outputs/`에는 실행 결과 파일만 넣습니다. README나 설명 파일은 넣지 않습니다.

결과를 올릴 수 있다면 코드 기준으로 다음 파일이 대상입니다.

- `panel_diagnostic_report_for_chatgpt.txt`
- `gasoline/gasoline_validation_scores_full_features.csv`
- `gasoline/gasoline_feature_importance.csv`
- `gasoline/gasoline_selected_features.json`
- `gasoline/gasoline_final_native_importance.csv`
- `gasoline/gasoline_oof_residual_sample.parquet`
- `gasoline/model/gasoline_grid_fair_model_bundle.joblib`
- `gasoline/model/gasoline_model_metadata.json`
- `gasoline/gasoline_grid_fair_predictions_2025_2026.parquet`
- `gasoline/gasoline_grid_fair_daily_summary_2025_2026.csv`
- `gasoline/plots/*.png`
- `gasoline/plots/maps/*.png`
- `diesel/diesel_validation_scores_full_features.csv`
- `diesel/diesel_feature_importance.csv`
- `diesel/diesel_selected_features.json`
- `diesel/diesel_final_native_importance.csv`
- `diesel/diesel_oof_residual_sample.parquet`
- `diesel/model/diesel_grid_fair_model_bundle.joblib`
- `diesel/model/diesel_model_metadata.json`
- `diesel/diesel_grid_fair_predictions_2025_2026.parquet`
- `diesel/diesel_grid_fair_daily_summary_2025_2026.csv`
- `diesel/plots/*.png`
- `diesel/plots/maps/*.png`
