# K-Fuel Fair Price

국제 석유가격 대비 국내 유가의 적정성을 분석하고, 그 결과를 AI 모델용 격자 데이터와 예측 모델로 확장하는 저장소입니다.

이 README는 전체 구조를 빠르게 이해하기 위한 문서입니다. 단계별 상세 입력, 처리 로직, 출력 파일, 주요 수치는 각 하위 폴더의 `README.md`에 정리되어 있습니다. 웹페이지 구축 관련 문서는 이 정리 범위에서 제외했습니다.

## 전체 흐름

```text
data collection
  -> data-analysis/00~05
  -> ai-model/01_derived_features
  -> ai-model/02_spatial_grid_build
  -> ai-model/03_prediction_model_design
```

## 폴더 역할

| 폴더 | 역할 | 현재 상태 |
|---|---|---|
| `data-analysis/` | 전국 단위 유가 적정성 분석 | 00~05 산출물과 README 정리 완료 |
| `ai-model/` | 주유소/시설/격자 기반 AI 모델 데이터와 학습 코드 | 01~02 산출물 구조 확정, 03 학습 진행 중 |
| `page/` | GitHub Pages 대시보드와 자동화 | 이번 README 정리 대상 제외 |

## Data Analysis 요약

`data-analysis`는 원천 데이터 준비 상태를 확인한 뒤, 전국 일별 통합 데이터, benchmark 선택, 시차 분석, 정책 미반영 적정가격, 정책 적용 판정을 순서대로 생성합니다.

| 단계 | 폴더 | 핵심 산출물 |
|---|---|---|
| 00 | `data-analysis/00_data_collection` | 원천 데이터 manifest, 수기 정책 폴더 생성 |
| 01 | `data-analysis/01_data_preprocessing` | `outputs/분석용일별통합데이터.csv` |
| 02 | `data-analysis/02_benchmark_selection` | `outputs/stage0_selected_benchmarks.csv` |
| 03 | `data-analysis/03_lag_analysis` | 유종/층위별 `analysis_summary.csv`, `impulse_response_path.csv` |
| 04 | `data-analysis/04_fair_price_model` | `*_production_predictions_full_calendar.csv` |
| 05 | `data-analysis/05_policy_application` | 정책 적용 일별 데이터, 판정 요약, 정유사 최고가격제 점검표 |

주요 결론은 다음과 같습니다.

| 항목 | 휘발유 | 경유 |
|---|---|---|
| 선택 benchmark | `휘발유92RON_원리터` | `경유0.001_원리터` |
| 소비자가격 평균 반영 시차 | 약 20일 | 약 23일 |
| 정유사 세전가격 평균 반영 시차 | 약 8주 | 약 6주 |
| 정책 미반영 운영 CSV 행 | 6,630 | 6,630 |
| 정책 적용 판정 가능일 | 5,979 | 4,567 |

## AI Model 요약

`ai-model`은 전국 평균 분석을 주유소/격자 단위 예측 문제로 확장합니다.

| 단계 | 폴더 | 핵심 산출물 또는 역할 |
|---|---|---|
| 01 | `ai-model/01_derived_features` | 주유소 좌표/속성 이력, 시설 좌표, 공시지가 격자, 전국 500m land grid |
| 02 | `ai-model/02_spatial_grid_build` | 최종 학습 입력 `ROOT_PATH/그리드/grid.parquet` |
| 03 | `ai-model/03_prediction_model_design` | 격자별 spread 변동 예측 LSTM 학습 코드. 모델 학습 결과는 아직 작성 대상 아님 |

AI 02 최종 노트북 출력 기준 `grid.parquet`는 63,800,291행, 12,338개 격자, 2008-04-15 ~ 2026-06-11 기간을 포함합니다. 이 파일은 대용량이라 레포에 포함하지 않고 Colab/Drive 또는 로컬 실행 환경에서 관리합니다.

## 경로 원칙

Colab 기준 기본 루트는 아래입니다.

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
```

원천 수집 데이터는 `DATA_COLLECTION_PATH/{dataset}/final/`의 수집 산출물을 직접 사용합니다. 과거 구조였던 `ROOT_PATH/data/` fallback 또는 `preprocessed_data/additional_data` 기준 경로는 새 코드에서 사용하지 않는 방향으로 정리했습니다.

수동 수집 데이터는 폴더명 앞에 `z_pa_`를 붙입니다.

```text
data collection/z_pa_policy/final/korea_fuel_tax_price_policies.csv
data collection/z_pa_facility/final/facility_data.csv
```

## 실행 순서

1. `data collection/`에 자동 수집 산출물과 수동 수집 파일을 준비합니다.
2. `data-analysis/00_data_collection`으로 필수 입력 존재 여부를 점검합니다.
3. `data-analysis/01_data_preprocessing`부터 `05_policy_application`까지 순서대로 실행합니다.
4. `ai-model/01_derived_features`로 주유소/시설/공시지가/격자 전처리 산출물을 만듭니다.
5. `ai-model/02_spatial_grid_build`로 최종 `grid.parquet`을 만듭니다.
6. `ai-model/03_prediction_model_design`에서 `grid.parquet` 기반 모델을 학습합니다.

## 자세한 문서

| 문서 | 내용 |
|---|---|
| `data-analysis/README.md` | 전국 단위 분석 전체 요약과 핵심 수치 |
| `data-analysis/*/README.md` | 단계별 입력, 처리 로직, 산출물, 해석 |
| `ai-model/README.md` | AI 모델 파이프라인 전체 요약 |
| `ai-model/*/README.md` | AI 단계별 입력, 출력, 스키마, 학습 설계 |
