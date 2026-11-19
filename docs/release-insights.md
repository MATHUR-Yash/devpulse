# Investigating delivery health

The three buttons above Overview open account-scoped insights.

* **Repository portfolio** lists all repositories connected to your account with up to 100 saved runs, failure counts, latest deployment and last sync. Open a repository to load its dashboard.
* **Check release readiness** reads the live default-branch head and compares saved workflow results, available JUnit reports and the latest production deployment. Missing or stale evidence needs attention. The check covers synced runs and cannot prove that every required workflow has been configured. The deployment environment must be named production.
* **Analyze test stability** examines up to five completed attempts of one workflow and branch. Available reports are saved in the database. Mixed outcomes on the same commit provide a stronger flaky-test signal. Differences across commits may reflect code changes. Missing artifacts and duplicate test identities are excluded from the signal.
* Open a failed workflow and select **Compare with last successful run**. The baseline is an earlier saved successful attempt with the same workflow name and branch. The view lists failed steps and links to the commit comparison. GitHub's job order determines the first reported failure, which may differ from chronological order across parallel jobs.

These views require connected repositories. Demo mode explains how to connect real data. Insights do not run or deploy code.
