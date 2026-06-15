# Result Information Requests For AI Model 01-03

AI Model 단계는 산출물 용량이 커서 파일 전체를 전달하기 어려울 수 있습니다. 아래 요약 정보만 있어도 README와 실행 점검을 보완할 수 있습니다.

| 단계 | 확인할 내용 | 보내주면 좋은 최소 정보 |
|---|---|---|
| 01 데이터 수집 | 데이터별 raw/final 생성 여부, 기간, 행 수 | 각 데이터 저장 완료 출력, `DATA_COLLECTION_PATH` 하위 폴더 구조 |
| 01 주유소 지역별 원자료 | 지역별 가격 CSV와 메타데이터 coverage | 지역별 `gasoline.csv`, `diesel.csv` 행/열 수, date min/max, station 수, `metadata__latlon.json` 생성 여부 |
| 01 시설 | 시설 목록과 좌표 보강 결과 | `facility_data.csv` 행 수/컬럼, `facility_location_data_final.csv` 행 수/좌표 결측 수 |
| 01 공시지가 수동 파일 | 02번에서 읽을 공시지가 파일 형식 | `공시지가.csv` 컬럼명, 행 수, snapshot 날짜 목록, `cell_x/cell_y` 중복 수 |
| 02 격자화 | land grid, station panel, facility, geo, official price 결합 상태 | 각 parquet row 수, column 수, file size, date min/max, unique grid 수 |
| 02 주유소/시설 feature | 주유소 개수/영향력, 시설 count/influence 생성 여부 | `grid_station_daily_panel_500m.parquet`, `grid_station_daily_panel_500m_plus_station_influence.parquet`, `facility_effect_land_grid_static_500m.parquet`, `grid_station_daily_panel_500m_plus_facility.parquet` 컬럼 목록과 주요 describe |
| 03 최종 패널 진단 | 모델 입력 패널 schema와 target coverage | `panel_diagnostic_report_for_chatgpt.txt` 또는 FILE_INFO, GLOBAL_SUMMARY, TARGET_SUMMARY |
| 03 모델 결과 | 최종 제출/보고용 metrics, feature 수, 공시지가 feature 반영 여부 | `{fuel}_model_metadata.json`, `{fuel}_validation_scores_full_features.csv`, `{fuel}_feature_importance.csv`, `{fuel}_selected_features.json` |
| 03 예측/시각화 결과 | 2025~2026 예측 row 수와 생성 plot | `{fuel}_grid_fair_daily_summary_2025_2026.csv`, prediction parquet의 row 수/date min/max/grid 수, `plots/` 파일명 목록 |

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
