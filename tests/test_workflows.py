import re
from pathlib import Path
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SETUP_UV = "astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2"
PINS = {
    "actions/checkout@v7",
    "actions/upload-artifact@v7",
    "actions/upload-pages-artifact@v5",
    "actions/deploy-pages@v5",
    "actions/configure-pages@v6",
    SETUP_UV,
    "./.github/workflows/pages.yml",
}
APT = "sudo apt-get install -y --no-install-recommends libreoffice-calc-nogui fonts-crosextra-carlito poppler-utils"
TASK = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"


def load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def triggers(data):
    return data.get("on", data.get(True))  # PyYAML reads the key `on` as True


def steps(job):
    return job.get("steps", [])


def runs(job):
    return [step["run"] for step in steps(job) if "run" in step]


def test_every_action_is_pinned():
    assert {p.name for p in WORKFLOWS.glob("*.yml")} == {"ci.yml", "pages.yml", "weekly-report.yml"}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for used in re.findall(r"uses:\s*([^\s,}]+)", text):
            assert used in PINS, (path.name, used)
    assert "setup-uv@v" not in "".join(path.read_text(encoding="utf-8") for path in WORKFLOWS.glob("*.yml"))


def test_uv_sync_is_locked_everywhere():
    assert {p.name for p in WORKFLOWS.glob("*.yml")} == {"ci.yml", "pages.yml", "weekly-report.yml"}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "uv sync" in line:
                assert "uv sync --locked" in line, (path.name, line)


def test_ci_triggers_and_permissions():
    data = load("ci.yml")
    assert set(triggers(data)) == {"push", "pull_request"}
    assert triggers(data)["push"] == {"branches": ["main"]}
    assert data["permissions"] == {"contents": "read"}
    assert set(data["jobs"]) == {"lint", "test", "render", "scheduler", "checks"}


def test_ci_lint_and_test_matrix():
    jobs = load("ci.yml")["jobs"]
    assert runs(jobs["lint"]) == [
        "uv sync --locked",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy",
    ]
    matrix = jobs["test"]["strategy"]["matrix"]
    assert matrix == {"os": ["ubuntu-24.04", "windows-2025"], "python": ["3.11", "3.12", "3.13"]}
    assert jobs["test"]["strategy"]["fail-fast"] is False
    assert jobs["test"]["runs-on"] == "${{ matrix.os }}"
    assert runs(jobs["test"]) == ["uv sync --locked", "uv run pytest -q"]


def test_ci_render_job():
    job = load("ci.yml")["jobs"]["render"]
    assert job["runs-on"] == "ubuntu-24.04"
    commands = "\n".join(runs(job))
    assert APT in commands
    build = next(step for step in steps(job) if "build-report run" in step.get("run", ""))
    assert build["env"] == {"SOURCE_DATE_EPOCH": "1758520800"}
    assert "--period 2025-W38 --input data/incoming --out build/demo --notify dry-run" in build["run"]
    assert (
        "uv run python tools/render_sheets.py build/demo/Cedarline_Weekly_Report_2025-W38.xlsx --out build/render --check-recalc"
        in commands
    )
    assert "uv run pytest -m render -q" in commands
    upload = next(step for step in steps(job) if step.get("uses") == "actions/upload-artifact@v7")
    assert upload["with"]["name"] == "demo-render" and upload["with"]["retention-days"] == 30
    assert upload["with"]["path"].split() == ["build/demo", "build/render"]


def test_ci_scheduler_and_checks_jobs():
    jobs = load("ci.yml")["jobs"]
    assert jobs["scheduler"]["runs-on"] == "windows-2025"
    script = "\n".join(runs(jobs["scheduler"]))
    assert (
        "Register-ScheduledTask -TaskPath '\\Cedarline\\' -TaskName 'Weekly report' "
        "-Xml (Get-Content -Raw docs\\scheduling\\build-report-weekly.xml)" in script
    )
    assert "Get-ScheduledTask" in script and "Unregister-ScheduledTask" in script
    kit = next(step for step in steps(jobs["checks"]) if step.get("with", {}).get("path") == "_kit")
    want = {"repository": "HARISPAARTAN/portfolio-kit", "ref": "refs/tags/v0.1.0", "path": "_kit"}
    assert kit["with"] == want
    assert runs(jobs["checks"]) == [
        "uv sync --locked",
        "uv run python tools/check_fixtures.py",
        "uv run python tools/sync_kit.py --check --kit _kit",
        "uv run python tools/checks/scrub.py",
        "uv run python tools/checks/page_weight.py web",
        "node tools/checks/contrast.mjs",
    ]


def test_weekly_report_workflow():
    data = load("weekly-report.yml")
    on = triggers(data)
    assert on["schedule"] == [{"cron": "0 6 * * 1"}]
    assert on["workflow_dispatch"]["inputs"]["period"]["default"] == "last"
    assert data["permissions"] == {"contents": "read"}
    assert data["concurrency"] == {"group": "weekly-report", "cancel-in-progress": False}
    report = data["jobs"]["report"]
    assert report["permissions"] == {"contents": "write"}
    assert report["env"] == {"PERIOD": "${{ inputs.period || 'last' }}"}
    assert runs(report)[:3] == [
        "uv sync --locked",
        'uv run build-report generate-fixtures --weeks 8 --end-week "$PERIOD" --deviations demo --out build/incoming',
        'uv run build-report run --period "$PERIOD" --input build/incoming --out build/report --notify dry-run',
    ]
    upload = next(step for step in steps(report) if step.get("uses") == "actions/upload-artifact@v7")
    assert upload["with"] == {"name": "weekly-report", "path": "build/report", "retention-days": 90}
    pages = data["jobs"]["pages"]
    assert pages["uses"] == "./.github/workflows/pages.yml" and pages["needs"] == "report"
    assert pages["with"] == {"ref": "${{ needs.report.outputs.sha }}"}
    assert pages["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}


def test_weekly_commit_step():
    report = load("weekly-report.yml")["jobs"]["report"]
    commit = next(step for step in steps(report) if step.get("id") == "commit")["run"]
    assert 'git config user.name "github-actions[bot]"' in commit
    assert 'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"' in commit
    assert "git add -A web/latest" in commit
    assert 'git commit -m "chore(report): weekly report ${DONE} [skip ci]"' in commit
    assert "git pull --rebase origin main" in commit
    assert "git push origin HEAD:main" in commit
    assert "git pull --rebase origin main && git push origin HEAD:main" not in commit
    assert 'echo "sha=$(git rev-parse HEAD)" >> "$GITHUB_OUTPUT"' in commit


def test_pages_workflow():
    data = load("pages.yml")
    on = triggers(data)
    assert on["push"]["branches"] == ["main"]
    assert on["push"]["paths"] == ["web/**", "tools/render_sheets.py", ".github/workflows/pages.yml"]
    assert "workflow_dispatch" in on
    assert on["workflow_call"]["inputs"]["ref"] == {"type": "string", "required": False, "default": ""}
    assert data["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}
    assert "concurrency" not in data
    job = data["jobs"]["deploy"]
    assert job["concurrency"] == {"group": "pages", "cancel-in-progress": False}
    assert job["environment"]["name"] == "github-pages"
    uses = [step.get("uses") for step in steps(job) if "uses" in step]
    assert uses == [
        "actions/checkout@v7",
        SETUP_UV,
        "actions/configure-pages@v6",
        "actions/upload-pages-artifact@v5",
        "actions/deploy-pages@v5",
    ]
    assert steps(job)[0]["with"] == {"ref": "${{ inputs.ref || github.sha }}"}
    upload = next(step for step in steps(job) if step.get("uses") == "actions/upload-pages-artifact@v5")
    assert upload["with"] == {"path": "web"}


def test_pages_render_steps_are_skipped_without_a_workbook():
    job = load("pages.yml")["jobs"]["deploy"]
    guarded = [step for step in steps(job) if "if" in step]
    assert len(guarded) == 2
    for step in guarded:
        assert step["if"] == "hashFiles('web/latest/Cedarline_Weekly_Report_*.xlsx') != ''"
    commands = [step["run"] for step in guarded]
    assert APT in commands[0]
    assert commands[1] == (
        "uv run python tools/render_sheets.py web/latest/Cedarline_Weekly_Report_*.xlsx --out web/latest/preview"
    )


def test_long_jobs_have_timeouts():
    assert load("ci.yml")["jobs"]["render"]["timeout-minutes"] == 30
    assert load("ci.yml")["jobs"]["scheduler"]["timeout-minutes"] == 15
    assert load("pages.yml")["jobs"]["deploy"]["timeout-minutes"] == 30


def test_dependabot():
    data = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    assert data["version"] == 2
    updates = [(u["package-ecosystem"], u["directory"], u["schedule"]["interval"]) for u in data["updates"]]
    assert updates == [("github-actions", "/", "weekly"), ("uv", "/", "weekly")]


def test_task_scheduler_xml():
    root = ElementTree.parse(ROOT / "docs" / "scheduling" / "build-report-weekly.xml").getroot()
    trigger = root.find(f"{TASK}Triggers/{TASK}CalendarTrigger")
    assert trigger.findtext(f"{TASK}StartBoundary") == "2025-09-22T07:00:00"
    assert trigger.findtext(f"{TASK}ScheduleByWeek/{TASK}WeeksInterval") == "1"
    assert trigger.find(f"{TASK}ScheduleByWeek/{TASK}DaysOfWeek/{TASK}Monday") is not None
    assert root.findtext(f"{TASK}Principals/{TASK}Principal/{TASK}LogonType") == "InteractiveToken"
    settings = root.find(f"{TASK}Settings")
    assert settings.findtext(f"{TASK}StartWhenAvailable") == "true"
    assert settings.findtext(f"{TASK}ExecutionTimeLimit") == "PT30M"
    assert settings.findtext(f"{TASK}MultipleInstancesPolicy") == "IgnoreNew"
    action = root.find(f"{TASK}Actions/{TASK}Exec")
    assert action.findtext(f"{TASK}Command") == "%USERPROFILE%\\.local\\bin\\uv.exe"
    assert action.findtext(f"{TASK}Arguments") == (
        "run build-report --log-file D:\\Cedarline\\Reports\\build-report.log run --period last "
        "--input D:\\Cedarline\\Incoming --out D:\\Cedarline\\Reports --notify smtp"
    )
    assert action.findtext(f"{TASK}WorkingDirectory") == "D:\\Cedarline\\build-report"


def test_scheduling_doc_has_the_commands():
    text = (ROOT / "docs" / "scheduling.md").read_text(encoding="utf-8")
    assert (
        "Register-ScheduledTask -TaskPath '\\Cedarline\\' -TaskName 'Weekly report' "
        "-Xml (Get-Content -Raw docs\\scheduling\\build-report-weekly.xml)" in text
    )
    assert (
        "0 7 * * 1  cd /opt/cedarline/build-report && set -a && . /etc/cedarline/build-report.env && set +a && "
        "/usr/local/bin/uv run build-report --log-file /var/log/cedarline/build-report.log run --period last "
        "--input /srv/cedarline/incoming --out /srv/cedarline/reports --notify smtp" in text
    )
    assert "plain text" in text and "send-only" in text
