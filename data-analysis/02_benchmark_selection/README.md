# 02. Benchmark Selection

## 목적

`02_benchmark_selection.ipynb`는 국내 석유제품 가격을 설명할 국제 가격 benchmark를 고르는 단계입니다. 01 통합 데이터에서 원유 가격과 국제 제품가격을 원화/리터 단위로 비교하고, 휘발유와 경유 각각에 대해 주간 정유사 세전 공급가격을 가장 잘 예측하는 후보를 선택합니다.

노트북 구조는 markdown 1개, code 7개, 총 802줄입니다. 출력이 저장된 code 셀은 3개이며, 주간 리버킷팅 결과와 후보별 grid search 결과가 포함되어 있습니다.

## 입력 데이터

| 입력 | 행 | 열 | 기간 |
|---|---:|---:|---|
| 01 통합 데이터 `분석용_일별_통합데이터.csv` | 6,630 | 44 | 2008-04-15 ~ 2026-06-09 |
| 노트북 내부 생성 `daily_benchmark_df` | 6,630 | 6 | 2008-04-15 ~ 2026-06-09 |
| 노트북 내부 생성 `weekly_refinery_df` | 868 | 3 | 2008-05-10 ~ 2026-05-30 |

`weekly_refinery_df`는 정유사 주간 가격을 `W-SAT` 기준 토요일 week-end로 다시 정렬한 테이블입니다. 노트북 출력에서 모든 `week_end`가 토요일임을 확인했습니다.

## 후보 benchmark

휘발유와 경유 모두 원유 후보 3개와 제품 후보 1개를 비교합니다.

| 유종 | 후보군 | 후보 컬럼 |
|---|---|---|
| 휘발유 | 원유 | `dubai_krw_l`, `brent_krw_l`, `wti_krw_l` |
| 휘발유 | 제품 | `mogas92_krw_l` |
| 경유 | 원유 | `dubai_krw_l`, `brent_krw_l`, `wti_krw_l` |
| 경유 | 제품 | `gasoil_0001_krw_l` |

일별 후보 가격의 주요 통계는 다음과 같습니다.

| 후보 | 비결측 | 평균 | 중앙값 | 최소 | 최대 | 단위 |
|---|---:|---:|---:|---:|---:|---|
| `dubai_krw_l` | 6,630 | 569.362 | 572.197 | 104.708 | 1,596.098 | 원/L |
| `brent_krw_l` | 6,630 | 582.145 | 580.417 | 148.172 | 1,126.574 | 원/L |
| `wti_krw_l` | 6,630 | 541.412 | 564.554 | -288.591 | 1,070.766 | 원/L |
| `mogas92_krw_l` | 6,630 | 643.799 | 644.997 | 113.149 | 1,478.283 | 원/L |
| `gasoil_0001_krw_l` | 4,937 | 686.346 | 650.493 | 177.275 | 2,797.108 | 원/L |

정유사 주간 target은 다음 분포를 보입니다.

| target | 비결측 | 평균 | 중앙값 | 최소 | 최대 | 단위 |
|---|---:|---:|---:|---:|---:|---|
| `refinery_gasoline_pre_tax` | 868 | 718.924 | 743.505 | 247.01 | 1,309.87 | 원/L |
| `refinery_diesel_pre_tax` | 868 | 786.186 | 779.665 | 304.16 | 1,550.34 | 원/L |

## 모델링 로직

각 후보마다 `p`, `q` lag 조합을 grid search합니다. 휘발유와 경유 모두 후보 4개에 대해 후보당 108개 모델을 평가하여 유종별 432개 모델을 비교했습니다.

평가 지표는 다음을 함께 저장합니다.

| 지표 | 의미 |
|---|---|
| `bic` | 모형 복잡도와 적합도를 함께 보는 정보 기준 |
| `train_lb_p`, `full_lb_p` | Ljung-Box 잔차 자기상관 검정 p-value |
| `train_block_p`, `full_block_p` | 국제 가격 lag 블록 유의성 검정 p-value |
| `train_stable`, `full_stable` | AR lag 안정성 여부 |
| `oos_rmse_level`, `oos_mae_level`, `oos_mape_level_pct` | out-of-sample 수준 가격 예측 오차 |
| `ok` | 엄격한 진단 조건 통과 여부 |

엄격한 `ok=True` 모델은 모든 후보에서 0개였습니다. 따라서 최종 benchmark는 진단 결과를 함께 보되, 최종적으로 out-of-sample 수준 가격 RMSE가 가장 낮은 후보를 선택했습니다.

## 최종 선택

| 유종 | 선택 후보 | 후보군 | p | q | OOS RMSE | OOS MAE | OOS MAPE | OOS n | 비고 |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 휘발유 | `mogas92_krw_l` | 제품 | 8 | 8 | 16.360 | 12.587 | 1.984% | 678 | 제품가격이 원유 후보보다 우수 |
| 경유 | `gasoil_0001_krw_l` | 제품 | 6 | 5 | 18.223 | 13.892 | 1.993% | 458 | 저유황 경유 제품가격이 원유 후보보다 우수 |

휘발유 최종 후보의 BIC는 712.248, train Ljung-Box p-value는 0.9297, full Ljung-Box p-value는 0.0123입니다. 경유 최종 후보의 BIC는 831.326, train Ljung-Box p-value는 0.5648, full Ljung-Box p-value는 0.00162입니다. 두 모델 모두 full sample 잔차 진단은 엄격 기준을 통과하지 못했으므로, 이 단계의 결론은 "국제제품가격 후보가 가장 낫다"는 benchmark 선택에 한정하는 것이 안전합니다.

## 후보별 최저 OOS 오차

| 유종 | 후보 | p | q | OOS RMSE | OOS MAE | OOS MAPE |
|---|---|---:|---:|---:|---:|---:|
| 휘발유 | `mogas92_krw_l` | 8 | 8 | 16.360 | 12.587 | 1.984% |
| 휘발유 | `brent_krw_l` | 8 | 6 | 19.577 | 15.150 | 2.285% |
| 휘발유 | `dubai_krw_l` | 8 | 7 | 20.189 | 15.327 | 2.336% |
| 휘발유 | `wti_krw_l` | 8 | 3 | 21.312 | 15.905 | 2.423% |
| 경유 | `gasoil_0001_krw_l` | 6 | 5 | 18.223 | 13.892 | 1.993% |
| 경유 | `brent_krw_l` | 0 | 2 | 23.009 | 17.377 | 2.430% |
| 경유 | `dubai_krw_l` | 0 | 2 | 23.035 | 17.390 | 2.437% |
| 경유 | `wti_krw_l` | 0 | 3 | 23.681 | 17.567 | 2.472% |

제품 benchmark는 휘발유에서 원유 후보 대비 RMSE를 약 3.2~5.0원/L 낮추고, 경유에서 원유 후보 대비 RMSE를 약 4.8~5.5원/L 낮춥니다.

## 산출물

| 파일 | 내용 |
|---|---|
| `outputs/stage0_selected_benchmarks.csv` | 유종별 최종 선택 benchmark |
| `outputs/gasoline_stage0_candidate_grid.csv` | 휘발유 후보별 전체 grid 결과 432행 |
| `outputs/diesel_stage0_candidate_grid.csv` | 경유 후보별 전체 grid 결과 432행 |
| `outputs/gasoline_stage0_best_each.csv` | 휘발유 후보별 최저 RMSE 모델 |
| `outputs/diesel_stage0_best_each.csv` | 경유 후보별 최저 RMSE 모델 |
| `outputs/report_outputs/tables/stage0_candidate_grid_all_fuels.csv` | 전 유종 전체 후보 grid 통합 |
| `outputs/report_outputs/tables/stage0_candidate_summary.csv` | 후보별 시도 모델 수, best/median RMSE, 진단 요약 |
| `outputs/report_outputs/diagnostics/*.csv` | 입력 profile, 일별 후보 통계, 정유사 주간 target 통계 |
| `outputs/report_outputs/stage0_report.md` | 단계별 보고서용 요약 |

## 다음 단계와의 연결

03 시차분석과 04 적정가격 모델은 이 단계의 결론에 따라 휘발유는 `휘발유92RON_원리터`, 경유는 `경유0.001_원리터`를 기본 benchmark로 사용합니다. 즉, 국내 가격 적정성 판단의 국제 기준은 원유 자체보다 국내 제품과 직접 대응되는 국제 석유제품 가격입니다.
