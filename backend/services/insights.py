"""Small, evidence-based summaries of saved CI data."""

from collections import Counter

FAILURES = {"failure", "timed_out", "startup_failure", "action_required", "error"}


def test_signals(reports):
    grouped = {}
    for run, cases in reports:
        # Duplicate names within one report are ambiguous, so exclude them.
        identities = Counter((case["class"], case["name"]) for case in cases)
        for case in cases:
            identity = (case["class"], case["name"])
            if identities[identity] > 1 or case["status"] == "skipped":
                continue
            grouped.setdefault(identity, []).append({
                "run_id": run.id, "sha": run.commit_sha, "attempt": run.run_attempt,
                "status": case["status"],
            })
    signals = []
    for (classname, name), history in grouped.items():
        passed = {item["sha"] for item in history if item["status"] == "passed"}
        failed = {item["sha"] for item in history if item["status"] in {"failure", "error"}}
        if passed and failed:
            signals.append({"class": classname, "name": name, "history": history,
                            "same_commit": bool(passed & failed)})
    return signals


def readiness(runs, reports, deployments, head):
    latest = {}
    for run in runs:
        if run.commit_sha == head:
            latest.setdefault(run.github_run_id, run)
    current = list(latest.values())
    workflows_ok = bool(current) and all(r.status == "completed" and r.conclusion == "success" for r in current)
    tests_ok = bool(reports) and all(report and all(c["status"] == "passed" for c in report) for report in reports)
    deployment = next((d for d in deployments if d.environment.lower() == "production"), None)
    deployed = bool(deployment and deployment.status == "success" and deployment.commit_sha == head)
    checks = [
        {"name": "Default-branch workflows", "passed": workflows_ok,
         "detail": f"{len(current)} saved runs for the current head. All must have succeeded."},
        {"name": "Individual test reports", "passed": tests_ok,
         "detail": "At least one nonempty JUnit report is required. Every reported case must pass."},
        {"name": "Production deployment", "passed": deployed,
         "detail": "The latest production record must be successful and match the current head."},
    ]
    return {"ready": all(c["passed"] for c in checks), "sha": head, "checks": checks}
