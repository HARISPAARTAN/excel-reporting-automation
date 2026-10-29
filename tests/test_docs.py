import re
from pathlib import Path
from xml.etree import ElementTree

from conftest import ROOT

NOTE = "Rebuilt from memory as a demo. The original client's name and data are not used."
NOTE_DE = (
    "Aus dem Gedächtnis als Demo nachgebaut. "
    "Name und Daten des ursprünglichen Kundenunternehmens werden nicht verwendet."
)
SITE = "https://harispaartan.github.io/excel-reporting-automation/"
SECTIONS_EN = [
    "Status",
    "Client brief",
    "Live demo",
    "What it does",
    "How it works",
    "Data model",
    "Getting started",
    "Project layout",
    "Decisions",
    "Compared with the original delivery",
    "Licence and data note",
]
SECTIONS_DE = [
    "Status",
    "Auftrag",
    "Live-Demo",
    "Funktionen",
    "So funktioniert es",
    "Datenmodell",
    "Erste Schritte",
    "Projektstruktur",
    "Entscheidungen",
    "Im Vergleich zur ursprünglichen Lieferung",
    "Lizenz und Datenhinweis",
]
MASCULINE = re.compile(
    r"\b(Mitarbeiter|Filialleiter|Benutzer|Nutzer|Kunde|Kunden|Kundin|Administrator|Entwickler|Prüfer|Leser|Empfänger)\b"
)
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
BENEFIT = [
    re.compile(r"\b(save[sd]?|saving)\b[^.\n]{0,40}\b(hours?|minutes?|days?|time)\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:[.,]\d+)?\s?%\s+(faster|less|fewer|more|schneller|weniger)\b", re.IGNORECASE),
    re.compile(r"\b(time-saving|zeitersparnis|zeit\s?gespart|stunden\s+gespart)\b", re.IGNORECASE),
]
ENV = (
    "SOURCE_DATE_EPOCH",
    "BUILD_REPORT_SMTP_HOST",
    "BUILD_REPORT_SMTP_PORT",
    "BUILD_REPORT_SMTP_USER",
    "BUILD_REPORT_SMTP_PASSWORD",
    "BUILD_REPORT_SMTP_SECURITY",
    "GITHUB_SERVER_URL",
    "GITHUB_REPOSITORY",
    "GITHUB_RUN_ID",
)
ADRS = (
    "0001-values-with-formula-totals.md",
    "0002-reproducible-workbooks.md",
    "0003-cover-week-wins.md",
    "0004-weekly-commit-and-pages-render.md",
)
BOXES = (
    "Generator",
    "Input folder",
    "Discover",
    "Template reader",
    "Resolver",
    "Long records",
    "Metrics engine",
    "Workbook writer",
    "Reproducible save",
    "Manifest",
    "Notifier",
    "Output folder",
    "weekly-report.yml",
    "build-report run",
    "web/latest/",
    "pages.yml",
    "Pages site",
)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def headings(text: str) -> list[str]:
    return re.findall(r"^## (.+)$", text, flags=re.MULTILINE)


def doc_files() -> list[Path]:
    return [
        ROOT / "README.md",
        ROOT / "README.de.md",
        ROOT / "CHANGELOG.md",
        *sorted((ROOT / "docs").rglob("*.md")),
    ]


def test_readme_sections_follow_the_umbrella_order():
    assert headings(read("README.md")) == SECTIONS_EN


def test_german_readme_mirrors_the_sections():
    assert headings(read("README.de.md")) == SECTIONS_DE


def test_readmes_carry_the_notes_and_link_each_other():
    english, german = read("README.md"), read("README.de.md")
    assert english.count(NOTE) == 2 and "[Deutsch](README.de.md)" in english
    assert german.count(NOTE_DE) == 2 and NOTE in german and "[English](README.md)" in german
    assert SITE in english and SITE in german


def test_german_readme_is_gender_neutral():
    assert MASCULINE.findall(read("README.de.md")) == []


def test_relative_links_resolve():
    broken = []
    for path in doc_files():
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            if re.match(r"(https?:|mailto:|#)", target):
                continue
            if not (path.parent / target.split("#")[0]).exists():
                broken.append(f"{path.relative_to(ROOT).as_posix()}: {target}")
    assert broken == []


def test_usage_lists_every_command_and_option():
    from buildreport.cli import cli

    usage = read("docs/usage.md")
    options = [opt for param in cli.params for opt in param.opts if opt.startswith("--")]
    for name, command in cli.commands.items():
        assert f"### `{name}`" in usage, name
        options += [opt for param in command.params for opt in param.opts if opt.startswith("--")]
    missing = sorted({opt for opt in options if f"`{opt}" not in usage})
    assert missing == []


def test_usage_lists_every_finding_exit_code_and_variable():
    from buildreport.findings import ERROR_CODES, WARNING_CODES

    usage = read("docs/usage.md")
    assert [code for code in sorted(ERROR_CODES | WARNING_CODES) if f"`{code}`" not in usage] == []
    assert [code for code in range(6) if f"| {code} |" not in usage] == []
    assert [name for name in ENV if f"`{name}`" not in usage] == []


def test_usage_shows_the_real_validate_output(run_cli, demo_dir):
    result = run_cli(
        ["validate", "--input", demo_dir, "--period", "2025-W38", "--config", ROOT / "report.yaml"]
    )
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert len(lines) == 6
    usage = read("docs/usage.md")
    assert [line for line in lines if line not in usage] == []


def test_data_model_lists_every_metric_branch_group_and_role(cfg):
    text = read("docs/data-model.md")
    for key, spec in cfg.model.metrics.items():
        assert f"`{key}`" in text and f"`{spec.expr}`" in text, key
    for branch in cfg.branches:
        assert f"| {branch.code} | {branch.name} | {branch.format} |" in text
    for name in (*cfg.product_groups, *cfg.roles):
        assert f"| {name} |" in text, name


def test_adrs_have_status_context_decision_and_consequences():
    folder = ROOT / "docs" / "adr"
    assert sorted(path.name for path in folder.glob("*.md")) == sorted(ADRS)
    for name in ADRS:
        text = (folder / name).read_text(encoding="utf-8")
        assert text.startswith(f"# ADR {name[:4]}: "), name
        for heading in (
            "## Status",
            "## Context",
            "## Decision",
            "## Consequences",
            "## Alternatives considered",
        ):
            assert heading in text, (name, heading)
        assert "Accepted (2026-10-29)" in text, name


def test_architecture_svg_is_well_formed_and_matches_the_page():
    ns = "{http://www.w3.org/2000/svg}"
    root = ElementTree.parse(ROOT / "docs" / "architecture.svg").getroot()
    assert root.tag == f"{ns}svg"
    assert root.findtext(f"{ns}title") == "How build-report works"
    labels = [node.text for node in root.iter(f"{ns}text")]
    page = read("web/index.html")
    assert [box for box in BOXES if box not in labels] == []
    assert [box for box in BOXES if f">{box}</text>" not in page] == []


def test_changelog_header():
    pattern = r"^## v0\.1\.0 \((unreleased|\d{4}-\d{2}-\d{2})\)$"
    assert re.search(pattern, read("CHANGELOG.md"), flags=re.MULTILINE)


def test_readmes_make_no_benefit_claims():
    for name in ("README.md", "README.de.md"):
        text = read(name)
        assert [pattern.pattern for pattern in BENEFIT if pattern.search(text)] == [], name
