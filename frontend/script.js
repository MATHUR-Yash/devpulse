"use strict";

const $ = (id) => document.getElementById(id);
const state = { user: null, repos: [], repository: "demo", runs: [], deployments: [] };
const demoRuns = [
  ["Build and test", "failure", "feat/deploy-preview", "c8ae19b", 0, 222],
  ["Deploy to production", "success", "main", "b7ad22c", 0, 96],
  ["Build and test", "active", "main", "ac930f1", 0, 0],
  ["Build and test", "success", "main", "b7ad22c", 1, 139],
  ["Build and test", "success", "main", "a5e82db", 1, 121],
  ["Deploy to staging", "success", "main", "a5e82db", 2, 86],
  ["Build and test", "failure", "feat/cache-tests", "fd1a3d4", 2, 181],
  ["Build and test", "success", "main", "98ceb3a", 3, 155],
  ["Build and test", "success", "main", "8dc9e14", 3, 142],
  ["Deploy to staging", "success", "main", "8dc9e14", 4, 73],
  ["Build and test", "success", "main", "582ac21", 4, 108],
  ["Build and test", "success", "main", "50ecd98", 5, 133],
  ["Build and test", "failure", "feat/test-retry", "67bd34a", 5, 149],
  ["Build and test", "success", "main", "1a9f2d4", 6, 162],
  ["Deploy to production", "success", "main", "1a9f2d4", 6, 93],
].map(([name, result, branch, sha, days, duration], index) => {
  const start = new Date(Date.now() - days * 86400000 - (index + 1) * 2400000);
  return {
    id: index + 1, name, branch, sha, attempt: 1, started_at: start.toISOString(),
    status: result === "active" ? "in_progress" : "completed",
    conclusion: result === "active" ? null : result,
    completed_at: duration ? new Date(+start + duration * 1000).toISOString() : null,
  };
});

function element(tag, value = "", className = "") {
  const item = document.createElement(tag);
  item.textContent = value;
  item.className = className;
  return item;
}

function button(label, handler, className = "secondary") {
  const item = element("button", label, className);
  item.type = "button";
  item.addEventListener("click", handler);
  return item;
}

async function api(path, input, method = input === undefined ? "GET" : "POST") {
  const response = await fetch("/api" + path, {
    method,
    headers: input === undefined ? {} : { "Content-Type": "application/json" },
    body: input === undefined ? undefined : JSON.stringify(input),
  });
  if (response.status === 204) return null;
  const payload = await response.json();
  if (!response.ok) {
    const message = typeof payload.detail === "string" ? payload.detail : "Check the form values and try again.";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function outcome(run) {
  if (run.conclusion === "success") return "success";
  if (["failure", "timed_out", "startup_failure", "action_required", "error"].includes(run.conclusion)) return "failure";
  return run.status === "completed" ? "other" : "active";
}

function badge(value, kind = value) {
  return element("span", String(value || "pending").replaceAll("_", " "), "badge " + kind);
}

function timestamp(value) {
  return value ? new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";
}

function elapsed(run) {
  if (!run.started_at || !run.completed_at) return "—";
  const seconds = Math.max(0, Math.round((new Date(run.completed_at) - new Date(run.started_at)) / 1000));
  return Math.floor(seconds / 60) + "m " + String(seconds % 60).padStart(2, "0") + "s";
}

function notice(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}

function renderChart() {
  const days = new Map();
  for (const run of state.runs) {
    if (!run.started_at) continue;
    const date = run.started_at.slice(0, 10);
    const data = days.get(date) || { success: 0, failure: 0, other: 0 };
    const kind = outcome(run);
    data[kind === "active" ? "other" : kind]++;
    days.set(date, data);
  }
  const recent = [...days].sort(([a], [b]) => a.localeCompare(b)).slice(-7);
  const chart = $("chart");
  chart.replaceChildren();
  if (!recent.length) {
    chart.append(element("p", "Workflow activity appears after a sync.", "empty"));
    return;
  }
  const max = Math.max(...recent.map(([, data]) => data.success + data.failure + data.other));
  const bars = element("div", "", "bars");
  const labels = element("div", "", "bar-labels");
  for (const [date, data] of recent) {
    const group = element("div", "", "bar-group");
    const description = date + ": " + data.success + " passed, " + data.failure + " failed, " + data.other + " other";
    group.title = description;
    group.setAttribute("role", "img");
    group.setAttribute("aria-label", description);
    for (const [kind, css] of [["other", "other"], ["failure", "fail"], ["success", "pass"]]) {
      if (!data[kind]) continue;
      const segment = element("span", "", css);
      segment.style.height = Math.round(data[kind] / max * 132) + "px";
      group.append(segment);
    }
    bars.append(group);
    labels.append(element("span", date.slice(5).replace("-", "/")));
  }
  chart.append(bars, labels);
}

function emptyRow(text, columns) {
  const row = element("tr");
  const cell = element("td", text, "quiet");
  cell.colSpan = columns;
  row.append(cell);
  return row;
}

function addCell(row, value) {
  const td = element("td");
  td.append(value);
  row.append(td);
}

function renderRuns() {
  const rows = $("runs");
  rows.replaceChildren();
  const filter = $("filter").value;
  const visible = state.runs.filter((run) => filter === "all" || outcome(run) === filter);
  if (!visible.length) rows.append(emptyRow("No workflow runs match this view.", 6));
  for (const run of visible) {
    const row = element("tr");
    const label = run.name + (run.attempt > 1 ? " · attempt " + run.attempt : "");
    addCell(row, button(label, () => showRun(run), "run-link"));
    addCell(row, badge(run.conclusion || run.status, outcome(run)));
    addCell(row, run.branch || "—");
    addCell(row, element("code", run.sha.slice(0, 7)));
    addCell(row, timestamp(run.started_at));
    addCell(row, elapsed(run));
    rows.append(row);
  }
}

function render() {
  const demo = state.repository === "demo";
  $("context").textContent = demo ? "Demo workspace" : "GitHub Actions";
  $("subtitle").textContent = demo ? "Sample workflow and deployment data"
    : state.lastSync ? "Last sync " + timestamp(state.lastSync.at) + " · " + state.lastSync.status
      : "Sync this repository to load its workflow history.";
  $("account").textContent = state.user ? state.user.username : "Sign in";
  $("connect").hidden = !state.user;
  $("sync").hidden = demo;
  const metrics = $("metrics");
  metrics.replaceChildren();
  const passed = state.runs.filter((run) => outcome(run) === "success").length;
  const failed = state.runs.filter((run) => outcome(run) === "failure").length;
  const active = state.runs.filter((run) => outcome(run) === "active").length;
  const rate = passed + failed ? Math.round(passed / (passed + failed) * 100) + "%" : "—";
  for (const [label, value] of [["Workflow runs", state.runs.length], ["Passed", passed], ["Failed", failed], ["Pass rate", rate]]) {
    const card = element("article", "", "metric");
    card.append(element("p", label), element("strong", value));
    if (label === "Workflow runs") card.append(element("p", active + " in progress"));
    if (label === "Pass rate") card.append(element("p", "Of passed and failed runs"));
    metrics.append(card);
  }
  renderChart();
  const attention = $("attention");
  attention.replaceChildren();
  const latest = state.runs.find((run) => outcome(run) === "failure");
  if (latest) {
    const alert = element("div", "", "alert");
    alert.append(badge(latest.conclusion, "failure"), element("h3", latest.name),
      element("p", demo ? "The test step failed, so the deployment stage was skipped." : "Inspect the stages to see which job or step failed."),
      button("Inspect failure", () => showRun(latest)));
    attention.append(alert);
  } else {
    attention.append(element("p", "No failed workflows in the current history.", "empty"));
  }
  renderRuns();
  const deployments = $("deployment-rows");
  deployments.replaceChildren();
  if (!state.deployments.length) deployments.append(emptyRow("No deployment records yet.", 4));
  for (const item of state.deployments) {
    const row = element("tr");
    addCell(row, item.environment);
    addCell(row, element("code", item.version));
    addCell(row, badge(item.status, item.status === "error" ? "failure" : item.status));
    addCell(row, timestamp(item.updated_at));
    deployments.append(row);
  }
}

function selectOptions() {
  const selector = $("repository");
  selector.replaceChildren(new Option("Demo · acme/web-platform", "demo"));
  for (const repo of state.repos) selector.add(new Option(repo.name, repo.id));
  selector.value = state.repository;
}

async function loadRepository() {
  const chosen = state.repository;
  if (chosen === "demo") {
    state.runs = demoRuns;
    state.deployments = [
      { environment: "Production", version: "v1.8.2", status: "success", updated_at: demoRuns[1].completed_at },
      { environment: "Staging", version: "v1.8.3-rc.1", status: "success", updated_at: demoRuns[5].completed_at },
      { environment: "Production", version: "v1.8.1", status: "success", updated_at: demoRuns[14].completed_at },
    ];
    render();
    return;
  }
  const data = await api("/repositories/" + chosen + "/dashboard");
  if (state.repository !== chosen) return;
  state.runs = data.runs;
  state.deployments = data.deployments;
  state.lastSync = data.last_sync;
  render();
}

function dialog(title) {
  $("dialog-title").textContent = title;
  $("dialog-content").replaceChildren();
  if (!$("dialog").open) $("dialog").showModal();
  return $("dialog-content");
}

function showTestSummary(jobs, details) {
  const tests = jobs.flatMap((job) => job.steps).filter((step) => /\b(test|tests|pytest|jest|vitest|playwright)\b/i.test(step.name));
  const passed = tests.filter((step) => step.conclusion === "success").length;
  const failed = tests.filter((step) => outcome(step) === "failure").length;
  const pending = tests.length - passed - failed;
  details.append(element("p", tests.length
    ? "Test steps · " + passed + " passed · " + failed + " failed · " + pending + " other"
    : "No test steps identified in the workflow.", "quiet"));
}

async function showRun(run) {
  const repo = state.repository;
  const target = dialog(run.name).id;
  const loading = element("p", "Loading workflow stages…", "quiet");
  $(target).append(loading);
  const result = run.conclusion || run.status;
  try {
    const data = repo === "demo" ? {
      jobs: [{
        name: "CI", status: run.status, conclusion: run.conclusion, started_at: run.started_at,
        steps: [
          { name: "Checkout code", conclusion: "success" },
          { name: "Install dependencies", conclusion: "success" },
          { name: "Run pytest", conclusion: result === "in_progress" ? null : result, status: run.status },
          { name: "Build Docker image", conclusion: result === "failure" ? "skipped" : run.conclusion, status: run.status },
        ],
      }, {
        name: "Deploy", status: run.status, conclusion: result === "failure" ? "skipped" : run.conclusion, steps: [],
      }],
    } : await api("/repositories/" + repo + "/runs/" + run.id);
    if (!loading.isConnected || !$("dialog").open) return;
    const details = $(target);
    details.replaceChildren(element("p", (run.branch || "Unknown branch") + " · " + run.sha.slice(0, 7) + " · " + elapsed(run), "quiet"));
    const failedSteps = data.jobs.flatMap((job) => job.steps).filter((step) => outcome(step) === "failure");
    if (failedSteps.length) details.append(element("p", "Failed steps: " + failedSteps.map((step) => step.name).join(", "), "alert"));
    showTestSummary(data.jobs, details);
    const timeline = element("ol", "", "timeline");
    for (const job of data.jobs) {
      const li = element("li");
      li.append(element("strong", job.name), badge(job.conclusion || job.status, outcome(job)));
      if (job.started_at) li.append(element("p", "Started " + timestamp(job.started_at), "quiet"));
      const steps = element("ul");
      for (const step of job.steps) {
        const item = element("li", step.name);
        item.append(badge(step.conclusion || step.status, outcome(step)));
        if (step.started_at) item.append(element("p", timestamp(step.started_at), "quiet"));
        steps.append(item);
      }
      if (job.steps.length) li.append(steps);
      timeline.append(li);
    }
    if (data.jobs.length) details.append(timeline);
    else details.append(element("p", "GitHub has no job details for this attempt yet.", "empty"));
    if (data.url) {
      const link = element("a", "View logs on GitHub ↗");
      link.href = data.url;
      link.target = "_blank";
      link.rel = "noopener";
      details.append(link);
    }
  } catch (error) {
    if (loading.isConnected) loading.textContent = error.message;
  }
}

function field(form, label, name, type, autocomplete) {
  const wrapper = element("label", label);
  const input = element("input");
  Object.assign(input, { name, type, required: true, autocomplete });
  wrapper.append(input);
  form.append(wrapper);
}

function formDialog(title, fields, onSubmit, toggle) {
  const content = dialog(title);
  const form = element("form", "", "form");
  for (const args of fields) field(form, ...args);
  const error = element("p", "", "form-error");
  error.setAttribute("role", "alert");
  const actions = element("div", "", "actions");
  const submit = element("button", title, "primary");
  submit.type = "submit";
  actions.append(submit);
  if (toggle) actions.append(button(toggle.label, toggle.action));
  form.append(error, actions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    error.textContent = "";
    try {
      await onSubmit(Object.fromEntries(new FormData(form)));
      $("dialog").close();
    } catch (err) {
      error.textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
  content.append(form);
  form.querySelector("input").focus();
}

function account(register = false) {
  if (state.user) {
    dialog("Account").append(element("p", "Signed in as " + state.user.username, "quiet"),
      button("Sign out", async () => {
        try {
          await api("/auth/logout", undefined, "POST");
          state.user = null;
          state.repos = [];
          state.repository = "demo";
          selectOptions();
          await loadRepository();
          $("dialog").close();
        } catch (error) {
          $("dialog-content").append(element("p", error.message, "form-error"));
        }
      }));
    return;
  }
  const fields = [["Username", "username", "text", "username"]];
  if (register) fields.push(["Email", "email", "email", "email"]);
  fields.push(["Password", "password", "password", register ? "new-password" : "current-password"]);
  formDialog(register ? "Create account" : "Sign in", fields, async (values) => {
    state.user = await api(register ? "/auth/register" : "/auth/login", values);
    state.repos = await api("/repositories");
    selectOptions();
    render();
  }, { label: register ? "Use existing account" : "Create account", action: () => account(!register) });
}

$("account").addEventListener("click", () => account());
$("filter").addEventListener("change", renderRuns);
$("repository").addEventListener("change", async (event) => {
  state.repository = event.target.value;
  state.runs = [];
  state.deployments = [];
  state.lastSync = null;
  notice();
  render();
  try { await loadRepository(); } catch (error) { notice(error.message); }
});
$("connect").addEventListener("click", () => {
  formDialog("Add repository", [["GitHub owner/name or URL", "repository", "text", "off"]], async (values) => {
    const added = await api("/repositories", values);
    state.repos = await api("/repositories");
    state.repository = String(added.id);
    selectOptions();
    notice();
    await loadRepository();
  });
});
$("sync").addEventListener("click", async () => {
  const repo = state.repository;
  $("sync").disabled = true;
  notice("Syncing workflows and deployments…");
  try {
    const count = await api("/repositories/" + repo + "/sync", undefined, "POST");
    if (state.repository !== repo) return;
    await loadRepository();
    notice("Synced " + count.runs + " workflow runs and " + count.deployments + " deployments.");
  } catch (error) {
    if (state.repository === repo) notice(error.message);
  } finally {
    $("sync").disabled = false;
  }
});

selectOptions();
loadRepository();
api("/auth/me").then(async (user) => {
  state.user = user;
  state.repos = await api("/repositories");
  selectOptions();
  render();
}).catch((error) => { if (error.status !== 401) notice(error.message); });
