# 02. Spatial Grid Build

AI Model 01에서 만든 `derived_data`와 대용량 주유소 가격 원자료를 결합해 최종 학습 입력인 일별 500m 격자 패널을 생성하는 단계입니다.

이 단계의 영구 산출물은 원칙적으로 하나입니다.

```text
ROOT_PATH/그리드/grid.parquet
```

중간 parquet는 `/content/kff_spatial_grid_build_tmp` 아래에 만들고, 최종 산출물 저장 후 삭제합니다.

## 실행 파일

| 파일 | 역할 |
|---|---|
| `02_spatial_grid_build.ipynb` | Colab 실행용 노트북 |

노트북 구조는 markdown 1개, code 12개입니다. 저장된 출력 기준으로 마지막 검증 셀에는 최종 `grid.parquet`의 행 수, 격자 수, 기간, 스키마가 표시됩니다.

## 경로

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
DERIVED_DATA_PATH = DATA_COLLECTION_PATH + "derived_data/"
GRID_OUTPUT_PATH = ROOT_PATH + "그리드/"
FINAL_PANEL_PATH = ROOT_PATH + "그리드/grid.parquet"
```

## 입력

### 01 산출물

| 입력 | 최신 실행 행 수 | 용도 |
|---|---:|---|
| `derived_data/korea_land_grid_500m.parquet` | 396,185 | 기본 land grid |
| `derived_data/station_location_history.csv` | 28,171 | 주유소 위치 이력 |
| `derived_data/station_attribute_history.csv` | 153,625 | 브랜드/셀프 여부 이력 |
| `derived_data/facility_points.csv` | 797 | 시설 포인트. 유효 좌표 740건 사용 |
| `derived_data/official_land_price_grid.csv` | 396,185 | 공시지가 snapshot 격자 |

### 대용량 주유소 가격 원자료

```text
data collection/gas_station_prices_by_region/final/{region}/gasoline.csv
data collection/gas_station_prices_by_region/final/{region}/diesel.csv
data collection/gas_station_prices_by_region/final/{region}/metadata__latlon.json
```

지역별 가격 CSV는 wide 형식입니다. 컬럼은 `date`와 각 `station_id`로 구성되어 있고, 02 단계에서 필요한 station id만 batch 단위로 long 변환합니다.

## 처리 로직

### 1. 01 산출물 로드와 이벤트 정리

`station_location_history`는 `station_id`, `effective_date`, `lat`, `lon` 기준 위치 이벤트로 정리합니다. `station_attribute_history`는 브랜드 이벤트와 셀프 여부 이벤트로 나눕니다.

최신 실행 출력:

| 객체 | 행 |
|---|---:|
| `location_events` | 27,891 |
| `brand_events` | 37,755 |
| `self_events` | 28,873 |

### 2. 지역별 주유소 가격을 격자 일별 additive part로 변환

지역별 `gasoline.csv`, `diesel.csv`에서 station id 목록을 읽고 batch 단위로 처리합니다. 이미 처리한 `station_id`는 `seen_station_ids`로 제외해 중복을 방지합니다.

주요 집계 컬럼:

| 컬럼 | 의미 |
|---|---|
| `station_count_total` | 해당 날짜/격자의 전체 주유소 수 |
| `gasoline_station_count`, `diesel_station_count` | 유종별 가격 존재 주유소 수 |
| `gasoline_price_mean`, `diesel_price_mean` | 격자별 평균 가격 |
| `brand_count__*` | 브랜드별 주유소 수 |
| `self_count__*` | 셀프/일반/미상 수 |
| `gasoline_price_mean__셀프`, `diesel_price_mean__셀프` 등 | 셀프 여부별 평균 가격 |

노트북 출력 기준 지역별 신규 station id는 예를 들어 서울 1,489개, 경기 6,278개, 경북 2,797개, 경남 2,509개 등으로 처리되었습니다. 전체 임시 additive part는 49개입니다.

### 3. base panel 생성

임시 part를 DuckDB로 합치고 `korea_land_grid_500m.parquet`와 left join하여 날짜별 land grid 패널을 만듭니다.

```text
/content/kff_spatial_grid_build_tmp/grid_station_daily_panel_500m_base.parquet
```

이 파일은 최종 산출물이 아니라 중간 파일입니다.

### 4. 주유소 주변 영향력 계산

같은 날짜의 다른 격자 주유소 수를 거리 감쇠로 합산해 `station_neighbor_influence`를 만듭니다.

| 파라미터 | 값 |
|---|---:|
| band | 3 km |
| cutoff | 15 km |
| 입력 | 날짜별 `station_count_total` |
| 출력 | `station_neighbor_influence` |

월별 임시 parquet로 저장한 뒤 최종 join에 사용합니다.

### 5. 시설 영향력 계산

유효 좌표 시설 740건을 `storage`, `agency`, `factory` 유형으로 나누고, full land grid 중심점에 거리 감쇠 영향력을 계산합니다.

| 시설 유형 | count 컬럼 | influence 컬럼 | band | cutoff |
|---|---|---|---:|---:|
| 저유소 | `facility_storage_count` | `storage_influence` | 20 km | 60 km |
| 대리점 | `facility_agency_count` | `agency_influence` | 10 km | 30 km |
| 공장 | `facility_factory_count` | `factory_influence` | 35 km | 105 km |

전체 시설 수는 `facility_count_total`에 저장합니다.

### 6. 지리 flag 생성

land grid의 연결 성분을 계산해 섬 여부와 component id를 저장합니다.

| 컬럼 | 의미 |
|---|---|
| `is_sea` | 최종 land grid에서는 0 |
| `is_island` | mainland component가 아닌 land component 여부 |
| `land_component_id` | 연결 성분 id |

### 7. 공시지가 as-of 결합

01 단계의 snapshot 공시지가를 날짜별 as-of 값으로 변환합니다.

| 컬럼 | 의미 |
|---|---|
| `official_land_price` | 해당 날짜 기준 사용 가능한 최신 공시지가 |
| `official_price_source_date` | 사용된 공시지가 snapshot 날짜 |

최신 실행에서 사용한 snapshot 컬럼은 `20160921`, `20171121`, `20181129`, `20190820`, `20200813`, `20211123`, `20220805`, `20231221`, `20240802`입니다.

## 최종 산출물

최신 노트북 출력 기준입니다.

| 파일 | 크기 | 행 | unique grid | 기간 |
|---|---:|---:|---:|---|
| `ROOT_PATH/그리드/grid.parquet` | 1,893.63 MB | 63,800,291 | 12,338 | 2008-04-15 ~ 2026-06-11 |

추가 요약:

| 항목 | 값 |
|---|---:|
| `gasoline_target_rows` | 63,800,291 |
| `diesel_target_rows` | 63,800,291 |
| `official_land_price_null_rows` | 29,800,121 |
| `avg_station_neighbor_influence` | 18.669220 |
| `avg_storage_influence` | 0.926178 |
| `avg_agency_influence` | 8.748984 |
| `avg_factory_influence` | 0.385327 |

## 최종 스키마

`grid.parquet`의 컬럼은 41개입니다.

| 구분 | 컬럼 |
|---|---|
| 날짜/격자 | `date`, `grid_id`, `cell_x`, `cell_y`, `center_lon`, `center_lat` |
| 주유소 수/가격 | `station_count_total`, `gasoline_station_count`, `diesel_station_count`, `gasoline_price_mean`, `diesel_price_mean` |
| 브랜드 count | `brand_count__SK에너지`, `brand_count__GS칼텍스`, `brand_count__HD현대오일뱅크`, `brand_count__S-OIL`, `brand_count__알뜰`, `brand_count__NH-OIL`, `brand_count__자가상표`, `brand_count__기타` |
| 셀프 여부 | `self_count__셀프`, `self_count__일반`, `self_count__미상`, `gasoline_price_mean__셀프`, `diesel_price_mean__셀프`, `gasoline_price_mean__일반`, `diesel_price_mean__일반`, `gasoline_price_mean__미상`, `diesel_price_mean__미상` |
| 주유소 영향 | `station_neighbor_influence` |
| 시설 count/영향 | `facility_count_total`, `facility_storage_count`, `facility_factory_count`, `facility_agency_count`, `storage_influence`, `agency_influence`, `factory_influence` |
| 지리 flag | `is_sea`, `is_island`, `land_component_id` |
| 공시지가 | `official_land_price`, `official_price_source_date` |

## 03 단계와의 연결

03 학습 코드는 기본 입력으로 아래 파일을 기대합니다.

```text
ai-model/02_spatial_grid_build/outputs/grid.parquet
```

하지만 Colab 02 노트북의 실제 최종 저장 위치는 아래입니다.

```text
ROOT_PATH/그리드/grid.parquet
```

따라서 03을 로컬에서 실행할 때는 `ROOT_PATH/그리드/grid.parquet`를 `ai-model/02_spatial_grid_build/outputs/grid.parquet`로 복사하거나, 03 코드의 `GRID_PATH`를 실행 환경에 맞게 조정해야 합니다.
