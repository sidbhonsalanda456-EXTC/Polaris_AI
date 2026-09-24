// Polar Station Mission Control Application Logic
let ws = null;
let trainingWs = null;
let isPlaying = true;
let currentMode = "AI_PPO";
let currentSpeed = 1.0;
let isDemoActive = false;
let currentStreamFeedMode = "DYNAMIC_SYNTHETIC";
let sliderDebounceTimer = null;

// 8 Chart Instances
let chartGen = null;
let chartLoad = null;
let chartBattery = null;
let chartRenew = null;
let chartBalance = null;
let chartWeather = null;
let chartReward = null;
let chartOverlay = null;
let chartTraining = null;

const MAX_HISTORY_POINTS = 30;

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  initCharts();
  connectWebSocket();
  connectTrainingWebSocket();
  fetchInitialComparison();
});

// Tab Switching
function switchTab(tabId) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll(".nav-tab").forEach(el => {
    el.classList.remove("border-cyan-400", "text-cyan-300", "bg-slate-900/80");
    el.classList.add("border-transparent", "text-slate-400");
  });

  const targetContent = document.getElementById(tabId);
  if (targetContent) targetContent.classList.remove("hidden");

  const targetBtn = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
  if (targetBtn) {
    targetBtn.classList.add("border-cyan-400", "text-cyan-300", "bg-slate-900/80");
    targetBtn.classList.remove("border-transparent", "text-slate-400");
  }
}

// Chart.js Common Config Helper
function createLineChart(ctx, datasets, yTitle = "") {
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: { color: "#94a3b8", boxWidth: 10, font: { size: 9, family: "monospace" } }
        },
        tooltip: { mode: "index", intersect: false }
      },
      scales: {
        x: { display: false, grid: { display: false } },
        y: {
          grid: { color: "rgba(56, 189, 248, 0.08)" },
          ticks: { color: "#94a3b8", font: { size: 9, family: "monospace" } },
          title: { display: !!yTitle, text: yTitle, color: "#64748b", font: { size: 9 } }
        }
      }
    }
  });
}

function initCharts() {
  // Chart 1: Generation (Solar vs Wind vs Diesel)
  chartGen = createLineChart(document.getElementById("chart-generation").getContext("2d"), [
    { label: "Solar (Part 1)", borderColor: "#fbbf24", backgroundColor: "rgba(251,191,36,0.1)", data: [], borderWidth: 1.8, tension: 0.2 },
    { label: "Wind (Part 1)", borderColor: "#34d399", backgroundColor: "rgba(52,211,153,0.1)", data: [], borderWidth: 1.8, tension: 0.2 },
    { label: "Diesel (Part 2)", borderColor: "#f87171", borderDash: [4, 4], data: [], borderWidth: 1.5 }
  ]);

  // Chart 2: Consumption
  chartLoad = createLineChart(document.getElementById("chart-consumption").getContext("2d"), [
    { label: "Critical", borderColor: "#f87171", data: [], borderWidth: 1.8, tension: 0.2 },
    { label: "Flexible", borderColor: "#a78bfa", data: [], borderWidth: 1.8, tension: 0.2 },
    { label: "Heating", borderColor: "#fb923c", data: [], borderWidth: 1.5, tension: 0.2 }
  ]);

  // Chart 3: Battery
  chartBattery = createLineChart(document.getElementById("chart-battery").getContext("2d"), [
    { label: "SOC (%)", borderColor: "#38bdf8", data: [], borderWidth: 2, tension: 0.2, yAxisID: "y" },
    { label: "Temp (°C)", borderColor: "#fbbf24", data: [], borderWidth: 1.5, tension: 0.2, yAxisID: "y1" }
  ]);
  chartBattery.options.scales.y1 = {
    position: "right",
    grid: { display: false },
    ticks: { color: "#fbbf24", font: { size: 9, family: "monospace" } }
  };

  // Chart 4: Renewable %
  chartRenew = createLineChart(document.getElementById("chart-renewable").getContext("2d"), [
    { label: "Clean %", borderColor: "#34d399", backgroundColor: "rgba(52,211,153,0.15)", fill: true, data: [], borderWidth: 2, tension: 0.2 }
  ]);

  // Chart 5: Balance
  chartBalance = createLineChart(document.getElementById("chart-balance").getContext("2d"), [
    { label: "Net Balance", borderColor: "#38bdf8", backgroundColor: "rgba(56,189,248,0.1)", fill: true, data: [], borderWidth: 2, tension: 0.2 }
  ]);

  // Chart 6: Dynamic Weather Inputs
  chartWeather = createLineChart(document.getElementById("chart-weather").getContext("2d"), [
    { label: "Temp (°C)", borderColor: "#60a5fa", data: [], borderWidth: 1.8, tension: 0.2, yAxisID: "y" },
    { label: "Wind (m/s)", borderColor: "#2dd4bf", data: [], borderWidth: 1.5, tension: 0.2, yAxisID: "y1" }
  ]);
  chartWeather.options.scales.y1 = {
    position: "right",
    grid: { display: false },
    ticks: { color: "#2dd4bf", font: { size: 9, family: "monospace" } }
  };

  // Chart 7: Reward
  chartReward = createLineChart(document.getElementById("chart-reward").getContext("2d"), [
    { label: "AI Reward", borderColor: "#c084fc", backgroundColor: "rgba(192,132,252,0.1)", fill: true, data: [], borderWidth: 2, tension: 0.2 }
  ]);

  // Chart 8: Overlay
  chartOverlay = createLineChart(document.getElementById("chart-overlay").getContext("2d"), [
    { label: "Supply", borderColor: "#34d399", data: [], borderWidth: 1.8, tension: 0.2 },
    { label: "Demand", borderColor: "#38bdf8", data: [], borderWidth: 1.8, tension: 0.2 }
  ]);

  // Training Progress Chart
  const trainCtx = document.getElementById("chart-training-progress").getContext("2d");
  chartTraining = new Chart(trainCtx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Episode Reward", borderColor: "#a855f7", data: [], borderWidth: 1.5, pointRadius: 2 },
        { label: "Running Avg Reward", borderColor: "#34d399", data: [], borderWidth: 2.5, pointRadius: 0 }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: "#94a3b8", font: { family: "monospace" } } }
      },
      scales: {
        x: { ticks: { color: "#94a3b8", font: { size: 10 } }, title: { display: true, text: "Episode", color: "#64748b" } },
        y: { ticks: { color: "#94a3b8", font: { size: 10 } }, title: { display: true, text: "Reward", color: "#64748b" } }
      }
    }
  });
}

function pushChartData(chart, label, datasetsData) {
  if (!chart) return;
  chart.data.labels.push(label);
  datasetsData.forEach((val, i) => {
    if (chart.data.datasets[i]) {
      chart.data.datasets[i].data.push(val);
    }
  });

  if (chart.data.labels.length > MAX_HISTORY_POINTS) {
    chart.data.labels.shift();
    chart.data.datasets.forEach(ds => ds.data.shift());
  }
  chart.update("none");
}

// WebSocket Connection
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById("conn-dot").className = "pulse-dot pulse-green";
    document.getElementById("conn-label").textContent = "LIVE FEED";
    document.getElementById("conn-label").className = "text-emerald-400";
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "telemetry" || msg.type === "initial_state") {
        updateDashboard(msg.data, msg.twin);
      }
    } catch (e) {
      console.error("WS Parse error:", e);
    }
  };

  ws.onclose = () => {
    document.getElementById("conn-dot").className = "pulse-dot pulse-red";
    document.getElementById("conn-label").textContent = "DISCONNECTED";
    document.getElementById("conn-label").className = "text-red-400";
    setTimeout(connectWebSocket, 2000);
  };
}

function connectTrainingWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/training`;

  trainingWs = new WebSocket(wsUrl);

  trainingWs.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "training_update" || msg.type === "training_state") {
        updateTrainingUI(msg.data);
      }
    } catch (e) {
      console.error("Training WS error:", e);
    }
  };

  trainingWs.onclose = () => {
    setTimeout(connectTrainingWebSocket, 3000);
  };
}

// Dashboard Update Routine
function updateDashboard(data, twin) {
  if (!data) return;

  // 1. Clock & Mode
  document.getElementById("sim-clock").textContent = data.sim_time_str || "";
  
  // 2. Demo Banner
  const banner = document.getElementById("demo-banner");
  if (data.demo_phase && data.demo_phase !== "Inactive") {
    banner.classList.remove("hidden");
    document.getElementById("demo-phase-text").textContent = data.demo_phase;
    document.getElementById("demo-timer").textContent = `${data.demo_elapsed_s || 0}s`;
  } else {
    banner.classList.add("hidden");
  }

  // 3. Real-Time Dynamic Input Data Stream
  const inStream = data.dynamic_input_stream || {};
  document.getElementById("input-feed-source").textContent = inStream.feed_source_label || "Dynamic Stream";
  document.getElementById("in-temp").textContent = `${inStream.temperature_c?.toFixed(1) || data.temperature_c?.toFixed(1)}°C`;
  document.getElementById("in-solar").textContent = `${inStream.solar_irradiance_w_m2?.toFixed(1) || data.solar_irradiance_w_m2?.toFixed(1)} W/m²`;
  document.getElementById("in-wind").textContent = `${inStream.wind_speed_m_s?.toFixed(1) || data.wind_speed_m_s?.toFixed(1)} m/s`;
  document.getElementById("in-cloud").textContent = `${Math.round((inStream.cloud_cover ?? data.cloud_cover ?? 0.3) * 100)}%`;
  document.getElementById("in-press").textContent = `${inStream.atmospheric_pressure_hpa?.toFixed(1) || 985.0} hPa`;

  // Sync sliders if not in manual mode
  if (currentStreamFeedMode !== "MANUAL_STREAM") {
    document.getElementById("slider-wind").value = inStream.wind_speed_m_s || data.wind_speed_m_s || 9.2;
    document.getElementById("slider-wind-val").textContent = `${(inStream.wind_speed_m_s || data.wind_speed_m_s || 9.2).toFixed(1)} m/s`;
    document.getElementById("slider-solar").value = inStream.solar_irradiance_w_m2 || data.solar_irradiance_w_m2 || 420;
    document.getElementById("slider-solar-val").textContent = `${Math.round(inStream.solar_irradiance_w_m2 || data.solar_irradiance_w_m2 || 420)} W/m²`;
    document.getElementById("slider-temp").value = inStream.temperature_c || data.temperature_c || -25;
    document.getElementById("slider-temp-val").textContent = `${(inStream.temperature_c || data.temperature_c || -25).toFixed(1)}°C`;
  }

  // 4. PART 1: RENEWABLE ENERGY RESOURCES
  const ren = data.renewable_resources || {};
  document.getElementById("p1-total-ren-kw").textContent = ren.total_renewable_kw?.toFixed(1) || (data.solar_power_kw + data.wind_power_kw).toFixed(1);
  document.getElementById("p1-solar-kw").textContent = `${ren.solar_power_kw?.toFixed(1) || data.solar_power_kw?.toFixed(1)} kW`;
  document.getElementById("p1-wind-kw").textContent = `${ren.wind_power_kw?.toFixed(1) || data.wind_power_kw?.toFixed(1)} kW`;
  
  const windFeathered = data.wind_speed_m_s > 25.0;
  document.getElementById("p1-wind-status").textContent = windFeathered ? "STORM CUT-OUT" : "Active";
  document.getElementById("p1-wind-status").className = windFeathered ? "text-[10px] font-mono text-red-400 font-bold" : "text-[10px] font-mono text-emerald-400 font-bold";

  const soc = data.battery_soc_pct || 70.0;
  document.getElementById("p1-bat-soc").textContent = `${soc.toFixed(1)}% SOC`;
  document.getElementById("p1-bat-bar").style.width = `${Math.min(100, Math.max(0, soc))}%`;
  document.getElementById("p1-bat-flow").textContent = (data.battery_power_kw > 0 ? "+" : "") + data.battery_power_kw?.toFixed(1) + " kW";
  document.getElementById("p1-ren-share").textContent = `${data.renewable_percentage?.toFixed(1) || 0.0}%`;
  document.getElementById("p1-co2-offset").textContent = `${ren.co2_offset_kg?.toFixed(1) || 0.0} kg`;

  // 5. PART 2: NON-RENEWABLE ENERGY RESOURCES
  const nonRen = data.non_renewable_resources || {};
  const totalFossil = nonRen.total_non_renewable_kw || data.generator_power_kw || 0.0;
  document.getElementById("p2-total-fossil-kw").textContent = totalFossil.toFixed(1);
  
  const priKw = nonRen.primary_diesel_kw || data.generator_power_kw || 0.0;
  document.getElementById("p2-diesel-kw").textContent = `${priKw.toFixed(1)} kW`;
  document.getElementById("p2-diesel-status").textContent = priKw > 0.5 ? "ONLINE" : "STANDBY";
  document.getElementById("p2-diesel-status").className = priKw > 0.5 ? "text-[10px] font-mono text-amber-400 font-bold glow-amber" : "text-[10px] font-mono text-slate-500";

  const auxKw = nonRen.aux_generator_kw || 0.0;
  document.getElementById("p2-aux-kw").textContent = `${auxKw.toFixed(1)} kW`;
  document.getElementById("p2-aux-status").textContent = auxKw > 0.5 ? "ONLINE" : "STANDBY";
  document.getElementById("p2-aux-status").className = auxKw > 0.5 ? "text-[10px] font-mono text-red-400 font-bold" : "text-[10px] font-mono text-slate-500";

  document.getElementById("p2-fuel-pct").textContent = `${nonRen.reserve_tank_pct?.toFixed(1) || 100}%`;
  document.getElementById("p2-fuel-rem").textContent = `${Math.round(nonRen.remaining_fuel_liters || 12000).toLocaleString()} L`;
  document.getElementById("p2-fuel-burned").textContent = nonRen.total_fuel_consumed_liters?.toFixed(1) || data.summary?.fuel_consumed_liters || "0.0";
  document.getElementById("p2-burn-rate").textContent = nonRen.fuel_burn_rate_l_h?.toFixed(1) || "0.0";
  document.getElementById("p2-carbon-emitted").textContent = `${nonRen.carbon_emissions_kg_co2?.toFixed(1) || "0.0"} kg CO₂`;
  document.getElementById("p2-fuel-cost").textContent = `$${(nonRen.fuel_cost_usd || 0.0).toFixed(2)}`;

  // 6. AI Decision Panel
  const actionBadge = document.getElementById("ai-decision-badge");
  actionBadge.textContent = data.ai_action_name || "MAINTAIN";
  document.getElementById("ai-action-code").textContent = `Action Code: ${data.ai_action ?? 0}`;
  document.getElementById("ai-reason-text").textContent = data.ai_action_reason || "Station operates in balance.";

  const actionColors = {
    0: "bg-cyan-950 text-cyan-300 border-cyan-500/40 glow-cyan",
    1: "bg-emerald-950 text-emerald-300 border-emerald-500/40 glow-green",
    2: "bg-sky-950 text-sky-300 border-sky-500/40 glow-cyan",
    3: "bg-amber-950 text-amber-300 border-amber-500/40",
    4: "bg-purple-950 text-purple-300 border-purple-500/40",
    5: "bg-red-950 text-red-300 border-red-500/40 glow-red"
  };
  actionBadge.className = `text-sm font-black px-3 py-1.5 rounded-md border ${actionColors[data.ai_action] || actionColors[0]}`;

  document.getElementById("ai-in-net").textContent = `${data.power_balance_kw?.toFixed(1) || 0.0} kW`;
  document.getElementById("ai-in-soc").textContent = `${soc.toFixed(1)}%`;
  document.getElementById("ai-in-temp").textContent = `${data.temperature_c?.toFixed(1)}°C`;
  document.getElementById("ai-in-shed").textContent = data.shedding_active ? "YES (Curtailed)" : "No";

  // 7. Alerts Feed
  updateAlertsFeed(data.alerts || []);

  // 8. Dynamic Synchronized Charts
  const timeLabel = (data.sim_time_str || "").split(" ")[1] || "";
  pushChartData(chartGen, timeLabel, [data.solar_power_kw, data.wind_power_kw, totalFossil]);
  pushChartData(chartLoad, timeLabel, [data.critical_load_kw, data.flexible_load_kw, data.heating_load_kw]);
  pushChartData(chartBattery, timeLabel, [data.battery_soc_pct, data.battery_temperature_c]);
  pushChartData(chartRenew, timeLabel, [data.renewable_percentage]);
  pushChartData(chartBalance, timeLabel, [data.power_balance_kw]);
  pushChartData(chartWeather, timeLabel, [data.temperature_c, data.wind_speed_m_s]);
  pushChartData(chartReward, timeLabel, [data.ai_reward]);
  pushChartData(chartOverlay, timeLabel, [data.total_generation_kw, data.total_station_load_kw]);

  // 9. Digital Twin SVG & JSON
  updateDigitalTwinSVG(data, nonRen);
  if (twin) {
    document.getElementById("ditto-json-view").textContent = JSON.stringify(twin, null, 2);
  }

  // 10. Mission Summary Tab
  if (data.summary) {
    document.getElementById("sum-renew-kwh").textContent = `${data.summary.total_renewable_kwh} kWh`;
    document.getElementById("sum-renew-pct").textContent = `${data.renewable_percentage?.toFixed(1) || 0.0}%`;
    document.getElementById("sum-co2-offset").textContent = `${ren.co2_offset_kg?.toFixed(1) || 0.0} kg`;
    document.getElementById("sum-diesel-kwh").textContent = `${data.summary.total_diesel_kwh} kWh`;
    document.getElementById("sum-fuel-liters").textContent = `${data.summary.fuel_consumed_liters} L`;
    document.getElementById("sum-fuel-rem").textContent = `${Math.round(nonRen.remaining_fuel_liters || 12000).toLocaleString()} L`;
    document.getElementById("sum-fuel-cost").textContent = `$${(nonRen.fuel_cost_usd || 0.0).toFixed(2)}`;
    document.getElementById("sum-total-cons").textContent = `${data.summary.total_energy_consumed_kwh} kWh`;
    document.getElementById("sum-crit-avail").textContent = `${data.summary.critical_availability_pct}%`;
    document.getElementById("sum-shortages").textContent = data.summary.critical_shortage_events;
    document.getElementById("summary-timestamp").textContent = data.sim_time_str || "Live";
  }

  // 11. Master Integration Hub Dynamic Metrics
  updateIntegrationHub(data);
}

function updateAlertsFeed(alerts) {
  const container = document.getElementById("alert-container");
  document.getElementById("alert-count-pill").textContent = `${alerts.length} Active`;

  if (alerts.length === 0) {
    container.innerHTML = `
      <div class="p-2 rounded bg-emerald-950/40 border border-emerald-500/30 text-emerald-300 text-[11px] flex items-center space-x-2">
        <span>✓</span>
        <span>All polar station subsystems operating within nominal safety margins.</span>
      </div>
    `;
    return;
  }

  container.innerHTML = alerts.map(a => {
    const isDanger = a.severity === "danger";
    const bg = isDanger ? "bg-red-950/70 border-red-500/50 text-red-200" : "bg-amber-950/70 border-amber-500/50 text-amber-200";
    const icon = isDanger ? "🚨" : "⚠️";
    return `
      <div class="p-2 rounded border ${bg} text-[11px] flex items-start space-x-2">
        <span>${icon}</span>
        <div class="flex-1">
          <div class="flex justify-between font-bold">
            <span>${a.title}</span>
            <span class="text-[10px] text-slate-400">${a.timestamp}</span>
          </div>
          <p class="text-[10px] mt-0.5">${a.message}</p>
        </div>
      </div>
    `;
  }).join("");
}

function updateDigitalTwinSVG(data, nonRen) {
  const solarText = document.getElementById("svg-solar-val");
  if (solarText) solarText.textContent = `${data.solar_power_kw?.toFixed(1) || 0} kW • Clean PV`;

  const windText = document.getElementById("svg-wind-val");
  if (windText) windText.textContent = `${data.wind_power_kw?.toFixed(1) || 0} kW • ${data.wind_speed_m_s?.toFixed(1) || 0} m/s`;

  const batText = document.getElementById("svg-bat-val");
  if (batText) batText.textContent = `SOC: ${data.battery_soc_pct?.toFixed(0) || 70}% • ${data.battery_power_kw?.toFixed(1) || 0} kW`;

  const dieselText = document.getElementById("svg-diesel-val");
  if (dieselText) {
    const dKw = nonRen.primary_diesel_kw || data.generator_power_kw || 0.0;
    if (dKw > 0.5) {
      dieselText.textContent = `ONLINE • ${dKw.toFixed(1)} kW`;
      dieselText.setAttribute("fill", "#f87171");
    } else {
      dieselText.textContent = "STANDBY • 0.0 kW";
      dieselText.setAttribute("fill", "#fbbf24");
    }
  }

  const auxText = document.getElementById("svg-aux-val");
  if (auxText) {
    const aKw = nonRen.aux_generator_kw || 0.0;
    if (aKw > 0.5) {
      auxText.textContent = `ONLINE • ${aKw.toFixed(1)} kW`;
      auxText.setAttribute("fill", "#f87171");
    } else {
      auxText.textContent = "STANDBY • 0.0 kW";
      auxText.setAttribute("fill", "#fb923c");
    }
  }

  const critText = document.getElementById("svg-crit-val");
  if (critText) critText.textContent = `${data.critical_load_supplied_pct?.toFixed(0) || 100}% Met • ${data.critical_load_kw?.toFixed(0) || 38} kW`;

  const heatText = document.getElementById("svg-heat-val");
  if (heatText) heatText.textContent = `${data.heating_load_kw?.toFixed(0) || 16} kW • Amb: ${data.temperature_c?.toFixed(0) || -25}°C`;

  const flexText = document.getElementById("svg-flex-val");
  if (flexText) {
    if (data.shedding_active) {
      flexText.textContent = `${data.flexible_load_kw?.toFixed(0)} kW • CURTAILED`;
      flexText.setAttribute("fill", "#fbbf24");
    } else {
      flexText.textContent = `${data.flexible_load_kw?.toFixed(0) || 25} kW • Normal`;
      flexText.setAttribute("fill", "#a78bfa");
    }
  }
}

function updateIntegrationHub(data) {
  if (!data) return;
  const im = data.integration_metrics || {};

  // HUD Metrics
  const totLat = document.getElementById("integ-total-latency");
  if (totLat) totLat.textContent = `${im.total_pipeline_ms?.toFixed(2) || "3.20"} ms`;

  const freqEl = document.getElementById("integ-freq");
  if (freqEl) freqEl.textContent = `${im.throughput_hz?.toFixed(0) || "280"} Hz`;

  // Pipeline Step Badges
  const s1 = document.getElementById("integ-step1-ms");
  if (s1) s1.textContent = `${im.data_pipeline_ms?.toFixed(2) || "0.80"} ms`;

  const s2 = document.getElementById("integ-step2-ms");
  if (s2) s2.textContent = `0.45 ms`;

  const s3 = document.getElementById("integ-step3-ms");
  if (s3) s3.textContent = `${im.ai_inference_ms?.toFixed(2) || "1.20"} ms`;

  const s4 = document.getElementById("integ-step4-ms");
  if (s4) s4.textContent = `${im.simulation_physics_ms?.toFixed(2) || "1.50"} ms`;

  const s5 = document.getElementById("integ-step5-ms");
  if (s5) s5.textContent = `${im.digital_twin_sync_ms?.toFixed(2) || "0.90"} ms`;

  // Dynamic Pipeline Values
  const dSrc = document.getElementById("integ-data-src");
  if (dSrc) dSrc.textContent = im.data_feed_source || "Live Stream";

  const aiAct = document.getElementById("integ-ai-act");
  if (aiAct) aiAct.textContent = `Action ${data.ai_action ?? 0}`;

  const renFlow = document.getElementById("integ-ren-flow");
  if (renFlow) renFlow.textContent = `${data.renewable_power_kw?.toFixed(1) || 0} kW`;

  const genFlow = document.getElementById("integ-gen-flow");
  if (genFlow) genFlow.textContent = `${data.generator_power_kw?.toFixed(1) || 0} kW`;

  const twinHealth = document.getElementById("integ-twin-health");
  if (twinHealth) twinHealth.textContent = `${im.twin_health_score || 100} / 100`;

  // Individual Track Cards
  const cAi = document.getElementById("integ-card-ai-ms");
  if (cAi) cAi.textContent = `${im.ai_inference_ms?.toFixed(2) || "1.20"} ms`;

  const cData = document.getElementById("integ-card-data-ms");
  if (cData) cData.textContent = `${im.data_pipeline_ms?.toFixed(2) || "0.80"} ms`;

  const cSim = document.getElementById("integ-card-sim-ms");
  if (cSim) cSim.textContent = `${im.simulation_physics_ms?.toFixed(2) || "1.50"} ms`;

  const cTwinMs = document.getElementById("integ-card-twin-ms");
  if (cTwinMs) cTwinMs.textContent = `${im.digital_twin_sync_ms?.toFixed(2) || "0.90"} ms`;

  const cTwinHealth = document.getElementById("integ-card-twin-health");
  if (cTwinHealth) cTwinHealth.textContent = `${im.twin_health_score || 100}% Nominal`;
}

// Stream Feed Mode Switcher
async function setStreamFeedMode(mode) {
  currentStreamFeedMode = mode;
  await fetch("/api/stream/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode })
  });

  const buttons = {
    REAL_WORLD_LIVE: document.getElementById("feed-btn-real"),
    DYNAMIC_SYNTHETIC: document.getElementById("feed-btn-dyn"),
    MANUAL_STREAM: document.getElementById("feed-btn-manual")
  };

  Object.entries(buttons).forEach(([key, btn]) => {
    if (key === mode) {
      btn.className = "px-2 py-0.5 rounded bg-cyan-700 text-white transition";
    } else {
      btn.className = "px-2 py-0.5 rounded text-slate-400 hover:text-white transition";
    }
  });
}

// Live Manual Slider Changes
function onManualSliderChange() {
  currentStreamFeedMode = "MANUAL_STREAM";
  const windVal = parseFloat(document.getElementById("slider-wind").value);
  const solarVal = parseFloat(document.getElementById("slider-solar").value);
  const tempVal = parseFloat(document.getElementById("slider-temp").value);

  document.getElementById("slider-wind-val").textContent = `${windVal.toFixed(1)} m/s`;
  document.getElementById("slider-solar-val").textContent = `${Math.round(solarVal)} W/m²`;
  document.getElementById("slider-temp-val").textContent = `${tempVal.toFixed(1)}°C`;

  // Highlight manual button
  document.getElementById("feed-btn-manual").className = "px-2 py-0.5 rounded bg-cyan-700 text-white transition";
  document.getElementById("feed-btn-real").className = "px-2 py-0.5 rounded text-slate-400 hover:text-white transition";
  document.getElementById("feed-btn-dyn").className = "px-2 py-0.5 rounded text-slate-400 hover:text-white transition";

  // Debounce API dispatch to prevent spamming
  clearTimeout(sliderDebounceTimer);
  sliderDebounceTimer = setTimeout(async () => {
    await fetch("/api/stream/input", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        temperature: tempVal,
        solar: solarVal,
        wind: windVal
      })
    });
  }, 100);
}

// Training UI Update
function updateTrainingUI(stats) {
  if (!stats) return;
  document.getElementById("tr-status").textContent = stats.is_active ? "TRAINING ACTIVE" : "IDLE";
  document.getElementById("tr-status").className = stats.is_active ? "font-bold text-purple-400 animate-pulse" : "font-bold text-slate-300";
  document.getElementById("tr-episode").textContent = stats.episode || 0;
  document.getElementById("tr-cur-reward").textContent = stats.current_reward?.toFixed(1) || "0.0";
  document.getElementById("tr-avg-reward").textContent = stats.average_reward?.toFixed(1) || "0.0";
  document.getElementById("tr-best-reward").textContent = stats.best_reward?.toFixed(1) || "0.0";

  const prog = stats.progress_pct || 0.0;
  document.getElementById("tr-progress-pct").textContent = `${prog.toFixed(1)}%`;
  document.getElementById("tr-progress-bar").style.width = `${Math.min(100, prog)}%`;

  if (stats.episode && stats.current_reward) {
    chartTraining.data.labels.push(`Ep ${stats.episode}`);
    chartTraining.data.datasets[0].data.push(stats.current_reward);
    chartTraining.data.datasets[1].data.push(stats.average_reward);
    if (chartTraining.data.labels.length > 50) {
      chartTraining.data.labels.shift();
      chartTraining.data.datasets[0].data.shift();
      chartTraining.data.datasets[1].data.shift();
    }
    chartTraining.update("none");
  }
}

// Controls
async function togglePlayPause() {
  isPlaying = !isPlaying;
  const endpoint = isPlaying ? "/api/simulation/start" : "/api/simulation/stop";
  await fetch(endpoint, { method: "POST" });
  document.getElementById("play-pause-icon").textContent = isPlaying ? "⏸" : "▶";
  document.getElementById("play-pause-text").textContent = isPlaying ? "Pause" : "Resume";
  document.getElementById("btn-play-pause").className = isPlaying ? 
    "px-3 py-1 rounded-md bg-emerald-600/90 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center space-x-1" :
    "px-3 py-1 rounded-md bg-amber-600/90 hover:bg-amber-500 text-white text-xs font-bold transition flex items-center space-x-1";
}

async function resetSimulation() {
  await fetch("/api/simulation/reset", { method: "POST" });
}

async function setMode(mode) {
  currentMode = mode;
  await fetch("/api/simulation/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode })
  });

  const buttons = {
    AI_PPO: document.getElementById("mode-ai"),
    BASELINE: document.getElementById("mode-baseline"),
    MANUAL: document.getElementById("mode-manual")
  };

  Object.entries(buttons).forEach(([key, btn]) => {
    if (key === mode) {
      btn.className = "px-2.5 py-1 rounded bg-cyan-600 text-white shadow-sm transition";
    } else {
      btn.className = "px-2.5 py-1 rounded text-slate-400 hover:text-white transition";
    }
  });
}

async function setSpeed(speed) {
  currentSpeed = speed;
  await fetch("/api/simulation/speed", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ speed })
  });

  document.querySelectorAll(".speed-btn").forEach(btn => {
    if (parseFloat(btn.dataset.speed) === speed) {
      btn.className = "speed-btn px-1.5 py-0.5 rounded bg-cyan-600 text-white";
    } else {
      btn.className = "speed-btn px-1.5 py-0.5 rounded text-slate-400 hover:text-white";
    }
  });
}

async function toggleDemoMode() {
  isDemoActive = !isDemoActive;
  const endpoint = isDemoActive ? "/api/demo/start" : "/api/demo/stop";
  await fetch(endpoint, { method: "POST" });
  document.getElementById("demo-btn-label").textContent = isDemoActive ? "STOP DEMO" : "START DEMO";
}

async function injectWeather(cond, temp, wind, solar) {
  await fetch("/api/simulation/weather", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      condition: cond,
      temperature: temp,
      wind_speed: wind,
      solar_irradiance: solar,
      cloud_cover: 0.95
    })
  });
}

async function clearWeatherOverride() {
  await fetch("/api/simulation/weather/clear", { method: "POST" });
}

// AI vs Baseline Comparison
async function fetchInitialComparison() {
  try {
    const res = await fetch("/api/comparison?steps=144&seed=42");
    const json = await res.json();
    if (json.status === "success") {
      populateBenchmark(json.data);
    }
  } catch (e) {
    console.error("Comparison fetch error:", e);
  }
}

async function runComparisonBenchmark() {
  const btn = event.currentTarget;
  const oldText = btn.innerHTML;
  btn.innerHTML = "<span>⏳</span><span>Simulating 144 Steps...</span>";
  btn.disabled = true;

  try {
    const res = await fetch("/api/comparison?steps=144&seed=42");
    const json = await res.json();
    if (json.status === "success") {
      populateBenchmark(json.data);
    }
  } catch (e) {
    console.error("Benchmark error:", e);
  } finally {
    btn.innerHTML = oldText;
    btn.disabled = false;
  }
}

function populateBenchmark(data) {
  const imp = data.improvement;
  const ai = data.ai_controller;
  const base = data.baseline;

  document.getElementById("bm-fuel-saved").textContent = imp.diesel_fuel_saved_liters;
  document.getElementById("bm-co2-saved").textContent = imp.carbon_offset_kg_co2;
  document.getElementById("bm-renew-gain").textContent = imp.renewable_gain_pct;
  document.getElementById("bm-reward-gain").textContent = imp.reward_gain;

  document.getElementById("bm-ai-fuel").textContent = `${ai.fuel_consumed_liters} L`;
  document.getElementById("bm-base-fuel").textContent = `${base.fuel_consumed_liters} L`;
  document.getElementById("bm-diff-fuel").textContent = `-${imp.diesel_fuel_saved_liters} L Saved`;

  document.getElementById("bm-ai-renew").textContent = `${ai.renewable_percentage}%`;
  document.getElementById("bm-base-renew").textContent = `${base.renewable_percentage}%`;
  document.getElementById("bm-diff-renew").textContent = `+${imp.renewable_gain_pct}% Higher`;

  document.getElementById("bm-ai-crit").textContent = `${ai.critical_availability_pct}%`;
  document.getElementById("bm-base-crit").textContent = `${base.critical_availability_pct}%`;

  document.getElementById("bm-ai-short").textContent = `${ai.power_shortages} events`;
  document.getElementById("bm-base-short").textContent = `${base.power_shortages} events`;

  document.getElementById("bm-ai-reward").textContent = ai.total_reward;
  document.getElementById("bm-base-reward").textContent = base.total_reward;
  document.getElementById("bm-diff-reward").textContent = `+${imp.reward_gain} pts`;
}

// Training API Controls
async function startTraining() {
  await fetch("/api/training/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ timesteps: 2880 })
  });
}

async function stopTraining() {
  await fetch("/api/training/stop", { method: "POST" });
}

async function reloadModel() {
  await fetch("/api/model/load", { method: "POST" });
  alert("AI Model weights reloaded and deployed to live coordinator!");
}
