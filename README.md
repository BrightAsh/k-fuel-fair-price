# K-Fuel Fair Price

국제 유가 대비 국내 유가 적정성을 분석하기 위해 원본 Colab 코드를 단계별 노트북으로 분리한 저장소입니다.

## Web Page

GitHub Pages 대시보드 주소:

[https://brightash.github.io/k-fuel-fair-price/](https://brightash.github.io/k-fuel-fair-price/)

Chrome에서 기존 BrightAsh 블로그의 `404: Page not found`가 계속 보이면 아래 캐시 우회 주소로 한 번 접속하세요. 이 페이지가 로드되면 루트 블로그 서비스워커 캐시를 정리합니다.

[https://brightash.github.io/k-fuel-fair-price/?v=refresh](https://brightash.github.io/k-fuel-fair-price/?v=refresh)

레포의 `Settings > Pages > Source = GitHub Actions` 설정이 켜져 있고, `page/` 변경분이 `main`에 push된 뒤 접속할 수 있습니다.

## 폴더 구조

```text
data-analysis/
  00_data_collection/         # 수집 산출물 점검, 수동 폴더 생성
  01_data_preprocessing/      # 일별 통합 데이터 생성
  02_benchmark_selection/     # benchmark 선택
  03_lag_analysis/            # 시차 분석
  04_fair_price_model/        # 적정 가격 분석
  05_policy_application/      # 정책 적용

ai-model/
  01_derived_features/        # AI 모델용 파생 feature 생성
  02_spatial_grid_build/      # 격자/공간 데이터 구성
  03_prediction_model_design/ # 예측 모델 설계
```

## 데이터 경로 원칙

Colab 기준 기본 루트는 아래입니다.

```python
ROOT_PATH = "/content/drive/MyDrive/Data_analysis/The appropriateness of domestic oil prices compared to international oil prices/산업부/"
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
PROCESSED_PATH = ROOT_PATH + "preprocessed_data/"
```

원천 입력은 `DATA_COLLECTION_PATH/{dataset}/final/`의 수집 산출물을 직접 사용합니다. `ROOT_PATH/data/`로 표준 복사본을 만들거나 fallback으로 읽는 흐름은 사용하지 않습니다.

수동 수집 데이터는 폴더명 앞에 `z_pa_`를 붙입니다.

```text
data collection/z_pa_policy/final/korea_fuel_tax_price_policies.csv
data collection/z_pa_facility/final/facility_data.csv
```

## 분석 흐름

1. 자동 수집 + 수동 수집을 `data collection/` 아래에 저장
2. `data-analysis/00_data_collection`으로 수집 산출물 manifest 점검 및 수동 폴더 생성
3. `data-analysis/01_data_preprocessing`으로 일별 통합 데이터 생성
4. `data-analysis/02_benchmark_selection`으로 benchmark 선택
5. `data-analysis/03_lag_analysis`로 시차 분석
6. `data-analysis/04_fair_price_model`로 적정 가격 분석
7. `data-analysis/05_policy_application`으로 정책 적용

현재 data-analysis에서 없는 필수 데이터는 수동 정책 이력 파일입니다.

```text
data collection/z_pa_policy/final/korea_fuel_tax_price_policies.csv
```
