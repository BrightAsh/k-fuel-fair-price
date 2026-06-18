# 03. Target Dataset Build

AI 03은 AI 02의 `grid.parquet`을 수정하지 않고, `data-analysis/05_policy_application`의 전국 적정가격 산출물을 결합해 격자별 적정가격 target dataset을 새로 만드는 단계입니다.

## 실행 파일

| 파일 | 역할 |
|---|---|
| `03_target_dataset_build.py` | 로컬/PyCharm/Anaconda 기준 target dataset 생성 스크립트 |
| `environment-conda.yml` | 실행 환경 정의 |

## 입력

| 입력 | 경로 | 내용 |
|---|---|---|
| AI 02 격자 패널 | `ai-model/02_spatial_grid_build/outputs/grid.parquet` | 일별 500m 격자별 실제 유가, 주유소 수, 시설/공시지가/위치 feature |
| 휘발유 정책 적용 적정가격 | `data-analysis/05_policy_application/outputs/휘발유/일별_정책적용_데이터_휘발유.csv` | 전국 단위 휘발유 정책 적용 적정가격 |
| 경유 정책 적용 적정가격 | `data-analysis/05_policy_application/outputs/경유/일별_정책적용_데이터_경유.csv` | 전국 단위 경유 정책 적용 적정가격 |

`grid.parquet`은 AI 02의 원본 산출물이므로 이 단계에서 덮어쓰지 않습니다.

## Target 정의

`data-analysis`는 전국 평균 기준 적정가격을 만들었습니다. AI 03은 이 전국 적정가격을 격자 단위로 확장합니다.

```text
national_actual_price_grid(t)
  = grid.parquet에서 유종별 station_count로 가중평균한 전국 실제 가격

grid_actual_spread(t)
  = grid_actual_price(t) - national_actual_price_grid(t)

grid_fair_price_target(t)
  = national_fair_price_policy(t) + grid_actual_spread(t)

fair_price_delta_target(t)
  = grid_fair_price_target(t) - grid_actual_price(t-1)
```

즉 “전국 기준으로는 data-analysis가 계산한 정책 적용 적정가격을 따르고, 격자별 상대적 비싸고 싼 정도는 실제 격자 spread로 유지”합니다.
전일 가격 대비 delta target은 AI 04 학습 frame을 만들 때 `grid_fair_price_target`과 전일 실제 가격으로 계산합니다.

## 주요 출력

| 출력 | 내용 |
|---|---|
| `outputs/national_fair_prices.parquet` | `data-analysis/05`의 휘발유/경유 전국 적정가격을 ASCII 컬럼으로 정리한 중간 산출물 |
| `outputs/grid_target.parquet` | AI 04 학습 입력이 되는 격자별 target dataset |
| `outputs/target_dataset_summary.csv` | 행 수, 격자 수, target 생성 가능 행 수, 2026 target 행 수, 평균 gap 요약 |
| `outputs/target_dataset_metadata.json` | 입력 파일 signature, target 공식, 출력 경로, summary |

`grid_target.parquet`은 원본 `grid.parquet`의 컬럼을 유지하고 다음 target 관련 컬럼을 추가합니다.

| 컬럼 | 의미 |
|---|---|
| `{fuel}_national_actual_price_grid` | grid panel에서 계산한 전국 실제 가중평균 가격 |
| `{fuel}_national_actual_price_da` | data-analysis 전국 실제 가격 |
| `{fuel}_national_actual_gap_grid_vs_da` | grid 기준 전국 실제 가격과 data-analysis 전국 실제 가격 차이 |
| `{fuel}_national_fair_price_policy` | 정책 적용 전국 적정가격 |
| `{fuel}_national_gap_policy` | 전국 실제 가격과 정책 적용 전국 적정가격 차이 |
| `{fuel}_actual_spread_grid` | 해당 격자의 실제 가격 spread |
| `{fuel}_grid_fair_price_target` | 최종 격자별 적정가격 target |
| `{fuel}_grid_fair_band_low_policy` | 격자별 정책 적용 적정범위 하한 |
| `{fuel}_grid_fair_band_high_policy` | 격자별 정책 적용 적정범위 상한 |
| `{fuel}_grid_fair_gap_to_actual` | 실제 격자 가격 - 격자 적정가격 |

`{fuel}`은 `gasoline` 또는 `diesel`입니다.

## 실행

```powershell
cd C:\Users\user\Desktop\산업부\k-fuel-fair-price
conda env create -f .\ai-model\03_target_dataset_build\environment-conda.yml
conda activate k-fuel-stage3
python .\ai-model\03_target_dataset_build\03_target_dataset_build.py
```

간단한 SQL/경로 점검만 하고 싶으면 smoke output을 만들 수 있습니다.

```powershell
python .\ai-model\03_target_dataset_build\03_target_dataset_build.py --smoke-limit 1000
```

smoke 실행은 `outputs/grid_target_smoke.parquet`을 만들며, AI 04 기본 입력으로 사용하지 않습니다.

## AI 04와의 관계

AI 04는 이 단계의 `outputs/grid_target.parquet`을 읽어 학습합니다. 2026년 이후 행은 학습에 사용하지 않고 test로만 사용합니다. train/validation에서는 기존 정책 기간과 29일 입력 history 안에 정책 기간이 포함된 행을 제외합니다.
