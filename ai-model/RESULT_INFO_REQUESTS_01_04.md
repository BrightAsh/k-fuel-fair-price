# Result Information Requests For AI Model

AI Model 단계는 대용량 산출물 전체를 채팅으로 전달하기 어렵기 때문에, 실행 후 아래 요약 정보만 확인해도 다음 단계 수정과 README 보강에 충분합니다.

## 01. Derived Features

| 확인할 내용 | 최소 정보 |
|---|---|
| `derived_data` 산출물 생성 여부 | 최종 출력 표의 파일별 row 수, column 수, date min/max |
| 전국 일별 feature | `national_daily_features.csv` rows, columns, date min/max |
| 주유소 좌표/속성 | `station_location_history.csv`, `station_attribute_history.csv`, `station_latest_profile.csv`, `station_points.csv` row 수 |
| 좌표 QC | station/facility 전체 행, missing lon/lat, outside range, valid lon/lat |
| 시설 데이터 | `facility_points.csv`, `facility_location_data_final.csv` row 수와 주요 컬럼 |
| 공시지가 | `official_land_price_grid.csv` row 수, snapshot 컬럼 목록 |
| land grid | `korea_land_grid_500m.parquet` row 수, grid 수, 기간 또는 schema |

## 02. Spatial Grid Build

| 확인할 내용 | 최소 정보 |
|---|---|
| 최종 panel | `ROOT_PATH/그리드/grid.parquet` file size, rows, unique grid count, date min/max |
| target coverage | gasoline/diesel target rows |
| 주요 결측 | `official_land_price_null_rows` |
| 영향력 feature | `avg_station_neighbor_influence`, `avg_storage_influence`, `avg_agency_influence`, `avg_factory_influence` |
| schema | `DESCRIBE SELECT * FROM read_parquet(...)` 결과 |
| 중간 산출물 처리 | `/content/kff_spatial_grid_build_tmp` 삭제 여부 |

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
      MAX(CAST(date AS DATE)) AS max_date,
      SUM(CASE WHEN official_land_price IS NULL THEN 1 ELSE 0 END) AS official_land_price_null_rows,
      AVG(station_neighbor_influence) AS avg_station_neighbor_influence,
      AVG(storage_influence) AS avg_storage_influence,
      AVG(agency_influence) AS avg_agency_influence,
      AVG(factory_influence) AS avg_factory_influence
    FROM read_parquet('{path}')
""").df())
print(con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").df())
con.close()
```

## 03. Prediction Model Design

모델 학습 중간 또는 완료 후 아래 정보를 전달하면 README 결과 섹션을 갱신할 수 있습니다.

| 확인할 내용 | 최소 정보 |
|---|---|
| 입력 grid | `GRID_PATH`, file size, rows, unique grid count, date min/max |
| train/validation split | `{fuel}_model_metadata.json`의 `train_validation_split` |
| cache 사용 여부 | `[CACHE HIT]`, `[CACHE SAVE]`, `[CACHE MISS]` 로그 |
| validation 성능 | `{fuel}_validation_scores.csv` 전체 또는 상위 row |
| 학습 이력 | `{fuel}_training_history.csv` 마지막 5행, best epoch |
| test 성능 | `{fuel}_test_metrics_2026.csv`의 `test_2026_all` row |
| 2026 예측 row 수 | `{fuel}_test_predictions_2026.parquet` rows/date/grid 수 |
| 일별/격자 요약 | `{fuel}_test_daily_summary_2026.csv`, `{fuel}_test_grid_summary_2026.csv` row 수와 주요 컬럼 |
| 전체 실행 요약 | `model_run_summary.csv` |

03 단계의 현재 코드 기준 주요 산출물은 다음입니다.

```text
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_training_history.csv
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_validation_scores.csv
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_validation_predictions.parquet
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_model.pt
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_model_metadata.json
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_test_predictions_2026.parquet
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_test_daily_summary_2026.csv
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_test_grid_summary_2026.csv
ai-model/03_prediction_model_design/outputs/{fuel}/{fuel}_test_metrics_2026.csv
ai-model/03_prediction_model_design/outputs/model_run_summary.csv
```

`{fuel}`은 `gasoline` 또는 `diesel`입니다.
