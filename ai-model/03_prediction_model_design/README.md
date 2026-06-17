# 03. Prediction Model Design

AI Model 02에서 생성한 500m 격자 일별 패널을 입력으로 사용해, 격자별 가격 spread 변동을 예측하는 단계입니다. 현재 모델 학습이 진행 중이므로 최종 성능 지표와 결과 해석은 아직 확정하지 않습니다. 이 README는 코드 내용 기준으로 입력, target, 학습 데이터 구성, cache, 모델, 예상 산출물을 정리합니다.

## 실행 파일

| 파일 | 역할 |
|---|---|
| `03_prediction_model_design.py` | 로컬/PyCharm/Anaconda 기준 학습 스크립트 |
| `environment-conda.yml` | 실행 환경 정의 |

이 단계는 Colab mount나 Google Drive fallback을 사용하지 않습니다. repo 루트를 working directory로 두고 실행하는 구조입니다.

## 실행 환경

`environment-conda.yml` 기준입니다.

| 항목 | 값 |
|---|---|
| Python | 3.12 |
| 주요 패키지 | `numpy`, `pandas`, `scikit-learn`, `pyarrow`, `duckdb` |
| PyTorch | `https://download.pytorch.org/whl/cu126` index의 `torch` |

실행 예시:

```powershell
cd C:\Users\user\Desktop\산업부\k-fuel-fair-price
conda env create -f .\ai-model\03_prediction_model_design\environment-conda.yml
conda activate k-fuel-stage3
python .\ai-model\03_prediction_model_design\03_prediction_model_design.py
```

## 입력

코드의 기본 입력 경로는 다음입니다.

```text
ai-model/02_spatial_grid_build/outputs/grid.parquet
```

AI 02 Colab 노트북의 실제 최종 저장 위치는 `ROOT_PATH/그리드/grid.parquet`입니다. 로컬 03 실행 전에는 해당 파일을 위 기본 경로로 복사하거나, 코드 상단의 `GRID_PATH`를 실행 환경에 맞게 조정해야 합니다.

`grid.parquet`는 최소한 아래 컬럼을 포함해야 합니다.

| 컬럼 | 용도 |
|---|---|
| `date` | target date와 history window 구성 |
| `grid_id` | 격자 식별자 |
| `gasoline_price_mean`, `diesel_price_mean` | 유종별 격자 평균 가격 |
| `gasoline_station_count`, `diesel_station_count` | 유종별 station weight |
| `cell_x`, `cell_y`, `center_lon`, `center_lat` | 예측 결과 위치/패널 출력 |

02 최신 출력의 `grid.parquet`는 63,800,291행, 12,338개 격자, 2008-04-15 ~ 2026-06-11 기간을 포함합니다.

## 유종별 설정

코드는 휘발유와 경유를 같은 로직으로 순차 학습합니다.

| fuel key | 가격 컬럼 | station weight 컬럼 | label |
|---|---|---|---|
| `gasoline` | `gasoline_price_mean` | `gasoline_station_count` | 휘발유 |
| `diesel` | `diesel_price_mean` | `diesel_station_count` | 경유 |

실행 대상은 코드 상단의 `RUN_FUELS = ("gasoline", "diesel")`입니다.

## 예측 target

모델은 격자 가격 자체가 아니라 전국 평균 대비 격자 가격 차이인 spread의 다음 날 변동값을 예측합니다.

```text
national_actual_price = 날짜별 station_count 가중 전국 평균 가격
spread_target = actual_grid_price - national_actual_price
spread_delta_target = spread_target - spread_lag_1d
```

예측 후에는 아래 방식으로 다시 spread와 격자 가격을 복원합니다.

```text
pred_spread_raw = spread_lag_1d + pred_spread_delta
pred_spread = 날짜별 station_count 가중평균이 0이 되도록 재중심화한 pred_spread_raw
pred_grid_price = national_actual_price + pred_spread
```

날짜별 재중심화는 spread가 "전국 평균 대비 상대 가격"이라는 정의를 유지하기 위한 처리입니다.

## 입력 시계열

각 학습 행은 특정 `grid_id`, 특정 `target_date`에 대한 28일 시계열입니다.

| 설정 | 값 |
|---|---|
| sequence length | 28일 |
| target column | `spread_delta_target` |
| target mode | `spread_delta` |
| history 필요 조건 | 직전 29일의 spread 이력이 연속 존재 |

모델 입력 channel은 4개입니다.

```text
spread_delta
actual_price_delta
national_price_delta
station_weight
```

결측이 있거나 history window가 끊긴 행은 학습/평가 frame에서 제외합니다.

## 정책기간 제외

학습/검증/final train에서는 정책기간 영향을 제거합니다.

제외 방식:

| 대상 | 처리 |
|---|---|
| `target_date`가 정책기간인 행 | 제외 |
| 29일 input history 안에 정책기간이 포함된 행 | 제외 |
| 2026년 이후 test 행 | 학습에는 사용하지 않고 평가 전용 |

정책기간은 코드 상단의 `POLICY_EXCLUDE_RANGES`에 고정되어 있습니다.

## Train / Validation / Test 분리

| 구분 | 조건 |
|---|---|
| train/validation 후보 | `target_date < 2026-01-01` |
| test | `target_date >= 2026-01-01` |
| train/validation split | pre-2026 eligible day를 시간순 7:3 비율로 분리 |
| gap | train 종료일과 validation 시작일 사이 7일 gap |
| final train | pre-2026 전체 eligible frame |

row 수가 매우 크기 때문에 hash 기반 고정 샘플링과 최대 row 제한을 사용합니다.

| 설정 | 값 |
|---|---:|
| `TRAIN_SAMPLE_PER_MILLE` | 100 |
| `VALID_SAMPLE_PER_MILLE` | 100 |
| final train sampling | `TRAIN_SAMPLE_PER_MILLE`와 동일 |
| `MAX_TRAIN_ROWS_PER_FUEL` | 3,000,000 |
| `MAX_VALID_ROWS_PER_FUEL` | 1,300,000 |
| `MAX_FINAL_TRAIN_ROWS_PER_FUEL` | 4,500,000 |

샘플링은 `hash(grid_id, target_date, salt)` 기반이라 시간이나 특정 지역만 잘리지 않고 재현 가능한 표본을 만듭니다.

## 중간 데이터 cache

DuckDB로 `grid.parquet`를 읽어 lag, spread, 정책기간 제외, 28일 sequence 조건을 계산하는 과정이 오래 걸리므로 중간 frame을 parquet로 cache합니다.

```text
ai-model/03_prediction_model_design/outputs/intermediate_data/
```

cache 재사용 여부는 metadata JSON과 아래 조건을 비교해 결정합니다.

| 조건 | 내용 |
|---|---|
| 입력 grid | 경로, 파일 크기, 수정 시각 |
| fuel | `gasoline` 또는 `diesel` |
| frame label | train, validation, final_train, test 월별 frame 등 |
| 날짜 범위 | start/end |
| 샘플링 | 비율, salt, 최대 row 수 |
| sequence | 길이, input channel, target 정의 |
| 정책 제외 | target/history 정책기간 제외 여부와 정책기간 목록 |
| dataset version | `stage03_spread_delta_lstm_v1` |

조건이 바뀌면 기존 cache는 사용하지 않고 새로 생성합니다.

## 모델

현재 모델은 단일 PyTorch bidirectional LSTM입니다.

| 항목 | 값 |
|---|---|
| 입력 | 28 days x 4 channels |
| hidden size | 128 |
| layers | 2 |
| dropout | 0.20 |
| loss | station count weighted Smooth L1 |
| optimizer | AdamW |
| scheduler | ReduceLROnPlateau |
| early stopping 기준 | validation weighted MAE |

baseline도 함께 계산합니다.

| baseline | 의미 |
|---|---|
| `baseline_national_average` | 모든 격자 spread를 0으로 보는 기준 |
| `baseline_lag1_delta0` | 전일 spread가 그대로 유지된다고 보는 기준 |
| `baseline_train_mean_delta` | train 평균 spread delta를 적용하는 기준 |

## 예상 산출물

학습이 완료되면 `outputs/` 아래에 유종별 폴더가 생성됩니다.

```text
ai-model/03_prediction_model_design/outputs/gasoline/
ai-model/03_prediction_model_design/outputs/diesel/
```

유종별 예상 산출물은 다음입니다.

| 파일 | 내용 |
|---|---|
| `{fuel}_training_history.csv` | epoch별 train loss, validation metric |
| `{fuel}_validation_scores.csv` | baseline과 LSTM validation 성능 비교 |
| `{fuel}_validation_predictions.parquet` | validation 예측 결과 |
| `model/{fuel}_spread_delta_lstm.pt` | final train으로 학습한 최종 모델 가중치 |
| `{fuel}_model_metadata.json` | split, 입력 컬럼, 정책 제외, 성능 요약 등 실행 metadata |
| `{fuel}_test_predictions_2026.parquet` | 2026년 test 예측 결과 통합 |
| `{fuel}_test_daily_summary_2026.csv` | 2026년 일별 예측 요약 |
| `{fuel}_test_grid_summary_2026.csv` | 2026년 격자별 예측 요약 |
| `{fuel}_test_metrics_2026.csv` | 월별 및 전체 test metric |

전체 실행이 끝나면 아래 통합 요약도 저장합니다.

```text
ai-model/03_prediction_model_design/outputs/model_run_summary.csv
```

## 현재 상태

이 README는 모델 학습 결과가 나오기 전 기준입니다. 따라서 validation/test 성능, 최종 모델 비교, 2026년 예측 해석은 아직 작성하지 않았습니다. 학습 완료 후에는 `model_run_summary.csv`, `{fuel}_model_metadata.json`, `{fuel}_test_metrics_2026.csv`를 기준으로 결과 섹션을 추가해야 합니다.
