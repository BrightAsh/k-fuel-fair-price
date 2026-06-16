# 01. Derived Features And Grid Frame

AI 모델용 격자 패널을 만들기 전 준비 단계입니다.

이 단계는 `data collection/`의 수집 산출물만 입력으로 사용합니다. 수동 수집 데이터는 폴더명 앞에 `z_pa_`를 붙입니다.

## 실행 파일

- `01_derived_features_3.ipynb`
- 동일 코드 원본: `01_derived_features.py`

## 입력 경로

```python
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
DERIVED_DATA_PATH = DATA_COLLECTION_PATH + "derived_data/"
```

필요한 입력:

```text
DATA_COLLECTION_PATH/fx_usdkrw/final/fx_usdkrw_*.csv
DATA_COLLECTION_PATH/crude/final/crude_*.csv
DATA_COLLECTION_PATH/intl_products/final/intl_products_*.csv
DATA_COLLECTION_PATH/retail_avg/final/retail_avg_*.csv
DATA_COLLECTION_PATH/brand_price/final/brand_gasoline_*.csv
DATA_COLLECTION_PATH/brand_price/final/brand_diesel_*.csv
DATA_COLLECTION_PATH/fuel_tax_trend/final/gasoline_tax_trend_*.xls
DATA_COLLECTION_PATH/fuel_tax_trend/final/diesel_tax_trend_*.xls
DATA_COLLECTION_PATH/refinery_weekly_supply/final/refinery_weekly_supply_prices_by_product_*.csv
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/gasoline.csv
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/diesel.csv
DATA_COLLECTION_PATH/gas_station_prices_by_region/final/{region}/metadata__latlon.json
DATA_COLLECTION_PATH/z_pa_facility/final/facility_data.csv
DATA_COLLECTION_PATH/official_land_price/final/*.csv
```

`gas_station_prices_by_region`은 대용량이라 Git에 올리지 않아도 됩니다. Colab Drive의 `data collection`에 있으면 실행 시 사용합니다.

좌표 보강은 원문 주유소 좌표화에 쓰던 GIMI9 주소 API를 1차로 사용합니다. Colab secret에 `GEOCODER_TOKEN` 또는 `GIMI9_GEOCODER_TOKEN`을 넣으면 됩니다.

GIMI9에서 실패한 주소는 선택적으로 보조 API를 사용합니다.

- Kakao: `KAKAO_REST_API_KEY`
- Naver Maps: `NAVER_MAPS_CLIENT_ID`, `NAVER_MAPS_CLIENT_SECRET`

Kakao와 Naver가 모두 있으면 두 결과의 거리 차이를 비교하고, 500m를 넘으면 `needs_review=True` 상태로 표시합니다. VWorld는 공식 문서상 API 결과 저장 제한이 있어 기본값으로 사용하지 않습니다.

## 주요 산출물

```text
DATA_COLLECTION_PATH/derived_data/national_daily_features.csv
DATA_COLLECTION_PATH/derived_data/station_location_history.csv
DATA_COLLECTION_PATH/derived_data/station_attribute_history.csv
DATA_COLLECTION_PATH/derived_data/station_latest_profile.csv
DATA_COLLECTION_PATH/derived_data/station_points.csv
DATA_COLLECTION_PATH/derived_data/facility_points.csv
DATA_COLLECTION_PATH/derived_data/facility_location_data_final.csv
DATA_COLLECTION_PATH/derived_data/korea_land_grid_500m.parquet
DATA_COLLECTION_PATH/derived_data/official_land_price_grid.csv
```

`station_latest_profile.csv`와 `facility_points.csv`에는 전체 행과 `coord_valid`가 남습니다. 격자화 입력으로 쓰는 `station_points.csv`와 `facility_location_data_final.csv`는 유효 좌표 행만 저장합니다. `station_points.csv`는 같은 `station_id`가 여러 지역 폴더에 중복 등장해도 1개 좌표만 남깁니다.

## 역할 구분

- 01: 좌표 보강, 포인트 데이터, 전국 500m 격자틀, 영향력 파라미터를 준비합니다.
- 02: 01 산출물을 사용해 일별 격자 패널과 주유소/시설 영향력 feature를 계산합니다.

시설 영향력과 주유소 이웃 영향력은 격자 중심점과 일별 station count가 필요하므로 최종 계산은 02에서 수행합니다.
