# 07 Spatial Grid Build

이 단계는 `06_external_data_collection`에서 만든 외부 공간 데이터를 전국 500m 격자에 결합하는 단계입니다. 원본 Colab의 `그리드 작업 (그리드 생성 및 데이터 입력)` 구간을 분리해 `07_spatial_grid_build.ipynb`로 정리했습니다.

최종 목표 산출물은 주유소 가격, 주유소 영향력, 공장/저유소/대리점 시설 영향력, 섬 여부, 개별공시지가가 결합된 격자 단위 일별 패널입니다.

## Notebook

- `07_spatial_grid_build.ipynb`

노트북은 Colab에서 단독 실행할 수 있도록 Google Drive mount, 패키지 설치, `ROOT_PATH`, `DATA_PATH`, `PROCESSED_PATH` 설정 셀을 포함합니다. 다른 사용자는 첫 설정 셀의 `ROOT_PATH`만 본인 경로로 수정하면 됩니다.

## Code Corrections

정리 과정에서 원본 코드의 흐름을 유지하되, 실행 안정성과 결과 일관성을 위해 두 가지를 보정했습니다.

첫째, 오피넷 원천 가격이 격자 평균에 들어가기 전에 `500~3500원/L` 범위 밖 값은 결측으로 처리하도록 했습니다. 원본 최종 패널 진단 출력에는 `gasoline_price_mean` 최소값 3원/L, `diesel_price_mean` 최소값 1원/L, 최대값 6190원/L 같은 비정상 극단값이 보였습니다. 이는 실제 가격으로 해석하기 어렵고, 모델 target에 그대로 들어가면 학습 결과를 왜곡할 수 있습니다.

둘째, 시설 데이터 결합 단계가 주유소 영향력 패널을 우선 사용하도록 수정했습니다. 원본 코드에서는 `grid_station_daily_panel_500m_plus_station_influence.parquet`를 만든 뒤에도 시설 결합 단계가 기본 패널을 다시 입력으로 잡을 수 있었습니다. 정리본은 해당 파일이 있으면 우선 사용해 `station_neighbor_influence`가 최종 패널까지 유지되도록 했습니다.

## Inputs

필수 입력은 다음과 같습니다.

- `PROCESSED_PATH/additional_data/gas_station_prices_by_region/{지역}/gasoline.csv`
- `PROCESSED_PATH/additional_data/gas_station_prices_by_region/{지역}/diesel.csv`
- `PROCESSED_PATH/additional_data/gas_station_prices_by_region/{지역}/metadata__latlon.json`
- `PROCESSED_PATH/additional_data/1 facility_location_data_final.csv`
- `DATA_PATH/공시지가.csv`

외부에서 내려받는 보조 데이터는 Natural Earth minor islands zip입니다. 코드는 실행 시 다음 URL을 우선 사용합니다.

```text
https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_scale_rank_minor_islands.zip
```

## Processing Flow

| 순서 | 처리 | 주요 내용 | 산출물 |
|---:|---|---|---|
| 1 | 전체 육지 500m grid 생성 | Natural Earth 기반 남한 육지 mask 생성, 제주/울릉/독도 guard 추가, 주유소/시설 위치 기반 patch grid 결합 | `south_korea_land_mask_500m.gpkg`, `korea_land_grid_500m.parquet` |
| 2 | 주유소 기본 패널 생성 | 지역별 주유소 가격 CSV와 위치 이력을 일별 long 형태로 변환, 가격 이상치 제거, 격자별 주유소 수/평균가격/상표/셀프 여부 집계 | `grid_station_daily_panel_500m.parquet` |
| 3 | 세분화 label table 생성 | `date × grid × brand × self_type × fuel` 단위 정답 label 생성. 모델 feature로 쓰면 leakage가 되므로 검증/분석용으로 분리 | `grid_brand_self_fuel_daily_label_500m/` |
| 4 | 주유소 영향력 계산 | 월별 partition 단위로 주변 주유소 밀도 감쇠합 계산 | `grid_station_daily_panel_500m_plus_station_influence.parquet` |
| 5 | 시설 feature 결합 | 공장/저유소/대리점 count와 거리 감쇠 influence 계산 | `facility_effect_land_grid_static_500m.parquet`, `grid_station_daily_panel_500m_plus_facility.parquet` |
| 6 | 지리 flag 결합 | land grid 연결 컴포넌트 기준으로 `is_island`, `land_component_id` 생성. 현재 land grid만 쓰므로 `is_sea=0` | `geo_flag_land_grid_500m.parquet`, `*_plus_geo.parquet` |
| 7 | 공시지가 결합 | 연도별 공시지가 snapshot을 날짜 기준 forward mapping해 최종 패널에 `official_land_price`, `official_price_source_date` 추가 | `grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet` |

## Confirmed Output From Original Cells

원본 출력 셀에서 확인된 내용입니다. 단, 정리본은 가격 이상치 필터와 주유소 영향력 유지 로직을 보강했으므로, 아래 수치는 원본 실행 결과의 참고값입니다. 최종 README 결과값은 정리본 재실행 후 갱신하는 것이 정확합니다.

### Land Grid

| 항목 | 값 |
|---|---:|
| Natural Earth 기반 base land grid | 395,989 |
| 주유소 위치 patch grid | 12,510 |
| 시설 위치 patch grid | 739 |
| station patch only grid | 187 |
| facility patch only grid | 14 |
| 최종 land grid | 396,183 |

### Public Land Price

공시지가 CSV는 396,183개 grid와 9개 snapshot 컬럼을 포함했습니다.

| snapshot | not null | null |
|---|---:|---:|
| 2016-09-21 | 393,397 | 2,786 |
| 2017-11-21 | 393,777 | 2,406 |
| 2018-11-29 | 393,727 | 2,456 |
| 2019-08-20 | 393,846 | 2,337 |
| 2020-08-13 | 393,840 | 2,343 |
| 2021-11-23 | 393,949 | 2,234 |
| 2022-08-05 | 393,942 | 2,241 |
| 2023-12-21 | 393,853 | 2,330 |
| 2024-08-02 | 393,948 | 2,235 |

원본 최종 패널에서 공시지가가 붙은 행은 33,759,224행, 공시지가가 없는 행은 30,104,508행이었습니다. 공시지가 snapshot이 2016년부터 시작되므로 2008~2016년 이전 구간은 `official_land_price`가 결측인 것이 자연스럽습니다.

## Outputs Folder

이 폴더의 `outputs/`에는 실행 결과 파일만 넣습니다. README나 설명 파일은 넣지 않습니다.

결과를 올릴 수 있다면 코드 기준으로 다음 파일이 대상입니다.

- `south_korea_land_mask_500m.gpkg`
- `korea_land_grid_500m.parquet`
- `grid_station_daily_panel_500m.parquet`
- `grid_brand_self_fuel_daily_label_500m/`
- `grid_station_daily_panel_500m_plus_station_influence.parquet`
- `facility_effect_land_grid_static_500m.parquet`
- `grid_station_daily_panel_500m_plus_facility.parquet`
- `geo_flag_land_grid_500m.parquet`
- `korea_land_grid_500m_plus_geo.parquet`
- `facility_effect_land_grid_static_500m_plus_geo.parquet`
- `grid_station_daily_panel_500m_plus_geo.parquet`
- `grid_station_daily_panel_500m_plus_facility_plus_geo.parquet`
- `grid_station_daily_panel_500m_plus_facility_plus_geo_plus_official_price.parquet`
- 실행 중 저장한 시각화 이미지가 있다면 해당 PNG 파일

파일 크기가 너무 크면 원본 파일 대신 행 수, 컬럼 수, 날짜 범위, grid 수, 결측률 요약만 제공해도 결과 문서를 보완할 수 있습니다.
