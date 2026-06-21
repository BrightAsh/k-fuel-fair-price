# 03. Target Dataset Build

AI 03은 AI 02의 실제 격자 패널과 `data-analysis/05`의 전국 정책 적용 적정가격을 결합해, 격자별 적정가격 target dataset을 만드는 단계입니다. 원본 `grid.parquet`은 수정하지 않고 별도 target dataset을 생성합니다.

## 핵심 아이디어

전국 적정가격은 `data-analysis/05`가 이미 계산합니다. AI 03의 역할은 이 전국 적정가격을 500m 격자별 가격 구조로 확장하는 것입니다.

단순히 전국 적정가격을 모든 격자에 동일하게 넣으면 지역별 가격 차이가 사라집니다. 따라서 각 격자가 전국 평균보다 비싼지 싼지를 나타내는 실제 spread를 유지합니다.

```text
national_actual_price_grid(t)
  = grid panel에서 유종별 station_count로 가중평균한 전국 실제 가격

grid_actual_spread(t)
  = grid_actual_price(t) - national_actual_price_grid(t)

grid_fair_price_target(t)
  = national_fair_price_policy(t) + grid_actual_spread(t)
```

즉 “전국 레벨은 정책 적용 적정가격을 따르고, 공간적 상대가격은 격자의 실제 spread를 따른다”는 정의입니다.

## 코드 구성

| 파일 | 역할 |
|---|---|
| `03_target_dataset_build.py` | 전국 적정가격 정리, grid anchor 계산, 격자별 target 생성 |

## 입력 데이터

| 입력 | 내용 |
|---|---|
| AI 02 `grid.parquet` | 일별 500m 격자별 실제 유가, 주유소 수, 공간 feature |
| 휘발유 정책 적용 일별 데이터 | 전국 휘발유 정책 적용 적정가격과 band |
| 경유 정책 적용 일별 데이터 | 전국 경유 정책 적용 적정가격과 band |

정책 적용 일별 데이터의 핵심 컬럼은 `적정가격_정책적용_원L`, `적정범위_정책적용_하한_원L`, `적정범위_정책적용_상한_원L`입니다.

## 처리 로직

### 1. 전국 적정가격 정리

`data-analysis/05`의 휘발유/경유 CSV를 읽어 ASCII 컬럼명으로 정리한 `national_fair_prices.parquet`을 만듭니다.

주요 변환 컬럼:

| 컬럼 | 의미 |
|---|---|
| `{fuel}_national_actual_price_da` | data-analysis 전국 실제 가격 |
| `{fuel}_national_fair_price_no_policy` | 정책 미반영 전국 적정가격 |
| `{fuel}_national_fair_price_policy` | 정책 적용 전국 적정가격 |
| `{fuel}_national_fair_band_low_policy` | 정책 적용 적정범위 하한 |
| `{fuel}_national_fair_band_high_policy` | 정책 적용 적정범위 상한 |
| `{fuel}_policy_effect` | 정책 적용으로 낮아진 가격 |

### 2. grid 기준 전국 실제 가격 계산

AI 02의 `grid.parquet`에서 유종별 가격과 station count를 사용해 날짜별 전국 가중평균 실제 가격을 다시 계산합니다.

```text
national_actual_price_grid
  = sum(grid_price_mean * station_count) / sum(station_count)
```

`data-analysis`의 전국 실제 가격과 AI grid에서 재계산한 전국 실제 가격은 원천/집계 기준이 조금 다를 수 있으므로, 둘의 차이도 `national_actual_gap_grid_vs_da`로 남깁니다.

### 3. 격자별 target 생성

각 유종별로 다음 컬럼을 추가합니다.

| 컬럼 | 의미 |
|---|---|
| `{fuel}_national_actual_price_grid` | grid panel에서 계산한 전국 실제 가중평균 가격 |
| `{fuel}_national_actual_gap_grid_vs_da` | grid 기준 전국가격과 data-analysis 전국가격 차이 |
| `{fuel}_national_gap_policy` | 전국 실제 가격 - 정책 적용 전국 적정가격 |
| `{fuel}_actual_spread_grid` | 격자 실제 가격 - grid 기준 전국 실제 가격 |
| `{fuel}_grid_fair_price_target` | 최종 격자별 적정가격 target |
| `{fuel}_grid_fair_band_low_policy` | 격자별 정책 적용 적정범위 하한 |
| `{fuel}_grid_fair_band_high_policy` | 격자별 정책 적용 적정범위 상한 |
| `{fuel}_grid_fair_gap_to_actual` | 실제 격자 가격 - 격자 적정가격 |

`{fuel}`은 `gasoline` 또는 `diesel`입니다.

## 생성 결과

| 항목 | 값 |
|---|---:|
| 전체 행 | 63,800,291 |
| unique grid | 12,338 |
| 기간 | 2008-04-15 ~ 2026-06-11 |
| 휘발유 target 행 | 59,613,708 |
| 경유 target 행 | 45,487,926 |
| 휘발유 2026 target 행 | 1,443,008 |
| 경유 2026 target 행 | 1,443,008 |
| 휘발유 target 가중평균 | 1,675.984원/L |
| 경유 target 가중평균 | 1,487.338원/L |
| 휘발유 전국 gap 평균 | -17.521원/L |
| 경유 전국 gap 평균 | -40.856원/L |

경유 target 행이 휘발유보다 적은 이유는 경유 국제 benchmark와 정책 적용 적정가격의 유효 기간이 더 짧기 때문입니다.

## 산출물

| 산출물 | 내용 |
|---|---|
| `outputs/national_fair_prices.parquet` | 휘발유/경유 전국 적정가격 정리본 |
| `outputs/grid_target.parquet` | AI 04 입력이 되는 격자별 target dataset |
| `outputs/target_dataset_summary.csv` | 행 수, target coverage, 평균 gap 요약 |
| `outputs/target_dataset_metadata.json` | 입력 signature, target 공식, 산출물 summary |

## 다음 단계 연결

AI 04는 이 단계의 `grid_fair_price_target`을 학습 target으로 사용했습니다. 다만 첫 LSTM 실험 결과, 전국 적정가격 레벨까지 모델이 직접 예측하게 하는 구조는 2026년 급격한 전국 레벨 변화에 취약했습니다. 다음 모델에서는 이 target dataset을 유지하되, AI가 직접 예측할 대상은 격자 spread 또는 지역 보정값으로 좁히는 방향이 더 적합합니다.
