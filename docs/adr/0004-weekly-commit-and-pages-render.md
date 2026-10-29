# ADR 0004: Weekly commit of the report, preview render at deployment

## Status

Accepted (2026-10-29)

## Context

The demo shows a report that is built every Monday without anyone starting it, and a page that shows the latest one with images of its sheets. The images need LibreOffice. Committing them every week would grow the repository by megabytes a year, and this repository keeps generated images out of the history. A push made with the workflow's `GITHUB_TOKEN` does not start other workflows, so the deployment cannot simply react to the weekly commit; a personal access token would avoid that but is a secret to keep and renew.

## Decision

`weekly-report.yml` builds the report, uploads it as an artifact (90 days), and commits only four files to `web/latest/` as `github-actions[bot]`, with `[skip ci]` in the message: the workbook, the `.eml`, the manifest `<stem>.manifest.json` and a copy of the manifest named `manifest.json`, which `publish_latest.py` writes for the page (for the demo week the workbook is about 130 KB, the `.eml` about 185 KB and each of the two manifest files about 35 KB). It then calls `pages.yml` as a reusable workflow (`workflow_call`) with the new commit. `pages.yml` checks out that commit, renders the previews with LibreOffice into `web/latest/preview/` inside the job, and deploys `web/` to GitHub Pages. Before the first weekly run there is no workbook, so the render steps are skipped and the page shows its empty state. The page reads only `latest/manifest.json`.

## Consequences

- The page always shows the latest report with previews that match it; the preview images exist only in the deployed site and in the CI artifact.
- No secret is needed; the weekly run uses `--notify dry-run` and publishes the `.eml` instead of sending it.
- A deployment takes a few minutes for the LibreOffice install and render.
- The history grows by the four committed files each week; `docs/handover.md` notes how to re-enable the schedule when GitHub disables it after 60 days without activity.

## Alternatives considered

- Committing the previews every week: rejected for history growth.
- A personal access token so the push starts `pages.yml`: rejected, because it is a long-lived secret.
- Rendering in `weekly-report.yml` and deploying from there: rejected, because pushes of `web/` by the owner would then deploy without previews; one deployment workflow serves both paths.
