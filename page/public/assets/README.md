# Public Assets

GitHub Pages에서 그대로 공개되는 정적 파일을 넣는 폴더입니다.

현재 페이지는 정적 이미지 대신 시도 경계 GeoJSON을 사용해 지역별 색상을 직접 칠합니다.

```text
korea-provinces.geojson
korea-districts.geojson
```

- `korea-provinces.geojson`: 첫 화면의 대한민국 시도별 가격 지도
- `korea-districts.geojson`: 시도 클릭 후 시군구 상세 지도
- 출처: `southkorea/southkorea-maps`의 KOSTAT 2013 province GeoJSON
- 원본 파일: KOSTAT 2013 province/municipality 단순 경계 GeoJSON

`korea-districts.geojson`은 원본 시군구 단순 경계에 웹 표시용 `region`, `level` 속성을 추가한 파일입니다.

나중에 더 최신 행정구역 경계가 필요하면 같은 스키마의 GeoJSON으로 이 파일만 교체하면 됩니다.
