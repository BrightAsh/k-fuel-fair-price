# Analysis And Model Development

이 폴더는 대회 분석 및 예측 모델 제작 과정을 단계별로 분리해 정리하는 공간입니다.

각 단계 폴더는 같은 구조를 가집니다.

- `{단계 폴더명}.ipynb`: 해당 단계의 실행 코드
- `README.md`: 목적, 입력 데이터, 주요 처리, 산출물 설명
- `outputs/`: 실행 결과물만 보관하는 공간

각 노트북은 Colab에서 파일 하나만 열어도 실행될 수 있도록 자체 설정 셀을 포함합니다. 별도 환경 설정 단계는 두지 않습니다.

`outputs/`에는 README, `.gitkeep`, 설명 문서 같은 보조 파일을 넣지 않습니다. 결과 파일이 없으면 GitHub에서는 빈 폴더가 보이지 않을 수 있습니다.

현재 `01_data_preprocessing`, `02_benchmark_selection`, `03_lag_analysis`는 원본 Colab 셀을 분리해 실행 가능한 형태로 정리했습니다. 나머지 단계는 다음 작업에서 순차적으로 채울 예정입니다.

## Steps

1. `01_data_preprocessing`: 원천 데이터 로딩, 통합 일별 데이터 생성
2. `02_benchmark_selection`: 국제 원유/제품 benchmark 후보 비교
3. `03_lag_analysis`: 국내 가격 반영 시차 분석
4. `04_fair_price_model`: 전국 단위 적정 유가 및 가격대 산정
5. `05_policy_application`: 유류세 인하, 최고가격제 등 국내 정책 반영
6. `06_grid_data_build`: 500m 격자, 주유소/시설/공시지가 feature 생성
7. `07_prediction_model_build`: 격자 단위 적정가격 예측 모델 학습 및 산출물 생성
