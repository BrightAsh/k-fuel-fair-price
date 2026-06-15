# 02. Benchmark Selection

01번 전처리 산출물인 `분석용_일별_통합데이터.csv`를 사용해 유종별 국제 가격 benchmark를 선택합니다.

## 입력

```text
{PROCESSED_PATH}/분석용_일별_통합데이터.csv
```

주요 사용 컬럼은 아래입니다.

| 컬럼 | 용도 |
| --- | --- |
| `date` | 일별 기준일 |
| `두바이_원리터` | Dubai 원유 가격 후보 |
| `브렌트_원리터` | Brent 원유 가격 후보 |
| `WTI_원리터` | WTI 원유 가격 후보 |
| `휘발유92RON_원리터` | 휘발유 국제 제품 가격 후보 |
| `경유0.001_원리터` | 경유 국제 제품 가격 후보 |
| `정유소_세전_보통휘발유` 또는 `정유사_세전_보통휘발유` | 휘발유 target |
| `정유소_세전_자동차용경유` 또는 `정유사_세전_자동차용경유` | 경유 target |

## 기본 산출물

기존 분석용 CSV는 아래 폴더에 저장됩니다.

```text
{ROOT_PATH}/benchmark_selection/
```

| 파일 | 내용 |
| --- | --- |
| `gasoline_stage0_candidate_grid.csv` | 휘발유 전체 p/q 후보 탐색 결과 |
| `gasoline_stage0_best_each.csv` | 휘발유 후보별 best row |
| `gasoline_stage0_winner.csv` | 휘발유 최종 winner |
| `diesel_stage0_candidate_grid.csv` | 경유 전체 p/q 후보 탐색 결과 |
| `diesel_stage0_best_each.csv` | 경유 후보별 best row |
| `diesel_stage0_winner.csv` | 경유 최종 winner |
| `stage0_selected_benchmarks.csv` | 유종별 최종 선택 benchmark 요약 |

## 보고서용 상세 산출물

보고서 작성용 파일은 별도 폴더에 저장됩니다.

```text
{ROOT_PATH}/benchmark_selection/report_outputs/
```

주요 파일은 아래입니다.

| 파일 | 내용 |
| --- | --- |
| `report_outputs_manifest.csv` | 보고서용 산출물 목록 |
| `stage0_run_config.json` | 실행 설정, 입력 경로, 후보군, 저장 경로 |
| `stage0_report.md` | 보고서 초안용 markdown 요약 |
| `tables/stage0_candidate_grid_all_fuels.csv` | 휘발유/경유 전체 후보 탐색 결과 통합 |
| `tables/stage0_candidate_rankings.csv` | 유종별 정렬 rank 포함 후보 랭킹 |
| `tables/stage0_top20_by_fuel.csv` | 유종별 상위 20개 후보 |
| `tables/stage0_candidate_summary.csv` | 후보 단위 요약 통계 |
| `tables/stage0_best_each_all_fuels.csv` | 유종별 후보 best row 통합 |
| `tables/stage0_winner_details.csv` | 최종 선택 benchmark 상세 |
| `diagnostics/input_profile.csv` | 입력 데이터 행 수, 날짜 범위, 컬럼 수 |
| `diagnostics/daily_benchmark_candidates.csv` | 일별 benchmark 후보 데이터 |
| `diagnostics/weekly_refinery_targets.csv` | 주간 정유사 target 데이터 |
| `diagnostics/daily_numeric_summary.csv` | 일별 후보 기술통계 |
| `diagnostics/weekly_refinery_numeric_summary.csv` | 주간 target 기술통계 |
| `diagnostics/gasoline_weekly_common_sample.csv` | 휘발유 모델 공통 주간 표본 |
| `diagnostics/diesel_weekly_common_sample.csv` | 경유 모델 공통 주간 표본 |

## 선택 기준

각 후보별로 `p=0~8`, `q=1~12` 조합을 탐색합니다. 최종 winner는 먼저 `ok=True`를 우선하고, 그 다음 `oos_rmse_level`이 낮고, `full_lb_p`가 높고, `bic`가 낮은 순서로 선택합니다.

`ok=True` 조건은 아래를 모두 만족해야 합니다.

- train/full 구간 AR 안정성 조건 만족
- train/full Ljung-Box p-value가 `0.05` 이상
- train/full block p-value가 `0.10` 미만
