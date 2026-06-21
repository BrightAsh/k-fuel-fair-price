# 02. Spatial Grid Build

AI 02는 AI 01의 파생 데이터와 주유소 가격 원자료를 결합해 일별 500m 격자 패널을 만드는 단계입니다. 이 패널은 이후 target 생성과 모델 학습의 기본 단위입니다.

## 핵심 아이디어

주유소 가격은 개별 주유소 단위로 존재하지만, AI 모델과 웹 지도는 고정된 공간 단위가 필요합니다. 따라서 날짜별로 각 주유소를 500m 격자에 배정하고, 해당 격자의 가격 평균, 주유소 구성, 시설 영향권, 공시지가, 지리 flag를 하나의 행으로 만듭니다.

```text
date + grid_id
  = 유종별 가격 평균
  + 유종별 주유소 수
  + 브랜드/셀프 여부 구성
  + 주변 주유소 밀도
  + 시설 영향권
  + 공시지가 as-of 값
  + 섬/육지 지리 flag
```

## 입력 재료

| 입력 | 최신 행 수 | 사용 방식 |
|---|---:|---|
| `korea_land_grid_500m.parquet` | 396,185 | 전국 500m 기본 격자 |
| `station_location_history.csv` | 28,171 | 날짜별 주유소 위치 결정 |
| `station_attribute_history.csv` | 153,625 | 브랜드/셀프 여부 날짜별 속성 |
| `facility_points.csv` | 797 | 시설 count와 거리 감쇠 영향권 |
| `official_land_price_grid.csv` | 396,185 | 날짜별 공시지가 as-of 결합 |
| 지역별 주유소 가격 wide table | 대용량 | 유종별 격자 가격 평균과 station count |

## 처리 로직

### 1. 위치/속성 이벤트 정리

주유소 위치 이력은 `station_id`, 적용일, 좌표 기준 이벤트로 만들고, 속성 이력은 브랜드 이벤트와 셀프 여부 이벤트로 나눕니다.

| 객체 | 행 |
|---|---:|
| `location_events` | 27,891 |
| `brand_events` | 37,755 |
| `self_events` | 28,873 |

### 2. 주유소 가격을 격자 일별 part로 변환

지역별 가격 wide table은 `date x station_id` 형태입니다. 코드는 필요한 station id만 batch 단위로 long 변환하고, 같은 station id가 중복 처리되지 않도록 `seen_station_ids`로 관리합니다.

주요 집계 컬럼은 다음과 같습니다.

| 컬럼 | 의미 |
|---|---|
| `station_count_total` | 해당 날짜/격자의 전체 주유소 수 |
| `gasoline_station_count`, `diesel_station_count` | 유종별 가격 존재 주유소 수 |
| `gasoline_price_mean`, `diesel_price_mean` | 격자별 유종 평균 가격 |
| `brand_count__*` | 브랜드별 주유소 수 |
| `self_count__*` | 셀프/일반/미상 수 |
| `gasoline_price_mean__셀프`, `diesel_price_mean__셀프` 등 | 셀프 여부별 평균 가격 |

### 3. base panel 생성

날짜별 주유소 additive part를 합치고 전국 land grid와 결합합니다. 이때 주유소가 없는 격자도 land grid에는 남으므로 공간 coverage가 유지됩니다.

### 4. 주변 주유소 영향력

같은 날짜의 다른 격자 주유소 수를 거리 감쇠로 합산해 `station_neighbor_influence`를 만듭니다.

| 파라미터 | 값 |
|---|---:|
| band | 3 km |
| cutoff | 15 km |
| 입력 | 날짜별 `station_count_total` |
| 출력 | `station_neighbor_influence` |

### 5. 시설 영향력

시설은 유형별 count와 거리 감쇠 영향력으로 변환합니다.

| 시설 유형 | count 컬럼 | influence 컬럼 | band | cutoff |
|---|---|---|---:|---:|
| 저유소 | `facility_storage_count` | `storage_influence` | 20 km | 60 km |
| 대리점 | `facility_agency_count` | `agency_influence` | 10 km | 30 km |
| 공장 | `facility_factory_count` | `factory_influence` | 35 km | 105 km |

### 6. 지리 flag와 공시지가

land grid의 연결 성분을 계산해 `is_island`, `land_component_id`를 저장합니다. 공시지가는 날짜별로 사용 가능한 최신 snapshot을 선택해 `official_land_price`, `official_price_source_date`로 붙입니다.

## 최종 산출물

| 파일 | 크기 | 행 | unique grid | 기간 |
|---|---:|---:|---:|---|
| `grid.parquet` | 1,893.63 MB | 63,800,291 | 12,338 | 2008-04-15 ~ 2026-06-11 |

추가 요약:

| 항목 | 값 |
|---|---:|
| `official_land_price_null_rows` | 29,800,121 |
| `avg_station_neighbor_influence` | 18.669220 |
| `avg_storage_influence` | 0.926178 |
| `avg_agency_influence` | 8.748984 |
| `avg_factory_influence` | 0.385327 |

공시지가 결측이 많은 이유는 공시지가 snapshot이 2016년 이후부터 유효하기 때문입니다. 모델에서는 결측 여부와 snapshot age를 함께 다뤄야 합니다.

## 최종 스키마

`grid.parquet`의 주요 컬럼은 41개입니다.

| 구분 | 컬럼 |
|---|---|
| 날짜/격자 | `date`, `grid_id`, `cell_x`, `cell_y`, `center_lon`, `center_lat` |
| 주유소 수/가격 | `station_count_total`, `gasoline_station_count`, `diesel_station_count`, `gasoline_price_mean`, `diesel_price_mean` |
| 브랜드 count | `brand_count__SK에너지`, `brand_count__GS칼텍스`, `brand_count__HD현대오일뱅크`, `brand_count__S-OIL`, `brand_count__알뜰`, `brand_count__NH-OIL`, `brand_count__자가상표`, `brand_count__기타` |
| 셀프 여부 | `self_count__셀프`, `self_count__일반`, `self_count__미상`, 셀프 여부별 유종 평균 가격 |
| 주유소 영향 | `station_neighbor_influence` |
| 시설 count/영향 | `facility_count_total`, `facility_storage_count`, `facility_factory_count`, `facility_agency_count`, `storage_influence`, `agency_influence`, `factory_influence` |
| 지리 flag | `is_sea`, `is_island`, `land_component_id` |
| 공시지가 | `official_land_price`, `official_price_source_date` |

## 다음 단계 연결

AI 03은 이 패널을 원본으로 두고, `data-analysis/05`의 전국 정책 적용 적정가격을 결합해 격자별 적정가격 target을 만듭니다. AI 02는 실제 가격과 공간 feature를 만드는 단계이고, 적정가격 판단 자체는 AI 03부터 시작됩니다.
