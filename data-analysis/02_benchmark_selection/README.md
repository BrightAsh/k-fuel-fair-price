# 02. Benchmark Selection

이 단계는 전처리 단계에서 생성한 `분석용_일별_통합데이터.csv`를 사용해, 국내 정유사 세전 공급가격을 설명할 국제 benchmark 후보를 비교하고 유종별 대표 benchmark를 선택합니다.

원본 Colab 노트북의 `0단계: 국제 benchmark` 구간을 분리했습니다. 원본에서는 `PROCESSED_PATH`가 정의되지 않은 상태에서 설정 셀이 실행되어 `NameError`가 발생했고, 휘발유/경유 실행 셀에는 결과 출력이 남아 있지 않았습니다. 이번 분리본에서는 Colab 단독 실행을 위해 경로 설정을 노트북 내부에 추가했고, 실행 결과를 CSV로 저장하도록 정리했습니다.

## 실행 파일

- `02_benchmark_selection.ipynb`: Colab에서 단독 실행 가능한 benchmark 선정 노트북

첫 설정 셀의 기본 경로는 현재 작업자가 사용한 원본 경로를 그대로 둡니다.

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
BENCHMARK_OUTPUT_PATH = ROOT_PATH + "benchmark_selection/"
```

다른 사용자는 `ROOT_PATH`만 본인의 Google Drive 경로로 수정하면 됩니다.

## 입력 데이터

이 단계의 입력은 전처리 단계 산출물입니다.

```text
{PROCESSED_PATH}/분석용_일별_통합데이터.csv
```

노트북은 통합 데이터에서 다음 컬럼을 사용합니다.

| 컬럼 | 용도 |
| --- | --- |
| `date` | 일별 기준일 |
| `두바이_원리터` | Dubai 원유 가격을 원/L로 환산한 benchmark 후보 |
| `브렌트_원리터` | Brent 원유 가격을 원/L로 환산한 benchmark 후보 |
| `WTI_원리터` | WTI 원유 가격을 원/L로 환산한 benchmark 후보 |
| `휘발유92RON_원리터` | 휘발유 국제제품가 benchmark 후보 |
| `경유0.001_원리터` | 경유 국제제품가 benchmark 후보 |
| `정유소_세전_보통휘발유` 또는 `정유사_세전_보통휘발유` | 휘발유 target |
| `정유소_세전_자동차용경유` 또는 `정유사_세전_자동차용경유` | 경유 target |

정유사 세전 가격 컬럼은 두 가지 이름 후보 중 실제 존재하는 컬럼을 자동으로 선택합니다.

## 비교 대상

휘발유는 다음 후보를 비교합니다.

| 후보명 | 원본 컬럼 | 그룹 |
| --- | --- | --- |
| `dubai_krw_l` | `두바이_원리터` | crude |
| `brent_krw_l` | `브렌트_원리터` | crude |
| `wti_krw_l` | `WTI_원리터` | crude |
| `mogas92_krw_l` | `휘발유92RON_원리터` | product |

경유는 다음 후보를 비교합니다.

| 후보명 | 원본 컬럼 | 그룹 |
| --- | --- | --- |
| `dubai_krw_l` | `두바이_원리터` | crude |
| `brent_krw_l` | `브렌트_원리터` | crude |
| `wti_krw_l` | `WTI_원리터` | crude |
| `gasoil_0001_krw_l` | `경유0.001_원리터` | product |

## 분석 방식

1. 전처리 통합 데이터를 날짜순으로 정렬합니다.
2. 국제 가격 후보는 주간 토요일 기준(`W-SAT`) 평균으로 변환합니다.
3. 정유사 세전 공급가격은 일별 데이터에서 토요일 기준 주간 마지막 값으로 재버킷팅합니다.
4. target과 후보 benchmark를 로그 차분한 뒤 동적 회귀 설계행렬을 만듭니다.
5. 각 후보별로 `p=0~8`, `q=1~12` 조합을 탐색합니다.
6. 초기 학습 구간은 `min_train=156`으로 둡니다. 이는 약 3년치 주간 데이터입니다.
7. 학습 구간 OLS, 전체 구간 OLS, restricted OLS를 적합합니다.
8. rolling out-of-sample 예측으로 level/change 기준 RMSE, MAE, MAPE를 계산합니다.
9. Ljung-Box p-value, block F-test p-value, AR 안정성, BIC를 함께 계산합니다.
10. 후보별 best model을 고른 뒤, 전체 후보 중 최종 winner를 선택합니다.

모델이 `ok=True`가 되려면 다음 조건을 모두 만족해야 합니다.

- 학습 구간과 전체 구간 모두 AR 안정성 조건을 만족
- 학습 구간과 전체 구간의 Ljung-Box p-value가 `0.05` 이상
- 학습 구간과 전체 구간의 block p-value가 `0.10` 미만

최종 winner는 `ok=True` 여부를 우선하고, 그 다음 `oos_rmse_level`이 낮고, `full_lb_p`가 높고, `bic`가 낮은 순서로 선택합니다.

## 저장 결과

분리본 노트북은 실행 결과를 `BENCHMARK_OUTPUT_PATH`에 저장하도록 정리했습니다.

저장되는 결과는 유종별 전체 탐색 grid, 후보별 best row, 최종 winner, 그리고 유종별 winner 요약입니다. 모든 CSV는 `utf-8-sig` 인코딩으로 저장됩니다.

## 출력셀 기반 결과 정리

원본 Colab 노트북의 benchmark 설정 셀에는 다음 오류가 남아 있었습니다.

```text
NameError: name 'PROCESSED_PATH' is not defined
```

휘발유 실행 셀과 경유 실행 셀에는 출력이 남아 있지 않았습니다. 따라서 원본 출력셀만 기준으로는 다음 결과를 확정할 수 없습니다.

- 휘발유 최종 선택 benchmark
- 경유 최종 선택 benchmark
- 후보별 RMSE, MAE, MAPE, BIC
- 후보별 `ok` 여부
- 최종 winner의 `p`, `q`, Ljung-Box p-value, block p-value

이 값들은 노트북을 재실행하거나, 실행 후 저장된 benchmark 결과 CSV를 받아야 정리할 수 있습니다.
