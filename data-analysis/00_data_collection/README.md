# 00. Data Collection Readiness

00 단계는 분석에 필요한 원천 데이터가 준비되어 있는지 확인하고, 이후 단계가 사용할 입력 목록을 manifest로 정리하는 단계입니다. 실제 분석 모델을 만들기보다, “어떤 데이터가 어느 단계에 필요한가”와 “현재 사용할 수 있는가”를 점검합니다.

## 단계 목적

| 목적 | 내용 |
|---|---|
| 입력 데이터 점검 | 원유, 국제제품가격, 환율, 전국 평균 가격, 세금, 주유소 가격, 정책 데이터 등 필수 입력의 존재 여부 확인 |
| 분석 계약 정리 | 각 입력이 어느 단계에서 쓰이는지 기록 |
| 수동 데이터 구조 보장 | 정책 자료처럼 수동으로 넣어야 하는 데이터의 보관 구조 확인 |
| 다음 단계 연결 | 01 전처리와 05 정책 적용 단계가 필요한 입력을 안정적으로 찾을 수 있게 정리 |

## 점검 로직

| 함수 | 역할 |
|---|---|
| `latest_under(base, pattern)` | 지정한 dataset 안에서 패턴에 맞는 최신 파일을 찾습니다. |
| `first_existing(paths)` | 후보 경로 중 실제 존재하는 첫 파일을 선택합니다. |
| `ensure_manual_dataset_folders(dataset_name)` | 수동 입력 데이터셋의 `raw`, `final`, `logs` 구조를 보장합니다. |

원천 파일 평가는 `SPECS` 목록을 기준으로 수행합니다. 각 spec은 데이터 이름, dataset 묶음, 필수 여부, 예상 파일명, 다음 단계 사용처를 포함합니다.

## 필수 입력 데이터

01 전처리에 필요한 핵심 입력은 다음과 같습니다.

| name | dataset | 입력 성격 | 다음 단계 |
|---|---|---|---|
| `crude` | `crude` | 두바이, 브렌트, WTI 원유 가격 | 01 |
| `retail_avg` | `retail_avg` | 전국 주유소 평균 소비자 가격 | 01 |
| `brand_gasoline` | `brand_price` | 휘발유 브랜드별 평균 가격 | 01 |
| `brand_diesel` | `brand_price` | 경유 브랜드별 평균 가격 | 01 |
| `fx_usdkrw` | `fx_usdkrw` | 원/달러 환율 | 01 |
| `intl_products` | `intl_products` | 국제 석유제품 가격 | 01 |
| `intl_product_diesel_0001` | `intl_products` | 저유황 경유 제품가격 | 01 |
| `gasoline_tax_trend` | `fuel_tax_trend` | 휘발유 세금 구성 | 01 |
| `diesel_tax_trend` | `fuel_tax_trend` | 경유 세금 구성 | 01 |
| `refinery_weekly_supply` | `refinery_weekly_supply` | 정유사 주간 공급 가격 | 01 |

05 정책 적용 단계에 필요한 정책 입력은 별도 필수 데이터로 관리합니다.

| name | dataset | 내용 | 다음 단계 |
|---|---|---|---|
| `korea_fuel_tax_price_policies` | `z_pa_policy` | 유류세 인하, 최고가격제, 정책 적용 기간 | 05 |

다음 입력은 manifest에는 기록되지만 현재 01~05 분석 파이프라인의 핵심 계산에는 직접 쓰이지 않는 보조 입력입니다.

| name | dataset | 비고 |
|---|---|---|
| `import_cost` | `import_cost` | 원유/제품 도입 비용 보조 자료 |
| `opinet_station_master` | `gas_station_master` | 주유소 master 후보 자료 |
| `opinet_station_price` | `gas_station_price` | 주유소 가격 보조 후보 자료 |

## 산출물 성격

| 산출물 | 설명 |
|---|---|
| `data_analysis_input_manifest.csv` | 원천 파일별 발견 여부, 필수 여부, 다음 단계 사용처를 기록한 입력 점검표 |
| 수동 정책 데이터 구조 | 유류세 인하와 최고가격제 정책 자료를 05 단계가 읽을 수 있게 정리한 구조 |

이 단계의 핵심 산출물은 분석 데이터 자체가 아니라 “원천 데이터가 준비되어 있다”는 표현 가능성 확인입니다. 실제 가격 병합과 변수 정리는 01 전처리부터 수행됩니다.

## 다음 단계 연결

01 전처리는 이 단계에서 확인한 원유, 국제제품가격, 환율, 전국 평균 가격, 세금 자료를 이용해 일별 통합 데이터를 만듭니다. 정책 자료는 05 단계에서 적정가격 산출과 정책 적용 여부 판정에 사용됩니다.
