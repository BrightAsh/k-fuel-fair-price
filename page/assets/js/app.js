const SVG_NS = "http://www.w3.org/2000/svg";

const state = {
  fuel: "gasoline",
  manifest: null,
  national: null,
  regions: [],
  stations: [],
  geojson: null,
  selectedRegion: "서울",
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
  "충청북도": "충북",
  "충청남도": "충남",
  "전라북도": "전북",
  "전라남도": "전남",
  "경상북도": "경북",
  "경상남도": "경남",
  "제주특별자치도": "제주",
};

const LABEL_POSITIONS = {
  서울: [239, 176],
  인천: [126, 236],
  경기: [328, 206],
  강원: [438, 164],
  충북: [405, 296],
  충남: [218, 333],
  세종: [306, 301],
  대전: [331, 367],
  전북: [298, 414],
  광주: [228, 461],
  전남: [212, 532],
  경북: [548, 315],
  대구: [466, 382],
  울산: [562, 422],
  부산: [541, 474],
  경남: [428, 486],
  제주: [238, 653],
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
  { station_id: "sample-1", name: "예시 주유소", brand: "SK에너지", region: "서울", address: "서울특별시 예시로 1", gasoline_price: 2012, diesel_price: 1998, judge_policy: "적정" },
  { station_id: "sample-2", name: "데모 셀프주유소", brand: "GS칼텍스", region: "경기", address: "경기도 예시시 샘플로 2", gasoline_price: 1999, diesel_price: 1982, judge_policy: "비쌈" },
  { station_id: "sample-3", name: "표준가격 확인소", brand: "HD현대오일뱅크", region: "부산", address: "부산광역시 예시대로 3", gasoline_price: 1984, diesel_price: 1969, judge_policy: "적정" },
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

function signedWon(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}원/L`;
}

function judgeClass(value, gap) {
  if (value === "적정") return "good";
  if (value === "비쌈" || value === "상향이탈") return "high";
  if (value === "저렴" || value === "하향이탈") return "low";
  if (Number(gap) > 30) return "high";
  if (Number(gap) < -30) return "low";
  return "good";
}

function fillForMetric(metric = {}) {
  const gap = Number(metric.gap_policy || 0);
  if (gap >= 130) return "#b73535";
  if (gap >= 80) return "#d8742f";
  if (gap <= -30) return "#087f72";
  return "#23966b";
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
      <tr class="${row.region === state.selectedRegion ? "is-selected" : ""}">
        <td>${escapeHtml(row.region)}</td>
        <td>${won(metric.actual_price)}</td>
        <td>${won(metric.fair_price_policy)}</td>
        <td>${signedWon(metric.gap_policy)}</td>
        <td><span class="badge ${klass}">${escapeHtml(metric.judge_policy || "-")}</span></td>
      </tr>
    `;
  }).join("");
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

function projectionFor(geojson, width, height, padding) {
  const all = geojson.features.flatMap((feature) => geometryCoordinates(feature.geometry));
  const minLon = Math.min(...all.map((point) => point[0]));
  const maxLon = Math.max(...all.map((point) => point[0]));
  const minLat = Math.min(...all.map((point) => point[1]));
  const maxLat = Math.max(...all.map((point) => point[1]));
  const scale = Math.min((width - padding * 2) / (maxLon - minLon), (height - padding * 2) / (maxLat - minLat));
  const usedWidth = (maxLon - minLon) * scale;
  const usedHeight = (maxLat - minLat) * scale;
  const x0 = (width - usedWidth) / 2;
  const y0 = (height - usedHeight) / 2;

  return ([lon, lat]) => [
    x0 + (lon - minLon) * scale,
    height - (y0 + (lat - minLat) * scale),
  ];
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

function renderMap() {
  const svg = document.getElementById("korea-map");
  const labelLayer = document.getElementById("map-label-layer");
  const rows = new Map(regionRows().map((row) => [row.region, row]));

  svg.innerHTML = "";
  labelLayer.innerHTML = "";

  if (!state.geojson?.features?.length) {
    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("x", "360");
    text.setAttribute("y", "390");
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("class", "map-empty");
    text.textContent = "지도 경계 데이터를 불러오지 못했습니다";
    svg.append(text);
    return;
  }

  const project = projectionFor(state.geojson, 720, 780, 36);
  const group = document.createElementNS(SVG_NS, "g");
  group.setAttribute("class", "province-layer");

  state.geojson.features.forEach((feature) => {
    const region = canonicalRegionName(feature.properties?.name);
    const row = rows.get(region);
    const metric = metricFor(row);
    const path = document.createElementNS(SVG_NS, "path");

    path.setAttribute("d", geometryPath(feature.geometry, project));
    path.setAttribute("class", `province-path ${region === state.selectedRegion ? "is-selected" : ""}`);
    path.setAttribute("fill", fillForMetric(metric));
    path.setAttribute("data-region", region);
    path.setAttribute("tabindex", "0");
    path.setAttribute("aria-label", `${region} 실제 ${won(metric.actual_price)}, 적정 ${won(metric.fair_price_policy)}`);

    const title = document.createElementNS(SVG_NS, "title");
    title.textContent = `${region}: 실제 ${won(metric.actual_price)} / 적정 ${won(metric.fair_price_policy)}`;
    path.append(title);

    path.addEventListener("click", () => {
      state.selectedRegion = region;
      renderMap();
      renderRegions();
    });
    path.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        state.selectedRegion = region;
        renderMap();
        renderRegions();
      }
    });

    group.append(path);
  });
  svg.append(group);

  regionRows().forEach((row) => {
    const metric = metricFor(row);
    const [x, y] = LABEL_POSITIONS[row.region] || [360, 390];
    const klass = judgeClass(metric.judge_policy, metric.gap_policy);
    const label = document.createElement("div");
    label.className = `map-label ${klass} ${row.region === state.selectedRegion ? "is-selected" : ""}`;
    label.style.left = `${(x / 720) * 100}%`;
    label.style.top = `${(y / 780) * 100}%`;
    label.innerHTML = `
      <strong>${escapeHtml(row.region)}</strong>
      <span>실제 ${won(metric.actual_price)}</span>
      <span>적정 ${won(metric.fair_price_policy)}</span>
    `;
    labelLayer.append(label);
  });
}

function renderStations() {
  const input = document.getElementById("station-search");
  const query = input.value.trim().toLowerCase();
  const base = Array.isArray(state.stations) && state.stations.length ? state.stations : FALLBACK_STATIONS;
  const rows = query
    ? base
      .filter((station) => [station.name, station.brand, station.region, station.address].join(" ").toLowerCase().includes(query))
      .slice(0, 12)
    : [];

  document.getElementById("search-count").textContent = query ? `${rows.length}개 결과` : "검색어를 입력하세요";
  document.getElementById("station-results").innerHTML = rows.map((station) => {
    const price = state.fuel === "gasoline" ? station.gasoline_price : station.diesel_price;
    const klass = judgeClass(station.judge_policy);
    return `
      <article class="station-card">
        <strong>${escapeHtml(station.name || station.station_id)}</strong>
        <span>${escapeHtml(station.brand || "-")} · ${escapeHtml(station.region || "-")}</span>
        <span>${escapeHtml(station.address || "")}</span>
        <span>${state.fuel === "gasoline" ? "휘발유" : "경유"} ${won(price)} · <b class="${klass}">${escapeHtml(station.judge_policy || "-")}</b></span>
      </article>
    `;
  }).join("");
}

function activatePanel(name) {
  document.querySelectorAll(".top-tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.panel === name);
  });
  document.querySelectorAll(".dashboard-panel").forEach((panel) => {
    panel.classList.toggle("is-visible", panel.id === `panel-${name}`);
  });
}

function render() {
  renderStatus();
  renderNational();
  renderPolicies();
  renderRegions();
  renderMap();
  renderStations();
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

  document.querySelectorAll(".fuel-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.fuel = button.dataset.fuel;
      document.querySelectorAll(".fuel-button").forEach((item) => item.classList.toggle("is-active", item === button));
      render();
    });
  });

  document.querySelectorAll(".top-tab").forEach((button) => {
    button.addEventListener("click", () => activatePanel(button.dataset.panel));
  });

  document.getElementById("station-search").addEventListener("input", () => {
    renderStations();
    if (document.getElementById("station-search").value.trim()) activatePanel("search");
  });

  render();
}

boot();
