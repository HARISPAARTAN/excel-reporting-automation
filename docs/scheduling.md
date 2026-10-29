# Scheduling the weekly report

`build-report run --period last` builds the report for the ISO week before the current one. `last` is computed in UTC, so a run on Monday morning in Dublin always picks the week that ended on Sunday. Three ways to run it every Monday are described here: GitHub Actions (what the demo uses), Windows Task Scheduler and cron.

## GitHub Actions (the demo)

`.github/workflows/weekly-report.yml` runs every Monday at 06:00 UTC (`cron: "0 6 * * 1"`) and on demand (`workflow_dispatch` with an optional `period`). It generates eight weeks of invented branch files with the `demo` deviations, builds the report with `--notify dry-run`, keeps the outputs as the `weekly-report` artifact for 90 days, commits them to `web/latest/` as `github-actions[bot]` with `[skip ci]`, and then calls `pages.yml`, which renders the sheet previews with LibreOffice and deploys the site.

GitHub starts scheduled runs on the latest commit of the default branch, in UTC, and may start them late when load is high. In a public repository the schedule is switched off after 60 days without repository activity; `docs/handover.md` shows how to switch it on again.

## Windows Task Scheduler

The task definition is `docs/scheduling/build-report-weekly.xml`: every Monday at 07:00 local time, started late when the computer was off (`StartWhenAvailable`), only with a network, never twice at once, stopped after 30 minutes. It runs as the signed-in user (`InteractiveToken`), so Task Scheduler stores no password. The action runs:

```text
%USERPROFILE%\.local\bin\uv.exe run build-report --log-file D:\Cedarline\Reports\build-report.log run --period last --input D:\Cedarline\Incoming --out D:\Cedarline\Reports --notify smtp
```

in the working directory `D:\Cedarline\build-report` (a checkout of this repository with `uv sync` done once). Change the three folders in the XML if your paths differ.

Register it from the repository folder in PowerShell:

```powershell
Register-ScheduledTask -TaskPath '\Cedarline\' -TaskName 'Weekly report' -Xml (Get-Content -Raw docs\scheduling\build-report-weekly.xml)
```

Check it, run it once, and remove it again:

```powershell
Get-ScheduledTask -TaskPath '\Cedarline\' -TaskName 'Weekly report' | Select-Object -ExpandProperty Triggers
Start-ScheduledTask -TaskPath '\Cedarline\' -TaskName 'Weekly report'
Get-ScheduledTaskInfo -TaskPath '\Cedarline\' -TaskName 'Weekly report'
Unregister-ScheduledTask -TaskPath '\Cedarline\' -TaskName 'Weekly report' -Confirm:$false
```

`Get-ScheduledTaskInfo` shows `LastTaskResult`, which is the exit code of `build-report` (0 built, 3 blocked, 4 report built but sending failed, 5 report built with excluded files; see `docs/usage.md`).

### SMTP settings on Windows

`--notify smtp` reads its settings only from environment variables. Set them once as user variables (they apply to new processes, including the scheduled task):

```powershell
setx BUILD_REPORT_SMTP_HOST smtp.cedarline.example
setx BUILD_REPORT_SMTP_PORT 587
setx BUILD_REPORT_SMTP_USER reporting@cedarline.example
setx BUILD_REPORT_SMTP_PASSWORD "<the password>"
```

`setx` stores the values in plain text in the user profile (registry key `HKCU\Environment`), readable by anyone who can sign in as that user. Use a send-only SMTP credential that can do nothing but send from `reporting@cedarline.example`, and change it when people with access to the account change.

## cron on a Linux server

For a server whose clock runs on Dublin time, with the `BUILD_REPORT_SMTP_*` variables in `/etc/cedarline/build-report.env` (mode 600, owned by the user that runs the job):

```text
0 7 * * 1  cd /opt/cedarline/build-report && set -a && . /etc/cedarline/build-report.env && set +a && /usr/local/bin/uv run build-report --log-file /var/log/cedarline/build-report.log run --period last --input /srv/cedarline/incoming --out /srv/cedarline/reports --notify smtp
```

The environment file holds one `NAME=value` per line, for example `BUILD_REPORT_SMTP_HOST=smtp.cedarline.example`. Without `BUILD_REPORT_SMTP_HOST`, `--notify smtp` stops with exit code 2 before anything is written.

## What every scheduled run leaves behind

In the output folder: `Cedarline_Weekly_Report_<period>.xlsx`, `.eml` (the message as sent) and `.manifest.json` (always, also when blocked). The log file grows by a few lines per run; findings appear there as `WARNING` or `ERROR` lines and on the sheet Run info.
