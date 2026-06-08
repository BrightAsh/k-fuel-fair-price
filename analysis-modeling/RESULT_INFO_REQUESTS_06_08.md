# Result Information Requests For Steps 06-08

06~08 단계는 산출물 용량이 커서 파일 전체를 전달하기 어려울 수 있습니다. 아래 표의 요약 정보만 있어도 각 단계 README의 결과 설명을 상당 부분 보완할 수 있습니다.

| 단계 | 현재 문서화 가능한 내용 | 부족한 내용 | 보내주면 좋은 최소 정보 |
|---|---|---|---|
| 06 외부 데이터 수집 및 전처리 | 코드 기준 수집 원천, 처리 흐름, 산출 파일명, 공시지가 API 가능성 | 실제 수집 성공률과 최종 행 수는 출력 셀이 없어 확인 불가 | `facility_data.csv` 행 수와 상표/구분별 count, `1 facility_location_data.csv` 좌표 성공/실패 count, `1 facility_location_data_final.csv` 행 수, 지역별 `metadata__latlon.json` 주유소 수와 좌표 성공률 |
| 06 전국 주유소 가격 | 오피넷 지역별 CSV 다운로드 및 전처리 방식 | 지역별 기간 coverage, 누락 지역/파일, 가격 CSV shape 확인 불가 | 지역별 `gasoline.csv`, `diesel.csv`의 행/열 수, date min/max, station 수, 결측률 요약 |
| 06 개별공시지가 로컬 처리 | 로컬 외부 프로그램으로 처리했다는 사실과 API 대체 가능성 | 로컬 프로그램 이름, 처리 좌표계, 집계 방식, 최종 CSV schema | `공시지가.csv` 컬럼명, 행 수, grid 수, snapshot 날짜 목록, 각 snapshot not-null/null count |
| 07 데이터 격자화 | 원본 출력 기준 land grid 396,183개, 공시지가 snapshot 9개, 최종 패널 일부 진단 | 가격 필터와 주유소 영향력 유지 로직을 반영한 재실행 결과가 없음 | 각 parquet의 row 수, column 수, file size, date min/max, unique grid 수. 특히 최종 `grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet` 진단 요약 |
| 07 주유소/시설/지리 feature | 코드 기준 feature 생성 방식 | 주유소 기본 패널, label table, station influence, facility, geo flag 셀 출력이 비어 있음 | `grid_station_daily_panel_500m.parquet`, `grid_station_daily_panel_500m_plus_station_influence.parquet`, `facility_effect_land_grid_static_500m.parquet`, `geo_flag_land_grid_500m.parquet`의 column list와 핵심 컬럼 describe |
| 08 최종 패널 진단 | 원본 진단 출력 기준 63,863,732행, 41열, 날짜 2008-04-15~2026-04-07, date-grid 중복 0 | 정리본은 공시지가 포함 패널과 가격 필터를 사용하므로 최신 재진단 결과 필요 | 재실행된 `panel_diagnostic_report_for_chatgpt.txt` 전체 또는 FILE_INFO, GLOBAL_SUMMARY, TARGET_SUMMARY, MODEL_SELECTOR_SUMMARY 섹션 |
| 08 모델 결과 | 원본 출력 기준 휘발유/경유 best model과 WMAE/WRMSE 참고값 | 정리본 코드 기준 재학습 metrics, feature 수, 공시지가 feature 반영 여부 | `{fuel}_model_metadata.json`, `{fuel}_validation_scores_full_features.csv`, `{fuel}_feature_importance.csv`, `{fuel}_selected_features.json` |
| 08 예측/시각화 결과 | 코드 기준 예측/summary/plot 저장 경로 | 2025~2026 예측 row 수, date range, summary 통계, 생성 plot 목록 | `{fuel}_grid_fair_daily_summary_2025_2026.csv`, prediction parquet의 row 수/date min/max/grid 수, `plots/` 파일명 목록 |

대용량 parquet을 직접 보내기 어렵다면, Colab에서 다음 형태의 요약만 복사해도 충분합니다.

```python
import duckdb
from pathlib import Path

path = Path("여기에 parquet 경로")
con = duckdb.connect()
print("file_size_mb", path.stat().st_size / 1024 / 1024)
print(con.execute(f"""
    SELECT
      COUNT(*) AS rows,
      COUNT(DISTINCT grid_id) AS grids,
      MIN(CAST(date AS DATE)) AS min_date,
      MAX(CAST(date AS DATE)) AS max_date
    FROM read_parquet('{path}')
""").df())
print(con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").df())
con.close()
```
