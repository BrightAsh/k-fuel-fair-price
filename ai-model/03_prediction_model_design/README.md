# 03. Prediction Model Design

격자별 당일 적정가격을 예측하는 3단계 모델입니다.

## 사용할 파일

- `03_prediction_model_design.py`: Anaconda/PyCharm 로컬 실행용 코드
- `environment-conda.yml`: Anaconda 환경 생성 파일
- `03_prediction_model_design.ipynb`: Colab/노트북용 동일 코드

현재 실행은 `03_prediction_model_design.py`를 사용하면 됩니다.

## Anaconda 환경 생성

Anaconda Prompt에서 repo 루트로 이동한 뒤 실행합니다.

```powershell
cd C:\Users\user\Desktop\산업부\k-fuel-fair-price
conda env create -f .\ai-model\03_prediction_model_design\environment-conda.yml
conda activate k-fuel-stage3
```

PyCharm interpreter는 아래 conda 환경을 선택하면 됩니다.

```text
k-fuel-stage3
```

또는 직접 경로를 잡는 경우 Anaconda 설치 위치 아래의 `envs\k-fuel-stage3\python.exe`를 선택합니다.

## 로컬 실행

Anaconda Prompt에서:

```powershell
cd C:\Users\user\Desktop\산업부\k-fuel-fair-price
conda activate k-fuel-stage3
python .\ai-model\03_prediction_model_design\03_prediction_model_design.py
```

PyCharm에서는 `03_prediction_model_design.py`를 열고 실행하면 됩니다. Working directory는 repo 루트인 아래 경로를 권장합니다.

```text
C:\Users\user\Desktop\산업부\k-fuel-fair-price
```

## 로컬 입력 파일

현재 로컬 데이터만으로 실행 가능합니다.

```text
ai-model/02_spatial_grid_build/outputs/grid.parquet
data-analysis/05_policy_application/outputs/휘발유/일별_정책적용_데이터_휘발유.csv
data-analysis/05_policy_application/outputs/경유/일별_정책적용_데이터_경유.csv
data-analysis/04_fair_price_model/outputs/gasoline_production_predictions_full_calendar.csv
data-analysis/04_fair_price_model/outputs/diesel_production_predictions_full_calendar.csv
```

## 핵심 예측 구조

- `target_date`: 예측 대상일
- `feature_date = target_date - 1일`
- `2026-01-01` 이후 `target_date`는 전부 test
- train/validation은 유류세 인하/환원 등 정책 적용 기간을 완전히 제외한 정상기간만 사용
- 정책기간을 제외한 pre-2026 eligible row를 시간순으로 7:3에 가깝게 분할
- `target_spread = actual_grid_price(target_date) - national_actual_price(target_date)`
- 최종 격자 적정가격은 `national_fair_center(target_date) + predicted_spread(target_date)`

## 모델

- Lag/Rolling LightGBM
- Temporal CNN + LSTM + Static MLP 후보 모델
- `auto` 모드에서는 validation에서 충분히 좋은 모델을 선택합니다.

Windows에서 LightGBM GPU는 OpenCL/Boost.Compute 캐시 문제로 프로세스가 강제 종료될 수 있어 기본값은 CPU입니다. PyTorch sequence 모델은 별도 설정으로 CUDA를 계속 사용할 수 있습니다.

딥러닝 후보 모델은 기본 최대 epoch가 `1000`입니다. 다만 validation 가중 MAE가 개선되지 않으면 early stopping으로 중단되고, 정체 구간에서는 learning rate가 자동으로 감소합니다. sequence 후보는 `lag_1 spread`를 기준값으로 두고 residual을 학습하므로 최근 격자 spread를 복사하는 기본 동작을 구조적으로 보장합니다. 또한 LightGBM 기준선보다 명확히 나쁘면 오래 끌지 않고 중단합니다. 각 epoch마다 train loss, validation MAE, best MAE, learning rate, epoch 소요 시간, 누적 시간이 출력되고 CSV에도 저장됩니다.

주요 설정:

- `K_FUEL_TRAIN_VALID_TRAIN_RATIO`: 기본값 `0.70`
- `K_FUEL_EXCLUDE_POLICY_PERIODS_FROM_TRAIN_VALID`: 기본값 `1`
- `K_FUEL_GAP_DAYS`: 기본값 `7`
- `K_FUEL_MAX_TRAIN_TUNE_ROWS`: 기본값 `2500000`
- `K_FUEL_MAX_VALID_ROWS`: 기본값 `1100000`
- `K_FUEL_USE_LGBM_GPU`: 기본값 `0`
- `K_FUEL_USE_GPU`: 기본값 `1`, PyTorch sequence 모델 CUDA 사용 여부
- `K_FUEL_SEQUENCE_MODEL_EPOCHS`: 기본값 `1000`
- `K_FUEL_SEQUENCE_MODEL_MAX_TRAIN_ROWS`: 기본값 `700000`
- `K_FUEL_SEQUENCE_MODEL_MAX_VALID_ROWS`: 기본값 `300000`
- `K_FUEL_SEQUENCE_EARLY_STOPPING_PATIENCE`: 기본값 `30`
- `K_FUEL_SEQUENCE_EARLY_STOPPING_MIN_DELTA`: 기본값 `0.001`
- `K_FUEL_SEQUENCE_LR_PATIENCE`: 기본값 `8`
- `K_FUEL_SEQUENCE_LR_REDUCE_FACTOR`: 기본값 `0.5`
- `K_FUEL_SEQUENCE_MIN_LR`: 기본값 `0.00001`
- `K_FUEL_SEQUENCE_RESIDUAL_FROM_LAG1`: 기본값 `1`
- `K_FUEL_SEQUENCE_MIN_EPOCHS_BEFORE_REFERENCE_ABORT`: 기본값 `50`
- `K_FUEL_SEQUENCE_ABORT_WORSE_THAN_REFERENCE_RATIO`: 기본값 `1.30`

GTX 1060 6GB에서 메모리가 부족하면 코드 상단 환경변수 또는 실행 전 환경변수로 `K_FUEL_RUN_SEQUENCE_MODEL=0`을 설정해 LightGBM만 먼저 돌릴 수 있습니다.

기본 유종은 아래처럼 휘발유와 경유가 모두 들어갑니다.

```text
K_FUEL_RUN_FUELS=gasoline,diesel
```
