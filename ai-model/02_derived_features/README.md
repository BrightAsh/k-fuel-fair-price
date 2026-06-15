# AI Model 02 파생 변수/파생 데이터 추가

이 단계는 신규 추가 단계입니다. AI Model 01의 자동 수집/1차 전처리 산출물을 읽어, AI Model 03 격자화 전에 필요한 표준 CSV 묶음을 만듭니다.

## Notebook

- `02_derived_features.ipynb`
- 동일 코드 원본: `02_derived_features.py`

## Output Folder

Colab 실행 시 아래 폴더를 생성하고 CSV를 저장합니다.

```python
DERIVED_DATA_PATH = DATA_COLLECTION_PATH + "derived_data/"
```

## Main Outputs

```text
data_readiness_summary.csv
national_daily_features.csv
fx_usdkrw_daily.csv
crude_daily.csv
intl_products_daily.csv
retail_avg_daily.csv
brand_gasoline_daily.csv
brand_diesel_daily.csv
gasoline_tax_daily.csv
diesel_tax_daily.csv
refinery_weekly_supply_daily_like.csv
station_price_manifest.csv
station_location_history.csv
station_attribute_history.csv
station_latest_profile.csv
facility_points.csv
facility_location_data_final.csv
official_land_price_grid.csv
official_land_price_snapshots.csv
derived_outputs_summary.csv
```

## Checks

이 단계에서 확인하는 내용은 다음입니다.

- 원문 격자화/AI 모델 코드가 필요로 하는 데이터 파일 존재 여부
- 수집 데이터의 컬럼, 행 수, 날짜 범위
- 지역별 주유소 `gasoline.csv`, `diesel.csv`, `metadata__latlon.json` 존재 여부
- 주유소 위치 history와 최신 위도/경도
- 시설 목록의 좌표 존재 여부
- 좌표 없는 시설은 선택적으로 Kakao/VWorld geocoding
- 공시지가 `cell_x`, `cell_y`, `p_YYYYMMDD` snapshot 형식 검증

## Facility Geocoding

시설 파일에 `경도`, `위도`가 없으면 `KAKAO_REST_API_KEY` 또는 `VWORLD_API_KEY`를 Colab 보안 비밀에 넣고 실행해야 합니다.

우선순위는 다음입니다.

```text
1. DATA_COLLECTION_PATH/facility/final/facility_location_data_final.csv
2. DATA_COLLECTION_PATH/facility/final/facility_points.csv
3. PROCESSED_PATH/additional_data/1 facility_location_data_final.csv
4. DATA_COLLECTION_PATH/facility/final/facility_data.csv
5. DATA_PATH/facility_data.csv
```

좌표가 끝까지 없는 시설이 있으면 노트북은 명시적으로 에러를 냅니다. 이 에러는 정상적인 방어 로직입니다.

## Next Step

AI Model 03 격자화 단계는 이 폴더의 CSV를 입력으로 읽도록 맞춥니다.
