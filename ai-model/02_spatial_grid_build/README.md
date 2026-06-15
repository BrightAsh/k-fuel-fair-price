# 02. Spatial Grid Build

AI Model 01에서 만든 `derived_data` CSV를 바탕으로 전국 500m 격자 패널과 공간 feature를 생성하는 단계입니다.

## 실행 파일

- `03_spatial_grid_build.ipynb`

## 입력

```text
DATA_COLLECTION_PATH/derived_data/station_price_manifest.csv
DATA_COLLECTION_PATH/derived_data/station_location_history.csv
DATA_COLLECTION_PATH/derived_data/station_attribute_history.csv
DATA_COLLECTION_PATH/derived_data/station_latest_profile.csv
DATA_COLLECTION_PATH/derived_data/facility_location_data_final.csv
DATA_COLLECTION_PATH/derived_data/facility_points.csv
DATA_COLLECTION_PATH/derived_data/official_land_price_grid.csv
```

보조 지리 데이터는 Natural Earth minor islands zip을 사용합니다.

```text
https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_scale_rank_minor_islands.zip
```

## 주요 산출물

```text
ROOT_PATH/그리드data_1/south_korea_land_mask_500m.gpkg
ROOT_PATH/그리드data_1/korea_land_grid_500m.parquet
ROOT_PATH/그리드data_1/grid_station_daily_panel_500m.parquet
ROOT_PATH/그리드data_1/grid_station_daily_panel_500m_plus_station_influence.parquet
ROOT_PATH/그리드data_1/facility_effect_land_grid_static_500m.parquet
ROOT_PATH/그리드data_1/grid_station_daily_panel_500m_plus_facility.parquet
ROOT_PATH/그리드data_1/grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet
```

이 단계에서 과거 `DATA_PATH/공시지가.csv` 구조를 쓰지 않도록, 입력은 `DATA_COLLECTION_PATH/derived_data/` 기준으로 맞춥니다.
