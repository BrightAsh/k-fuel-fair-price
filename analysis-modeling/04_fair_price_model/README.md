# 04. 적정 가격대 선정

이 단계는 전처리 통합 데이터와 시차 분석 결과를 사용해 전국 단위 주유소 적정가격과 적정 가격대를 산정하는 단계입니다. 원본 Colab의 `2단계-v2: 국제제품가격 기반 정유사/주유소 2층 적정가격 모델` 구간을 분리했습니다.

핵심 목적은 휘발유와 경유 각각에 대해 `국제제품가격 -> 국내 주유소 소비자가격` 경로의 정책 미반영 적정가격을 만들고, 실제 가격이 적정 가격대 안에 있는지 `저렴/적정/비쌈`으로 판정하는 것입니다.

## 실행 파일

- `04_fair_price_model.ipynb`: Colab에서 단독 실행 가능한 적정가격대 선정 노트북

노트북의 기본 경로는 원본 작업 경로를 그대로 유지했습니다. 다른 사용자는 아래 경로만 본인 Drive 구조에 맞게 수정하면 됩니다.

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
OUTPUT_DIR = Path(ROOT_PATH) / "적정가격대선정_v2"
```

## 입력 데이터

| 입력 | 원본 기준 경로 | 용도 |
| --- | --- | --- |
| 전처리 통합 일별 데이터 | `{PROCESSED_PATH}/분석용_일별_통합데이터.csv` | 실제 주유소 평균 가격, 국제제품가격, 정유사 세전 공급가격을 포함한 기본 데이터 |
| 휘발유 주유소 시차 분석 | `{ROOT_PATH}/시차분석_v2/gasoline_lag_analysis/` | 휘발유 direct 모델의 IRF feature와 lag 후보 |
| 경유 주유소 시차 분석 | `{ROOT_PATH}/시차분석_v2/diesel_lag_analysis/` | 경유 direct 모델의 IRF feature와 lag 후보 |
| 휘발유 정유사 주간 시차 분석 | `{ROOT_PATH}/시차분석_v2/gasoline_refinery_weekly_lag_analysis/` | 정유사 주간 diagnostic 모델의 IRF feature |
| 경유 정유사 주간 시차 분석 | `{ROOT_PATH}/시차분석_v2/diesel_refinery_weekly_lag_analysis/` | 정유사 주간 diagnostic 모델의 IRF feature |

시차 분석 폴더에서는 `analysis_summary.csv`와 `impulse_response_path.csv`를 읽습니다. IRF는 과도한 음수 반응을 제외하고 양수 반응 중심의 가중 feature를 만드는 데 사용됩니다.

## 사용 컬럼

| 유종 | 실제 판매가격 컬럼 | 국제제품가격 후보 | 정유사 세전 공급가격 후보 |
| --- | --- | --- | --- |
| 휘발유 | `보통휘발유_평균` | `휘발유92RON_달러`, `휘발유95RON_달러` | `정유사세전_보통휘발유` |
| 경유 | `자동차용경유_평균` | `경유0.001_달러`, `경유0.05_달러` | `정유사세전_자동차용경유` |

실행 결과와 최종 production CSV 기준으로 실제 선택된 benchmark는 아래와 같습니다.

| 유종 | 실제 사용 benchmark |
| --- | --- |
| 휘발유 | `휘발유92RON_달러` |
| 경유 | `경유0.001_달러` |

## 모델 구조

최종 주유소 적정가격 모델은 direct 모델로 고정되어 있습니다.

```python
USE_REFINERY_FOR_RETAIL_MODEL = False
RUN_REFINERY_DIAGNOSTIC = True
FINAL_RETAIL_MODEL_MODE = "direct"
```

따라서 정유사 세전 공급가격을 최종 주유소 모델의 입력으로 사용하지 않습니다. 정유사 weekly 모델은 별도 진단 산출물로만 생성됩니다.

주유소 direct 모델은 rolling Huber 회귀로 학습됩니다. 국제제품가격 IRF feature, 상승/하락 분해 feature, 차분, 변동성, 이동평균, 달력 변수를 사용하며, 각 시점의 예측은 과거 관측치만 사용하는 rolling 방식입니다.

최종 적정가격 컬럼 `pred_gross`는 정책 미반영 전국 단위 소비자가격입니다. 이후 정책 적용 단계에서 유류세 인하, 최고가격제 같은 국내 정책 효과를 별도로 반영하기 위해 이 값을 그대로 넘깁니다.

## 정책 제외 구간

모델 학습과 band 평가에서는 유류세 조정, 가격통제, 정책 충격 구간을 제외합니다. 기본 제외 구간은 아래와 같습니다.

| 기간 | 사유 |
| --- | --- |
| 2008-03-10 ~ 2008-12-31 | `fuel_tax_cut_2008` |
| 2011-04-07 ~ 2011-07-06 | `fuel_tax_cut_2011_100won` |
| 2018-11-06 ~ 2019-05-06 | `fuel_tax_cut_2018_15pct` |
| 2019-05-07 ~ 2019-08-31 | `fuel_tax_cut_2019_7pct` |
| 2021-11-12 ~ 2022-04-30 | `fuel_tax_cut_2021_20pct` |
| 2022-05-01 ~ 2022-06-30 | `fuel_tax_cut_2022_30pct` |
| 2022-07-01 ~ 2022-12-31 | `fuel_tax_cut_2022_37pct` |
| 2023-01-01 ~ 2024-06-30 | `fuel_tax_cut_2023_2024` |
| 2024-07-01 ~ 2024-10-31 | `fuel_tax_cut_2024_partial` |
| 2024-11-01 ~ 2025-04-30 | `fuel_tax_cut_2024_2025_partial` |
| 2025-05-01 ~ 2025-10-31 | `fuel_tax_cut_2025_readjusted` |
| 2025-11-01 ~ 2026-04-30 | `fuel_tax_cut_2025_2026_partial` |
| 2026-03-13 ~ 2026-03-26 | `price_cap_2026_round1` |
| 2026-01-01 ~ 2026-12-31 | `holdout_2026_full_year` |

일반 정책 구간은 시작 전 14일, 종료 후 30일의 완충 기간을 둡니다. 2026년 holdout 구간은 완충 없이 전체 연도를 학습과 band 보정에서 제외합니다.

## 첨부 결과 파일 검증

사용자가 제공한 `result.zip`은 원본 Drive 경로의 `적정가격대선정_v2` 실행 결과로 확인했습니다. 노트북의 저장 경로와 파일명이 압축 파일 구조와 일치합니다.

```text
{ROOT_PATH}/적정가격대선정_v2/
  gasoline_production_predictions_full_calendar.csv
  diesel_production_predictions_full_calendar.csv
  gasoline/
    gasoline_step2_v2_daily_frame.csv
    gasoline_retail_model_internal_predictions.csv
    gasoline_step2_v2_weekly_refinery_frame.csv
    gasoline_refinery_weekly_predictions.csv
    gasoline_model_comparison_v2.csv
    gasoline_band_comparison_v2.csv
  diesel/
    diesel_step2_v2_daily_frame.csv
    diesel_retail_model_internal_predictions.csv
    diesel_step2_v2_weekly_refinery_frame.csv
    diesel_refinery_weekly_predictions.csv
    diesel_model_comparison_v2.csv
    diesel_band_comparison_v2.csv
  gasoline_yearly_plots_v2/
    gasoline_{year}_step2_v2.png
  diesel_yearly_plots_v2/
    diesel_{year}_step2_v2.png
```

현재 이 레포의 `outputs/`에는 첨부 결과 중 CSV 14개와 PNG 38개를 반영했습니다. README나 `.gitkeep` 같은 보조 파일은 넣지 않았습니다.

| 구분 | 확인 결과 |
| --- | ---: |
| 최상위 production CSV | 2개 |
| 유종별 상세 CSV | 휘발유 6개, 경유 6개 |
| 연도별 그래프 PNG | 휘발유 19개, 경유 19개 |
| 그래프 연도 범위 | 2008년 ~ 2026년 |
| outputs 내 결과 외 파일 | 없음 |

## 최종 production CSV

`*_production_predictions_full_calendar.csv`는 이후 정책 적용 단계의 핵심 입력입니다.

| 유종 | 행 수 | 날짜 범위 | 실제 가격 non-null | 국제제품가격 non-null | `pred_gross` non-null | band/judge non-null | 선택 모델 | 선택 band |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: |
| 휘발유 | 6,547 | 2008-04-15 ~ 2026-03-18 | 6,547 | 6,547 | 6,016 | 5,896 | direct | 0.70 |
| 경유 | 6,547 | 2008-04-15 ~ 2026-03-18 | 6,547 | 4,854 | 4,604 | 4,484 | direct | 0.70 |

최종 production CSV의 컬럼은 아래 20개입니다.

```text
date
actual_gross_full
international_full
pred_gross
band_low
band_high
pred_pretax
tax_sum_full
selected_model_name
selected_model_name_daily
selected_band_coverage
judge
inside_band
below_band
above_band
is_excluded
fair_retail_direct
retail_gap_원L
source_retail_col
source_intl_col
```

`actual_gross_full`은 실제 전국 평균 소비자가격이고, `pred_gross`는 정책 미반영 적정 소비자가격입니다. `retail_gap_원L`은 `actual_gross_full - pred_gross`로 해석할 수 있습니다. 양수면 실제 가격이 적정가격보다 높은 방향이고, 음수면 실제 가격이 적정가격보다 낮은 방향입니다.

## 판정 결과

`judge`는 실제 가격이 band보다 낮으면 `저렴`, band 안이면 `적정`, band보다 높으면 `비쌈`으로 표시됩니다.

| 유종 | 판정 없음 | 저렴 | 적정 | 비쌈 | 판정 가능 합계 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 휘발유 | 651 | 2,607 | 2,500 | 789 | 5,896 |
| 경유 | 2,063 | 2,307 | 1,670 | 507 | 4,484 |

판정 가능 합계는 `band_low`, `band_high`, `judge`가 모두 존재하는 행 수와 일치합니다. 따라서 판정 집계 자체는 CSV 내부 컬럼 간 정합성이 맞습니다.

## 가격 통계

| 유종 | 실제 가격 평균 | 적정가격 평균 | band 평균 폭 | gap 평균 | gap 절대평균 | gap 절대중앙값 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 휘발유 | 1,660.079 | 1,577.534 | 24.372 | -54.332 | 62.575 | 16.685 |
| 경유 | 1,499.363 | 1,076.508 | 17.553 | -87.364 | 93.503 | 20.602 |

위 통계는 전체 production CSV 기준 집계입니다. 경유는 국제제품가격 non-null 기간이 휘발유보다 짧기 때문에 적정가격과 판정 가능 행 수도 작습니다.

## 모델 성능

`*_model_comparison_v2.csv` 기준 성능은 아래와 같습니다.

| 유종 | 모델 | clean n | MAE | median AE | bias | ACF1 | ACF7 | 용도 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 휘발유 | `gasoline_retail_direct_huber` | 3,936 | 11.970 | 9.156 | 0.062 | 0.986 | 0.883 | 최종 direct 주유소 모델 |
| 휘발유 | `gasoline_selected_direct` | 3,936 | 11.970 | 9.156 | 0.062 | 0.986 | 0.883 | 선택된 최종 모델 |
| 휘발유 | `gasoline_refinery_weekly_huber` | 514 | 20.436 | 17.648 | 3.150 | 0.653 | 0.185 | 정유사 진단 모델 |
| 경유 | `diesel_retail_direct_huber` | 2,659 | 11.240 | 7.799 | -0.975 | 0.989 | 0.898 | 최종 direct 주유소 모델 |
| 경유 | `diesel_selected_direct` | 2,659 | 11.240 | 7.799 | -0.975 | 0.989 | 0.898 | 선택된 최종 모델 |
| 경유 | `diesel_refinery_weekly_huber` | 331 | 29.741 | 21.408 | 4.427 | 0.822 | 0.540 | 정유사 진단 모델 |

휘발유 direct 모델은 MAE 약 11.97원/L, 경유 direct 모델은 MAE 약 11.24원/L입니다. bias는 휘발유가 0.062원/L로 거의 0에 가깝고, 경유는 -0.975원/L입니다.

다만 direct 모델의 잔차 ACF1과 ACF7이 매우 높습니다. 가격 시계열의 지속성이 강하게 남아 있다는 뜻이므로, MAE만으로 독립 오차처럼 해석하면 안 됩니다. 실서비스에서는 연속일의 오차가 비슷한 방향으로 이어질 가능성을 감안해야 합니다.

## 적정 가격대 band

`*_band_comparison_v2.csv` 기준 band 후보별 결과입니다.

### 휘발유

| target coverage | clean n | empirical coverage | mean width | interval score |
| ---: | ---: | ---: | ---: | ---: |
| 0.55 | 3,816 | 0.498 | 17.900 | 40.664 |
| 0.60 | 3,816 | 0.543 | 20.146 | 43.079 |
| 0.65 | 3,816 | 0.587 | 22.469 | 45.843 |
| 0.70 | 3,816 | 0.650 | 25.014 | 48.920 |
| 0.75 | 3,816 | 0.696 | 28.076 | 52.564 |
| 0.80 | 3,816 | 0.740 | 31.717 | 56.976 |

### 경유

| target coverage | clean n | empirical coverage | mean width | interval score |
| ---: | ---: | ---: | ---: | ---: |
| 0.55 | 2,539 | 0.494 | 14.559 | 41.516 |
| 0.60 | 2,539 | 0.543 | 16.272 | 44.476 |
| 0.65 | 2,539 | 0.592 | 18.387 | 47.898 |
| 0.70 | 2,539 | 0.641 | 20.953 | 52.055 |
| 0.75 | 2,539 | 0.687 | 24.335 | 56.838 |
| 0.80 | 2,539 | 0.735 | 28.740 | 62.635 |

최종 production CSV의 `selected_band_coverage`는 휘발유와 경유 모두 0.70입니다. 0.70 band는 두 유종 모두 empirical coverage가 0.60 이상이며, 선택 결과와 production CSV 값이 일치합니다.

## 결과 해석

첨부 결과는 코드에서 생성된 산출물로 보는 것이 맞습니다. 노트북의 `OUTPUT_DIR`, 유종별 하위 폴더, production CSV, model comparison CSV, band comparison CSV, 연도별 plot 저장 파일명이 첨부 압축 구조와 일치합니다.

CSV 내부 정합성도 큰 틀에서 맞습니다. production CSV의 `judge` 개수는 `inside_band`, `below_band`, `above_band` 개수와 대응되고, 선택 모델은 두 유종 모두 direct로 고정되어 있습니다. 연도별 PNG도 2008년부터 2026년까지 각 19개로 날짜 범위와 맞습니다.

다만 다음 값은 웹 표시나 다음 정책 적용 단계에서 반드시 처리해야 합니다.

- `pred_gross` 최솟값과 band width 최솟값이 0인 행이 존재합니다. 초기 구간, 결측 대체, rolling 예측 불가 구간의 영향일 수 있으므로 화면 표시 전에는 `pred_gross <= 0`, `band_low <= 0`, `band_high <= 0`, `band_high <= band_low` 같은 방어 필터를 두는 것이 좋습니다.
- `judge`가 비어 있는 행이 있습니다. 휘발유는 651행, 경유는 2,063행입니다. 이 행은 판정률 계산에서 제외해야 하며, 웹에서는 `판정 불가` 또는 미표시로 처리해야 합니다.
- 경유는 `international_full` non-null이 4,854행으로 전체 6,547행보다 작습니다. 경유 benchmark 데이터의 사용 가능 기간이 짧기 때문에 경유 결과는 휘발유보다 예측 가능 기간이 제한됩니다.
- 2026년은 holdout 구간으로 학습과 band 보정에서 제외되지만, production CSV에는 2026-03-18까지의 예측 결과가 포함됩니다. 추론 결과로 표시할 수는 있으나 성능 평가 표본과는 분리해서 봐야 합니다.

## 다음 단계 연결

다음 `05_policy_application` 단계에서는 이 단계의 최종 production CSV를 입력으로 사용합니다.

| 컬럼 | 다음 단계 용도 |
| --- | --- |
| `date` | 정책 적용 기준 날짜 |
| `actual_gross_full` | 실제 전국 평균 소비자가격 |
| `pred_gross` | 정책 미반영 적정 소비자가격 |
| `band_low` | 정책 미반영 적정 가격대 하한 |
| `band_high` | 정책 미반영 적정 가격대 상한 |
| `judge` | 정책 적용 전 기준의 가격 판정 |
| `selected_model_name` | 최종 모델명 |
| `selected_band_coverage` | 선택 band coverage |

## 검토 결론

4단계 결과 파일은 코드 산출물 구조와 일치하며, 이 레포의 `outputs/`에는 필요한 결과 CSV와 PNG를 모두 반영했습니다. 결과 내용도 모델 선택, band 선택, 판정 개수, 그래프 생성 범위 측면에서 정합성이 확인됩니다.

단, `pred_gross`와 band에 0 값이 존재하는 행, `judge` 결측 행, 경유 benchmark 결측 기간은 후속 정책 적용 및 웹 자동화 단계에서 명시적으로 필터링하거나 별도 상태로 처리해야 합니다.
