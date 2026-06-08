# 04. Fair Price Model

이 단계는 전처리 통합 데이터와 시차 분석 결과를 사용해 정책 미반영 전국 단위 주유소 적정가격과 적정 가격대를 산정합니다. 원본 Colab 노트북의 `2단계: 적정 가격 선정` 구간을 분리했습니다.

핵심 목적은 휘발유와 경유 각각에 대해 `국제제품가격 -> 국내 주유소 소비자가격` 경로의 적정가격을 만들고, 실제 가격이 적정 가격대 안에 있는지 판정하는 것입니다.

## 실행 파일

- `04_fair_price_model.ipynb`: Colab에서 단독 실행 가능한 적정가격 모델 노트북

첫 설정 셀의 기본 경로는 현재 작업자가 사용한 원본 경로를 그대로 둡니다.

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
```

실행 결과는 원본 코드 기준으로 다음 폴더에 저장됩니다.

```text
{ROOT_PATH}/적정가격대선정_v2/
```

## 입력 데이터

이 단계는 다음 파일과 폴더를 필요로 합니다.

| 입력 | 경로 | 용도 |
| --- | --- | --- |
| 전처리 통합 데이터 | `{PROCESSED_PATH}/분석용_일별_통합데이터.csv` | 실제 소매가격, 국제제품가격, 정유사 세전 공급가격을 포함한 기본 데이터 |
| 주유소 휘발유 시차 분석 | `{ROOT_PATH}/시차분석_v2/gasoline_lag_analysis/` | 휘발유 주유소 direct 모델의 IRF feature |
| 주유소 경유 시차 분석 | `{ROOT_PATH}/시차분석_v2/diesel_lag_analysis/` | 경유 주유소 direct 모델의 IRF feature |
| 정유사 휘발유 주간 시차 분석 | `{ROOT_PATH}/시차분석_v2/gasoline_refinery_weekly_lag_analysis/` | 정유사 주간 diagnostic 모델의 IRF feature |
| 정유사 경유 주간 시차 분석 | `{ROOT_PATH}/시차분석_v2/diesel_refinery_weekly_lag_analysis/` | 정유사 주간 diagnostic 모델의 IRF feature |

시차 분석 폴더에서는 `analysis_summary.csv`와 `impulse_response_path.csv`를 읽습니다. IRF는 음수 반응을 제외하고 양수 반응을 가중치로 사용하며, 주유소 모델은 최소 1일 lag부터 사용합니다.

## 사용 컬럼

| 유종 | 소매가격 컬럼 | 국제제품가격 후보 | 정유사 세전 후보 |
| --- | --- | --- | --- |
| 휘발유 | `보통휘발유_평균` | `휘발유92RON_원리터`, `휘발유95RON_원리터` | `정유소_세전_보통휘발유` |
| 경유 | `자동차용경유_평균` | `경유0.001_원리터`, `경유0.05_원리터` | `정유소_세전_자동차용경유` |

실행 로그 기준으로 최종 사용된 국제제품가격 컬럼은 다음과 같습니다.

| 유종 | 실제 사용 benchmark |
| --- | --- |
| 휘발유 | `휘발유92RON_원리터` |
| 경유 | `경유0.001_원리터` |

## 모델 구조

최종 주유소 적정가격 모델은 direct 모델로 고정되어 있습니다.

```python
USE_REFINERY_FOR_RETAIL_MODEL = False
RUN_REFINERY_DIAGNOSTIC = True
FINAL_RETAIL_MODEL_MODE = "direct"
```

즉 정유사 세전 공급가격을 주유소 모델의 입력으로 사용하지 않습니다. 정유사 weekly 모델은 별도 진단용으로만 실행합니다.

주유소 direct 모델은 rolling Huber 회귀로 학습합니다. 국제제품가격 IRF feature, 상승/하락 분해 feature, 차분, 변동성, 이동평균, 달력 변수를 사용합니다. 각 시점의 예측은 과거 일정 관측치만 사용해 rolling 방식으로 적합합니다.

정유사 weekly 모델도 Huber 기반으로 실행하지만, 최종 주유소 적정가격 산정에는 연결하지 않습니다. 이는 원본 코드의 “최종 주유소 모델에는 정유사 데이터를 사용하지 않는다”는 기준을 그대로 따른 것입니다.

## 정책 제외

모델 학습과 band 평가에서는 유류세 조정, 가격통제 등 정책 충격 구간을 제외합니다. 기본 제외 구간은 다음과 같습니다.

| 기간 | 라벨 |
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

정책 제외 구간에는 기본적으로 시작 전 14일, 종료 후 30일의 완충기간을 둡니다. 2026년 holdout 구간은 완충기간 없이 전체 연도 제외로 설정되어 있습니다.

## 저장 결과

코드 기준으로 다음 결과가 저장됩니다.

```text
{ROOT_PATH}/적정가격대선정_v2/
  gasoline_production_predictions_full_calendar.csv
  diesel_production_predictions_full_calendar.csv
  gasoline_yearly_plots_v2/
    gasoline_{year}_step2_v2.png
  diesel_yearly_plots_v2/
    diesel_{year}_step2_v2.png
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
```

`production_predictions_full_calendar.csv`는 이후 정책 적용 단계의 핵심 입력입니다. 이 파일의 `pred_gross`는 정책 미반영 적정가격이며, 3단계에서 국내 정책을 별도로 반영하기 위해 그대로 저장됩니다.

## 출력셀 기반 실행 결과

원본 Colab 출력셀에는 휘발유와 경유 모두 실행 완료 로그가 남아 있습니다.

| 유종 | 일별 주유소 frame | direct 적정가격 non-null | 정유사 weekly frame | 정유사 진단 non-null | 최종 모델 |
| --- | ---: | ---: | ---: | ---: | --- |
| 휘발유 | 6,547행 | 6,016 | 932행 | 813 | direct |
| 경유 | 6,547행 | 4,604 | 693행 | 610 | direct |

저장 로그 기준 최종 파일은 다음 두 개입니다.

```text
{ROOT_PATH}/적정가격대선정_v2/gasoline_production_predictions_full_calendar.csv
{ROOT_PATH}/적정가격대선정_v2/diesel_production_predictions_full_calendar.csv
```

## 모델 성능

출력셀의 model metrics를 기준으로 정리하면 다음과 같습니다.

| 유종 | 모델 | clean n | MAE | median AE | bias | ACF1 | ACF7 | 용도 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 휘발유 | `gasoline_retail_direct_huber` | 3,936 | 11.970 | 9.156 | 0.062 | 0.986 | 0.883 | 최종 direct 주유소 모델 |
| 휘발유 | `gasoline_selected_direct` | 3,936 | 11.970 | 9.156 | 0.062 | 0.986 | 0.883 | 선택된 최종 모델 |
| 휘발유 | `gasoline_refinery_weekly_huber` | 514 | 20.436 | 17.648 | 3.150 | 0.653 | 0.185 | 정유사 진단용 |
| 경유 | `diesel_retail_direct_huber` | 2,659 | 11.240 | 7.799 | -0.975 | 0.989 | 0.898 | 최종 direct 주유소 모델 |
| 경유 | `diesel_selected_direct` | 2,659 | 11.240 | 7.799 | -0.975 | 0.989 | 0.898 | 선택된 최종 모델 |
| 경유 | `diesel_refinery_weekly_huber` | 331 | 29.741 | 21.408 | 4.427 | 0.822 | 0.540 | 정유사 진단용 |

최종 주유소 direct 모델 기준 MAE는 휘발유 약 11.97원/L, 경유 약 11.24원/L입니다. 경유 direct 모델은 bias가 -0.975원/L로 약간 과대 예측 방향의 잔차가 남고, 휘발유 direct 모델은 bias가 0.062원/L로 평균 잔차가 거의 0에 가깝습니다.

다만 direct 모델의 잔차 ACF1과 ACF7이 매우 높습니다. 이는 가격 수준 데이터의 시계열 지속성이 강하게 남아 있다는 뜻입니다. 따라서 MAE만으로 모델을 평가하지 말고, 정책 제외 구간과 band 판정 결과를 함께 봐야 합니다.

## 적정 가격대 band 결과

출력셀의 band metrics를 기준으로 정리하면 다음과 같습니다.

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

band 선택 함수는 empirical coverage가 최소 0.60 이상인 후보를 우선합니다. 출력셀 기준으로 휘발유와 경유 모두 target coverage 0.70에서 empirical coverage가 각각 0.650, 0.641로 0.60 이상을 만족합니다. 따라서 실제 선택 band는 0.70 coverage 후보일 가능성이 높습니다.

## 결과 해석

휘발유와 경유 모두 최종 모델은 direct 주유소 모델입니다. 정유사 two-layer 모델은 최종 사용하지 않고, 정유사 weekly 모델은 진단용으로만 산출됩니다.

휘발유 direct 모델은 clean MAE가 약 11.97원/L이고 bias가 거의 0에 가까워 전국 평균 소비자가격 수준에서는 평균적인 편향이 작습니다. 경유 direct 모델은 clean MAE가 약 11.24원/L로 휘발유보다 조금 낮지만, bias는 -0.975원/L로 휘발유보다 큽니다.

band 폭은 같은 coverage target에서 경유가 휘발유보다 좁습니다. 예를 들어 target coverage 0.70에서 휘발유 mean width는 약 25.01원/L, 경유 mean width는 약 20.95원/L입니다. 이는 경유 모델의 적정 가격대가 출력셀 기준 더 좁게 산정되었다는 뜻입니다.

## 확인 한계

현재 이 레포에는 4단계 실행 결과 파일이 제공되어 있지 않습니다. 따라서 이 README에서 확정한 결과는 원본 Colab 출력셀에 남아 있는 로그와 표에 근거합니다.

다음 항목은 결과 CSV와 PNG 파일이 있어야 정확히 정리할 수 있습니다.

- 최종 production CSV의 전체 행 수
- 최종 production CSV의 날짜 범위
- 최종 production CSV의 전체 컬럼 목록
- `pred_gross`, `band_low`, `band_high`, `judge`의 결측치 수
- 연도별 그래프 파일 개수와 실제 생성 연도
- 2026년 holdout 구간의 예측값 존재 여부
- 실제 가격이 band 위/아래에 있는 날짜 수

이 항목까지 정리하려면 `적정가격대선정_v2` 폴더의 실행 결과 파일이 필요합니다.

## 다음 단계 연결

다음 `05_policy_application` 단계에서는 이 단계의 `*_production_predictions_full_calendar.csv`를 입력으로 사용해 유류세 인하 등 국내 정책을 반영합니다.

정책 적용 전 기준 핵심 컬럼은 다음과 같습니다.

| 컬럼 | 의미 |
| --- | --- |
| `pred_gross` | 정책 미반영 적정 소비자가격 |
| `band_low` | 적정 가격대 하한 |
| `band_high` | 적정 가격대 상한 |
| `judge` | 실제 가격이 적정 가격대 대비 저렴/적정/비쌈인지 판정 |
| `selected_model_name` | 최종 모델명 |
| `selected_band_coverage` | 선택된 band coverage |

## 검토 결론

4단계 코드는 Colab에서 단독 실행할 수 있도록 분리했습니다. 원본 출력셀만으로도 최종 모델이 direct 모델이라는 점, 휘발유/경유 모델 성능, band 성능, 최종 저장 경로는 정리할 수 있었습니다.

다만 결과 파일이 없으므로 production CSV 내부 검증과 그래프 파일 검토는 아직 불가능합니다. 이 부분을 완성하려면 `적정가격대선정_v2` 실행 결과 폴더가 필요합니다.
