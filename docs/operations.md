# Operator guide

## Individual test results

Run pytest with `--junitxml=reports/junit.xml` and upload that file using the artifact name `devpulse-junit-${{ github.run_attempt }}`. Copy the upload step from the delivery workflow, including its failure condition. Open a run and select **View individual test results**. Reports are read on demand while the GitHub artifact is retained. Older runs without the artifact still show job steps. The limit is 2 MiB and 5000 test cases per report.

## Automatic refresh

An open, visible dashboard checks GitHub when its last sync is five minutes old, including for public repositories where the viewer cannot install hooks. A newly connected repository starts syncing on the next dashboard refresh. GitHub failures back off for five minutes. Signed events can arrive between those checks, including while the browser is closed.

Select a connected public repository. Open **Account → Set up repository webhook**, generate its secret and copy the URL and secret into GitHub repository Settings → Webhooks. Choose application/json, Workflow runs, and Deployment statuses. GitHub must show a successful delivery. The visible dashboard checks saved events every 15 seconds. Use Sync GitHub for history, private repositories and missed deliveries. A scoped hook belongs to just one DevPulse connection.

## Private access

Register a GitHub App with read-only Metadata, Actions and Deployments permissions. Install it on the selected repositories. Set its callback to the HTTPS service origin plus `/api/auth/github/callback`. Provide `DEVPULSE_GITHUB_CLIENT_ID`, `DEVPULSE_GITHUB_CLIENT_SECRET` and the full `DEVPULSE_GITHUB_CALLBACK_URL` through service settings. Sign in to DevPulse, select **Account → Connect GitHub for private repositories**, authorize, then add the repository. Private dashboard reads recheck access with GitHub. The shared public-repository token cannot authorize a private connection.

The single-worker service stores PKCE challenges and user tokens in memory. Reauthorize after a restart, expiry or sign-out. Multiple workers would require a shared encrypted grant store. GitHub's installation and user access rules apply.

## PostgreSQL backups

On a trusted backup host install matching PostgreSQL client tools. Supply PGHOST, PGUSER, PGDATABASE and PGPASSWORD via the host's secret manager and require TLS for a remote connection. Run `bash scripts/backup.sh /private/backup-directory`. The script verifies the archive index and publishes the completed file with restrictive permissions. Store dumps on encrypted storage outside the web service with restricted access. They contain account and webhook data.

Schedule that command with your backup host scheduler after provisioning the destination. Restore into a new, empty database with `pg_restore --exit-on-error --single-transaction --no-owner --no-acl -d NEW_DATABASE FILE.dump`. Check accounts, workflow counts and health there before switching the service. CI rehearses a backup and restore on its disposable PostgreSQL instance. Backups do not extend the Render database lifetime.
