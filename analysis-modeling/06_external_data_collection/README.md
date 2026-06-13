# 06 External Data Collection And Preprocessing

이 단계는 원본 Colab의 `4단계: 데이터 격자화` 안에 있던 외부 데이터 수집 및 전처리 부분만 분리한 단계입니다. 다음 단계인 `07_spatial_grid_build`에서 사용할 공간 기반 외부 데이터를 준비하는 것이 목적입니다.

정리 대상은 현재 원본 코드에 실제로 구현되어 있는 두 묶음입니다.

- 공장, 저유소, 대리점 위치 데이터
- 전국 개별 주유소 가격 및 메타데이터

개별공시지가는 원본 프로젝트에서 브이월드 계열 데이터를 로컬 외부 프로그램으로 별도 처리한 것으로 확인됩니다. 따라서 이 폴더에는 개별공시지가 처리 코드를 억지로 만들지 않고, 처리 사실과 API 대체 가능성만 문서화했습니다.

## Notebook

- `06_external_data_collection.ipynb`

이 노트북은 Colab에서 단독 실행할 수 있도록 `ROOT_PATH`, `DATA_PATH`, `PROCESSED_PATH` 설정 셀을 포함합니다. 원본 경로는 유지했으므로 다른 사용자는 첫 설정 셀의 `ROOT_PATH`만 본인 Google Drive 경로로 바꾸면 됩니다.

## Source Data

### 1. 공장/저유소/대리점 위치

원천은 대한석유협회 회원사 페이지입니다.

- SK 계열: `https://www.petroleum.or.kr/association/member_1`
- GS 계열: `https://www.petroleum.or.kr/association/member_2`
- S-OIL 계열: `https://www.petroleum.or.kr/association/member_3`
- HD현대오일뱅크 계열: `https://www.petroleum.or.kr/association/member_4`

코드는 각 회사의 회사개요, 저유소, 대리점 페이지를 순회합니다. 회사개요에서는 공장 주소를 추출하고, 저유소 및 대리점은 목록형 게시판을 페이지 단위로 순회해 수집합니다.

### 2. 전국 개별 주유소

원천은 오피넷 다운로드 페이지입니다.

- 다운로드 URL: `https://www.opinet.co.kr/user/opdown/opDownload.do`
- 공공데이터포털 참고 페이지: `https://www.data.go.kr/data/15044646/fileData.do`

코드는 Selenium으로 오피넷 다운로드 화면을 열고, 지역별/연도별 기간을 지정해 CSV를 내려받습니다. 수집 기간은 코드상 2008년 4월 15일부터 2026년까지입니다.

처리 지역은 다음 17개입니다.

`강원`, `경기`, `경남`, `경북`, `광주`, `대구`, `대전`, `부산`, `서울`, `세종`, `울산`, `인천`, `전남`, `전북`, `제주`, `충남`, `충북`

## Processing Flow

### 1. 회원사 시설 데이터 수집

`COMPANY_MAP`에 정의된 4개 정유사 페이지를 순회합니다.

주요 처리 내용은 다음과 같습니다.

- HTML 요청 시 `requests.Session`과 브라우저 User-Agent 사용
- 회사개요 페이지에서 공장 주소 후보 추출
- 저유소, 대리점 게시판 페이지 수 확인
- 페이지별 행 파싱
- `상표`, `구분`, `이름`, `주소` 컬럼으로 표준화
- 중복 행 제거
- 상표 및 시설 구분 순서로 정렬

산출 파일은 다음 경로에 저장됩니다.

```text
DATA_PATH/facility_data.csv
```

### 2. 시설 좌표 보강

`facility_data.csv`를 입력으로 받아 Google Maps UI 자동화를 수행합니다. 원본 코드는 Playwright 기반 브라우저 자동화로 후보 장소를 검색하고, 주소 및 이름 유사도 기준으로 좌표 후보를 선택합니다.

주요 처리 내용은 다음과 같습니다.

- 주소 표기 정규화
- 정유사 상표명, 법인 표기, 휴게소/충전소 명칭 보정
- 후보 장소의 이름 유사도 계산
- 후보 장소의 주소 유사도 계산
- 좌표 중복 및 검색 실패 케이스 분리
- 중간 저장 및 이어받기 지원

산출 파일은 다음 경로에 저장됩니다.

```text
PROCESSED_PATH/additional_data/1 facility_location_data.csv
```

이후 원본 코드에는 좌표 누락 또는 오매칭 가능성이 있는 시설을 수동 보정하는 딕셔너리가 들어 있습니다. 이 보정 단계에서는 일부 시설을 제거하고, 직접 지정한 위도/경도를 덮어쓴 뒤 최종 파일을 저장합니다.

최종 산출 파일은 다음 경로입니다.

```text
PROCESSED_PATH/additional_data/1 facility_location_data_final.csv
```

최종 컬럼은 다음과 같습니다.

- `상표`
- `대상`
- `경도`
- `위도`

### 3. 오피넷 지역별 CSV 다운로드

Colab에 Google Chrome stable과 Selenium을 설치한 뒤 오피넷 다운로드 페이지를 자동 조작합니다.

주요 처리 내용은 다음과 같습니다.

- 지역별 다운로드 폴더 생성
- 2008년은 `20080415~20081231`, 이후 연도는 `YYYY0101~YYYY1231` 기간으로 분할
- 다운로드 완료 파일 감지
- 지역명, 연도, 기간이 포함된 파일명으로 저장
- 이미 처리한 지역은 `DONE_LIST`에 넣어 재수집 제외 가능

원본 코드에는 `Done_list`가 정의되어 있지 않아 단독 실행 시 오류가 날 수 있었습니다. 정리된 노트북에서는 이를 `DONE_LIST = []`로 명시해 바로 실행 가능한 형태로 수정했습니다.

다운로드 산출물은 다음 폴더 아래에 지역별로 저장됩니다.

```text
DATA_PATH/gas_station_prices_by_region/{지역}/
```

### 4. 중복 다운로드 파일 점검

오피넷 다운로드 과정에서 같은 파일이 `_1.csv` 형태로 중복 생성될 수 있어, 해당 파일을 찾아 삭제 후보로 출력합니다.

기본값은 다음과 같습니다.

```python
DRY_RUN = True
```

`DRY_RUN=True`이면 삭제하지 않고 대상만 출력합니다. 실제 삭제가 필요하면 파일 목록을 확인한 뒤 `False`로 바꿔 실행해야 합니다.

### 5. 지역별 가격 시계열 및 메타데이터 생성

지역별 원천 CSV를 읽어 주유소별 가격 시계열과 메타데이터를 생성합니다.

주요 처리 내용은 다음과 같습니다.

- 파일 인코딩 자동 판별
- 날짜, 상호, 주소, 상표, 셀프 여부, 휘발유 가격, 경유 가격 정규화
- `station_id`, `date` 기준 중복 제거
- 휘발유 가격 wide matrix 생성
- 경유 가격 wide matrix 생성
- 주유소별 메타데이터 변경 이력 생성

원본 코드는 `TARGET_REGION = "제주"`처럼 한 지역만 처리하도록 되어 있었습니다. 정리된 노트북에서는 17개 지역을 순회하도록 수정했습니다.

지역별 산출 파일은 다음 경로에 저장됩니다.

```text
PROCESSED_PATH/additional_data/gas_station_prices_by_region/{지역}/gasoline.csv
PROCESSED_PATH/additional_data/gas_station_prices_by_region/{지역}/diesel.csv
PROCESSED_PATH/additional_data/gas_station_prices_by_region/{지역}/metadata.json
PROCESSED_PATH/additional_data/gas_station_prices_by_region/{지역}/failed_files_log.csv
```

`failed_files_log.csv`는 처리 실패 파일이 있을 때만 생성됩니다.

### 6. 주유소 메타데이터 좌표 보강

`metadata.json`에 들어 있는 주소 이력을 지오코딩해 `location` 이력을 추가합니다.

주요 처리 내용은 다음과 같습니다.

- 주소 후보 정규화
- 1차 지오코더 API 배치 호출
- 선택적으로 JUSO 도로명주소 검색 API를 이용한 2차 보정
- 1차/2차 결과 거리 비교
- 주소 이력별 `[start_date, latitude, longitude]` 생성
- 좌표 실패 및 검토 필요 케이스 기록

원본 코드에는 지오코더 토큰과 JUSO API 키가 하드코딩되어 있었습니다. 공개 레포에 민감한 키를 올리지 않기 위해 정리된 노트북에서는 빈 문자열로 바꾸었습니다. 실행자는 해당 셀의 `GEOCODER_TOKEN`을 직접 입력해야 합니다. `SECONDARY_MODE`를 `fallback_only` 또는 `compare_all`로 바꿀 경우 `JUSO_SEARCH_API_KEY`도 입력해야 합니다.

좌표 보강 산출 파일은 다음 경로에 저장됩니다.

```text
PROCESSED_PATH/additional_data/gas_station_prices_by_region/{지역}/metadata__latlon.json
```

### 7. 전국 좌표 데이터 점검

모든 지역의 `metadata__latlon.json`을 읽어 유효 좌표 수와 지역별 점 개수를 출력하고, 지도 위에 위치를 시각화합니다.

이 셀은 현재 파일 저장 코드를 포함하지 않고 `plt.show()`로 그림을 표시합니다. 이미지 결과를 레포에 넣으려면 실행 후 별도로 저장 코드를 추가하거나 수동으로 저장해야 합니다.

## Public Land Price

개별공시지가는 노트북 셀에서 직접 실행하지 않고 별도 스크립트로 분리했습니다.

```text
official_land_price_wfs_grid.py
```

이 스크립트는 VWorld `개별공시지가WFS조회`에서 필지 geometry와 `pblntf_pclnd` 가격을 내려받고, EPSG:5179 기준 500m 격자에 면적가중 평균으로 집계합니다. 출력 CSV는 이후 `07_spatial_grid_build`에서 사용하는 형식과 맞춘 다음 컬럼을 가집니다.

```text
grid_id, cell_x, cell_y, p_YYYYMMDD
```

로컬/PyCharm 환경에서 smoke test를 통과했습니다.

```bash
python official_land_price_wfs_grid.py --snapshot-date 20260526 --output official_land_price_wfs_grid_20260526.csv
```

운영 실행에서는 VWorld 인증키를 환경변수로 지정하는 것을 권장합니다.

```bash
set VWORLD_KEY=...
python official_land_price_wfs_grid.py --no-doc-preview-key --snapshot-date 20260526 --bbox5179-file tiles_5179.csv --output 공시지가.csv
```

확인된 환경 제약은 다음과 같습니다.

- 로컬/PyCharm 환경에서는 WFS 데이터 다운로드와 500m 격자 전처리가 가능합니다.
- Colab과 GitHub-hosted Actions에서는 VWorld 목록 페이지 또는 WFS API가 `RemoteDisconnected`, `502 Bad Gateway`로 실패할 수 있습니다.
- GitHub 자동화가 필요하면 GitHub-hosted runner보다 로컬 PC 또는 self-hosted runner 사용을 권장합니다.

API 가능 여부는 별도로 확인했습니다.

- 공공데이터포털의 `국토교통부_개별공시지가정보(WMS/WFS/속성정보)`는 JSON/XML 형식의 공간정보 RestAPI로 개별토지 단위면적당 가격정보를 반환한다고 안내합니다.
- 같은 페이지에서 API 유형은 `LINK`, 데이터포맷은 `JSON+XML`, 제공기관은 국토교통부, 공간범위는 대한민국 전체, 비용은 무료로 표시됩니다.
- VWorld API 목록에는 개별공시지가에 대해 `WMS`, `WFS`, `속성조회`가 각각 제공되는 것으로 표시됩니다.

즉, 개별공시지가를 API로 조회하는 것은 가능합니다. 다만 이 프로젝트처럼 전국 격자 단위 feature를 만들려면 필지 단위 API를 대량 반복 호출해야 하므로 호출량 제한, 속도, 장애 복구를 고려해 bbox 타일을 작게 나누고 체크포인트를 남기는 방식이 필요합니다.

실무적으로 권장되는 방식은 다음과 같습니다.

- 전국 또는 시군구 단위의 개별공시지가 공간 데이터를 벌크로 확보
- 좌표계와 연도/기준월을 정리
- 필지 폴리곤 또는 대표점을 격자와 공간 조인
- 격자별 평균, 중앙값, 면적가중 평균 등으로 요약

전국 전체 수집은 `--bbox5179-file`에 작은 EPSG:5179 타일 목록을 넣어 반복 실행하는 방식으로 확장할 수 있습니다. 단일 bbox에서 `totalFeatures`가 `maxFeatures`보다 크면 스크립트가 중단되며, 해당 bbox를 더 작게 분할해야 합니다.

## Outputs Folder

이 폴더의 `outputs/`에는 결과 파일만 넣습니다. README나 설명용 문서는 넣지 않습니다.

현재 실행 결과 파일을 제공받지 않았으므로 `outputs/`는 비워 둡니다. 결과를 넣는다면 코드 기준으로 다음 파일들이 대상입니다.

- `facility_data.csv`
- `1 facility_location_data.csv`
- `1 facility_location_data_final.csv`
- `gas_station_prices_by_region/{지역}/gasoline.csv`
- `gas_station_prices_by_region/{지역}/diesel.csv`
- `gas_station_prices_by_region/{지역}/metadata.json`
- `gas_station_prices_by_region/{지역}/metadata__latlon.json`
- `gas_station_prices_by_region/{지역}/failed_files_log.csv` if generated

원천 다운로드 CSV는 용량이 클 수 있으므로 레포에 포함할지 별도 판단이 필요합니다. 모델 입력에 직접 필요한 것은 최종 전처리 산출물입니다.

## Notes

- Google Maps UI 자동화는 웹 UI 변경에 취약하고 서비스 정책 이슈가 있을 수 있습니다. 운영 자동화 단계에서는 공식 지오코딩 API 또는 이미 확보한 좌표 데이터 사용을 우선 검토해야 합니다.
- 오피넷 다운로드 자동화도 Selenium 기반이라 화면 구조 변경에 영향을 받을 수 있습니다.
- 지오코더 토큰은 공개 레포에 포함하지 않습니다.
- 출력 셀이 없는 원본 구간이라 결과 수치 요약은 작성할 수 없습니다. 이 README는 코드 구조, 처리 방식, 산출 파일 기준으로 정리했습니다.
