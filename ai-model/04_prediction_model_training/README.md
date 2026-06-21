# 04. Prediction Model Training

AI 04는 AI 03의 격자별 적정가격 target dataset으로 예측 모델을 학습한 단계입니다. 현재 코드는 첫 번째 LSTM 기반 모델 실험을 완료했으며, 결과적으로 이 구조는 최종 운영 모델로 쓰기 어렵다는 결론을 냈습니다.

## 예측 문제 정의

모델은 target date 당일 전국 평균 가격을 입력으로 보지 않고, 전날까지의 격자 시계열과 격자 context로 오늘의 격자별 적정가격을 예측하도록 설계했습니다.

```text
각 격자 실제 가격/전국 실제 가격/spread 변화량(t-1 ~ t-28)
  + 전날 상태값(t-1)
  + 고정/저빈도 격자 context
  -> 오늘 격자별 적정가격 target
```

학습 target은 level 자체가 아니라 전일 실제 격자 가격 대비 오늘 적정가격 변화량입니다.

```text
fair_price_delta_target
  = grid_fair_price_target(t) - actual_grid_price(t-1)

pred_grid_fair_price(t)
  = actual_grid_price(t-1) + pred_fair_price_delta
```

평가 지표 `price_weighted_mae`는 `pred_grid_fair_price`와 `grid_fair_price_target` 사이의 station-count weighted MAE입니다.

## 코드 구성

| 파일 | 역할 |
|---|---|
| `04_prediction_model_training.py` | 학습 frame 생성, cache, train/validation/test, 모델 저장 |

## 입력 데이터

기본 입력은 AI 03의 `grid_target.parquet`입니다.

| 입력 | 내용 |
|---|---|
| `grid_target.parquet` | 원본 grid feature + 격자별 적정가격 target |
| 정책 제외 기간 목록 | train/validation에서 target date와 29일 history 정책기간 제외 |
| 유종별 설정 | 휘발유/경유 실제 가격 컬럼, station count 컬럼, target 컬럼 |

## Feature 구조

### LSTM sequence branch

28일 길이의 일별 변화량만 LSTM에 넣습니다.

| channel | 내용 |
|---|---|
| `spread_delta` | 격자 실제 spread의 일별 변화 |
| `actual_price_delta` | 격자 실제 가격의 일별 변화 |
| `national_price_delta` | grid 기준 전국 실제 가중평균 가격의 일별 변화 |

### latest branch

target date 직전일 상태값입니다.

| feature | 내용 |
|---|---|
| `actual_price_lag_1d` | 전일 격자 실제 가격 |
| `national_price_lag_1d` | 전일 전국 실제 가중평균 가격 |
| `spread_lag_1d` | 전일 격자 실제 spread |
| `station_weight_lag_1d` | 전일 유종별 station count |

### static/slow branch

시계열로 매일 변하지 않는 값은 LSTM에 넣지 않고 별도 branch로 처리합니다.

| 묶음 | feature |
|---|---|
| 위치 | `cell_x`, `cell_y`, `center_lon`, `center_lat` |
| 주유소 구성 | 유종별 station count, 브랜드 count, 셀프 여부 count |
| 영향권 | `station_neighbor_influence`, `storage_influence`, `agency_influence`, `factory_influence` |
| 시설 | 시설 유형별 count |
| 지리 | `is_sea`, `is_island`, `land_component_id` |
| 공시지가 | `official_land_price`, `official_price_age_days`, `official_price_source_year` |

## 데이터 분리

| 구분 | 기준 |
|---|---|
| train/validation 후보 | `target_date < 2026-01-01` |
| test | `2026-01-01 <= target_date <= 2026-12-31` |
| split 방식 | eligible day를 row 수 기준 약 7:3으로 시간 순서 분리 |
| gap | train 종료일과 validation 시작일 사이 7일 |
| 정책 기간 처리 | train/validation/final train에서 target date가 정책 기간이면 제외 |
| history 정책 처리 | train/validation/final train에서 29일 입력 history 안에 정책 기간이 있으면 제외 |

test에서는 정책 기간을 제외하지 않았습니다. 실제 서비스 구간의 적정가격을 평가하기 위한 목적입니다.

## 샘플링과 cache

전체 후보 행이 너무 크기 때문에 train/validation/final train은 고정 hash sampling을 사용했습니다.

| 설정 | 값 |
|---|---:|
| train sample | 200/1000 |
| validation sample | 200/1000 |
| max train rows | 6,000,000 |
| max validation rows | 2,500,000 |
| max final train rows | 8,000,000 |

실제 로드 결과:

| 유종 | train eligible | train loaded | validation eligible | validation loaded |
|---|---:|---:|---:|---:|
| 휘발유 | 26,762,631 | 5,351,880 | 11,396,271 | 2,279,365 |
| 경유 | 18,158,724 | 3,633,409 | 7,703,397 | 1,539,406 |

## 모델 구조

| 항목 | 값 |
|---|---|
| model name | `hybrid_grid_fair_price_delta_lstm` |
| sequence length | 28 days |
| sequence channels | 3 |
| LSTM hidden size | 128 |
| LSTM layers | 2 |
| dropout | 0.20 |
| latest/static branch | MLP |
| loss | station count weighted Smooth L1 |
| optimizer | AdamW |
| scheduler | ReduceLROnPlateau |
| max epochs | 20 |
| early stopping patience | 5 |
| LR reduce patience | 2 |

validation weighted MAE가 개선될 때마다 checkpoint를 저장했습니다.

## Validation 결과

| 유종 | 모델 | weighted MAE | 해석 |
|---|---|---:|---|
| 휘발유 | 전일 실제가격 baseline | 15.211 | 단순히 어제 가격을 오늘 적정가격으로 보는 기준 |
| 휘발유 | train 평균 delta baseline | 19.192 | 평균 변화량만 더하는 기준 |
| 휘발유 | LSTM | 19.318 | baseline보다 나쁨 |
| 경유 | 전일 실제가격 baseline | 14.807 | 단순히 어제 가격을 오늘 적정가격으로 보는 기준 |
| 경유 | train 평균 delta baseline | 16.469 | 평균 변화량만 더하는 기준 |
| 경유 | LSTM | 19.422 | baseline보다 나쁨 |

best epoch는 휘발유와 경유 모두 4입니다. 이후에는 validation MAE가 개선되지 않아 early stopping이 발생했습니다.

| 유종 | best epoch | best validation WMAE | final train rows | final train epoch |
|---|---:|---:|---:|---:|
| 휘발유 | 4 | 19.318 | 7,644,896 | 4 |
| 경유 | 4 | 19.422 | 5,186,321 | 4 |

## 2026 test 결과

2026년 test는 2026-01-01 ~ 2026-06-09까지 월별 전체 예측을 수행했습니다.

| 유종 | 전체 test rows | weighted MAE |
|---|---:|---:|
| 휘발유 | 1,415,122 | 231.790 |
| 경유 | 1,415,122 | 518.133 |

월별로 보면 3월 이후 오차가 크게 증가합니다.

| 유종 | 월 | target 가중평균 | 예측 가중평균 | model WMAE |
|---|---|---:|---:|---:|
| 휘발유 | 2026-01 | 1,708.084 | 1,698.823 | 12.828 |
| 휘발유 | 2026-02 | 1,701.456 | 1,679.220 | 23.893 |
| 휘발유 | 2026-03 | 2,129.744 | 1,830.153 | 311.226 |
| 휘발유 | 2026-04 | 2,369.976 | 1,961.464 | 409.479 |
| 휘발유 | 2026-05 | 2,348.467 | 2,007.525 | 341.834 |
| 휘발유 | 2026-06 | 2,400.569 | 1,999.295 | 402.101 |
| 경유 | 2026-01 | 1,693.402 | 1,605.050 | 88.990 |
| 경유 | 2026-02 | 1,713.216 | 1,594.239 | 119.800 |
| 경유 | 2026-03 | 2,192.371 | 1,824.174 | 374.049 |
| 경유 | 2026-04 | 3,111.995 | 1,965.512 | 1,146.664 |
| 경유 | 2026-05 | 2,784.696 | 1,985.663 | 799.336 |
| 경유 | 2026-06 | 2,668.656 | 1,977.407 | 691.515 |

## 해석

현재 모델은 기술적으로는 끝까지 학습되고 산출물도 생성했지만, 모델링 목표가 과하게 넓었습니다. 전국 적정가격 레벨은 `data-analysis/05`가 이미 국제가격과 정책을 반영해 계산하는 값입니다. 그런데 AI 04는 이 전국 레벨 변화를 별도 anchor 없이 전날까지의 실제 가격 흐름만으로 맞히려 했습니다.

2026년 3월 이후 `grid_fair_price_target`의 전국 레벨이 크게 상승했지만, 모델 예측은 실제 유가 흐름 근처에 머물렀습니다. 따라서 큰 음의 bias와 높은 MAE가 발생했습니다.

## 다음 모델 방향

현 구조를 최종 모델로 쓰기보다, 문제를 다음처럼 분해하는 것이 더 적합합니다.

```text
전국 적정가격 레벨:
  data-analysis/05의 national_fair_price_policy 사용

격자별 공간 보정:
  AI 모델이 grid spread 또는 fair spread만 예측

최종 가격:
  pred_grid_fair_price = national_fair_price_policy + pred_grid_spread
```

이렇게 하면 국제가격/정책에 따른 전국 레벨 변화는 `data-analysis`가 담당하고, AI는 지역별 가격 차이와 공간 구조만 학습합니다. 현재 결과는 이 방향 전환의 근거로 보는 것이 맞습니다.

## 산출물

| 산출물 | 내용 |
|---|---|
| `{fuel}_validation_scores.csv` | baseline과 LSTM의 validation 적정가격 복원 오차 |
| `{fuel}_training_history.csv` | epoch별 train loss, validation MAE, learning rate, 소요 시간 |
| `{fuel}_validation_predictions.parquet` | validation 예측 결과 |
| `model/checkpoints/{fuel}_grid_fair_price_delta_best_latest.pt` | validation 기준 best checkpoint |
| `model/{fuel}_grid_fair_price_delta_lstm.pt` | final train으로 학습한 모델 |
| `test_predictions_by_month/YYYYMM.parquet` | 2026 test 월별 전체 예측 |
| `{fuel}_test_metrics_2026.csv` | 2026 test metric |
| `{fuel}_test_daily_summary_2026.csv` | 2026 일별 예측 요약 |
| `{fuel}_test_grid_summary_2026.csv` | 2026 격자별 예측 요약 |
| `{fuel}_model_metadata.json` | 입력/target/model/split/output metadata |
| `model_run_summary.csv` | 유종별 요약 |
