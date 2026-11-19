# DevPulse UX coursework

Import [the seven editable SVG screen groups](devpulse-frames.svg) into Figma. Ungroup the sheet, frame each screen, and connect Sign in → Overview → Repositories → Workflow runs → Failure details. Link Overview to Deployments and Analytics. Values in these wireframes are illustrative. At 390 px use one column, keep status text alongside color, and verify that dialogs return focus to their trigger.

## Participant worksheet

Use one anonymous participant ID per session. Ask permission before recording. Give the participant the goal and record where they hesitate before offering help.

| Participant ID | Task and viewport | Completed unaided? | Time | Wrong turns or quote | Design change to test |
| --- | --- | --- | --- | --- | --- |
| | Find the failed test and explain it | | | | |
| | Identify the deployed revision | | | | |
| | Connect a second repository on mobile | | | | |

After each session ask which status was hardest to interpret. Compare repeated observations across participants and record the change and retest outcome.

## Personas to validate

| Persona hypothesis | Goal | Friction to investigate |
| --- | --- | --- |
| Developer maintaining several repositories | Find the failed workflow and open the relevant log | Switching among repositories and reading several job logs |
| Release coordinator | Confirm what shipped and when | Difficulty comparing deployment outcomes across environments |

These are design hypotheses. Interviews and participant usability tests are pending.

## Prototype routes

The running dashboard is an interactive reference for the Figma prototype.

| Screen | Where to find it in DevPulse | Primary action |
| --- | --- | --- |
| Login | Sign in | Sign in or create an account |
| Main dashboard | Overview | Read status cards and recent alerts |
| Repository management | Repository selector and Add repository dialog | Connect a public repository and sync it |
| Pipeline monitoring | Workflows | Filter runs and open a job timeline |
| Build failure details | Inspect failure | Identify the failed step and open its GitHub log |
| Deployment history | Deployments | Check the environment, version, status, and time |
| Analytics dashboard | Analytics | Compare daily average run duration and pass rate |

## User journeys

1. A developer signs in, connects a repository, syncs it, filters to failed runs, and opens the failing step and its GitHub log.
2. A release coordinator selects a repository, checks the deployment-success notification, matches it to the deployment history, and checks analytics for slower runs.

## Usability test plan

Ask three or more participants to complete the two journeys with a test repository. Start with the demo workspace to verify that the prototype is navigable. Give participants a task outcome without naming the button they should use.

Record task completion, elapsed time, wrong turns, and comments. Ask participants to explain the difference between workflow status and deployment status and to locate the exact step that failed. Repeat the tasks at a mobile viewport and with keyboard navigation. Record observed results before drawing conclusions.
