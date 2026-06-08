# Analysis And Model Development

이 폴더는 대회 분석 및 예측 모델 제작 과정을 단계별로 분리해 정리하는 공간입니다.

각 단계 폴더는 같은 구조를 가집니다.

- `code.ipynb`: 해당 단계의 실행 코드
- `README.md`: 목적, 입력 데이터, 주요 처리, 산출물 설명
- `outputs/`: 실행 결과물 또는 사용자가 직접 추가할 산출물

현재 `code.ipynb` 파일들은 자리표시자입니다. 다음 작업에서 원본 Colab 노트북의 셀을 단계별로 분리해 채울 예정입니다.

## Steps

1. `00_environment_setup`: Colab 환경, 경로, 패키지, 한글 폰트 설정
2. `01_data_preprocessing`: 원천 데이터 로딩, 통합 일별 데이터 생성
3. `02_benchmark_selection`: 국제 원유/제품 benchmark 후보 비교
4. `03_lag_analysis`: 국내 가격 반영 시차 분석
5. `04_fair_price_model`: 전국 단위 적정 유가 및 가격대 산정
6. `05_policy_application`: 유류세 인하, 최고가격제 등 국내 정책 반영
7. `06_grid_data_build`: 500m 격자, 주유소/시설/공시지가 feature 생성
8. `07_prediction_model_build`: 격자 단위 적정가격 예측 모델 학습 및 산출물 생성

