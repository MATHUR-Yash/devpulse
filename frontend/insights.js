/* Account-scoped investigation views for the delivery dashboard. */
function investigationPanel(title) {
  const shell = dialog(title);
  const content = element("section");
  shell.append(content);
  return content;
}

function insightDialog(title) {
  const content = investigationPanel(title);
  if (state.repository === "demo" || !state.user) {
    content.append(element("p", "Sign in and select a connected repository to analyze its real workflow and deployment data.", "quiet"));
    return null;
  }
  return content;
}

function investigationError(content, error, retry) {
  content.replaceChildren(element("p", error.message, "form-error"), button("Retry", retry, "secondary"));
}

async function compareFailure(run) {
  const content = insightDialog("Failure comparison");
  if (!content) return;
  content.append(element("p", "Finding the previous successful run on this branch…", "quiet"));
  try {
    const data = await api("/repositories/" + state.repository + "/runs/" + run.id + "/comparison");
    content.replaceChildren();
    const grid = element("div", "", "insight-grid");
    for (const [label, item] of [["Failed run", data.failed], ["Previous success", data.baseline]]) {
      const card = element("section", "", "insight-card");
      card.append(element("h3", label));
      if (item) card.append(element("p", item.name + " · " + item.branch), element("code", item.sha),
        element("p", "Attempt " + item.attempt), badge(item.conclusion));
      else card.append(element("p", "No earlier success for this workflow and branch has been synced."));
      grid.append(card);
    }
    content.append(grid, element("h3", "Failed steps"));
    if (!data.failed_steps.length) content.append(element("p", "GitHub returned no failed steps. The job may have failed before steps began.", "quiet"));
    for (const [i, item] of data.failed_steps.entries()) content.append(element("p", (i === 0 ? "First reported failure · " : "") + item.job + " → " + item.step));
    if (data.baseline_jobs.length) content.append(element("p", "Baseline jobs · " + data.baseline_jobs.map((job) => job.name + " (" + job.conclusion + ")").join(", "), "quiet"));
    if (data.compare_url) {
      const link = element("a", data.failed.sha === data.baseline.sha ? "Both attempts used the same commit. View comparison ↗" : "Review code changes on GitHub ↗");
      Object.assign(link, { href: data.compare_url, target: "_blank", rel: "noopener" });
      content.append(link);
    }
  } catch (error) { investigationError(content, error, () => compareFailure(run)); }
}

async function showPortfolio() {
  const content = investigationPanel("Repository portfolio");
  if (!state.user) { content.append(element("p", "Sign in to see your connected repositories.", "quiet")); return; }
  content.append(element("p", "Loading saved repository summaries…", "quiet"));
  try {
    const data = await api("/portfolio");
    content.replaceChildren(element("p", "Summaries cover up to 100 saved runs per repository. Open a repository to sync newer activity.", "quiet"));
    if (!data.repositories.length) content.append(element("p", "Add a repository to start your portfolio."));
    for (const repo of data.repositories) {
      const card = element("section", "", "insight-card");
      card.append(element("h3", repo.name));
      if (!repo.accessible) card.append(element("p", "Reconnect GitHub to view this private repository."));
      else {
        card.append(element("p", repo.run_count + " saved runs · " + repo.failed + " failed"));
        if (repo.latest) card.append(badge(repo.latest.conclusion || repo.latest.status, outcome(repo.latest)), element("p", repo.latest.name));
        card.append(element("p", repo.deployment ? "Latest deployment · " + repo.deployment.environment + " · " + repo.deployment.status : "No deployments recorded.", "quiet"));
        card.append(element("p", repo.last_sync ? "Last sync · " + timestamp(repo.last_sync.at) + " · " + repo.last_sync.status : "Never synced", "quiet"));
        card.append(button("Open repository", async () => {
          state.repository = String(repo.id);
          selectOptions();
          $("dialog").close();
          try { await loadRepository(); } catch (error) { notice(error.message); }
        }, "secondary"));
      }
      content.append(card);
    }
  } catch (error) { investigationError(content, error, showPortfolio); }
}

async function showReadiness() {
  const content = insightDialog("Release readiness");
  if (!content) return;
  content.append(element("p", "Checking GitHub head, test reports and production deployment…", "quiet"));
  try {
    const data = await api("/repositories/" + state.repository + "/readiness");
    content.replaceChildren(element("h3", data.ready ? "Release evidence complete" : "Release evidence needs attention"),
      element("p", data.branch + " · " + data.sha.slice(0, 10), "quiet"));
    for (const check of data.checks) {
      const card = element("section", "", "insight-card");
      card.append(element("h3", check.name), badge(check.passed ? "success" : "pending"), element("p", check.detail, "quiet"));
      content.append(card);
    }
    content.append(element("p", data.scope, "quiet"), element("p", "Checked " + timestamp(data.checked_at), "quiet"));
    if (data.missing_reports.length) content.append(element("p", data.missing_reports.length + " run(s) had unavailable JUnit reports.", "quiet"));
  } catch (error) { investigationError(content, error, showReadiness); }
}

function chooseTestHistory() {
  const content = insightDialog("Test stability");
  if (!content) return;
  content.append(element("p", "Choose a completed run. Examine up to five saved attempts of the same workflow and branch.", "quiet"));
  const runs = state.runs.filter((run) => run.status === "completed");
  if (!runs.length) { content.append(element("p", "Sync completed workflows first.")); return; }
  const select = element("select");
  select.setAttribute("aria-label", "Test history starting run");
  for (const run of runs) select.add(new Option(run.name + " · " + run.branch + " · " + run.sha.slice(0, 7) + " · attempt " + run.attempt, run.id));
  const results = element("section");
  content.append(select, button("Analyze reports", async (event) => {
    const trigger = event.currentTarget;
    trigger.disabled = true;
    results.replaceChildren(element("p", "Reading up to five reports. This can take a minute…", "quiet"));
    try {
      const data = await api("/repositories/" + state.repository + "/runs/" + select.value + "/test-history");
      results.replaceChildren(element("p", data.reports_available + " reports available from " + data.examined + " attempts."));
      results.append(element("p", "Mixed outcomes suggest investigation. Code changes can also explain differences between commits.", "quiet"));
      if (!data.candidates.length) results.append(element("p", "No mixed pass/fail results found in the available reports."));
      for (const candidate of data.candidates) {
        const card = element("section", "", "insight-card");
        card.append(element("h3", candidate.name), element("p", candidate.class, "quiet"),
          element("p", candidate.same_commit ? "Flaky-test signal · different outcomes on the same commit" : "Changed outcome · different commits"));
        const history = element("div", "", "history-list");
        for (const item of candidate.history) history.append(element("span", item.sha.slice(0, 7) + " #" + item.attempt + " · " + item.status));
        card.append(history);
        results.append(card);
      }
      for (const missing of data.missing) results.append(element("p", "Run " + missing.run_id + " · " + missing.reason, "quiet"));
    } catch (error) { results.replaceChildren(element("p", error.message, "form-error")); }
    finally { trigger.disabled = false; }
  }, "primary"), results);
}
