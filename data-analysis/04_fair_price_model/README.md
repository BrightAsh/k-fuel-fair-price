# 04. Fair Price Model

## 목적

`04_fair_price_model.ipynb`는 국제 제품가격과 03 단계의 반영 시차를 이용해 국내 주유소 소비자가격의 적정가격대(fair price band)를 산정합니다. 최종 정책 적용 단계에서 사용할 `pred_gross`, `band_low`, `band_high`, `judge`를 만드는 단계입니다.

노트북 구조는 markdown 6개, code 8개, 총 1,539줄입니다. 출력이 저장된 code 셀은 7개이며, 휘발유와 경유의 모델 성능표, band 성능표, 연도별 그래프 생성 로그가 포함되어 있습니다.

## 핵심 설계

현재 최종 모델은 정유사 가격을 소비자가격 모델에 직접 넣지 않는 direct retail 구조입니다.

```python
USE_REFINERY_FOR_RETAIL_MODEL = False
```

즉, 최종 주유소 적정가격은 국제제품가격 IRF feature와 시간 더미를 사용한 rolling Huber 모델로 계산합니다. 정유사 주간 모델은 별도 진단 산출물로 유지합니다.

## 입력

| 입력 | 사용 내용 |
|---|---|
| 01 통합 데이터 | 국내 주유소 가격, 국제제품가격, 유류세, 정유사 세전 공급가격 |
| 03 `gasoline_lag_analysis` | 휘발유 일별 IRF, 소비자가격 반영 시차 |
| 03 `diesel_lag_analysis` | 경유 일별 IRF, 소비자가격 반영 시차 |
| 03 `gasoline_refinery_weekly_lag_analysis` | 휘발유 정유사 주간 IRF |
| 03 `diesel_refinery_weekly_lag_analysis` | 경유 정유사 주간 IRF |

## 모델 로직

1. 03 단계의 `impulse_response_path.csv`를 읽어 국제제품가격을 IRF 가중 feature로 변환합니다.
2. 일별 주유소 모델 feature를 만듭니다.
   - `intl_irf`
   - 상승/하락 분해 `intl_irf_up`, `intl_irf_down`
   - 단기 변화 `intl_irf_diff_1`, `intl_irf_diff_7`
   - 변동성 `intl_irf_vol_7`, `intl_irf_vol_14`
   - 이동평균 `intl_irf_ma_7`, `intl_irf_ma_30`
   - `trend`, 요일 더미, 월 더미
3. 정책 충격 기간과 2026년 holdout은 학습 및 band calibration에서 제외합니다.
4. rolling window마다 `HuberRegressor`를 학습해 이상치에 덜 민감한 적정가격을 산정합니다.
5. 잔차 기반 band 후보 coverage 0.55~0.80을 비교하고, 최종 운영 band는 coverage 0.70을 사용합니다.
6. 실제 국내가격이 band 아래면 `저렴`, band 안이면 `적정`, band 위면 `비쌈`으로 판정합니다.

## 최종 운영 산출물

| 파일 | 행 | 열 | 기간 |
|---|---:|---:|---|
| `outputs/gasoline_production_predictions_full_calendar.csv` | 6,630 | 20 | 2008-04-15 ~ 2026-06-09 |
| `outputs/diesel_production_predictions_full_calendar.csv` | 6,630 | 20 | 2008-04-15 ~ 2026-06-09 |

운영 CSV의 주요 컬럼은 다음과 같습니다.

| 컬럼 | 의미 |
|---|---|
| `actual_gross_full` | 실제 국내 주유소 소비자가격 |
| `international_full` | 국제제품가격 원화/리터 |
| `pred_gross` | 정책 미반영 기준 적정 소비자가격 |
| `band_low`, `band_high` | 적정가격 하한/상한 |
| `selected_model_name` | 최종 모델. 현재 모두 `direct` |
| `selected_band_coverage` | 운영 band target. 현재 모두 `0.7` |
| `judge` | `저렴`, `적정`, `비쌈` 판정 |
| `fair_retail_direct` | direct retail Huber 모델 적정가격 |
| `retail_gap_원L` | 실제가격 - 적정가격 |
| `source_retail_col`, `source_intl_col` | 사용한 국내가격/국제가격 원천 컬럼 |

## 운영 파일 결측과 판정 분포

| 유종 | actual 비결측 | international 비결측 | pred 비결측 | band 비결측 | 판정 가능일 | 모델 | band |
|---|---:|---:|---:|---:|---:|---|---:|
| 휘발유 | 6,630 | 6,630 | 6,099 | 5,979 | 5,979 | direct | 0.70 |
| 경유 | 6,630 | 4,937 | 4,687 | 4,567 | 4,567 | direct | 0.70 |

경유는 `경유0.001_원리터`의 비결측 기간이 4,937일이라 휘발유보다 예측 가능 기간이 짧습니다. band는 rolling calibration에 필요한 잔차 이력이 추가로 필요하므로 `pred_gross`보다 비결측 수가 더 적습니다.

| 유종 | 저렴 | 적정 | 비쌈 | 공백 |
|---|---:|---:|---:|---:|
| 휘발유 | 2,690 | 2,500 | 789 | 651 |
| 경유 | 2,390 | 1,670 | 507 | 2,063 |

## 가격 분포와 gap

| 유종 | 실제가격 평균 | 적정가격 평균 | band 평균 폭 | gap 평균 | gap 중앙값 | gap 최소 | gap 최대 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 휘발유 | 1,664.020 | 1,726.984 | 27.134 | -60.290 | -10.461 | -651.448 | 76.760 |
| 경유 | 1,505.244 | 1,556.227 | 25.775 | -103.462 | -13.484 | -1,421.988 | 44.631 |

`gap = actual_gross_full - pred_gross`입니다. 평균 gap이 음수라는 것은 전체 기간 평균으로 실제가격이 모델 적정가격보다 낮은 날이 많았다는 뜻입니다. 다만 정책 인하 기간은 05 단계에서 별도로 보정하므로, 이 표는 정책 미반영 기준 적정가격과의 차이입니다.

## 모델 성능

학습 clean sample 기준 성능은 다음과 같습니다.

| 모델 | clean n | MAE | median AE | bias | resid ACF1 | resid ACF7 |
|---|---:|---:|---:|---:|---:|---:|
| `gasoline_retail_direct_huber` | 3,936 | 11.970 | 9.156 | 0.062 | 0.986 | 0.883 |
| `gasoline_refinery_weekly_huber` | 514 | 20.436 | 17.648 | 3.150 | 0.653 | 0.185 |
| `diesel_retail_direct_huber` | 2,659 | 11.240 | 7.799 | -0.975 | 0.989 | 0.898 |
| `diesel_refinery_weekly_huber` | 331 | 29.741 | 21.408 | 4.427 | 0.822 | 0.540 |

주유소 direct 모델은 MAE가 휘발유 11.97원/L, 경유 11.24원/L로 정유사 weekly 진단 모델보다 작습니다. 따라서 최종 소비자가격 적정가격에는 direct retail 모델을 사용합니다. 정유사 weekly 모델은 05 단계의 정유사 최고가격제 점검을 위한 보조 산출물입니다.

## Band 후보 비교

최종 운영 band는 target coverage 0.70입니다. 후보별 성능은 아래와 같습니다.

### 휘발유

| target coverage | clean n | empirical coverage | 평균 폭 | interval score |
|---:|---:|---:|---:|---:|
| 0.55 | 3,816 | 0.498 | 17.900 | 40.664 |
| 0.60 | 3,816 | 0.543 | 20.146 | 43.079 |
| 0.65 | 3,816 | 0.587 | 22.469 | 45.843 |
| 0.70 | 3,816 | 0.650 | 25.014 | 48.920 |
| 0.75 | 3,816 | 0.696 | 28.076 | 52.564 |
| 0.80 | 3,816 | 0.740 | 31.717 | 56.976 |

### 경유

| target coverage | clean n | empirical coverage | 평균 폭 | interval score |
|---:|---:|---:|---:|---:|
| 0.55 | 2,539 | 0.494 | 14.559 | 41.516 |
| 0.60 | 2,539 | 0.543 | 16.272 | 44.476 |
| 0.65 | 2,539 | 0.592 | 18.387 | 47.898 |
| 0.70 | 2,539 | 0.641 | 20.953 | 52.055 |
| 0.75 | 2,539 | 0.687 | 24.335 | 56.838 |
| 0.80 | 2,539 | 0.735 | 28.740 | 62.635 |

coverage 0.70은 너무 좁은 band로 인한 과도한 이탈 판정을 줄이면서도 폭이 지나치게 넓어지는 것을 피하는 절충값입니다.

## 정유사 weekly 진단 산출물

정유사 모델은 최종 소비자가격에는 직접 쓰지 않지만, 주간 세전 정유사 가격의 적정 수준과 band를 산정합니다.

| 유종 | 파일 | 행 | 기간 | fair refinery 비결측 |
|---|---|---:|---|---:|
| 휘발유 | `outputs/gasoline/gasoline_refinery_weekly_predictions.csv` | 943 | 2008-05-10 ~ 2026-05-30 | 823 |
| 경유 | `outputs/diesel/diesel_refinery_weekly_predictions.csv` | 704 | 2012-12-08 ~ 2026-05-30 | 621 |

이 파일에는 `fair_refinery_pre`, `refinery_band_low`, `refinery_band_high`, `refinery_judge`, `refinery_gap_원L`가 포함됩니다.

## 그래프와 세부 산출물

| 산출물 | 내용 |
|---|---|
| `outputs/gasoline/gasoline_step2_daily_frame.csv` | 휘발유 일별 feature frame 6,630행 |
| `outputs/diesel/diesel_step2_daily_frame.csv` | 경유 일별 feature frame 6,630행 |
| `outputs/gasoline/gasoline_retail_model_internal_predictions.csv` | 휘발유 direct 모델 내부 예측 |
| `outputs/diesel/diesel_retail_model_internal_predictions.csv` | 경유 direct 모델 내부 예측 |
| `outputs/gasoline/gasoline_model_comparison.csv` | 휘발유 모델 성능 비교 |
| `outputs/diesel/diesel_model_comparison.csv` | 경유 모델 성능 비교 |
| `outputs/gasoline/gasoline_band_comparison.csv` | 휘발유 band coverage 비교 |
| `outputs/diesel/diesel_band_comparison.csv` | 경유 band coverage 비교 |
| `outputs/gasoline_yearly_plots/*.png` | 2008~2026년 휘발유 연도별 그래프 19개 |
| `outputs/diesel_yearly_plots/*.png` | 2008~2026년 경유 연도별 그래프 19개 |

## 다음 단계와의 연결

05 정책 적용은 이 단계의 운영 CSV를 그대로 읽습니다. `pred_gross`, `band_low`, `band_high`는 정책 미반영 기준 적정가격대이며, 05 단계에서 유류세 인하 정책 효과만큼 적정가격과 band를 아래로 shift하여 정책 적용 기준 판정을 다시 계산합니다. 정유사 weekly 진단 CSV는 2026년 정유사 최고가격제 점검에 사용됩니다.
