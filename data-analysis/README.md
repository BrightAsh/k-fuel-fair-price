# Data Analysis

이 폴더는 기존 1~5번 분석 파일을 모은 영역입니다. 목적은 벤치마크 선정, 시차 분석, 적정가격 산정, 정책 적용을 위한 분석 결과를 만드는 것입니다.

```text
01_data_preprocessing/      # 분석용 일별 통합데이터 생성
02_benchmark_selection/    # 국제 benchmark 비교
03_lag_analysis/           # 국내 유가와 국제 변수 시차 분석
04_fair_price_model/       # 적정가격 산정
05_policy_application/     # 정책 기준 적용
```

이 흐름은 AI 모델용 일일 자동 수집/격자화 파이프라인과 분리합니다. 분석 결과 파일은 이후 AI Model 단계에서 참고하거나 외부 설명 변수로 연결할 수 있지만, `data-analysis/` 자체가 웹사이트 운영용 자동 수집 코드의 기준은 아닙니다.

기본 경로는 기존 분석 코드와 맞춰 `DATA_PATH`와 `PROCESSED_PATH`를 사용합니다.

```python
DATA_PATH = ROOT_PATH + "data/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
```
