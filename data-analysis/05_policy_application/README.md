# 05. 정책 적용

이 단계는 04번 적정 가격 결과에 유류세 인하 효과를 반영하고, 최고가격제는 정유사 weekly 결과에서 별도로 점검합니다.

## 기본 루트

```python
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
OUTPUT_BASE = Path(ROOT_PATH) / "정책적용_v2"
```

## 입력 데이터

| 입력 | 경로 | 용도 |
| --- | --- | --- |
| 휘발유 적정가격 결과 | `{ROOT_PATH}/적정가격대선정_v2/gasoline_production_predictions_full_calendar.csv` | 정책 미반영 적정가격과 band |
| 경유 적정가격 결과 | `{ROOT_PATH}/적정가격대선정_v2/diesel_production_predictions_full_calendar.csv` | 정책 미반영 적정가격과 band |
| 휘발유 정유사 weekly 결과 | `{ROOT_PATH}/적정가격대선정_v2/gasoline/gasoline_refinery_weekly_predictions.csv` | 최고가격제 정유사 단계 점검 |
| 경유 정유사 weekly 결과 | `{ROOT_PATH}/적정가격대선정_v2/diesel/diesel_refinery_weekly_predictions.csv` | 최고가격제 정유사 단계 점검 |
| 정책 이력 | `{DATA_COLLECTION_PATH}/z_pa_policy/final/korea_fuel_tax_price_policies.csv` | 유류세 인하율, 최고가격제 기간과 상한 |
| 전처리 통합 데이터 | `{PROCESSED_PATH}/분석용_일별_통합데이터.csv` | 실제 국내 유가와 유류세 기준값 확인 |

정책 이력 파일은 현재 9개 수집 폴더에 없으므로 수동 수집 대상입니다. 00번 노트북을 실행하면 `z_pa_policy/raw`, `z_pa_policy/final`, `z_pa_policy/logs` 폴더만 생성됩니다.

코드 기준 정책 이력 필수 컬럼은 아래입니다.

```text
정책명, 시작일, 종료일, 유종, 가격, 카테고리
```

`근거출처`, `비고`, `적용단계` 같은 컬럼은 기록용으로 둘 수 있지만 현재 계산 필수 컬럼은 아닙니다.

## 산출물

```text
{ROOT_PATH}/정책적용_v2/
```

주요 CSV는 다음과 같습니다.

- `정책_적용가능여부_요약.csv`
- `정책_주요일자_감면액_스냅샷.csv`
- `범위판정_비교요약_전체.csv`
- `연도별_범위판정_비교요약_전체.csv`
- `유류세_정책효과_요약_전체.csv`
- `정유사_최고가격제_점검_전체.csv`
- `휘발유/일별_정책적용_데이터_휘발유.csv`
- `경유/일별_정책적용_데이터_경유.csv`
