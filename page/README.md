# Page

GitHub Pages로 공개할 일일 유가 적정가격 대시보드 영역입니다.

이 폴더는 AI 모델 원본 parquet나 학습 산출물 전체를 직접 서빙하지 않습니다. `data-analysis`와 `ai-model` 결과를 웹용 JSON으로 얇게 변환한 뒤, 정적 페이지가 그 JSON만 읽습니다.

## 폴더 구조

```text
page/
  index.html                     # GitHub Pages 첫 화면
  .nojekyll                      # GitHub Pages 정적 파일 그대로 배포

  assets/
    css/dashboard.css            # 화면 스타일
    js/app.js                    # 데이터 로드/렌더링

  public/
    assets/                      # 지도 이미지, 로고 등 공개 정적 자산
    data/latest/                 # 매일 갱신되는 웹용 JSON

  scripts/
    build_page_data.py           # 분석/AI 산출물을 웹용 JSON으로 변환

  manual_inputs/
    README.md                    # 사용자가 수동으로 넣어야 하는 웹 보조 파일 설명

  docs/
    data_contract.md             # page가 기대하는 입력/출력 포맷
    automation_plan.md           # GitHub Actions 자동화 설계
    user_inputs_needed.md        # 사용자가 준비해야 하는 파일/secret
```

GitHub Actions 워크플로는 GitHub가 인식해야 하므로 레포 루트의 `.github/workflows/`에 둡니다.

## 화면 방향

첫 화면은 매일 들어와 바로 보는 운영 대시보드입니다.

- 오늘 기준 전국 휘발유/경유 적정가격
- 실제가격, 정책 적용 적정가격, 적정 범위, 판정
- 지역별 요약과 지도 이미지
- 위치 기반 주변 주유소 전체 목록
- 전체 기간 기본값의 지역/유종별 가격 추이
- 기간/지역/유종 조건의 데이터 다운로드
- 지역/주유소 검색
- AI 학습 데이터 지역별 분포 지도

## 데이터 갱신 원칙

매일 새벽 자동화는 전날까지 수집된 데이터를 기준으로 `page/public/data/latest/*.json`을 갱신합니다.

기본 제안 시각은 한국시간 03:00입니다. 다만 원천 데이터 업로드가 늦는 데이터셋이 있으면 07:00 재시도 스케줄을 함께 두는 쪽이 안전합니다.

가격 추이는 `page/public/data/latest/price_history.json`을 누적 이력으로 사용합니다. 자동 갱신 스크립트는 기존 JSON과 새 산출물을 `date + region + fuel` 기준으로 병합하므로, 나중에 강제 수집으로 빈 날짜를 채워도 기존 날짜는 보존됩니다.

## 사용자가 넣는 파일

웹 공개용 수동 입력은 `page/manual_inputs/`에 넣습니다.

```text
page/manual_inputs/region_today.csv
page/manual_inputs/station_search_index.csv
page/manual_inputs/price_history.csv
page/manual_inputs/training_data_coverage.csv
```

- `region_today.csv`: 지역별 오늘 표시용 요약입니다. AI 모델 완료 전까지 수동 보강 파일로 사용합니다.
- `station_search_index.csv`: 주유소 검색과 주변 주유소 탭에 쓰는 공개 인덱스입니다. 위치 기반 목록은 반경 안의 주유소를 거리순으로 모두 표시합니다.
- `price_history.csv`: 비어 있는 기간을 수동/강제 수집 결과로 보강하는 파일입니다.
- `training_data_coverage.csv`: `데이터 현황` 탭의 AI 학습 데이터 히트맵용 시도별 집계 파일입니다.

파일별 컬럼은 `page/manual_inputs/README.md`와 `page/docs/data_contract.md`에 정리합니다.

