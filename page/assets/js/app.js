const state = {
  fuel: "gasoline",
  manifest: null,
  national: null,
  regions: [],
  stations: [],
};

const FALLBACK_NATIONAL = {
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
};

const FALLBACK_REGIONS = [
  { region: "서울", gasoline: { actual_price: 2078, fair_price_policy: 1934, gap_policy: 144, judge_policy: "비쌈" }, diesel: { actual_price: 2059, fair_price_policy: 1906, gap_policy: 153, judge_policy: "비쌈" } },
  { region: "경기", gasoline: { actual_price: 2010, fair_price_policy: 1886, gap_policy: 124, judge_policy: "비쌈" }, diesel: { actual_price: 2006, fair_price_policy: 1857, gap_policy: 149, judge_policy: "비쌈" } },
  { region: "부산", gasoline: { actual_price: 1988, fair_price_policy: 1880, gap_policy: 108, judge_policy: "비쌈" }, diesel: { actual_price: 1985, fair_price_policy: 1850, gap_policy: 135, judge_policy: "비쌈" } },
  { region: "제주", gasoline: { actual_price: 1914, fair_price_policy: 1889, gap_policy: 25, judge_policy: "적정" }, diesel: { actual_price: 1890, fair_price_policy: 1862, gap_policy: 28, judge_policy: "적정" } },
];

const FALLBACK_STATIONS = [
  { station_id: "sample-1", name: "예시 주유소", brand: "SK에너지", region: "서울", address: "서울특별시 예시로 1", gasoline_price: 2012, diesel_price: 1998, judge_policy: "적정" },
  { station_id: "sample-2", name: "데모 셀프주유소", brand: "GS칼텍스", region: "경기", address: "경기도 예시시 샘플로 2", gasoline_price: 1999, diesel_price: 1982, judge_policy: "비쌈" },
];

function won(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}원/L`;
}

function signedWon(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const sign = Number(value) > 0 ? "+" : "";
  return `${sign}${Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}원/L`;
}

function judgeClass(value) {
  if (value === "적정") return "good";
  if (value === "비쌈" || value === "상향이탈") return "high";
  if (value === "저렴" || value === "하향이탈") return "low";
  return "";
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

function renderStatus() {
  const data = state.national || FALLBACK_NATIONAL;
  const dot = document.getElementById("freshness-dot");
  const dataDate = document.getElementById("data-date");
  const generatedAt = document.getElementById("generated-at");

  dataDate.textContent = `기준일 ${data.as_of_date || "-"}`;
  generatedAt.textContent = data.generated_at ? `갱신 ${data.generated_at}` : "갱신 시각 없음";

  dot.classList.remove("is-fresh", "is-stale");
  if (data.freshness === "fresh") dot.classList.add("is-fresh");
  if (data.freshness === "stale") dot.classList.add("is-stale");
}

function renderNational() {
  const data = state.national || FALLBACK_NATIONAL;
  const fuel = data.fuels[state.fuel] || {};
  const judge = fuel.judge_policy || "-";
  const judgeCard = document.querySelector(".judgement-card");

  document.getElementById("metric-actual").textContent = won(fuel.actual_price);
  document.getElementById("metric-actual-delta").textContent = `전일 대비 ${signedWon(fuel.actual_delta_1d)}`;
  document.getElementById("metric-fair").textContent = won(fuel.fair_price_policy);
  document.getElementById("metric-band").textContent = `적정 범위 ${won(fuel.band_low_policy)} ~ ${won(fuel.band_high_policy)}`;
  document.getElementById("metric-gap").textContent = signedWon(fuel.gap_policy);
  document.getElementById("metric-judge").textContent = judge;
  document.getElementById("metric-policy").textContent = `정책효과 ${won(fuel.policy_effect)}`;

  judgeCard.classList.remove("is-good", "is-high", "is-low");
  const klass = judgeClass(judge);
  if (klass) judgeCard.classList.add(`is-${klass}`);
}

function renderRegions() {
  const rows = state.regions.length ? state.regions : FALLBACK_REGIONS;
  const fuel = state.fuel;
  const sorted = rows
    .map((row) => ({ ...row, metric: row[fuel] || {} }))
    .sort((a, b) => Math.abs(Number(b.metric.gap_policy || 0)) - Math.abs(Number(a.metric.gap_policy || 0)));

  document.getElementById("region-count").textContent = `${rows.length}개 지역`;
  document.getElementById("region-table").innerHTML = sorted.map((row) => {
    const metric = row.metric;
    const klass = judgeClass(metric.judge_policy);
    return `
      <tr>
        <td>${row.region}</td>
        <td>${won(metric.actual_price)}</td>
        <td>${won(metric.fair_price_policy)}</td>
        <td>${signedWon(metric.gap_policy)}</td>
        <td><span class="badge ${klass}">${metric.judge_policy || "-"}</span></td>
      </tr>
    `;
  }).join("");

  const maxGap = Math.max(...sorted.map((row) => Math.abs(Number(row.metric.gap_policy || 0))), 1);
  document.getElementById("region-rank").innerHTML = sorted.slice(0, 5).map((row) => {
    const pct = Math.min(100, Math.abs(Number(row.metric.gap_policy || 0)) / maxGap * 100);
    return `
      <div class="rank-row">
        <strong>${row.region}</strong>
        <div class="rank-bar"><span style="width:${pct}%"></span></div>
        <span>${signedWon(row.metric.gap_policy)}</span>
      </div>
    `;
  }).join("");
}

function renderStations() {
  const query = document.getElementById("station-search").value.trim().toLowerCase();
  const base = state.stations.length ? state.stations : FALLBACK_STATIONS;
  const rows = query
    ? base.filter((station) => [station.name, station.brand, station.region, station.address].join(" ").toLowerCase().includes(query)).slice(0, 12)
    : [];

  document.getElementById("search-count").textContent = query ? `${rows.length}개 결과` : "검색어를 입력하세요";
  document.getElementById("station-results").innerHTML = rows.map((station) => {
    const price = state.fuel === "gasoline" ? station.gasoline_price : station.diesel_price;
    return `
      <article class="station-card">
        <strong>${station.name || station.station_id}</strong>
        <span>${station.brand || "-"} · ${station.region || "-"}</span>
        <span>${station.address || ""}</span>
        <span>${state.fuel === "gasoline" ? "휘발유" : "경유"} ${won(price)} · ${station.judge_policy || "-"}</span>
      </article>
    `;
  }).join("");
}

function render() {
  renderStatus();
  renderNational();
  renderRegions();
  renderStations();
}

async function boot() {
  state.manifest = await loadJson("./public/data/latest/site_manifest.json", {});
  state.national = await loadJson("./public/data/latest/national_today.json", FALLBACK_NATIONAL);
  state.regions = await loadJson("./public/data/latest/region_today.json", FALLBACK_REGIONS);
  state.stations = await loadJson("./public/data/latest/station_search_index.json", FALLBACK_STATIONS);

  document.querySelectorAll(".fuel-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.fuel = button.dataset.fuel;
      document.querySelectorAll(".fuel-button").forEach((item) => item.classList.toggle("is-active", item === button));
      render();
    });
  });

  document.getElementById("station-search").addEventListener("input", renderStations);

  const map = document.getElementById("korea-map");
  const showMapFallback = () => {
    map.style.display = "none";
    document.getElementById("map-fallback").style.display = "grid";
  };
  map.addEventListener("error", showMapFallback);
  if (map.complete && map.naturalWidth === 0) showMapFallback();

  render();
}

boot();
