const SVG_NS = "http://www.w3.org/2000/svg";
const NATIONAL_REGION = "\uC804\uAD6D";
const DEFAULT_TREND_YEARS = 1;

const state = {
  fuel: "gasoline",
  manifest: null,
  national: null,
  regions: [],
  stations: [],
  history: [],
  trainingCoverage: null,
  geojson: null,
  selectedRegion: null,
  regionDetailEnabled: false,
  userLocation: null,
  locationError: "",
};

const REGION_ORDER = [
  "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
  "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
];

const REGION_NAME_MAP = {
  "서울특별시": "서울",
  "부산광역시": "부산",
  "대구광역시": "대구",
  "인천광역시": "인천",
  "광주광역시": "광주",
  "대전광역시": "대전",
  "울산광역시": "울산",
  "세종특별자치시": "세종",
  "경기도": "경기",
  "강원도": "강원",
  "강원특별자치도": "강원",
  "충청북도": "충북",
  "충청남도": "충남",
  "전라북도": "전북",
  "전북특별자치도": "전북",
  "전라남도": "전남",
  "경상북도": "경북",
  "경상남도": "경남",
  "제주특별자치도": "제주",
};

const REGION_COLORS = {
  서울: "#5b8def",
  부산: "#e06962",
  대구: "#55a868",
  인천: "#c47ad9",
  광주: "#e0a33a",
  대전: "#4db6ac",
  울산: "#ef7f45",
  세종: "#8d7bd8",
  경기: "#6aaed6",
  강원: "#8abf4f",
  충북: "#d783b5",
  충남: "#b6a04b",
  전북: "#4f9f8f",
  전남: "#d77a57",
  경북: "#7e9ad8",
  경남: "#76b37d",
  제주: "#b98b5f",
};

const MAP_SIZE = { width: 1040, height: 900 };
const MAP_BOUNDS = { x: 214, y: 58, width: 612, height: 780 };
const DETAIL_MAP_SIZE = { width: 620, height: 720 };
const CALLOUT_W = 228;
const CALLOUT_H = 76;
const KOREA_LAT_SCALE = 1.0;
const USE_FIXED_SAMPLE_PRICES = false;
const SAMPLE_ACTUAL_PRICE = 1500;
const SAMPLE_FAIR_PRICE = 1400;
const SAMPLE_BAND_LOW = 1380;
const SAMPLE_BAND_HIGH = 1420;
const SAMPLE_GAP_PRICE = SAMPLE_ACTUAL_PRICE - SAMPLE_FAIR_PRICE;

function sampleMetric(extra = {}) {
  return {
    actual_price: SAMPLE_ACTUAL_PRICE,
    fair_price_policy: SAMPLE_FAIR_PRICE,
    band_low_policy: SAMPLE_BAND_LOW,
    band_high_policy: SAMPLE_BAND_HIGH,
    gap_policy: SAMPLE_GAP_PRICE,
    judge_policy: "비쌈",
    ...extra,
  };
}

const TRAINING_COVERAGE_FALLBACK = {
  schema_version: "training_data_coverage_v1",
  generated_at: null,
  datasets: [
    {
      id: "grid_panel_rows",
      label: "AI 학습 격자 패널 행 수",
      unit: "행",
      status: "waiting",
      rows: 0,
      date_min: null,
      date_max: null,
      path: "ROOT_PATH/그리드/grid.parquet",
      note: "AI 02 최종 grid.parquet를 시도·날짜별로 집계한 값이 필요합니다.",
    },
    {
      id: "station_count",
      label: "주유소 입력 수",
      unit: "개",
      status: "waiting",
      rows: 0,
      date_min: null,
      date_max: null,
      path: "data-analysis/00_data_collection/outputs/derived_data/station_points.csv",
      note: "AI 01 주유소 좌표/프로필 산출물을 시도별로 집계한 값이 필요합니다.",
    },
    {
      id: "facility_count",
      label: "시설 영향력 입력 수",
      unit: "개",
      status: "waiting",
      rows: 0,
      date_min: null,
      date_max: null,
      path: "data-analysis/00_data_collection/outputs/derived_data/facility_points.csv",
      note: "AI 01 시설 좌표 산출물을 시도별로 집계한 값이 필요합니다.",
    },
    {
      id: "land_price_grid_count",
      label: "공시지가 격자 수",
      unit: "격자",
      status: "waiting",
      rows: 0,
      date_min: null,
      date_max: null,
      path: "data-analysis/00_data_collection/outputs/derived_data/official_land_price_grid.csv",
      note: "공시지가 500m 격자 산출물을 시도·날짜별로 집계한 값이 필요합니다.",
    },
  ],
  rows: [],
};

const CALLOUT_POSITIONS = {
  서울: { side: "left", x: 20, y: 38 },
  인천: { side: "left", x: 20, y: 122 },
  경기: { side: "left", x: 20, y: 206 },
  충남: { side: "left", x: 20, y: 290 },
  세종: { side: "left", x: 20, y: 374 },
  전북: { side: "left", x: 20, y: 458 },
  광주: { side: "left", x: 20, y: 542 },
  전남: { side: "left", x: 20, y: 626 },
  제주: { side: "left", x: 20, y: 786 },
  강원: { side: "right", x: 792, y: 54 },
  충북: { side: "right", x: 792, y: 158 },
  대전: { side: "right", x: 792, y: 262 },
  경북: { side: "right", x: 792, y: 366 },
  대구: { side: "right", x: 792, y: 470 },
  울산: { side: "right", x: 792, y: 574 },
  부산: { side: "right", x: 792, y: 678 },
  경남: { side: "right", x: 792, y: 782 },
};

const FALLBACK_NATIONAL = {
  schema_version: "national_today_v1",
  as_of_date: "2026-06-09",
  generated_at: "sample",
  freshness: "sample",
  fuels: {
    gasoline: {
      label: "휘발유",
      ...sampleMetric({ policy_effect: 0, actual_delta_1d: 0 }),
    },
    diesel: {
      label: "경유",
      ...sampleMetric({ policy_effect: 0, actual_delta_1d: 0 }),
    },
  },
  policies: [
    {
      title: "유류세 인하 반영",
      status: "정책 효과 반영",
      period: "분석 산출물 기준",
      gasoline_effect: 0,
      diesel_effect: 0,
      note: "전국 적정가격 산식에 반영된 정책효과입니다.",
    },
    {
      title: "정유사 최고가격제",
      status: "정책 탭 표시 대상",
      period: "정책 기간 데이터 연결 전",
      gasoline_effect: null,
      diesel_effect: null,
      note: "정책 기간 원자료가 연결되면 실제 적용 여부를 갱신합니다.",
    },
  ],
};

const FALLBACK_REGIONS = REGION_ORDER.map((region) => ({
  region,
  gasoline: sampleMetric(),
  diesel: sampleMetric(),
}));

const FALLBACK_STATIONS = [
  { station_id: "sample-seoul-1", name: "도심셀프주유소", brand: "SK에너지", region: "서울", address: "서울특별시 중구 세종대로 1", lon: 126.978, lat: 37.566, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
  { station_id: "sample-seoul-2", name: "한강대로주유소", brand: "GS칼텍스", region: "서울", address: "서울특별시 용산구 한강대로 100", lon: 126.972, lat: 37.532, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
  { station_id: "sample-gyeonggi-1", name: "수원표준주유소", brand: "HD현대오일뱅크", region: "경기", address: "경기도 수원시 팔달구 효원로 1", lon: 127.028, lat: 37.263, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
  { station_id: "sample-incheon-1", name: "송도에너지", brand: "S-OIL", region: "인천", address: "인천광역시 연수구 컨벤시아대로 1", lon: 126.645, lat: 37.389, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
  { station_id: "sample-busan-1", name: "부산항주유소", brand: "GS칼텍스", region: "부산", address: "부산광역시 중구 중앙대로 1", lon: 129.04, lat: 35.104, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
  { station_id: "sample-daegu-1", name: "달구벌셀프", brand: "SK에너지", region: "대구", address: "대구광역시 중구 달구벌대로 1", lon: 128.601, lat: 35.871, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
  { station_id: "sample-gwangju-1", name: "무등주유소", brand: "알뜰", region: "광주", address: "광주광역시 동구 금남로 1", lon: 126.916, lat: 35.146, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
  { station_id: "sample-daejeon-1", name: "대전IC주유소", brand: "HD현대오일뱅크", region: "대전", address: "대전광역시 동구 동서대로 1", lon: 127.433, lat: 36.35, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
  { station_id: "sample-ulsan-1", name: "태화강주유소", brand: "S-OIL", region: "울산", address: "울산광역시 남구 삼산로 1", lon: 129.311, lat: 35.539, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
  { station_id: "sample-jeju-1", name: "제주공항주유소", brand: "GS칼텍스", region: "제주", address: "제주특별자치도 제주시 공항로 1", lon: 126.493, lat: 33.506, gasoline_price: SAMPLE_ACTUAL_PRICE, diesel_price: SAMPLE_ACTUAL_PRICE, judge_policy: "비쌈" },
].map((station) => ({
  ...station,
  gasoline_price: SAMPLE_ACTUAL_PRICE,
  diesel_price: SAMPLE_ACTUAL_PRICE,
  judge_policy: "비쌈",
}));

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function won(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}원/L`;
}

function compactWon(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 0 });
}

function priceWon(value) {
  const formatted = compactWon(value);
  return formatted === "-" ? "-" : `${formatted}원`;
}

function signedPriceWon(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}원`;
}

function signedWon(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}원/L`;
}

function koreanDate(value) {
  const date = new Date(`${value || ""}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "오늘";
  return `${date.getFullYear()}년 ${String(date.getMonth() + 1).padStart(2, "0")}월 ${String(date.getDate()).padStart(2, "0")}일`;
}

function gapToneClass(gap) {
  const numeric = Number(gap);
  if (numeric > 0) return "gap-high";
  if (numeric < 0) return "gap-low";
  return "gap-good";
}

function judgeClass(value, gap) {
  if (value === "적정") return "good";
  if (value === "비쌈" || value === "상향이탈") return "high";
  if (value === "저렴" || value === "하향이탈") return "low";
  if (Number(gap) > 30) return "high";
  if (Number(gap) < -30) return "low";
  return "good";
}

function canonicalRegionName(name) {
  return REGION_NAME_MAP[name] || name;
}

async function loadJson(path, fallback) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return await response.json();
  } catch (error) {
    console.warn(`[fallback] ${path}`, error);
    return fallback;
  }
}

function mergeMetric(fallbackMetric = {}, incomingMetric = {}) {
  return { ...fallbackMetric, ...incomingMetric };
}

function regionRows() {
  const rows = new Map();
  FALLBACK_REGIONS.forEach((row) => rows.set(row.region, JSON.parse(JSON.stringify(row))));

  (Array.isArray(state.regions) ? state.regions : []).forEach((row) => {
    const region = canonicalRegionName(String(row.region || "").trim());
    if (!region) return;
    const fallback = rows.get(region) || { region };
    rows.set(region, {
      ...fallback,
      ...row,
      region,
      gasoline: mergeMetric(fallback.gasoline, row.gasoline),
      diesel: mergeMetric(fallback.diesel, row.diesel),
    });
  });

  return REGION_ORDER.map((region) => rows.get(region)).filter(Boolean);
}

function rowForRegion(region) {
  return regionRows().find((row) => row.region === region) || regionRows()[0];
}

function metricFor(row) {
  return row?.[state.fuel] || {};
}

function activeFuel() {
  const data = state.national || FALLBACK_NATIONAL;
  return data.fuels?.[state.fuel] || FALLBACK_NATIONAL.fuels[state.fuel];
}

function activePolicies() {
  const data = state.national || FALLBACK_NATIONAL;
  const policies = Array.isArray(data.policies) && data.policies.length ? data.policies : FALLBACK_NATIONAL.policies;
  return policies.map((policy) => ({
    ...policy,
    effect: policy[`${state.fuel}_effect`] ?? policy.effect ?? null,
  }));
}

function baseStations() {
  return Array.isArray(state.stations) && state.stations.length ? state.stations : FALLBACK_STATIONS;
}

function fuelLabel(fuel = state.fuel) {
  return fuel === "gasoline" ? "휘발유" : "경유";
}

function stationPrice(station) {
  return state.fuel === "gasoline" ? station.gasoline_price : station.diesel_price;
}

function toIsoDate(value) {
  if (!value) return "";
  const text = String(value).slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return formatIsoDate(date);
}

function formatIsoDate(date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function dateInRange(value, start, end) {
  const date = toIsoDate(value);
  if (!date) return false;
  if (start && date < start) return false;
  if (end && date > end) return false;
  return true;
}

function snapshotHistoryRows() {
  const data = state.national || FALLBACK_NATIONAL;
  const date = data.as_of_date || FALLBACK_NATIONAL.as_of_date;
  const rows = [];

  Object.entries(data.fuels || FALLBACK_NATIONAL.fuels).forEach(([fuel, metric]) => {
    rows.push({
      date,
      region: NATIONAL_REGION,
      fuel,
      actual_price: metric.actual_price,
      fair_price_policy: metric.fair_price_policy,
      band_low_policy: metric.band_low_policy,
      band_high_policy: metric.band_high_policy,
      gap_policy: metric.gap_policy,
      source: "latest_snapshot",
    });
  });

  regionRows().forEach((row) => {
    ["gasoline", "diesel"].forEach((fuel) => {
      const metric = row[fuel] || {};
      rows.push({
        date,
        region: row.region,
        fuel,
        actual_price: metric.actual_price,
        fair_price_policy: metric.fair_price_policy,
        band_low_policy: metric.band_low_policy,
        band_high_policy: metric.band_high_policy,
        gap_policy: metric.gap_policy,
        source: "latest_snapshot",
      });
    });
  });

  return rows;
}

function historyRows() {
  const incoming = Array.isArray(state.history) ? state.history : [];
  if (!incoming.length) return snapshotHistoryRows();

  const normalized = incoming
    .map((row) => ({
      date: toIsoDate(row.date || row.as_of_date),
      region: canonicalRegionName(row.region || NATIONAL_REGION),
      fuel: row.fuel,
      actual_price: row.actual_price,
      fair_price_policy: row.fair_price_policy,
      band_low_policy: row.band_low_policy,
      band_high_policy: row.band_high_policy,
      gap_policy: row.gap_policy,
      source: row.source || "history",
    }))
    .filter((row) => row.date && ["gasoline", "diesel"].includes(row.fuel));

  const seen = new Set(normalized.map((row) => `${row.date}|${row.region}|${row.fuel}`));
  snapshotHistoryRows().forEach((row) => {
    const key = `${row.date}|${row.region}|${row.fuel}`;
    if (!seen.has(key)) normalized.push(row);
  });

  return normalized.sort((a, b) => a.date.localeCompare(b.date));
}

function dateExtent(rows) {
  const dates = rows.map((row) => row.date).filter(Boolean).sort();
  return {
    min: dates[0] || "",
    max: dates[dates.length - 1] || "",
  };
}

function defaultTrendStart(extent) {
  if (!extent.max) return extent.min;
  const end = new Date(`${extent.max}T12:00:00`);
  if (Number.isNaN(end.getTime())) return extent.min;
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - DEFAULT_TREND_YEARS);
  const iso = formatIsoDate(start);
  return extent.min && iso < extent.min ? extent.min : iso;
}

function configureDateInput(id, extent, fallbackValue) {
  const input = document.getElementById(id);
  if (!input) return;
  input.min = extent.min;
  input.max = extent.max;
  if (!input.value) input.value = fallbackValue;
}

function setSelectOptions(select, options) {
  if (!select) return;
  const current = select.value;
  select.innerHTML = options.map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`).join("");
  if (options.some((option) => option.value === current)) select.value = current;
}

function formatCount(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString("ko-KR");
}

function dateRangeLabel(minDate, maxDate) {
  if (!minDate && !maxDate) return "-";
  if (minDate && maxDate && minDate !== maxDate) return `${minDate} ~ ${maxDate}`;
  return minDate || maxDate;
}

function renderStatus() {
  const data = state.national || FALLBACK_NATIONAL;
  const asOfCopy = document.getElementById("as-of-copy");
  const basisCopy = document.getElementById("data-basis-copy");
  const generatedAt = document.getElementById("site-generated-at");

  const samplePrefix = data.freshness === "sample" ? "샘플 " : "";
  const dateLabel = koreanDate(data.as_of_date);
  if (asOfCopy) asOfCopy.textContent = `${samplePrefix}적정가격 기준일: ${dateLabel}`;
  if (basisCopy) basisCopy.textContent = "현재가는 전일 공시 평균 가격입니다. 적정가격은 t-1~t-28 데이터를 입력해 t일 기준으로 산출합니다.";
  if (generatedAt) generatedAt.textContent = data.generated_at ? `데이터 생성: ${data.generated_at}` : "데이터 생성 시각 없음";
}

function renderNational() {
  const fuel = activeFuel();
  const judge = fuel.judge_policy || "-";
  const klass = judgeClass(judge, fuel.gap_policy);
  const chip = document.getElementById("judge-chip");

  document.getElementById("fuel-label").textContent = fuel.label || (state.fuel === "gasoline" ? "휘발유" : "경유");
  document.getElementById("metric-actual").textContent = won(fuel.actual_price);
  document.getElementById("metric-actual-delta").textContent = `전일 대비 ${signedWon(fuel.actual_delta_1d)}`;
  document.getElementById("metric-fair").textContent = won(fuel.fair_price_policy);
  document.getElementById("metric-band").textContent = `적정 범위 ${won(fuel.band_low_policy)} ~ ${won(fuel.band_high_policy)}`;
  document.getElementById("metric-gap").textContent = signedWon(fuel.gap_policy);
  document.getElementById("metric-judge").textContent = judge;
  document.getElementById("metric-policy").textContent = `정책효과 ${won(fuel.policy_effect)}`;
  chip.textContent = klass === "high" ? "적정가보다 높음" : klass === "low" ? "적정가보다 낮음" : "적정권";
  chip.className = `judge-chip ${klass}`;
}

function renderMapHeader() {
  const data = state.national || FALLBACK_NATIONAL;
  const fuel = activeFuel();
  const label = fuel.label || fuelLabel();
  const dateLabel = koreanDate(data.as_of_date);
  document.getElementById("map-today-copy").textContent = `오늘(${dateLabel}) 산출 ${label} 적정가격과 전일 실제가격을 비교합니다`;
}

function renderPolicies() {
  const policies = activePolicies();
  const policyMarkup = policies.map((policy) => `
    <article class="policy-item">
      <strong>${escapeHtml(policy.title)}</strong>
      <span>${escapeHtml(policy.status || policy.period || "-")}</span>
      <span>${policy.effect === null || policy.effect === undefined ? "효과 산정 대기" : `효과 ${won(policy.effect)}`}</span>
    </article>
  `).join("");

  const detailMarkup = policies.map((policy) => `
    <article class="policy-detail-card">
      <strong>${escapeHtml(policy.title)}</strong>
      <span>${escapeHtml(policy.period || "-")}</span>
      <span>${escapeHtml(policy.note || policy.status || "")}</span>
      <em>${policy.effect === null || policy.effect === undefined ? "효과 산정 대기" : won(policy.effect)}</em>
    </article>
  `).join("");

  const policyList = document.getElementById("policy-list");
  const policyDetailGrid = document.getElementById("policy-detail-grid");
  if (policyList) policyList.innerHTML = policyMarkup || `<div class="empty-state">진행 중인 정책 데이터가 없습니다</div>`;
  if (policyDetailGrid) policyDetailGrid.innerHTML = detailMarkup;
}

function renderRegions() {
  const tableBody = document.getElementById("region-table");
  if (!tableBody) return;

  const rows = regionRows();
  const sorted = rows
    .map((row) => ({ ...row, metric: metricFor(row) }))
    .sort((a, b) => Math.abs(Number(b.metric.gap_policy || 0)) - Math.abs(Number(a.metric.gap_policy || 0)));

  tableBody.innerHTML = sorted.map((row) => {
    const metric = row.metric;
    const klass = judgeClass(metric.judge_policy, metric.gap_policy);
    return `
      <tr class="${row.region === state.selectedRegion ? "is-selected" : ""}" data-region="${escapeHtml(row.region)}">
        <td>${escapeHtml(row.region)}</td>
        <td>${won(metric.actual_price)}</td>
        <td>${won(metric.fair_price_policy)}</td>
        <td>${signedWon(metric.gap_policy)}</td>
        <td><span class="badge ${klass}">${escapeHtml(metric.judge_policy || "-")}</span></td>
      </tr>
    `;
  }).join("");

  document.querySelectorAll("#region-table tr[data-region]").forEach((row) => {
    row.addEventListener("click", () => openRegionDetail(row.dataset.region));
  });
}

function geometryCoordinates(geometry) {
  const out = [];
  const walk = (value) => {
    if (Array.isArray(value) && typeof value[0] === "number" && typeof value[1] === "number") {
      out.push(value);
      return;
    }
    if (Array.isArray(value)) value.forEach(walk);
  };
  walk(geometry?.coordinates || []);
  return out;
}

function projectionForBox(geojson, box, padding) {
  const all = geojson.features.flatMap((feature) => geometryCoordinates(feature.geometry));
  const midLat = all.reduce((sum, point) => sum + point[1], 0) / Math.max(1, all.length);
  const lonScale = Math.cos(midLat * Math.PI / 180);
  const transformed = all.map(([lon, lat]) => [lon * lonScale, lat * KOREA_LAT_SCALE]);
  const minX = Math.min(...transformed.map((point) => point[0]));
  const maxX = Math.max(...transformed.map((point) => point[0]));
  const minY = Math.min(...transformed.map((point) => point[1]));
  const maxY = Math.max(...transformed.map((point) => point[1]));
  const scale = Math.min((box.width - padding * 2) / (maxX - minX), (box.height - padding * 2) / (maxY - minY));
  const usedWidth = (maxX - minX) * scale;
  const usedHeight = (maxY - minY) * scale;
  const x0 = box.x + (box.width - usedWidth) / 2;
  const y0 = box.y + (box.height - usedHeight) / 2;

  return ([lon, lat]) => {
    const x = lon * lonScale;
    const y = lat * KOREA_LAT_SCALE;
    return [
      x0 + (x - minX) * scale,
      y0 + (maxY - y) * scale,
    ];
  };
}

function ringPath(ring, project) {
  return ring.map((point, index) => {
    const [x, y] = project(point);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ") + " Z";
}

function geometryPath(geometry, project) {
  if (geometry.type === "Polygon") {
    return geometry.coordinates.map((ring) => ringPath(ring, project)).join(" ");
  }
  if (geometry.type === "MultiPolygon") {
    return geometry.coordinates.flatMap((polygon) => polygon.map((ring) => ringPath(ring, project))).join(" ");
  }
  return "";
}

function projectedCentroid(geometry, project) {
  const points = geometryCoordinates(geometry).map(project);
  if (!points.length) return [MAP_SIZE.width / 2, MAP_SIZE.height / 2];
  const x = points.reduce((sum, point) => sum + point[0], 0) / points.length;
  const y = points.reduce((sum, point) => sum + point[1], 0) / points.length;
  return [x, y];
}

function makeSvgElement(tag, attrs = {}) {
  const el = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value !== null && value !== undefined) el.setAttribute(key, value);
  });
  return el;
}

function connectorPath(anchor, callout) {
  const isLeft = callout.side === "left";
  const startX = isLeft ? callout.x + CALLOUT_W : callout.x;
  const startY = callout.y + CALLOUT_H / 2;
  const endX = anchor[0];
  const endY = anchor[1];
  return `M${startX.toFixed(1)} ${startY.toFixed(1)} L${endX.toFixed(1)} ${endY.toFixed(1)}`;
}

function renderMap() {
  const svg = document.getElementById("korea-map");
  const rows = new Map(regionRows().map((row) => [row.region, row]));

  svg.innerHTML = "";

  if (!state.geojson?.features?.length) {
    const text = makeSvgElement("text", { x: "520", y: "590", "text-anchor": "middle", class: "map-empty" });
    text.textContent = "지도 경계 데이터를 불러오지 못했습니다";
    svg.append(text);
    return;
  }

  const project = projectionForBox(state.geojson, MAP_BOUNDS, 22);
  const connectorLayer = makeSvgElement("g", { class: "connector-layer" });
  const provinceLayer = makeSvgElement("g", { class: "province-layer" });
  const calloutLayer = makeSvgElement("g", { class: "callout-layer" });
  const anchors = new Map();

  state.geojson.features.forEach((feature) => {
    const region = canonicalRegionName(feature.properties?.name);
    const row = rows.get(region);
    const metric = metricFor(row);
    const path = makeSvgElement("path", {
      d: geometryPath(feature.geometry, project),
      class: `province-path ${region === state.selectedRegion ? "is-selected" : ""}`,
      fill: REGION_COLORS[region] || "#9aa7b5",
      "data-region": region,
      tabindex: "0",
      "aria-label": `${region} 실제 ${won(metric.actual_price)}, 적정 ${won(metric.fair_price_policy)}`,
    });
    const title = makeSvgElement("title");
    title.textContent = `${region}: 실제 ${won(metric.actual_price)} / 적정 ${won(metric.fair_price_policy)}`;
    path.append(title);
    path.addEventListener("click", () => openRegionDetail(region));
    path.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openRegionDetail(region);
      }
    });
    anchors.set(region, projectedCentroid(feature.geometry, project));
    provinceLayer.append(path);
  });

  regionRows().forEach((row) => {
    const metric = metricFor(row);
    const callout = CALLOUT_POSITIONS[row.region];
    const anchor = anchors.get(row.region);
    if (!callout || !anchor) return;

    const selected = row.region === state.selectedRegion;
    const line = makeSvgElement("path", {
      d: connectorPath(anchor, callout),
      class: `map-connector ${selected ? "is-selected" : ""}`,
    });
    connectorLayer.append(line);

    const foreign = makeSvgElement("foreignObject", {
      x: callout.x,
      y: callout.y,
      width: CALLOUT_W,
      height: CALLOUT_H,
      class: "map-callout",
      tabindex: "0",
      "data-region": row.region,
    });
    const shell = document.createElement("div");
    shell.className = `map-callout-shell ${selected ? "is-selected" : ""}`;
    shell.style.borderLeftColor = REGION_COLORS[row.region] || "#102337";
    shell.innerHTML = `
      <strong>${escapeHtml(row.region)}</strong>
      <span>현재가 ${priceWon(metric.actual_price)}</span>
      <span>적정가 ${priceWon(metric.fair_price_policy)} <em class="${gapToneClass(metric.gap_policy)}">(${signedPriceWon(metric.gap_policy)})</em></span>
    `;
    foreign.append(shell);
    foreign.addEventListener("click", () => openRegionDetail(row.region));
    foreign.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openRegionDetail(row.region);
      }
    });
    calloutLayer.append(foreign);
  });

  svg.append(provinceLayer, connectorLayer, calloutLayer);
}

function selectedFeature() {
  return state.geojson?.features?.find((feature) => canonicalRegionName(feature.properties?.name) === state.selectedRegion);
}

function renderRegionDetailMap() {
  const svg = document.getElementById("region-detail-map");
  svg.innerHTML = "";

  const feature = selectedFeature();
  if (!feature) {
    const text = makeSvgElement("text", { x: "310", y: "360", "text-anchor": "middle", class: "map-empty" });
    text.textContent = "선택 지역 경계 없음";
    svg.append(text);
    return;
  }

  const oneFeatureGeojson = { type: "FeatureCollection", features: [feature] };
  const project = projectionForBox(oneFeatureGeojson, { x: 24, y: 24, width: 572, height: 672 }, 28);
  const path = makeSvgElement("path", {
    d: geometryPath(feature.geometry, project),
    class: "region-detail-path",
    fill: REGION_COLORS[state.selectedRegion] || "#9aa7b5",
  });
  const [cx, cy] = projectedCentroid(feature.geometry, project);
  const text = makeSvgElement("text", {
    x: cx.toFixed(1),
    y: cy.toFixed(1),
    "text-anchor": "middle",
    fill: "#102337",
    "font-size": "26",
    "font-weight": "900",
  });
  text.textContent = state.selectedRegion;
  svg.append(path, text);
}

function updateRegionDetailTab() {
  const tab = document.getElementById("region-detail-tab");
  if (!tab) return;
  tab.textContent = state.selectedRegion || "선택지역";
  tab.classList.toggle("has-region", Boolean(state.regionDetailEnabled && state.selectedRegion));
}

function renderRegionDetail() {
  if (!state.selectedRegion) {
    updateRegionDetailTab();
    return;
  }

  const row = rowForRegion(state.selectedRegion);
  const metric = metricFor(row);
  const klass = judgeClass(metric.judge_policy, metric.gap_policy);
  const data = state.national || FALLBACK_NATIONAL;

  document.getElementById("region-detail-title").textContent = `${state.selectedRegion} ${state.fuel === "gasoline" ? "휘발유" : "경유"}`;
  document.getElementById("region-detail-date").textContent = data.as_of_date || "-";
  document.getElementById("region-detail-actual").textContent = won(metric.actual_price);
  document.getElementById("region-detail-fair").textContent = won(metric.fair_price_policy);
  document.getElementById("region-detail-gap").textContent = signedWon(metric.gap_policy);
  document.getElementById("region-detail-judge").innerHTML = `<span class="badge ${klass}">${escapeHtml(metric.judge_policy || "-")}</span>`;
  document.getElementById("region-station-title").textContent = `${state.selectedRegion} 주유소`;

  updateRegionDetailTab();
  renderRegionDetailMap();
  renderRegionStations();
}

function stationMatches(station, query) {
  if (!query) return true;
  return [station.name, station.brand, station.region, station.address, station.station_id]
    .join(" ")
    .toLowerCase()
    .includes(query);
}

function stationCard(station, options = {}) {
  const price = stationPrice(station);
  const klass = judgeClass(station.judge_policy);
  const distanceMarkup = options.distanceKm === undefined
    ? ""
    : `<span class="distance">${options.distanceKm.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} km</span>`;
  return `
    <article class="station-card">
      <strong>${escapeHtml(station.name || station.station_id)}</strong>
      <span>${escapeHtml(station.brand || "-")} · ${escapeHtml(station.region || "-")}</span>
      <span>${escapeHtml(station.address || "")}</span>
      <span>${state.fuel === "gasoline" ? "휘발유" : "경유"} ${won(price)} · <b class="${klass}">${escapeHtml(station.judge_policy || "-")}</b></span>
      ${distanceMarkup}
    </article>
  `;
}

function renderStations() {
  const input = document.getElementById("station-search");
  const query = input.value.trim().toLowerCase();
  const rows = query
    ? baseStations()
      .filter((station) => stationMatches(station, query))
      .slice(0, 12)
    : [];

  document.getElementById("search-count").textContent = query ? `${rows.length}개 결과` : "검색어를 입력하세요";
  document.getElementById("station-results").innerHTML = rows.length
    ? rows.map((station) => stationCard(station)).join("")
    : `<div class="empty-state">${query ? "검색 결과가 없습니다" : "검색어를 입력하세요"}</div>`;
}

function renderRegionStations() {
  const input = document.getElementById("region-station-search");
  const query = input.value.trim().toLowerCase();
  const rows = baseStations()
    .filter((station) => canonicalRegionName(station.region) === state.selectedRegion)
    .filter((station) => stationMatches(station, query))
    .slice(0, 24);

  document.getElementById("region-station-count").textContent = `${rows.length}개`;
  document.getElementById("region-station-results").innerHTML = rows.length
    ? rows.map((station) => stationCard(station)).join("")
    : `<div class="empty-state">해당 지역 주유소 데이터가 없습니다</div>`;
}

function distanceKm(a, b) {
  const r = 6371;
  const toRad = (value) => Number(value) * Math.PI / 180;
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

function renderNearby() {
  const radius = Number(document.getElementById("nearby-radius")?.value || 5);
  const countEl = document.getElementById("nearby-count");
  const resultsEl = document.getElementById("nearby-results");
  const statusEl = document.getElementById("location-status");

  if (!state.userLocation) {
    countEl.textContent = "위치 확인 전";
    statusEl.textContent = state.locationError || "위치 동의 후 표시";
    resultsEl.innerHTML = `<div class="empty-state">내 위치 사용을 누르면 주변 주유소를 정렬합니다</div>`;
    return;
  }

  const rows = baseStations()
    .filter((station) => Number.isFinite(Number(station.lat)) && Number.isFinite(Number(station.lon)))
    .map((station) => ({
      station,
      distance: distanceKm(state.userLocation, { lat: Number(station.lat), lon: Number(station.lon) }),
    }))
    .filter((row) => row.distance <= radius)
    .sort((a, b) => a.distance - b.distance);

  countEl.textContent = `${rows.length}개 결과`;
  statusEl.textContent = `위치 ${state.userLocation.lat.toFixed(4)}, ${state.userLocation.lon.toFixed(4)}`;
  resultsEl.innerHTML = rows.length
    ? rows.map((row) => stationCard(row.station, { distanceKm: row.distance })).join("")
    : `<div class="empty-state">${radius} km 안의 주유소 데이터가 없습니다</div>`;
}

function filterOptions() {
  return [
    { value: NATIONAL_REGION, label: NATIONAL_REGION },
    ...REGION_ORDER.map((region) => ({ value: region, label: region })),
  ];
}

function initializeAnalysisControls() {
  const rows = historyRows();
  const extent = dateExtent(rows);

  ["trend-region", "download-region"].forEach((id) => {
    setSelectOptions(document.getElementById(id), filterOptions());
  });

  configureDateInput("trend-start", extent, defaultTrendStart(extent));
  configureDateInput("download-start", extent, extent.min);
  configureDateInput("trend-end", extent, extent.max);
  configureDateInput("download-end", extent, extent.max);
}

function selectedPriceRows(prefix) {
  const fuel = document.getElementById(`${prefix}-fuel`)?.value || state.fuel;
  const region = document.getElementById(`${prefix}-region`)?.value || NATIONAL_REGION;
  const start = document.getElementById(`${prefix}-start`)?.value || "";
  const end = document.getElementById(`${prefix}-end`)?.value || "";

  return historyRows()
    .filter((row) => row.fuel === fuel)
    .filter((row) => row.region === region)
    .filter((row) => dateInRange(row.date, start, end))
    .sort((a, b) => a.date.localeCompare(b.date));
}

function numberValue(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function chartPath(points) {
  return points.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
}

function contiguousSeries(rows, hasValue) {
  const series = [];
  let current = [];

  rows.forEach((row, index) => {
    if (hasValue(row)) {
      current.push({ row, index });
      return;
    }
    if (current.length) series.push(current);
    current = [];
  });

  if (current.length) series.push(current);
  return series;
}

function actualRangeTone(row) {
  const actual = numberValue(row.actual_price);
  const low = numberValue(row.band_low_policy);
  const high = numberValue(row.band_high_policy);

  if (actual === null || low === null || high === null) return "normal";
  if (actual > high) return "over";
  if (actual < low) return "under";
  return "normal";
}

function actualSegmentTone(leftRow, rightRow) {
  const left = actualRangeTone(leftRow);
  const right = actualRangeTone(rightRow);

  if (left === right) return left;
  if (right !== "normal") return right;
  return left;
}

function drawTrendChart(rows) {
  const svg = document.getElementById("price-trend-chart");
  if (!svg) return;
  svg.innerHTML = "";

  if (!rows.length) {
    const text = makeSvgElement("text", { x: "460", y: "240", "text-anchor": "middle", class: "chart-empty" });
    text.textContent = "선택한 조건의 가격 데이터가 없습니다";
    svg.append(text);
    return;
  }

  const width = 920;
  const height = 480;
  const margin = { left: 74, right: 30, top: 70, bottom: 64 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const values = rows.flatMap((row) => [
    numberValue(row.actual_price),
    numberValue(row.fair_price_policy),
    numberValue(row.band_low_policy),
    numberValue(row.band_high_policy),
  ]).filter((value) => value !== null);
  if (!values.length) {
    const text = makeSvgElement("text", { x: "460", y: "240", "text-anchor": "middle", class: "chart-empty" });
    text.textContent = "가격 숫자 데이터가 없습니다";
    svg.append(text);
    return;
  }
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const padding = Math.max(12, (maxValue - minValue) * 0.08);
  const low = minValue - padding;
  const high = maxValue + padding;
  const xFor = (index) => margin.left + (rows.length === 1 ? chartWidth / 2 : (chartWidth * index) / (rows.length - 1));
  const yFor = (value) => margin.top + ((high - Number(value)) / Math.max(1, high - low)) * chartHeight;

  for (let i = 0; i <= 4; i += 1) {
    const y = margin.top + (chartHeight * i) / 4;
    const value = high - ((high - low) * i) / 4;
    svg.append(makeSvgElement("line", { x1: margin.left, y1: y, x2: width - margin.right, y2: y, class: "chart-grid" }));
    const label = makeSvgElement("text", { x: margin.left - 12, y: y + 4, "text-anchor": "end", class: "chart-axis" });
    label.textContent = `${Math.round(value).toLocaleString("ko-KR")}원`;
    svg.append(label);
  }

  contiguousSeries(
    rows,
    (row) => numberValue(row.band_low_policy) !== null && numberValue(row.band_high_policy) !== null,
  ).forEach((segment) => {
    if (segment.length < 2) return;
    const upper = segment.map(({ row, index }) => [xFor(index), yFor(row.band_high_policy)]);
    const lower = segment.map(({ row, index }) => [xFor(index), yFor(row.band_low_policy)]);
    const lowerReversed = [...lower].reverse();
    const bandPath = `${chartPath(upper)} L${lowerReversed.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L")} Z`;
    svg.append(makeSvgElement("path", { d: bandPath, class: "chart-band" }));
    svg.append(makeSvgElement("path", { d: chartPath(upper), class: "chart-band-edge chart-band-edge-high" }));
    svg.append(makeSvgElement("path", { d: chartPath(lower), class: "chart-band-edge chart-band-edge-low" }));
  });

  contiguousSeries(rows, (row) => numberValue(row.fair_price_policy) !== null).forEach((segment) => {
    if (segment.length < 2) return;
    const points = segment.map(({ row, index }) => [xFor(index), yFor(row.fair_price_policy)]);
    svg.append(makeSvgElement("path", { d: chartPath(points), class: "chart-line-fair" }));
  });

  for (let index = 1; index < rows.length; index += 1) {
    const left = rows[index - 1];
    const right = rows[index];
    const leftActual = numberValue(left.actual_price);
    const rightActual = numberValue(right.actual_price);
    if (leftActual === null || rightActual === null) continue;

    const tone = actualSegmentTone(left, right);
    const points = [
      [xFor(index - 1), yFor(leftActual)],
      [xFor(index), yFor(rightActual)],
    ];
    svg.append(makeSvgElement("path", {
      d: chartPath(points),
      class: `chart-line-actual chart-line-actual-${tone}`,
    }));
  }

  const addLatestPoint = (key, className) => {
    for (let index = rows.length - 1; index >= 0; index -= 1) {
      const value = numberValue(rows[index][key]);
      if (value === null) continue;
      const tone = key === "actual_price" ? ` ${className}-${actualRangeTone(rows[index])}` : "";
      svg.append(makeSvgElement("circle", {
        cx: xFor(index),
        cy: yFor(value),
        r: 5,
        class: `${className}${tone}`,
      }));
      return;
    }
  };
  addLatestPoint("actual_price", "chart-point-actual");
  addLatestPoint("fair_price_policy", "chart-point-fair");

  const firstDate = rows[0]?.date || "";
  const lastDate = rows[rows.length - 1]?.date || "";
  [
    { x: margin.left, text: firstDate, anchor: "start" },
    { x: width - margin.right, text: lastDate, anchor: "end" },
  ].forEach((item) => {
    const text = makeSvgElement("text", { x: item.x, y: height - 22, "text-anchor": item.anchor, class: "chart-axis" });
    text.textContent = item.text;
    svg.append(text);
  });

  [
    { type: "line", x: margin.left, y: 26, className: "chart-line-actual chart-line-actual-normal", text: "전일 실제가격" },
    { type: "line", x: margin.left + 150, y: 26, className: "chart-line-fair", text: "오늘 적정가격" },
    { type: "band", x: margin.left + 320, y: 26, text: "적정가격대" },
    { type: "line", x: margin.left, y: 50, className: "chart-line-actual chart-line-actual-over", text: "빨강: 비쌈" },
    { type: "line", x: margin.left + 150, y: 50, className: "chart-line-actual chart-line-actual-under", text: "파랑: 저렴" },
  ].forEach((item) => {
    if (item.type === "band") {
      svg.append(makeSvgElement("rect", { x: item.x, y: item.y - 12, width: "26", height: "12", rx: "3", class: "chart-legend-band" }));
      const text = makeSvgElement("text", { x: item.x + 36, y: item.y, class: "chart-label" });
      text.textContent = item.text;
      svg.append(text);
      return;
    }

    svg.append(makeSvgElement("line", { x1: item.x, y1: item.y - 4, x2: item.x + 28, y2: item.y - 4, class: item.className }));
    const text = makeSvgElement("text", { x: item.x + 36, y: item.y, class: "chart-label" });
    text.textContent = item.text;
    svg.append(text);
  });
}

function renderTrend() {
  const rows = selectedPriceRows("trend");
  const fuel = document.getElementById("trend-fuel")?.value || state.fuel;
  const region = document.getElementById("trend-region")?.value || NATIONAL_REGION;
  const start = document.getElementById("trend-start")?.value || "";
  const end = document.getElementById("trend-end")?.value || "";
  const availableExtent = dateExtent(historyRows().filter((row) => row.fuel === fuel && row.region === region));
  const periodLabel = start === availableExtent.min && end === availableExtent.max
    ? "전체기간"
    : dateRangeLabel(start, end);
  const summary = document.getElementById("trend-summary");
  const note = document.getElementById("trend-note");

  if (summary) summary.textContent = `${region} · ${fuelLabel(fuel)} · ${periodLabel} · ${rows.length}개 시점`;
  if (note) {
    note.textContent = Array.isArray(state.history) && state.history.length
      ? "선택 기간의 실제가격, 적정가격, 적정가격 범위를 표시합니다. 실제가격은 전일 공시 데이터 기준입니다."
      : "현재 공개된 페이지 데이터는 최신 스냅샷 중심입니다. price_history.json이 생성되면 전체 기간 추이가 자동으로 표시됩니다.";
  }
  drawTrendChart(rows);
}

function downloadRows() {
  const kind = document.getElementById("download-kind")?.value || "price";
  const fuel = document.getElementById("download-fuel")?.value || state.fuel;
  const region = document.getElementById("download-region")?.value || NATIONAL_REGION;
  const start = document.getElementById("download-start")?.value || "";
  const end = document.getElementById("download-end")?.value || "";
  const data = state.national || FALLBACK_NATIONAL;

  if (kind === "station") {
    const asOfDate = data.as_of_date || FALLBACK_NATIONAL.as_of_date;
    if (!dateInRange(asOfDate, start, end)) return [];
    return baseStations()
      .filter((station) => region === NATIONAL_REGION || canonicalRegionName(station.region) === region)
      .map((station) => ({
        기준일: asOfDate,
        지역: canonicalRegionName(station.region),
        주유소ID: station.station_id,
        주유소명: station.name,
        브랜드: station.brand,
        주소: station.address,
        유종: fuelLabel(fuel),
        현재가_전일공시_원L: fuel === "gasoline" ? station.gasoline_price : station.diesel_price,
        판정: station.judge_policy,
        위도: station.lat,
        경도: station.lon,
      }));
  }

  return selectedPriceRows("download").map((row) => ({
    기준일: row.date,
    지역: row.region,
    유종: fuelLabel(row.fuel),
    현재가_전일공시_원L: row.actual_price,
    적정가격_오늘산출_원L: row.fair_price_policy,
    적정범위_하한_원L: row.band_low_policy,
    적정범위_상한_원L: row.band_high_policy,
    실제_minus_적정_원L: row.gap_policy,
    출처: row.source,
  }));
}

function renderDownloadSummary() {
  const count = document.getElementById("download-count");
  if (!count) return;
  count.textContent = `${downloadRows().length.toLocaleString("ko-KR")}개 행`;
}

function trainingCoverageData() {
  const data = state.trainingCoverage || TRAINING_COVERAGE_FALLBACK;
  return {
    ...TRAINING_COVERAGE_FALLBACK,
    ...data,
    datasets: Array.isArray(data.datasets) ? data.datasets : TRAINING_COVERAGE_FALLBACK.datasets,
    rows: Array.isArray(data.rows) ? data.rows : [],
  };
}

function trainingCoverageDatasets() {
  const data = trainingCoverageData();
  const fallbackById = new Map(TRAINING_COVERAGE_FALLBACK.datasets.map((item) => [item.id, item]));
  const seen = new Set();
  const merged = data.datasets.map((item) => {
    seen.add(item.id);
    return { ...fallbackById.get(item.id), ...item };
  });
  TRAINING_COVERAGE_FALLBACK.datasets.forEach((item) => {
    if (!seen.has(item.id)) merged.push(item);
  });
  return merged;
}

function selectedTrainingDataset() {
  const select = document.getElementById("training-dataset");
  return select?.value || trainingCoverageDatasets()[0]?.id || "";
}

function defaultTrainingDatasetId(datasets, current) {
  if (datasets.some((item) => item.id === current) && trainingRowsFor(current).length > 0) {
    return current;
  }
  const firstDatasetWithRows = datasets.find((item) => trainingRowsFor(item.id).length > 0);
  if (firstDatasetWithRows) return firstDatasetWithRows.id;
  return datasets.some((item) => item.id === current) ? current : datasets[0]?.id || "";
}

function trainingRowsFor(datasetId) {
  return trainingCoverageData().rows
    .filter((row) => row.dataset === datasetId)
    .map((row) => ({
      ...row,
      region: canonicalRegionName(row.region),
      value: numberValue(row.value),
      date: toIsoDate(row.date) || "",
    }))
    .filter((row) => row.region && row.value !== null);
}

function trainingDatesFor(datasetId) {
  return [...new Set(trainingRowsFor(datasetId).map((row) => row.date).filter(Boolean))].sort();
}

function syncTrainingDateOptions(datasetId) {
  const select = document.getElementById("training-date");
  if (!select) return;
  if (select.dataset.datasetId === datasetId) return;

  const dates = trainingDatesFor(datasetId);
  select.dataset.datasetId = datasetId;
  select.disabled = dates.length === 0;
  select.innerHTML = dates.length
    ? dates.map((date) => `<option value="${escapeHtml(date)}">${escapeHtml(date)}</option>`).join("")
    : `<option value="">전체</option>`;
  if (dates.length) select.value = dates[dates.length - 1];
}

function initializeTrainingCoverageControls() {
  const select = document.getElementById("training-dataset");
  if (!select) return;
  const datasets = trainingCoverageDatasets();
  const current = select.value;
  select.innerHTML = datasets.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join("");
  select.value = defaultTrainingDatasetId(datasets, current);
  syncTrainingDateOptions(select.value);
}

function coverageColor(value, minValue, maxValue) {
  if (!Number.isFinite(value)) return "#eef2f7";
  if (maxValue <= minValue) return "#2f80ed";
  const t = Math.max(0, Math.min(1, (value - minValue) / (maxValue - minValue)));
  const lightness = 88 - t * 46;
  return `hsl(211 82% ${lightness.toFixed(1)}%)`;
}

function renderTrainingCoverageMap(rows, dataset) {
  const svg = document.getElementById("training-data-map");
  if (!svg) return;
  svg.innerHTML = "";

  if (!state.geojson?.features?.length) {
    const text = makeSvgElement("text", { x: "310", y: "370", "text-anchor": "middle", class: "map-empty" });
    text.textContent = "지도 경계 데이터를 불러오지 못했습니다";
    svg.append(text);
    return;
  }

  const byRegion = new Map();
  rows.forEach((row) => {
    byRegion.set(row.region, (byRegion.get(row.region) || 0) + Number(row.value));
  });
  const values = [...byRegion.values()].filter((value) => Number.isFinite(value));
  const minValue = values.length ? Math.min(...values) : 0;
  const maxValue = values.length ? Math.max(...values) : 0;
  const project = projectionForBox(state.geojson, { x: 34, y: 24, width: 552, height: 690 }, 22);

  state.geojson.features.forEach((feature) => {
    const region = canonicalRegionName(feature.properties?.name);
    const value = byRegion.get(region);
    const hasValue = Number.isFinite(value);
    const path = makeSvgElement("path", {
      d: geometryPath(feature.geometry, project),
      class: `training-province ${hasValue ? "has-value" : ""}`,
      fill: hasValue ? coverageColor(value, minValue, maxValue) : "#eef2f7",
      "aria-label": `${region} ${dataset.label} ${hasValue ? formatCount(value) : "데이터 없음"}`,
    });
    const title = makeSvgElement("title");
    title.textContent = `${region}: ${hasValue ? `${formatCount(value)}${dataset.unit ? ` ${dataset.unit}` : ""}` : "데이터 없음"}`;
    path.append(title);
    svg.append(path);

    if (hasValue) {
      const [cx, cy] = projectedCentroid(feature.geometry, project);
      const label = makeSvgElement("text", {
        x: cx.toFixed(1),
        y: cy.toFixed(1),
        "text-anchor": "middle",
        class: "training-map-label",
      });
      label.textContent = region;
      svg.append(label);
    }
  });

  if (!values.length) {
    const text = makeSvgElement("text", { x: "310", y: "370", "text-anchor": "middle", class: "map-empty" });
    text.textContent = "GitHub에 지역별 AI 학습 데이터 집계가 없습니다";
    svg.append(text);
  }
}

function renderTrainingCoverage() {
  const datasetId = selectedTrainingDataset();
  syncTrainingDateOptions(datasetId);

  const dataset = trainingCoverageDatasets().find((item) => item.id === datasetId) || trainingCoverageDatasets()[0] || {};
  const dateSelect = document.getElementById("training-date");
  const selectedDate = dateSelect?.value || "";
  const rows = trainingRowsFor(datasetId).filter((row) => !selectedDate || row.date === selectedDate);
  const values = rows.map((row) => row.value).filter((value) => Number.isFinite(value));
  const total = values.reduce((sum, value) => sum + value, 0);
  const summary = document.getElementById("training-coverage-summary");
  const stats = document.getElementById("training-coverage-stats");
  const note = document.getElementById("training-coverage-note");
  const datasetPeriod = dateRangeLabel(dataset.date_min, dataset.date_max);
  const dateLabel = selectedDate || (datasetPeriod === "-" ? "전체" : datasetPeriod);

  if (summary) summary.textContent = values.length
    ? `${dataset.label} · ${dateLabel} · ${values.length}개 시도`
    : `${dataset.label || "AI 학습 데이터"} · 데이터 없음`;

  if (stats) {
    stats.innerHTML = `
      <div><span>시도 수</span><strong>${values.length.toLocaleString("ko-KR")}</strong></div>
      <div><span>합계</span><strong>${formatCount(total)}${dataset.unit ? ` ${escapeHtml(dataset.unit)}` : ""}</strong></div>
      <div><span>기간</span><strong>${escapeHtml(dateRangeLabel(dataset.date_min, dataset.date_max))}</strong></div>
      <div><span>입력</span><strong>${escapeHtml(dataset.path || "page/manual_inputs/training_data_coverage.csv")}</strong></div>
    `;
  }

  if (note) {
    note.textContent = values.length
      ? dataset.note || "선택한 학습 데이터의 지역별 분포입니다."
      : `${dataset.note || "지역별 집계 데이터가 필요합니다"} 현재 GitHub에는 이 지도를 칠할 시도별 학습 데이터 집계가 없습니다.`;
  }

  renderTrainingCoverageMap(rows, dataset);
}

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function exportCsv() {
  const rows = downloadRows();
  if (!rows.length) {
    const count = document.getElementById("download-count");
    if (count) count.textContent = "다운로드할 행이 없습니다";
    return;
  }

  const headers = Object.keys(rows[0]);
  const csv = [
    headers.map(csvCell).join(","),
    ...rows.map((row) => headers.map((header) => csvCell(row[header])).join(",")),
  ].join("\n");
  const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const kind = document.getElementById("download-kind")?.value || "price";
  const region = document.getElementById("download-region")?.value || NATIONAL_REGION;
  link.href = url;
  link.download = `fair_fuel_${kind}_${region}_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function fixedSampleFuel(metric = {}, label) {
  return {
    ...metric,
    label: metric.label || label,
    ...sampleMetric({
      actual_delta_1d: 0,
      policy_effect: metric.policy_effect ?? 0,
    }),
  };
}

function applyFixedSamplePrices() {
  if (!USE_FIXED_SAMPLE_PRICES) return;

  const baseNational = state.national || FALLBACK_NATIONAL;
  state.national = {
    ...baseNational,
    freshness: "sample",
    fuels: {
      gasoline: fixedSampleFuel(baseNational.fuels?.gasoline, "휘발유"),
      diesel: fixedSampleFuel(baseNational.fuels?.diesel, "경유"),
    },
  };

  if (Array.isArray(state.regions) && state.regions.length) {
    state.regions = state.regions.map((row) => ({
      ...row,
      gasoline: fixedSampleFuel(row.gasoline, "휘발유"),
      diesel: fixedSampleFuel(row.diesel, "경유"),
    }));
  }

  // Station search and price trend keep source data so users can inspect real history.
}

function requestUserLocation() {
  const statusEl = document.getElementById("location-status");
  if (!navigator.geolocation) {
    state.locationError = "브라우저 위치 기능을 사용할 수 없습니다";
    renderNearby();
    return;
  }

  statusEl.textContent = "위치 확인 중";
  navigator.geolocation.getCurrentPosition(
    (position) => {
      state.userLocation = {
        lat: position.coords.latitude,
        lon: position.coords.longitude,
      };
      state.locationError = "";
      renderNearby();
      activatePanel("nearby");
    },
    (error) => {
      state.locationError = error.code === 1 ? "위치 권한이 거부되었습니다" : "위치를 확인하지 못했습니다";
      renderNearby();
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
  );
}

function activatePanel(name) {
  document.querySelectorAll(".top-tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.panel === name);
  });
  document.querySelectorAll(".dashboard-panel").forEach((panel) => {
    panel.classList.toggle("is-visible", panel.id === `panel-${name}`);
  });
}

function clearRegionHash() {
  if (location.hash.startsWith("#region=")) {
    history.replaceState(null, "", `${location.pathname}${location.search}`);
  }
}

function clearRegionSelection(updateUrl = true) {
  state.selectedRegion = null;
  state.regionDetailEnabled = false;

  const regionSearch = document.getElementById("region-station-search");
  if (regionSearch) regionSearch.value = "";

  updateRegionDetailTab();
  renderRegions();
  renderMap();

  if (updateUrl) clearRegionHash();
}

function openRegionDetail(region) {
  if (!region) return;
  state.selectedRegion = canonicalRegionName(region);
  state.regionDetailEnabled = true;
  updateRegionDetailTab();
  renderRegions();
  renderMap();
  renderRegionDetail();
  activatePanel("region-detail");
  clearRegionHash();
}

function render() {
  renderStatus();
  renderNational();
  renderMapHeader();
  renderPolicies();
  renderRegions();
  renderMap();
  renderRegionDetail();
  renderStations();
  renderNearby();
  renderTrend();
  renderDownloadSummary();
  renderTrainingCoverage();
}

async function boot() {
  clearRegionHash();

  const [manifest, national, regions, stations, history, trainingCoverage, geojson] = await Promise.all([
    loadJson("./public/data/latest/site_manifest.json", {}),
    loadJson("./public/data/latest/national_today.json", FALLBACK_NATIONAL),
    loadJson("./public/data/latest/region_today.json", FALLBACK_REGIONS),
    loadJson("./public/data/latest/station_search_index.json", FALLBACK_STATIONS),
    loadJson("./public/data/latest/price_history.json", []),
    loadJson("./public/data/latest/training_data_coverage.json", TRAINING_COVERAGE_FALLBACK),
    loadJson("./public/assets/korea-provinces.geojson", null),
  ]);

  state.manifest = manifest;
  state.national = national;
  state.regions = regions;
  state.stations = stations;
  state.history = history;
  state.trainingCoverage = trainingCoverage;
  state.geojson = geojson;
  applyFixedSamplePrices();
  initializeAnalysisControls();
  initializeTrainingCoverageControls();

  document.querySelectorAll(".fuel-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.fuel = button.dataset.fuel;
      document.querySelectorAll(".fuel-button").forEach((item) => item.classList.toggle("is-active", item === button));
      render();
    });
  });

  document.querySelectorAll(".top-tab").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.panel === "map") {
        clearRegionSelection();
      } else if (button.dataset.panel === "region-detail") {
        state.regionDetailEnabled = Boolean(state.selectedRegion);
      }
      updateRegionDetailTab();
      activatePanel(button.dataset.panel);
      if (button.dataset.panel === "search") document.getElementById("station-search")?.focus();
    });
  });

  document.getElementById("brand-home")?.addEventListener("click", () => {
    clearRegionSelection();
    activatePanel("map");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  document.getElementById("station-search").addEventListener("input", () => {
    renderStations();
    if (document.getElementById("station-search").value.trim()) activatePanel("search");
  });

  document.getElementById("region-station-search").addEventListener("input", renderRegionStations);
  document.getElementById("use-location").addEventListener("click", requestUserLocation);
  document.getElementById("nearby-radius").addEventListener("change", renderNearby);
  ["trend-fuel", "trend-region", "trend-start", "trend-end"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", renderTrend);
  });
  ["download-kind", "download-fuel", "download-region", "download-start", "download-end"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", renderDownloadSummary);
  });
  document.getElementById("training-dataset")?.addEventListener("change", () => {
    const dateSelect = document.getElementById("training-date");
    if (dateSelect) dateSelect.dataset.datasetId = "";
    renderTrainingCoverage();
  });
  document.getElementById("training-date")?.addEventListener("change", renderTrainingCoverage);
  document.getElementById("download-csv")?.addEventListener("click", exportCsv);

  window.addEventListener("popstate", () => {
    clearRegionSelection(false);
    activatePanel("map");
  });

  render();
  if (state.regionDetailEnabled) activatePanel("region-detail");
}

boot();
