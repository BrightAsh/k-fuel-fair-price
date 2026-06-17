# Manual Inputs

웹 자동화가 아직 직접 만들 수 없는 보조 파일을 임시로 넣는 위치입니다.

## 선택 입력

```text
region_today.csv
station_search_index.csv
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

개인정보나 내부용 원천 컬럼은 넣지 않습니다. GitHub Pages에 올라가는 데이터는 공개 데이터로 봐야 합니다.

