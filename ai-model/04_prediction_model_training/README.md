# 04. Prediction Model Training

AI 04는 AI 03에서 만든 격자별 적정가격 target dataset을 읽어, 전날까지의 시계열과 격자 context만으로 오늘의 격자별 적정가격을 예측하는 단계입니다.

## 실행 파일

| 파일 | 역할 |
|---|---|
| `04_prediction_model_training.py` | 로컬/PyCharm/Anaconda 기준 PyTorch 학습/검증/test 스크립트 |
| `environment-conda.yml` | 실행 환경 정의 |

## 입력

기본 입력은 아래 하나입니다.

```text
ai-model/03_target_dataset_build/outputs/grid_target.parquet
```

이 파일이 없으면 먼저 AI 03을 실행해야 합니다.

```powershell
python .\ai-model\03_target_dataset_build\03_target_dataset_build.py
```

## 예측 문제

모델은 target date 당일 전국 평균 가격을 입력으로 보지 않습니다. 입력은 target date 기준 전날까지의 정보입니다.

```text
각 그리드 실제 가격/전국 실제 가격/spread 변화량(t-1 ~ t-28)
  + 전날 상태값(t-1)
  + 고정/저빈도 격자 context
  -> 오늘 격자별 적정가격 target
```

학습 target은 level이 아니라 전일 실제 격자 가격 대비 오늘 적정가격 변화량입니다.

```text
fair_price_delta_target
  = grid_fair_price_target(t) - actual_grid_price(t-1)

pred_grid_fair_price(t)
  = actual_grid_price(t-1) + pred_fair_price_delta
```

출력의 `price_weighted_mae`는 `pred_grid_fair_price`와 `grid_fair_price_target` 사이의 원 단위 station-count weighted MAE입니다.

## 입력 feature 구조

LSTM branch는 28일 시계열 변화량만 받습니다.

| channel | 내용 |
|---|---|
| `spread_delta` | 격자 실제 spread의 일별 변화 |
| `actual_price_delta` | 격자 실제 가격의 일별 변화 |
| `national_price_delta` | grid panel에서 계산한 전국 실제 가중평균 가격의 일별 변화 |

latest branch는 target date 전날의 상태값을 받습니다.

```text
actual_price_lag_1d
national_price_lag_1d
spread_lag_1d
station_weight_lag_1d
```

static/slow branch는 위치, 주유소 구성, 시설 영향권, 육지/섬 여부, 공시지가 같은 격자 context를 받습니다. 고정값이나 반년/연 단위로 바뀌는 값은 LSTM 시계열 branch가 아니라 이 branch로 들어갑니다.

## 데이터 분리

| 구분 | 기준 |
|---|---|
| train/validation 후보 | `target_date < 2026-01-01` |
| test | `2026-01-01 <= target_date <= 2026-12-31` |
| train/validation split | pre-2026 eligible day를 row 수 기준 약 7:3으로 시간 순서 분리 |
| gap | train 종료일과 validation 시작일 사이 7일 |
| 정책 기간 처리 | train/validation/final train에서 target date가 정책 기간이면 제외 |
| history 정책 처리 | train/validation/final train에서 29일 입력 history 안에 정책 기간이 있으면 제외 |

test는 정책 기간을 제외하지 않습니다. 사용자가 실제로 보려는 2026년 적정가격 평가 구간이기 때문입니다.

## 샘플링과 cache

대상 행이 매우 크기 때문에 train/validation/final train frame은 고정 hash sampling을 사용합니다.

| 설정 | 값 |
|---|---:|
| `TRAIN_SAMPLE_PER_MILLE` | 200 |
| `VALID_SAMPLE_PER_MILLE` | 200 |
| `MAX_TRAIN_ROWS_PER_FUEL` | 6,000,000 |
| `MAX_VALID_ROWS_PER_FUEL` | 2,500,000 |
| `MAX_FINAL_TRAIN_ROWS_PER_FUEL` | 8,000,000 |

중간 frame은 아래에 cache됩니다.

```text
ai-model/04_prediction_model_training/outputs/intermediate_data/
```

cache는 입력 target dataset의 파일 크기/수정시각, split 조건, sampling 조건, target 정의, feature 목록이 모두 같을 때만 재사용합니다. 조건이 바뀌면 새로 생성합니다.

## 모델

모델은 PyTorch hybrid LSTM입니다.

| 항목 | 값 |
|---|---|
| model name | `hybrid_grid_fair_price_delta_lstm` |
| sequence length | 28 days |
| sequence channels | 3 |
| LSTM hidden size | 128 |
| LSTM layers | 2 |
| dropout | 0.20 |
| loss | station count weighted Smooth L1 |
| optimizer | AdamW |
| scheduler | ReduceLROnPlateau |
| max epochs | 20 |
| early stopping patience | 5 |
| LR reduce patience | 2 |

validation weighted MAE가 개선될 때마다 checkpoint를 저장합니다. 중간에 실행을 끊어도 가장 좋았던 checkpoint는 남습니다.

## 주요 출력

유종별 출력 폴더:

```text
ai-model/04_prediction_model_training/outputs/gasoline/
ai-model/04_prediction_model_training/outputs/diesel/
```

| 출력 | 내용 |
|---|---|
| `{fuel}_validation_scores.csv` | baseline과 LSTM의 validation 적정가격 복원 오차 |
| `{fuel}_training_history.csv` | epoch별 train loss, validation MAE, LR, 소요 시간 |
| `{fuel}_validation_predictions.parquet` | validation 예측 결과 |
| `model/checkpoints/{fuel}_grid_fair_price_delta_best_latest.pt` | validation 기준 best checkpoint |
| `model/{fuel}_grid_fair_price_delta_lstm.pt` | final train으로 학습한 최종 모델 |
| `test_predictions_by_month/YYYYMM.parquet` | 2026 test 월별 전체 예측 |
| `{fuel}_test_predictions_2026.parquet` | 2026 test 예측 통합 parquet |
| `{fuel}_test_daily_summary_2026.csv` | 2026 일별 예측 요약 |
| `{fuel}_test_grid_summary_2026.csv` | 2026 격자별 예측 요약 |
| `{fuel}_model_metadata.json` | 입력/target/model/split/output metadata |

전체 요약:

```text
ai-model/04_prediction_model_training/outputs/model_run_summary.csv
```

## 실행

```powershell
cd C:\Users\user\Desktop\산업부\k-fuel-fair-price
conda env create -f .\ai-model\04_prediction_model_training\environment-conda.yml
conda activate k-fuel-stage4
python .\ai-model\04_prediction_model_training\04_prediction_model_training.py
```

PyCharm에서는 프로젝트 루트를 `C:\Users\user\Desktop\산업부\k-fuel-fair-price`로 잡고, interpreter를 `k-fuel-stage4` 환경으로 선택하면 됩니다.
