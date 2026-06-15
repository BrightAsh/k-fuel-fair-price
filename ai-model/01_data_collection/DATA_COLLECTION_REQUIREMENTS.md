# AI Model 01 Data Collection Requirements

이 문서는 AI Model 01 데이터 수집/1차 전처리 단계의 데이터별 판단을 정리합니다. 기준 경로는 `DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"`입니다.

## Data Source Summary

| 데이터 | 수집 판단 | AI Model 02 파생 데이터 입력 여부 |
|---|---|---|
| 환율 `fx_usdkrw.csv` | ECOS API 수집 가능 | 간접 사용 |
| 원유가 `crude.csv` | 오피넷 화면/CSV 다운로드 자동화 | 간접 사용 |
| 국제 석유제품 | 오피넷 화면/CSV 다운로드 자동화 | 간접 사용 |
| 전국 평균 소매가 | 오피넷 화면/CSV 다운로드 자동화 | 간접 사용 |
| 상표별 가격 | 오피넷 화면/CSV 다운로드 자동화 | 간접 사용 |
| 유류세 변동 | 오피넷 HTML 표 수집 | 간접 사용 |
| 정유사 주간 공급가격 | 오피넷/공공데이터 파일 다운로드 | 간접 사용 |
| 전국 개별 주유소/지역별 주유소 | 오피넷 지역별 파일 수집 또는 기존 raw 파일 추가 후 통합 | 직접 사용 |
| 대한석유협회 시설 목록 | 시설 목록 수집 후 좌표 보강 필요 | 직접 사용 |
| 공시지가 `공시지가.csv` | 대량 API 자동수집 대신 수동 파일 관리 | 직접 사용 |
| 정책 기준표 | 사람이 해석한 관리형 파일 유지 | 간접 사용 |

## Direct Handoff To AI Model 02

AI Model 02가 격자화 전 파생 CSV를 만들기 위해 읽는 핵심 파일은 다음입니다.

```text
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/gasoline.csv
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/diesel.csv
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/metadata.json
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/metadata__latlon.json

DATA_COLLECTION_PATH/facility/final/facility_data.csv
DATA_COLLECTION_PATH/facility/final/facility_location_data_final.csv

DATA_COLLECTION_PATH/official_land_price/final/공시지가.csv
```

`facility/final/facility_data.csv`는 시설 목록 파일입니다. 이 파일만으로는 시설 영향력 계산이 불가능하므로, AI Model 02에서 좌표를 보강하거나 좌표 보강 결과인 `facility_location_data_final.csv`를 준비해야 합니다.

## Feature Creation Boundary

AI Model 01은 feature를 만들지 않고 입력 파일을 준비합니다. AI Model 02는 격자화 전 표준 CSV를 만들고, AI Model 03에서 격자 feature를 생성합니다.

AI Model 03에서 생성하는 feature:

- 주유소 개수: `station_count_total`, `gasoline_station_count`, `diesel_station_count`
- 주유소 주변 영향력: `station_neighbor_influence`
- 시설 개수: `facility_count_total`, `facility_storage_count`, `facility_factory_count`, `facility_agency_count`
- 시설 영향력: `storage_influence`, `agency_influence`, `factory_influence`
- 지리 flag: `is_island`, `is_sea`, `land_component_id`
- 공시지가: `official_land_price`, `official_price_source_date`
