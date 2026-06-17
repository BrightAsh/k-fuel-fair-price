# Automation

웹 페이지 운영 자동화 설계 공간입니다.

실제 GitHub Actions 실행 파일은 레포 루트의 `.github/workflows/`에 있습니다. 이 폴더는 자동화 단계, 필요한 secret, 실행 순서를 설명하는 문서 공간으로 둡니다.

## Current Jobs

| Workflow | 역할 | 위치 |
|---|---|---|
| `Refresh Page Data` | 웹용 JSON 생성 후 변경 시 commit | `.github/workflows/page-data-refresh.yml` |
| `Deploy GitHub Pages` | `page/` 폴더를 GitHub Pages로 배포 | `.github/workflows/page-deploy.yml` |

## Future Jobs

원천 데이터 수집까지 GitHub Actions로 옮길 경우 아래 job을 추가합니다.

```text
collect_source_data
run_data_analysis_pipeline
run_ai_model_prediction
build_page_data
deploy_page
```

현재는 AI 모델 03 학습과 대용량 parquet 처리가 무거우므로, 수집/모델 실행은 Colab 또는 로컬에서 먼저 안정화하고, `page`는 최종 웹용 JSON 갱신부터 자동화합니다.

