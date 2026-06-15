# K-Fuel Fair Price

국제 석유제품 가격, 국내 유가, 정책 변수, 공간 격자 데이터를 이용해 국내 유가의 적정 가격을 분석하고 AI 모델 입력 데이터를 만드는 프로젝트입니다.

레포는 두 흐름으로 분리합니다.

## 1. Data Analysis

`data-analysis/`는 기존 1~5번 분석 단계입니다. 벤치마크 선정, 시차 분석, 적정가격 산정, 정책 적용을 위한 데이터 분석 흐름입니다.

```text
data-analysis/
  01_data_preprocessing/
  02_benchmark_selection/
  03_lag_analysis/
  04_fair_price_model/
  05_policy_application/
```

이 단계의 결과는 이후 AI 모델이나 웹서비스에서 참고할 수 있지만, 일일 자동 수집/격자화 파이프라인 자체는 아닙니다.

## 2. AI Model

`ai-model/`은 기존 6~8번에 격자화 전 파생 데이터 단계를 추가해 정리한 AI 모델용 데이터 파이프라인입니다.

```text
ai-model/
  01_data_collection/          # 기존 6번: 데이터 수집 및 1차 전처리
  02_derived_features/         # 신규: 파생 변수/파생 데이터 추가
  03_spatial_grid_build/       # 기존 7번: 500m 격자화
  04_prediction_model_design/  # 기존 8번: 예측 모델 설계 및 학습
```

AI 모델 흐름에서는 `ROOT_PATH/data collection/`을 자동 수집과 1차 전처리 산출물의 기준 경로로 둡니다. 원문 코드의 `preprocessed_data/additional_data` 경로는 참고용 과거 구조이며, 새 AI 파이프라인의 기준 경로는 아닙니다.

## Colab Path

각 노트북은 Colab에서 단독 실행할 수 있도록 Google Drive mount와 공통 경로 셀을 자체 포함합니다. 기본 기준은 다음과 같습니다.

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
DATA_PATH = ROOT_PATH + "data/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
```

## Important

- Data Analysis 1~5번과 AI Model 1~3번을 섞지 않습니다.
- AI Model 01은 데이터 수집/1차 전처리까지만 담당합니다.
- AI Model 02는 격자화 전 파생 CSV를 만들고, 좌표/컬럼/기간을 검증합니다.
- 주유소 개수, 주유소 주변 영향력, 시설 개수, 시설 거리 감쇠 영향력은 AI Model 03에서 격자 feature로 생성합니다.
- AI Model 04는 AI Model 03의 최종 격자 패널을 읽어 모델을 학습하고 예측 산출물을 만듭니다.
