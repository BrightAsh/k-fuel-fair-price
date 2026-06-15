# Result Information Requests For AI Model

AI Model 단계는 대용량 산출물 전체를 전달하기 어렵기 때문에, 실행 후 아래 요약 정보만 확인해도 다음 단계 수정에 충분합니다.

| 단계 | 확인할 내용 | 최소 정보 |
| --- | --- | --- |
| 01 파생 feature | `derived_data` 산출물 생성 여부 | `derived_outputs_summary.csv`, 파일별 row 수, date min/max, 주요 columns |
| 01 전국 일별 feature | data-analysis와 자동 수집 데이터 통합 상태 | `national_daily_features.csv` rows, date min/max, columns |
| 01 주유소 원자료 | 지역별 가격/메타데이터 coverage | 지역별 가격 CSV 목록, station 수, date min/max, 위경도 결측 수 |
| 01 시설/공시지가 | 수동 시설 데이터와 공시지가 스냅샷 상태 | `z_pa_facility/final/facility_data.csv` columns, 좌표 결측 수, `official_land_price` columns |
| 02 공간 격자 | land grid, station panel, facility, geo, official price 결합 상태 | parquet별 row 수, column 수, file size, date min/max, unique grid 수 |
| 02 주유소/시설 feature | 주유소 개수와 시설 영향 feature 생성 여부 | `grid_station_daily_panel_500m_plus_station_influence.parquet`, `grid_station_daily_panel_500m_plus_facility.parquet` columns와 describe |
| 03 모델 입력 패널 | target coverage와 schema | `panel_diagnostic_report_for_chatgpt.txt` 또는 FILE_INFO, GLOBAL_SUMMARY, TARGET_SUMMARY |
| 03 모델 결과 | 최종 모델 metrics와 feature 사용 현황 | `{fuel}_model_metadata.json`, `{fuel}_validation_scores_full_features.csv`, `{fuel}_feature_importance.csv`, `{fuel}_selected_features.json` |
| 03 예측 결과 | 2025~2026 예측 row 수와 plot 생성 여부 | `{fuel}_grid_fair_daily_summary_2025_2026.csv`, prediction parquet row/date/grid 수, `plots/` 파일 목록 |

대용량 parquet는 아래 요약만 복사해도 됩니다.

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
