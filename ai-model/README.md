# AI Model

이 폴더는 전국 단위 분석 이후 AI 모델용 feature, 공간 격자, 예측 모델을 구성하는 영역입니다. 데이터 수집 실행 노트북은 이 폴더에서 제거했습니다.

## 현재 구조

```text
01_derived_features/          # 수집 산출물과 분석 산출물 기반 파생 feature 생성
02_spatial_grid_build/        # 주유소/시설/공시지가 기반 격자 데이터 구성
03_prediction_model_design/   # 예측 모델 설계
```

## 입력 경로 원칙

AI Model도 원천 수집 산출물은 `ROOT_PATH/data collection/`을 기준으로 봅니다.

```python
DATA_COLLECTION_PATH = ROOT_PATH + "data collection/"
DERIVED_DATA_PATH = DATA_COLLECTION_PATH + "derived_data/"
```

수동 수집 데이터는 `z_pa_` 접두어 폴더에 둡니다.

```text
data collection/z_pa_facility/final/facility_data.csv
data collection/z_pa_policy/final/korea_fuel_tax_price_policies.csv
```

## 주의

기존 원본 코드에서 `DATA_PATH`나 `preprocessed_data/additional_data`를 참조하던 부분은 과거 구조입니다. 새 구조에서는 필요한 파일을 `data collection/{dataset}/final/` 또는 `data collection/derived_data/` 기준으로 맞추는 방향으로 정리합니다.
