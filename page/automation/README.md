# Automation

웹 페이지 운영 자동화 설계 공간입니다.

GitHub Actions 자동화의 역할과 책임을 정리하는 문서입니다. 자동화는 분석/AI 산출물을 웹 공개용 JSON으로 바꾸고, 정적 페이지 배포를 갱신하는 데 초점을 둡니다.

## 현재 자동화

| Workflow | 역할 |
|---|---|
| `Refresh Page Data` | 분석/AI 산출물을 웹용 JSON으로 변환하고 변경분을 반영 |
| `Deploy GitHub Pages` | 정적 대시보드를 GitHub Pages로 배포 |

## 확장 방향

향후 자동화 범위를 넓히면 아래 단계까지 하나의 운영 흐름으로 묶을 수 있습니다.

```text
collect_source_data
run_data_analysis_pipeline
run_ai_model_prediction
build_page_data
deploy_page
```

현재 자동화의 우선순위는 무거운 분석/학습 전체를 다시 생성하는 것이 아니라, 이미 생성된 핵심 산출물을 안정적으로 웹 데이터로 변환하는 것입니다.

