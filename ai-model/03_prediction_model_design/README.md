# 03. Prediction Model Design

AI Model 02에서 생성한 `grid.parquet`을 입력으로 사용해 격자별 유가 spread 변동 예측 모델을 학습하는 단계입니다.

이 단계의 목적은 각 격자의 직전 28일 시계열을 기반으로 다음 날 격자별 가격 spread 변동값을 예측하는 PyTorch LSTM 모델을 만드는 것입니다. `2026-01-01` 이후 데이터는 학습에 사용하지 않고 test 평가 구간으로만 사용합니다.

## 실행 파일

- `03_prediction_model_design.py`
- 실행 환경: `environment-conda.yml`

이 단계는 로컬 PyCharm/Anaconda 실행을 기준으로 작성되어 있습니다. Colab mount, Google Drive fallback, 환경변수 override는 사용하지 않습니다.

## 입력

```text
ai-model/02_spatial_grid_build/outputs/grid.parquet
```

`grid.parquet`에는 일자별 500m 격자 단위 주유소 가격, 주유소 수, 시설 영향, 지리 정보, 공시지가 정보 등이 포함되어 있어야 합니다.

모델 학습에 직접 사용하는 주요 컬럼은 다음과 같습니다.

```text
date
grid_id
gasoline_price_mean
diesel_price_mean
gasoline_station_count
diesel_station_count
cell_x
cell_y
center_lon
center_lat
```

휘발유와 경유는 같은 로직으로 순서대로 학습합니다.

## 예측 대상

모델은 격자 가격 자체가 아니라 전국 평균 대비 격자 가격 차이인 spread의 다음 날 변동값을 학습합니다.

```text
spread_target = actual_grid_price - national_actual_price
spread_delta_target = spread_target - spread_lag_1d
```

예측 후에는 아래 방식으로 다시 spread와 격자 가격을 복원합니다.

```text
pred_spread = spread_lag_1d + predicted_spread_delta
pred_grid_price = national_actual_price + pred_spread
```

날짜별 예측 spread는 주유소 수 가중평균이 0이 되도록 재중심화합니다. 이는 전국 평균 대비 각 격자의 상대적 가격 차이라는 spread 정의를 유지하기 위한 처리입니다.

## 입력 시계열

각 학습 행은 특정 `grid_id`와 특정 `target_date`에 대한 하나의 28일 시계열입니다.

입력 channel은 다음 4개입니다.

```text
spread_delta
actual_price_delta
national_price_delta
station_weight
```

`spread_delta`를 만들기 위해 직전 29일의 원 spread 이력이 필요합니다. 따라서 학습/검증에는 직전 29일 이력이 연속으로 존재하고, 필요한 시계열 값에 결측이 없는 행만 사용합니다.

## 데이터 분리

- `target_date < 2026-01-01`: train, validation, final train 후보
- `target_date >= 2026-01-01`: test 전용
- train/validation은 정책기간을 제외한 pre-2026 데이터에서 시간순 7:3 비율로 분리
- train과 validation 사이에는 7일 gap 적용
- train/validation/final train에서는 target date가 정책기간인 행을 제외
- train/validation/final train에서는 입력 29일 history 안에 정책기간이 포함된 행도 제외

정책기간은 코드 상단의 `POLICY_EXCLUDE_RANGES`에 고정되어 있습니다.

## 샘플링

학습 가능 행 전체를 그대로 사용하지 않고, train과 validation은 20%를 hash 기반 고정 랜덤으로 사용합니다.

```text
hash(grid_id, target_date, salt) 기반 샘플링
```

따라서 앞쪽 기간이나 특정 지역만 잘리는 방식이 아니라 시간과 공간 전반에 퍼진 재현 가능한 표본을 사용합니다.

## 중간 데이터 캐시

학습용 frame 생성에는 `grid.parquet` 전체를 읽고 lag, spread, 정책기간 제외, 결측 없는 28일 시계열 필터를 계산하는 과정이 필요합니다. 이 작업은 오래 걸리므로 생성된 중간 데이터는 아래 경로에 parquet로 저장합니다.

```text
ai-model/03_prediction_model_design/outputs/intermediate_data/
```

다음 실행 때 같은 조건의 중간 데이터가 있으면 DuckDB로 다시 만들지 않고 저장된 parquet를 바로 읽습니다. 캐시 재사용 여부는 다음 조건이 모두 같은지 확인해 결정합니다.

```text
grid.parquet 경로, 파일 크기, 수정시각
유종
train/validation/test/final_train 구분
날짜 범위
샘플링 비율과 salt
최대 row 수
정책기간 제외 조건
시계열 길이와 입력 channel
target 정의
정책기간 목록
```

조건이 바뀌면 기존 캐시를 사용하지 않고 새 중간 데이터를 생성합니다. `outputs/` 아래 파일은 Git에 올리지 않습니다.

## 모델

모델은 단일 PyTorch bidirectional LSTM입니다.

```text
input: 28 days x 4 channels
target: spread_delta_target
loss: station count weighted Smooth L1
optimizer: AdamW
scheduler: ReduceLROnPlateau
early stopping: validation weighted MAE 기준
```

LightGBM 후보, CNN, 주변 격자 patch, static MLP는 사용하지 않습니다.

## 실행

Anaconda Prompt에서 repo 루트로 이동한 뒤 실행합니다.

```powershell
cd C:\Users\user\Desktop\산업부\k-fuel-fair-price
conda env create -f .\ai-model\03_prediction_model_design\environment-conda.yml
conda activate k-fuel-stage3
python .\ai-model\03_prediction_model_design\03_prediction_model_design.py
```

PyCharm에서 실행할 경우 interpreter는 `k-fuel-stage3` 환경의 `python.exe`를 사용하고, working directory는 repo 루트를 권장합니다.

```text
C:\Users\user\Desktop\산업부\k-fuel-fair-price
```

## 단계 역할

- 01: 원천 수집 산출물을 AI 모델용 파생 feature와 좌표/격자 기반 입력으로 정리합니다.
- 02: 일자별 500m 격자 패널과 공간 feature를 구성합니다.
- 03: 02의 격자 패널을 이용해 격자별 spread 변동 예측 모델을 학습하고 2026년 test 구간에서 평가합니다.

학습 산출물 정리는 모델 학습 완료 후 결과 파일과 함께 추가합니다.
