# AI Model 03 데이터 격자화

이 단계는 기존 7번 파일입니다. AI Model 02에서 만든 파생 CSV를 바탕으로 전국 500m 격자 패널과 공간 feature를 생성합니다.

## Notebook

- `03_spatial_grid_build.ipynb`

## Inputs

새 구조의 기준 입력은 다음입니다.

```text
DATA_COLLECTION_PATH/derived_data/station_price_manifest.csv
DATA_COLLECTION_PATH/derived_data/station_location_history.csv
DATA_COLLECTION_PATH/derived_data/station_attribute_history.csv
DATA_COLLECTION_PATH/derived_data/station_latest_profile.csv
DATA_COLLECTION_PATH/derived_data/facility_location_data_final.csv
DATA_COLLECTION_PATH/derived_data/facility_points.csv
DATA_COLLECTION_PATH/derived_data/official_land_price_grid.csv
```

원문 코드에는 아직 `PROCESSED_PATH/additional_data/...` 또는 `DATA_PATH/공시지가.csv`를 읽는 부분이 남아 있을 수 있습니다. 03번 구현 시 위 `DERIVED_DATA_PATH` 기준으로 맞춥니다.

외부 보조 데이터는 Natural Earth minor islands zip입니다.

```text
https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_scale_rank_minor_islands.zip
```

## Processing Flow

| 순서 | 처리 | 주요 내용 | 산출물 |
|---:|---|---|---|
| 1 | 전체 육지 500m grid 생성 | Natural Earth 기반 남한 육지 mask 생성, 제주/울릉/독도 guard 추가, 주유소/시설 위치 기반 patch grid 결합 | `south_korea_land_mask_500m.gpkg`, `korea_land_grid_500m.parquet` |
| 2 | 주유소 기본 패널 생성 | 지역별 주유소 가격 CSV와 위치 이력을 일별 long 형태로 변환, 격자별 주유소 수/평균가격/상표/셀프 여부 집계 | `grid_station_daily_panel_500m.parquet` |
| 3 | 세분화 label table 생성 | `date × grid × brand × self_type × fuel` 단위 정답 label 생성. 모델 feature로 쓰면 leakage가 되므로 검증/분석용으로 분리 | `grid_brand_self_fuel_daily_label_500m/` |
| 4 | 주유소 영향력 계산 | 같은 날짜의 주변 grid 주유소 수를 거리 감쇠합으로 계산 | `grid_station_daily_panel_500m_plus_station_influence.parquet` |
| 5 | 시설 feature 결합 | 공장/저유소/대리점 count와 거리 감쇠 influence 계산 | `facility_effect_land_grid_static_500m.parquet`, `grid_station_daily_panel_500m_plus_facility.parquet` |
| 6 | 지리 flag 결합 | land grid 연결 컴포넌트 기준으로 `is_island`, `land_component_id` 생성. 현재 land grid만 쓰므로 `is_sea=0` | `geo_flag_land_grid_500m.parquet`, `*_plus_geo.parquet` |
| 7 | 공시지가 결합 | 공시지가 snapshot을 날짜 기준 as-of mapping해 `official_land_price`, `official_price_source_date` 추가 | `grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet` |

## Feature Outputs

이 단계에서 주유소/시설 영향력 feature가 생성됩니다.

```text
station_count_total
gasoline_station_count
diesel_station_count
station_neighbor_influence

facility_count_total
facility_storage_count
facility_factory_count
facility_agency_count
storage_influence
agency_influence
factory_influence
official_land_price
official_price_source_date
```

## Outputs

주요 산출물은 `ROOT_PATH/그리드/data_1/` 아래에 생성됩니다.

```text
south_korea_land_mask_500m.gpkg
korea_land_grid_500m.parquet
grid_station_daily_panel_500m.parquet
grid_brand_self_fuel_daily_label_500m/
grid_station_daily_panel_500m_plus_station_influence.parquet
facility_effect_land_grid_static_500m.parquet
grid_station_daily_panel_500m_plus_facility.parquet
geo_flag_land_grid_500m.parquet
korea_land_grid_500m_plus_geo.parquet
facility_effect_land_grid_static_500m_plus_geo.parquet
grid_station_daily_panel_500m_plus_geo.parquet
grid_station_daily_panel_500m_plus_facility_plus_geo.parquet
grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet
```
