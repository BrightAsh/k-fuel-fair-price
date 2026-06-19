# Automation

이 폴더는 매일 실행할 데이터 파이프라인을 관리합니다.

## 현재 기준

`data-analysis/00_data_collection/00_data_collection.ipynb`는 원천 데이터 수집 방식과 포맷을 정리한 기준 파일입니다. 운영 자동화는 이 노트북을 그대로 실행하지 않고, 검증된 수집 방식과 산출물 포맷만 `automation/collect_sources.py`와 `automation/preprocess_sources.py`로 옮겨 실행합니다.

수집 대상은 아래 원천 산출물입니다.

- `crude/crude_*.csv`
- `retail_avg/retail_avg_*.csv`
- `brand_price/brand_gasoline_*.csv`
- `brand_price/brand_diesel_*.csv`
- `fx_usdkrw/fx_usdkrw_*.csv`
- `intl_products/intl_products_*.csv`
- `intl_products/intl_product_diesel(0.001)_*.csv`
- `fuel_tax_trend/gasoline_tax_trend_*.xls`
- `fuel_tax_trend/diesel_tax_trend_*.xls`
- `refinery_weekly_supply/refinery_weekly_supply_prices_by_product_*.csv`
- `z_pa_policy/korea_fuel_tax_price_policies.csv`

## 실행 흐름

`daily_pipeline.py`는 아래 순서로 실행됩니다.

1. 기존 수집 산출물 상태와 날짜 범위를 점검합니다.
2. `collect_sources.py`가 0번 파일의 수집 방식에 맞춰 자동 수집 대상 데이터를 수집하고 기존 CSV에 날짜 기준으로 병합합니다.
3. `automation/incoming/{dataset}/`에 추가 파일이 있으면 기존 outputs CSV에 날짜 기준으로 병합합니다.
4. 옵션이 켜져 있으면 `preprocess_sources.py`가 01번 전처리의 최종 포맷에 맞춰 `분석용일별통합데이터.csv`를 재생성합니다.
5. AI 입력/모델 단계는 현재 Actions에서 바로 돌리지 않고 waiting 상태로 로그를 남깁니다.
6. 대시보드 JSON을 다시 생성합니다.
7. `automation/logs/latest_pipeline_report.json`에 실행 결과를 저장합니다.

## GitHub Actions

`.github/workflows/daily-data-pipeline.yml`이 이 파이프라인을 실행합니다.

- schedule: 매일 03:00 KST, 07:00 KST 재시도
- manual: `workflow_dispatch`에서 `start_date`, `end_date`를 지정해 강제 실행 가능

기존 `page-data-refresh.yml`은 같은 시간대에 페이지 JSON만 갱신하던 워크플로입니다. 새 파이프라인이 페이지 데이터 갱신까지 포함하므로, 중복 커밋 충돌을 피하기 위해 수동 실행만 남겨둡니다.

현재 secrets 기준으로 사용하는 값:

- `BOK_ECOS_API_KEY`
- `GEOCODER_TOKEN`
- `KAKAO_REST_API_KEY`
- `NAVER_MAPS_CLIENT_ID`
- `NAVER_MAPS_CLIENT_SECRET`
- `VWORLD_API_KEY`

OPINET 전국 단위 데이터는 현재 코드에서 OPINET CSV/HTML 다운로드 URL을 사용하므로 OPINET key가 필요하지 않습니다. `OPINET_CERTKEY`는 코드에 자리만 남아 있고 현재 자동수집 경로에서는 사용하지 않습니다.

주유소 지역별 가격 다운로드는 Selenium/브라우저 다운로드 방식이라 현재 일일 GitHub Actions 자동 수집에서 제외합니다. 대용량 개별 주유소 파일은 수동/별도 경로로 갱신한 뒤 필요한 경우 page 및 AI 입력 데이터에 반영합니다.
