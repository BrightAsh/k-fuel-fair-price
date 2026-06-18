# Manual Inputs

웹 자동화가 아직 직접 만들 수 없는 보조 파일을 임시로 넣는 위치입니다.

## 선택 입력

```text
region_today.csv
station_search_index.csv
price_history.csv
training_data_coverage.csv
```

`region_today.csv`는 지역별 적정가격 요약을 직접 제공할 때 사용합니다.

필수 컬럼 예시:

```text
as_of_date,region,fuel,actual_price,fair_price_policy,band_low_policy,band_high_policy,gap_policy,judge_policy
```

`station_search_index.csv`는 주유소 검색용 공개 인덱스를 직접 제공할 때 사용합니다.

필수 컬럼 예시:

```text
station_id,name,brand,region,address,lon,lat,gasoline_price,diesel_price,judge_policy
```

`price_history.csv`는 가격 추이 그래프와 다운로드용 기간 데이터를 수동/강제 수집 결과로 보강할 때 사용합니다. 기존 `page/public/data/latest/price_history.json`과 날짜·지역·유종 기준으로 병합되므로, 빈 날짜만 추가해도 됩니다.

필수 컬럼 예시:

```text
date,region,fuel,actual_price,fair_price_policy,band_low_policy,band_high_policy,gap_policy
```

`region`은 전국 또는 시도명, `fuel`은 `gasoline`, `diesel`을 사용합니다.

`training_data_coverage.csv`는 `데이터 현황` 탭의 AI 학습 데이터 히트맵에 사용합니다. 브라우저가 직접 CSV를 읽지 않고, 빌드 스크립트가 이 파일을 `page/public/data/latest/training_data_coverage.json`으로 변환합니다.

필수 컬럼 예시:

```text
dataset,date,region,value,unit,label
```

- `dataset`: `grid_panel_rows`, `station_count`, `facility_count`, `land_price_grid_count` 중 하나입니다.
- `date`: 날짜가 있는 데이터면 `YYYY-MM-DD`, 날짜가 없는 snapshot이면 비워도 됩니다.
- `region`: 서울, 부산, 경기 같은 시도명입니다.
- `value`: 지도 색상에 사용할 숫자입니다.
- `unit`, `label`: 선택 컬럼입니다.

개인정보나 내부용 원천 컬럼은 넣지 않습니다. GitHub Pages에 올라가는 데이터는 공개 데이터로 봐야 합니다.

