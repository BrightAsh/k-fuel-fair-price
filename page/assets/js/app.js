const SVG_NS = "http://www.w3.org/2000/svg";

const state = {
  fuel: "gasoline",
  manifest: null,
  national: null,
  regions: [],
  stations: [],
  geojson: null,
  selectedRegion: "서울",
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
      actual_price: 2009.98,
      fair_price_policy: 1886.91,
      band_low_policy: 1873.12,
      band_high_policy: 1901.02,
      gap_policy: 123.07,
      judge_policy: "비쌈",
      policy_effect: 123.07,
      actual_delta_1d: 1.2,
    },
    diesel: {
      label: "경유",
      actual_price: 2004.82,
      fair_price_policy: 1859.41,
      band_low_policy: 1845.22,
      band_high_policy: 1874.11,
      gap_policy: 145.41,
      judge_policy: "비쌈",
      policy_effect: 145.41,
      actual_delta_1d: 0.8,
    },
  },
  policies: [
    {
      title: "유류세 인하 반영",
      status: "정책 효과 반영",
      period: "분석 산출물 기준",
      gasoline_effect: 123.07,
      diesel_effect: 145.41,
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

const FALLBACK_REGIONS = [
  { region: "서울", gasoline: { actual_price: 2078, fair_price_policy: 1934, gap_policy: 144, judge_policy: "비쌈" }, diesel: { actual_price: 2059, fair_price_policy: 1906, gap_policy: 153, judge_policy: "비쌈" } },
  { region: "부산", gasoline: { actual_price: 1988, fair_price_policy: 1880, gap_policy: 108, judge_policy: "비쌈" }, diesel: { actual_price: 1985, fair_price_policy: 1850, gap_policy: 135, judge_policy: "비쌈" } },
  { region: "대구", gasoline: { actual_price: 1994, fair_price_policy: 1878, gap_policy: 116, judge_policy: "비쌈" }, diesel: { actual_price: 1987, fair_price_policy: 1848, gap_policy: 139, judge_policy: "비쌈" } },
  { region: "인천", gasoline: { actual_price: 2018, fair_price_policy: 1888, gap_policy: 130, judge_policy: "비쌈" }, diesel: { actual_price: 2002, fair_price_policy: 1860, gap_policy: 142, judge_policy: "비쌈" } },
  { region: "광주", gasoline: { actual_price: 1972, fair_price_policy: 1874, gap_policy: 98, judge_policy: "비쌈" }, diesel: { actual_price: 1964, fair_price_policy: 1844, gap_policy: 120, judge_policy: "비쌈" } },
  { region: "대전", gasoline: { actual_price: 1986, fair_price_policy: 1879, gap_policy: 107, judge_policy: "비쌈" }, diesel: { actual_price: 1977, fair_price_policy: 1850, gap_policy: 127, judge_policy: "비쌈" } },
  { region: "울산", gasoline: { actual_price: 1990, fair_price_policy: 1882, gap_policy: 108, judge_policy: "비쌈" }, diesel: { actual_price: 1976, fair_price_policy: 1852, gap_policy: 124, judge_policy: "비쌈" } },
  { region: "세종", gasoline: { actual_price: 2001, fair_price_policy: 1881, gap_policy: 120, judge_policy: "비쌈" }, diesel: { actual_price: 1988, fair_price_policy: 1853, gap_policy: 135, judge_policy: "비쌈" } },
  { region: "경기", gasoline: { actual_price: 2010, fair_price_policy: 1886, gap_policy: 124, judge_policy: "비쌈" }, diesel: { actual_price: 2006, fair_price_policy: 1857, gap_policy: 149, judge_policy: "비쌈" } },
  { region: "강원", gasoline: { actual_price: 2006, fair_price_policy: 1890, gap_policy: 116, judge_policy: "비쌈" }, diesel: { actual_price: 1992, fair_price_policy: 1860, gap_policy: 132, judge_policy: "비쌈" } },
  { region: "충북", gasoline: { actual_price: 1981, fair_price_policy: 1877, gap_policy: 104, judge_policy: "비쌈" }, diesel: { actual_price: 1972, fair_price_policy: 1848, gap_policy: 124, judge_policy: "비쌈" } },
  { region: "충남", gasoline: { actual_price: 1996, fair_price_policy: 1883, gap_policy: 113, judge_policy: "비쌈" }, diesel: { actual_price: 1984, fair_price_policy: 1852, gap_policy: 132, judge_policy: "비쌈" } },
  { region: "전북", gasoline: { actual_price: 1968, fair_price_policy: 1872, gap_policy: 96, judge_policy: "비쌈" }, diesel: { actual_price: 1956, fair_price_policy: 1843, gap_policy: 113, judge_policy: "비쌈" } },
  { region: "전남", gasoline: { actual_price: 1975, fair_price_policy: 1876, gap_policy: 99, judge_policy: "비쌈" }, diesel: { actual_price: 1961, fair_price_policy: 1846, gap_policy: 115, judge_policy: "비쌈" } },
  { region: "경북", gasoline: { actual_price: 1984, fair_price_policy: 1879, gap_policy: 105, judge_policy: "비쌈" }, diesel: { actual_price: 1974, fair_price_policy: 1849, gap_policy: 125, judge_policy: "비쌈" } },
  { region: "경남", gasoline: { actual_price: 1980, fair_price_policy: 1878, gap_policy: 102, judge_policy: "비쌈" }, diesel: { actual_price: 1969, fair_price_policy: 1848, gap_policy: 121, judge_policy: "비쌈" } },
  { region: "제주", gasoline: { actual_price: 1914, fair_price_policy: 1889, gap_policy: 25, judge_policy: "적정" }, diesel: { actual_price: 1890, fair_price_policy: 1862, gap_policy: 28, judge_policy: "적정" } },
];

const FALLBACK_STATIONS = [
  { station_id: "sample-seoul-1", name: "도심셀프주유소", brand: "SK에너지", region: "서울", address: "서울특별시 중구 세종대로 1", lon: 126.978, lat: 37.566, gasoline_price: 2012, diesel_price: 1998, judge_policy: "적정" },
  { station_id: "sample-seoul-2", name: "한강대로주유소", brand: "GS칼텍스", region: "서울", address: "서울특별시 용산구 한강대로 100", lon: 126.972, lat: 37.532, gasoline_price: 2038, diesel_price: 2017, judge_policy: "비쌈" },
  { station_id: "sample-gyeonggi-1", name: "수원표준주유소", brand: "HD현대오일뱅크", region: "경기", address: "경기도 수원시 팔달구 효원로 1", lon: 127.028, lat: 37.263, gasoline_price: 1999, diesel_price: 1982, judge_policy: "적정" },
  { station_id: "sample-incheon-1", name: "송도에너지", brand: "S-OIL", region: "인천", address: "인천광역시 연수구 컨벤시아대로 1", lon: 126.645, lat: 37.389, gasoline_price: 2016, diesel_price: 1993, judge_policy: "비쌈" },
  { station_id: "sample-busan-1", name: "부산항주유소", brand: "GS칼텍스", region: "부산", address: "부산광역시 중구 중앙대로 1", lon: 129.04, lat: 35.104, gasoline_price: 1984, diesel_price: 1969, judge_policy: "적정" },
  { station_id: "sample-daegu-1", name: "달구벌셀프", brand: "SK에너지", region: "대구", address: "대구광역시 중구 달구벌대로 1", lon: 128.601, lat: 35.871, gasoline_price: 1994, diesel_price: 1987, judge_policy: "비쌈" },
  { station_id: "sample-gwangju-1", name: "무등주유소", brand: "알뜰", region: "광주", address: "광주광역시 동구 금남로 1", lon: 126.916, lat: 35.146, gasoline_price: 1972, diesel_price: 1964, judge_policy: "적정" },
  { station_id: "sample-daejeon-1", name: "대전IC주유소", brand: "HD현대오일뱅크", region: "대전", address: "대전광역시 동구 동서대로 1", lon: 127.433, lat: 36.35, gasoline_price: 1986, diesel_price: 1977, judge_policy: "비쌈" },
  { station_id: "sample-ulsan-1", name: "태화강주유소", brand: "S-OIL", region: "울산", address: "울산광역시 남구 삼산로 1", lon: 129.311, lat: 35.539, gasoline_price: 1990, diesel_price: 1976, judge_policy: "비쌈" },
  { station_id: "sample-jeju-1", name: "제주공항주유소", brand: "GS칼텍스", region: "제주", address: "제주특별자치도 제주시 공항로 1", lon: 126.493, lat: 33.506, gasoline_price: 1914, diesel_price: 1890, judge_policy: "적정" },
];

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

function stationPrice(station) {
  return state.fuel === "gasoline" ? station.gasoline_price : station.diesel_price;
}

function renderStatus() {
  const data = state.national || FALLBACK_NATIONAL;
  const dot = document.getElementById("freshness-dot");
  const dataDate = document.getElementById("data-date");
  const generatedAt = document.getElementById("generated-at");

  const samplePrefix = data.freshness === "sample" ? "샘플 " : "";
  dataDate.textContent = `${samplePrefix}기준일 ${data.as_of_date || "-"}`;
  generatedAt.textContent = data.generated_at ? `갱신 ${data.generated_at}` : "갱신 시각 없음";

  dot.classList.remove("is-fresh", "is-stale");
  if (data.freshness === "fresh") dot.classList.add("is-fresh");
  if (data.freshness === "stale") dot.classList.add("is-stale");
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

  document.getElementById("policy-list").innerHTML = policyMarkup;
  document.getElementById("policy-detail-grid").innerHTML = detailMarkup;
}

function renderRegions() {
  const rows = regionRows();
  const sorted = rows
    .map((row) => ({ ...row, metric: metricFor(row) }))
    .sort((a, b) => Math.abs(Number(b.metric.gap_policy || 0)) - Math.abs(Number(a.metric.gap_policy || 0)));

  document.getElementById("region-count").textContent = `${rows.length}개 시도`;
  document.getElementById("region-table").innerHTML = sorted.map((row) => {
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
  tab.textContent = state.selectedRegion;
  tab.classList.toggle("has-region", state.regionDetailEnabled);
}

function renderRegionDetail() {
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
    .sort((a, b) => a.distance - b.distance)
    .slice(0, 24);

  countEl.textContent = `${rows.length}개 결과`;
  statusEl.textContent = `위치 ${state.userLocation.lat.toFixed(4)}, ${state.userLocation.lon.toFixed(4)}`;
  resultsEl.innerHTML = rows.length
    ? rows.map((row) => stationCard(row.station, { distanceKm: row.distance })).join("")
    : `<div class="empty-state">${radius} km 안의 주유소 데이터가 없습니다</div>`;
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

function openRegionDetail(region, updateUrl = true) {
  if (!region) return;
  state.selectedRegion = canonicalRegionName(region);
  state.regionDetailEnabled = true;
  updateRegionDetailTab();
  renderRegions();
  renderMap();
  renderRegionDetail();
  activatePanel("region-detail");
  if (updateUrl) {
    const encoded = encodeURIComponent(state.selectedRegion);
    history.pushState({ region: state.selectedRegion }, "", `#region=${encoded}`);
  }
}

function parseRegionHash() {
  const match = location.hash.match(/^#region=(.+)$/);
  if (!match) return null;
  try {
    return canonicalRegionName(decodeURIComponent(match[1]));
  } catch {
    return null;
  }
}

function render() {
  renderStatus();
  renderNational();
  renderPolicies();
  renderRegions();
  renderMap();
  renderRegionDetail();
  renderStations();
  renderNearby();
}

async function boot() {
  const [manifest, national, regions, stations, geojson] = await Promise.all([
    loadJson("./public/data/latest/site_manifest.json", {}),
    loadJson("./public/data/latest/national_today.json", FALLBACK_NATIONAL),
    loadJson("./public/data/latest/region_today.json", FALLBACK_REGIONS),
    loadJson("./public/data/latest/station_search_index.json", FALLBACK_STATIONS),
    loadJson("./public/assets/korea-provinces.geojson", null),
  ]);

  state.manifest = manifest;
  state.national = national;
  state.regions = regions;
  state.stations = stations;
  state.geojson = geojson;

  const hashRegion = parseRegionHash();
  if (hashRegion && REGION_ORDER.includes(hashRegion)) {
    state.selectedRegion = hashRegion;
    state.regionDetailEnabled = true;
  }

  document.querySelectorAll(".fuel-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.fuel = button.dataset.fuel;
      document.querySelectorAll(".fuel-button").forEach((item) => item.classList.toggle("is-active", item === button));
      render();
    });
  });

  document.querySelectorAll(".top-tab").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.panel === "region-detail") state.regionDetailEnabled = true;
      updateRegionDetailTab();
      activatePanel(button.dataset.panel);
    });
  });

  document.getElementById("station-search").addEventListener("input", () => {
    renderStations();
    if (document.getElementById("station-search").value.trim()) activatePanel("search");
  });

  document.getElementById("region-station-search").addEventListener("input", renderRegionStations);
  document.getElementById("use-location").addEventListener("click", requestUserLocation);
  document.getElementById("nearby-radius").addEventListener("change", renderNearby);

  window.addEventListener("popstate", () => {
    const region = parseRegionHash();
    if (region && REGION_ORDER.includes(region)) openRegionDetail(region, false);
  });

  render();
  if (state.regionDetailEnabled) activatePanel("region-detail");
}

boot();
