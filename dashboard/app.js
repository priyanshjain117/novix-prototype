const API_BASE = "";
const nodes = [
  { key: "edge-01", label: "Edge-01", url: "http://localhost:8001" },
  { key: "edge-02", label: "Edge-02", url: "http://localhost:8002" },
  { key: "master", label: "Master", url: "http://localhost:8003" },
];

const $ = (selector) => document.querySelector(selector);
const systemStatus = $("#system-status");
const queryForm = $("#query-form");
const queryInput = $("#query-input");
const executeButton = $("#execute-button");

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail?.error || body.detail || `Request failed (${response.status})`);
    return body;
  } finally {
    clearTimeout(timer);
  }
}

function setSystemStatus(text, state) {
  systemStatus.textContent = text;
  systemStatus.className = `status-pill ${state}`;
}

function setNodeStatus(card, status, state) {
  const badge = card.querySelector(".node-status");
  badge.textContent = status;
  badge.className = `node-status ${state}`;
}

async function refreshNode(node) {
  const card = $(`#${node.key}-card`);
  try {
    const resources = await fetchJson(`${node.url}/resources`);
    const cpu = Number(resources.cpu_percent || 0);
    const ram = Number(resources.memory?.percent || 0);
    if (node.key === "master") {
      setNodeStatus(card, "Available", "ok");
      card.querySelector(".master-state").textContent = "Ready";
      return true;
    }
    setNodeStatus(card, "Available", "ok");
    card.querySelector(".cpu-value").textContent = `${cpu.toFixed(1)}%`;
    card.querySelector(".ram-value").textContent = `${ram.toFixed(1)}%`;
    card.querySelector(".load-fill").style.width = `${Math.min(100, Math.max(cpu, ram))}%`;
    return true;
  } catch (error) {
    setNodeStatus(card, "Unavailable", "error");
    if (node.key === "master") card.querySelector(".master-state").textContent = "Offline";
    else {
      card.querySelector(".cpu-value").textContent = "—";
      card.querySelector(".ram-value").textContent = "—";
      card.querySelector(".load-fill").style.width = "0";
    }
    return false;
  }
}

async function refreshNodes() {
  const results = await Promise.all(nodes.map(refreshNode));
  const failed = results.filter((ready) => !ready).length;
  setSystemStatus(failed ? "Some nodes offline" : "System ready", failed ? "error" : "ok");
}

function renderPipeline(distributed, activeIndex = 4) {
  const steps = distributed
    ? [["Query", "Input"], ["Edge-01 + Edge-02", "Distributed"], ["Aggregation", "Merge"], ["Result", "Output"]]
    : [["Query", "Input"], ["Analyze", "Classify"], ["Route", "Decision"], ["Execute", "Run"], ["Result", "Output"]];
  const pipeline = $("#pipeline");
  pipeline.innerHTML = "";
  steps.forEach((step, index) => {
    const wrapper = document.createElement("div");
    wrapper.className = "pipeline-step";
    const node = document.createElement("div");
    node.className = `pipeline-node ${index < activeIndex ? "complete" : ""} ${index === activeIndex ? "active" : ""}`;
    node.innerHTML = `<strong>${step[0]}</strong><small>${step[1]}</small>`;
    wrapper.appendChild(node);
    if (index < steps.length - 1) {
      const arrow = document.createElement("span");
      arrow.className = "pipeline-arrow";
      arrow.textContent = "→";
      wrapper.appendChild(arrow);
    }
    pipeline.appendChild(wrapper);
  });
}

function renderRouting(data) {
  const decision = data.routing_decision || data.decision || "—";
  const targetNodes = data.nodes_used || data.selected_nodes || [];
  $("#routing-decision").innerHTML = `
    <div class="detail-list">
      <div class="detail-row"><span>Decision</span><span>${decision}</span></div>
      <div class="detail-row"><span>Complexity</span><span>${data.complexity || "—"}</span></div>
      <div class="detail-row"><span>Nodes used</span><span>${targetNodes.join(" + ") || "—"}</span></div>
      <div class="detail-row"><span>Unavailable</span><span>${(data.unavailable_nodes || []).join(", ") || "None"}</span></div>
    </div>`;
}

function renderExecution(data) {
  const result = $("#execution-steps");
  const subtasks = data.subtask_results || [];
  if (!subtasks.length) {
    result.innerHTML = `<div class="step-list"><div class="execution-step done"><strong>Routed to ${data.selected_nodes?.join(" + ") || data.decision || "target"}</strong><small>Execution response received</small></div></div>`;
    return;
  }
  result.innerHTML = `<div class="step-list">${subtasks.map((item) => `
    <div class="execution-step ${item.status === "completed" ? "done" : "failed"}">
      <strong>${item.node} · ${item.status}</strong><small>${item.subtask}</small>
    </div>`).join("")}</div>`;
}

async function executeQuery(event) {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;
  executeButton.disabled = true;
  setSystemStatus("Executing", "pending");
  $("#result-status").textContent = "Running";
  $("#final-response").textContent = "Waiting for router response…";
  renderPipeline(false, 1);
  try {
    const data = await fetchJson(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const distributed = data.routing_decision === "parallel-edge";
    renderPipeline(distributed, distributed ? 3 : 4);
    $("#pipeline-title").textContent = distributed ? "Distributed execution" : "Query execution";
    $("#query-id").textContent = data.query_id || "";
    renderRouting(data);
    renderExecution(data);
    const response = data.final_result || data.execution?.result || data;
    $("#final-response").textContent = response.answer || JSON.stringify(response, null, 2);
    $("#result-status").textContent = data.final_result?.status || "Complete";
    setSystemStatus("System ready", "ok");
  } catch (error) {
    $("#final-response").textContent = error.message;
    $("#final-response").classList.add("error-text");
    $("#result-status").textContent = "Failed";
    setSystemStatus("Request failed", "error");
  } finally {
    executeButton.disabled = false;
    refreshNodes();
  }
}

queryForm.addEventListener("submit", executeQuery);
$("#refresh-button").addEventListener("click", refreshNodes);
renderPipeline(false, 0);
refreshNodes();
setInterval(refreshNodes, 5000);
