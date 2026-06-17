# Automation Plan

## Goal

매일 전날까지의 데이터를 수집/갱신하고, GitHub Pages가 읽는 웹용 JSON을 새로 만듭니다.

## Proposed Schedule

기본 스케줄:

```text
03:00 KST daily
```

보수적인 재시도 스케줄:

```text
07:00 KST daily
```

이유:

- 웹은 오늘 아침 사용자가 볼 전날 기준 데이터를 보여주면 됩니다.
- 일부 원천이 새벽에 늦게 올라올 수 있으므로 03:00 1차, 07:00 2차 재시도가 안전합니다.
- 정확한 원천별 업로드 시각은 아직 확정 정보가 아니므로, 실행 로그에서 날짜 coverage를 보고 조정합니다.

GitHub Actions cron은 UTC 기준입니다.

```text
03:00 KST = 18:00 UTC previous day
07:00 KST = 22:00 UTC previous day
```

## Workflow Split

### 1. `page-data-refresh.yml`

역할:

1. 레포 checkout
2. Python 설치
3. 웹용 데이터 변환 스크립트 실행
4. `page/public/data/latest/*.json` 변경이 있으면 commit

현재는 레포에 포함된 산출물과 `page/manual_inputs/`를 기준으로 JSON을 만듭니다. Google Drive나 외부 API에서 직접 수집하려면 secret과 별도 수집 스크립트가 필요합니다.

### 2. `page-deploy.yml`

역할:

1. `page/` 폴더를 GitHub Pages artifact로 업로드
2. Pages에 배포

`page-data-refresh.yml`이 JSON을 commit하면 push 이벤트로 자동 배포됩니다.

## Data Collection Boundary

현재 레포 구조에서 진짜 원천 수집은 `data collection/`과 Colab/AI 파이프라인이 담당합니다.

GitHub Actions가 완전 자동 수집까지 하려면 아래 중 하나가 필요합니다.

1. 원천 API를 Actions에서 직접 호출하는 Python 수집 스크립트
2. Google Drive 파일을 읽을 수 있는 서비스 계정 또는 다운로드 링크
3. Colab/Drive에서 생성된 결과물을 GitHub Release 또는 artifact로 업로드하는 별도 단계

첫 운영 버전은 2단계로 나누는 것이 안전합니다.

```text
수집/모델 실행: Colab 또는 로컬
웹 데이터 변환/배포: GitHub Actions
```

이후 원천 API 키와 실행 시간이 안정되면 수집까지 Actions로 올립니다.

