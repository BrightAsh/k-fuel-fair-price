# AI Model

`ai-model`은 전국 단위 적정가격 분석을 주유소/격자 단위 데이터로 확장하는 영역입니다. 목표는 전국 평균 가격 하나가 아니라, 500m 격자별로 “이 위치에서의 적정가격은 얼마인가”를 표현하는 것입니다.

## 핵심 흐름

```text
주유소 가격/위치/속성
+ 시설 영향권
+ 공시지가
+ 전국 500m land grid
    -> 일별 격자 패널
    -> 전국 정책 적용 적정가격과 결합
    -> 격자별 적정가격 target
    -> AI 모델 성능 검토
```

## 단계 구조

| 단계 | 역할 | 핵심 산출물 또는 결론 |
|---|---|---|
| `01_derived_features` | 격자화 전 주유소, 시설, 공시지가, land grid 파생 데이터 생성 | 좌표 유효 주유소 27,830개, 시설 740개, 공시지가 격자 396,185행 |
| `02_spatial_grid_build` | 일별 500m 격자 패널 생성 | 63,800,291행, 12,338개 격자 |
| `03_target_dataset_build` | 전국 적정가격을 격자 spread와 결합해 target dataset 생성 | 휘발유 target 59,613,708행, 경유 target 45,487,926행 |
| `04_prediction_model_training` | 격자별 적정가격 예측 모델 학습 및 검토 | 첫 LSTM은 baseline보다 낮아 구조 재설계 필요 |

## Target 설계

AI 03은 전국 적정가격을 그대로 모든 격자에 복사하지 않습니다. 각 격자가 전국 평균보다 비싼지 싼지를 나타내는 실제 가격 spread를 보존합니다.

```text
national_actual_price_grid(t)
  = grid panel에서 유종별 station_count로 가중평균한 전국 실제 가격

grid_actual_spread(t)
  = grid_actual_price(t) - national_actual_price_grid(t)

grid_fair_price_target(t)
  = national_fair_price_policy(t) + grid_actual_spread(t)
```

이 구조는 `data-analysis/05`의 전국 정책 적용 적정가격을 anchor로 두고, 공간적 가격 차이를 격자 단위로 얹는 방식입니다.

## 현재 모델 검토

AI 04의 첫 모델은 28일 시계열 변화량, 전날 상태값, 격자 context를 입력으로 받아 `grid_fair_price_target`을 예측하도록 설계했습니다. 학습 target은 전일 실제 가격 대비 오늘 적정가격 변화량입니다.

```text
fair_price_delta_target
  = grid_fair_price_target(t) - actual_grid_price(t-1)
```

학습은 끝까지 완료되었지만, 성능은 최종 운영 모델로 쓰기 어렵습니다.

| 유종 | best epoch | validation LSTM WMAE | validation 전일가격 baseline WMAE | 2026 test WMAE |
|---|---:|---:|---:|---:|
| 휘발유 | 4 | 19.318원/L | 15.211원/L | 231.790원/L |
| 경유 | 4 | 19.422원/L | 14.807원/L | 518.133원/L |

문제는 모델이 전국 적정가격 레벨까지 직접 외삽하려 한다는 점입니다. 2026년 3월 이후 전국 적정가격 target이 급격히 상승하는 구간에서 예측은 실제 유가 흐름 근처에 머물러 큰 오차가 발생했습니다.

따라서 다음 모델 방향은 다음과 같습니다.

```text
data-analysis/05가 오늘 전국 정책 적용 적정가격을 제공
AI 모델은 격자별 spread 또는 지역 보정값을 예측
최종 격자 적정가격 = 전국 적정가격 + 예측 spread
```

이 방향은 전국 레벨 가격 판단과 공간 보정 문제를 분리하므로 현재 결과보다 안정적인 구조입니다.

## 산출물 해석 기준

| 단계 | 산출물 | 해석 |
|---|---|---|
| 01 | `station_points`, `facility_points`, `official_land_price_grid`, `korea_land_grid_500m` | 격자 feature의 재료 |
| 02 | `grid.parquet` | 날짜 x 격자 단위 실제 가격/공간 feature 패널 |
| 03 | `grid_target.parquet` | AI 학습용 격자별 적정가격 target dataset |
| 04 | validation/test 예측, checkpoint, summary | 현재 모델 구조의 성능 한계 확인 자료 |

세부 코드 로직, 컬럼, 수치, 결과 해석은 각 단계 README에 정리합니다.
