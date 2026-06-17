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
- 지역/주유소 검색
- 데이터 기준일, 갱신 시각, 데이터 신선도 표시

## 데이터 갱신 원칙

매일 새벽 자동화는 전날까지 수집된 데이터를 기준으로 `page/public/data/latest/*.json`을 갱신합니다.

기본 제안 시각은 한국시간 03:00입니다. 다만 원천 데이터 업로드가 늦는 데이터셋이 있으면 07:00 재시도 스케줄을 함께 두는 쪽이 안전합니다.

