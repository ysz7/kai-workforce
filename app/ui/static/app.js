/* The page. No framework, no build step: the whole interface is one request,
   one event stream and a handful of DOM updates, and a toolchain to produce
   that would be a second thing to install on a machine whose selling point is
   that it needs nothing installed.

   Two rules keep it honest.

   The trace is appended from the stream, never re-rendered from a poll: what
   the page shows while a task runs is what the runtime said as it happened.
   Opening a past task, by contrast, draws from the stored tool calls - the
   stream buffer is short-lived and is not the record.

   Nothing is approved by the page. The buttons send a decision; the run stays
   parked until the server answers, and a closed page means an unanswered
   question, which the server treats as a no. */

const el = (id) => document.getElementById(id);

const state = {
  selected: null,   // the task whose trace is on screen
  stream: null,     // the EventSource for it
};

// --- Talking to the server --------------------------------------------------

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.status === 204 ? null : response.json();
}

// --- Starting work ----------------------------------------------------------

async function loadEmployees() {
  const { employees } = await api("/api/employees");
  const select = el("employee");
  select.innerHTML = "";
  for (const employee of employees) {
    const option = document.createElement("option");
    option.value = employee.name;
    option.textContent = `${employee.name} - ${employee.title}`;
    select.append(option);
  }
  el("run").disabled = employees.length === 0;
}

el("new-task").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = el("form-error");
  error.hidden = true;
  el("run").disabled = true;
  try {
    const task = await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ goal: el("goal").value, employee: el("employee").value }),
    });
    el("goal").value = "";
    await refreshHistory();
    select(task.id);
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally {
    el("run").disabled = false;
  }
});

// --- History ----------------------------------------------------------------

async function refreshHistory() {
  const { tasks } = await api("/api/tasks");
  const list = el("history");
  list.innerHTML = "";
  for (const task of tasks) {
    const item = document.createElement("li");
    item.className = task.id === state.selected ? "selected" : "";
    item.innerHTML = `<span class="goal"></span>
      <span class="sub"><span class="status status-${task.status}"></span>
      &middot; ${task.step} steps &middot; $${task.cost_usd.toFixed(4)}</span>`;
    item.querySelector(".goal").textContent = task.goal;
    item.querySelector(".status").textContent = task.running ? "RUNNING" : task.status;
    item.addEventListener("click", () => select(task.id));
    list.append(item);
  }
}

// --- One run ----------------------------------------------------------------

async function select(taskId) {
  state.selected = taskId;
  if (state.stream) state.stream.close();
  el("trace").innerHTML = "";

  const task = await api(`/api/tasks/${taskId}`);
  drawHeader(task);
  // A finished run is drawn from what was stored; a live one from what the
  // server buffered and is still announcing. Drawing both would show every
  // tool call of a running task twice, and the stream is the better of the two
  // while it lasts - it carries the plan and the observations, not just the
  // calls.
  if (!task.running) for (const call of task.calls) drawStoredCall(call);
  await refreshHistory();

  state.stream = new EventSource(`/api/events?task=${taskId}`);
  state.stream.onmessage = (message) => onProgress(JSON.parse(message.data));
}

function drawHeader(task) {
  el("run-goal").textContent = task.goal;
  const status = task.running ? "RUNNING" : task.status;
  el("run-meta").innerHTML = `<span class="status status-${task.status}"></span>
    &middot; ${task.employee || "unassigned"} &middot; ${task.step} steps
    &middot; $${task.cost_usd.toFixed(6)}`;
  el("run-meta").querySelector(".status").textContent = status;
  el("cancel").hidden = task.status === "COMPLETED" || task.status === "FAILED"
    || task.status === "CANCELLED";

  const result = el("run-result");
  if (task.error) {
    result.hidden = false;
    result.className = "failed";
    result.textContent = `${task.error.kind}: ${task.error.message}`;
  } else if (task.result && task.result.summary) {
    result.hidden = false;
    result.className = "";
    result.textContent = task.result.summary;
  } else {
    result.hidden = true;
  }
}

el("cancel").addEventListener("click", async () => {
  if (!state.selected) return;
  el("cancel").disabled = true;
  try {
    await api(`/api/tasks/${state.selected}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: "Stopped from the interface." }),
    });
  } finally {
    el("cancel").disabled = false;
  }
});

function line({ step, kind, message, failed, interfaceLevel }) {
  const item = document.createElement("li");
  item.className = `kind-${kind}${failed ? " failed" : ""}`;
  item.innerHTML = `<span class="step"></span><span class="kind"></span>
    <span class="message"></span>`;
  item.querySelector(".step").textContent = step ? `#${step}` : "";
  item.querySelector(".kind").textContent = interfaceLevel || kind.toLowerCase();
  item.querySelector(".message").textContent = message;
  el("trace").append(item);
  item.scrollIntoView({ block: "nearest" });
}

function drawStoredCall(call) {
  const args = Object.entries(call.arguments || {})
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(", ");
  line({
    step: 0,
    kind: "TOOL_CALL",
    interfaceLevel: call.interface,
    message: `${call.tool}(${args})${call.error ? ` - ${call.error}` : ""}`,
    failed: !call.success,
  });
}

// --- The stream -------------------------------------------------------------

function onProgress(event) {
  line({
    step: event.step,
    kind: event.kind,
    interfaceLevel: event.payload.interface,
    message: event.message,
    failed: event.payload.succeeded === false || event.payload.status === "FAILED",
  });
  if (event.kind === "RESULT" || event.kind === "APPROVAL") {
    refreshTask();
    refreshApprovals();
    refreshSpend();
  }
  if (event.kind === "RESULT" && state.stream) {
    // The server ends the stream when the task ends. Closing it here too is
    // what stops EventSource from treating that as a dropped connection and
    // reconnecting to a run that has nothing left to say.
    state.stream.close();
    state.stream = null;
  }
}

async function refreshTask() {
  if (!state.selected) return;
  drawHeader(await api(`/api/tasks/${state.selected}`));
  await refreshHistory();
}

// --- Approvals --------------------------------------------------------------

async function refreshApprovals() {
  const { approvals } = await api("/api/approvals");
  el("approvals").hidden = approvals.length === 0;
  const list = el("approval-list");
  list.innerHTML = "";
  for (const item of approvals) {
    const node = document.createElement("li");
    node.innerHTML = `<div class="action"></div><p class="why"></p>
      <button type="button" class="approve">Approve</button>
      <button type="button" class="secondary reject">Reject</button>`;
    node.querySelector(".action").textContent = item.action;
    node.querySelector(".why").textContent =
      `${item.risk}${item.reason ? ` - ${item.reason}` : ""}`;
    node.querySelector(".approve").addEventListener("click", () => decide(item.id, true));
    node.querySelector(".reject").addEventListener("click", () => decide(item.id, false));
    list.append(node);
  }
}

async function decide(approvalId, approved) {
  await api(`/api/approvals/${approvalId}`, {
    method: "POST",
    body: JSON.stringify({ approved, comment: "" }),
  });
  await refreshApprovals();
}

// --- Cost -------------------------------------------------------------------

async function refreshSpend() {
  const spend = await api("/api/spend");
  el("spend").textContent =
    `${spend.calls} calls - $${spend.cost_usd.toFixed(6)}`;
}

// --- Start ------------------------------------------------------------------

async function start() {
  await loadEmployees();
  await refreshHistory();
  await refreshApprovals();
  await refreshSpend();
  // An approval raised by a task nobody has open still has to appear, so the
  // page watches everything as well as the run it is showing.
  const all = new EventSource("/api/events");
  all.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.kind === "APPROVAL") refreshApprovals();
    if (event.kind === "RESULT" && event.task_id !== state.selected) refreshHistory();
  };
}

start().catch((failure) => {
  const error = el("form-error");
  error.textContent = failure.message;
  error.hidden = false;
});
