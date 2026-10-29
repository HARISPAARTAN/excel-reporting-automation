import base64
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from email.message import EmailMessage
from html import unescape
from pathlib import Path

import pytest
from openpyxl import Workbook

from conftest import ROOT

needs_git_and_tar = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("tar") is None, reason="git and tar are needed"
)
CRON_LINE = (
    "0 7 * * 1  cd /opt/cedarline/build-report && set -a && . /etc/cedarline/build-report.env && set +a && "
    "/usr/local/bin/uv run build-report --log-file /var/log/cedarline/build-report.log run --period last "
    "--input /srv/cedarline/incoming --out /srv/cedarline/reports --notify smtp"
)
REGISTER = (
    "Register-ScheduledTask -TaskPath '\\Cedarline\\' -TaskName 'Weekly report' "
    "-Xml (Get-Content -Raw docs\\scheduling\\build-report-weekly.xml)"
)
FOOTER = "Rebuilt from memory as a demo. The original client's name and data are not used."
SECTIONS = (
    "latest",
    "empty",
    "run-card",
    "kpis",
    "ranking",
    "findings",
    "previews",
    "how",
    "schedule",
    "local",
)
REPO_URL = "https://github.com/HARISPAARTAN/excel-reporting-automation"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(folder: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture()
def kit(tmp_path):
    """A throwaway kit clone: dist/ with three files and its MANIFEST.json, staged as a git tree (no commit)."""
    folder = tmp_path / "kit"
    files = {
        "tokens.css": b":root{--bg:#0B0F14}\n",
        "kit.js": b"export const answer = 42;\n",
        "fonts/a.woff2": bytes(range(16)),
    }
    for name, data in files.items():
        target = folder / "dist" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    entries = [
        {"file": name, "bytes": len(data), "sha256": sha(data)} for name, data in sorted(files.items())
    ]
    manifest = {"name": "portfolio-kit", "version": "test", "files": entries}
    (folder / "dist" / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (folder / ".gitattributes").write_text("* -text\n", encoding="utf-8")  # no line-ending conversion
    subprocess.run(["git", "init", "-q", str(folder)], check=True, capture_output=True)
    git(folder, "add", "-A")
    return {"path": folder, "tree": git(folder, "write-tree"), "files": files}


def args(kit, dest, *extra):
    return [*extra, "--kit", str(kit["path"]), "--tag", kit["tree"], "--dest", str(dest)]


@needs_git_and_tar
def test_sync_kit_copies_and_checks(tool, kit, tmp_path, capsys):
    sync = tool("sync_kit")
    dest = tmp_path / "web" / "kit"
    assert sync.main(args(kit, dest)) == 0
    assert (dest / "VERSION").read_bytes() == f"{kit['tree']}\n".encode()
    assert (dest / "fonts" / "a.woff2").read_bytes() == kit["files"]["fonts/a.woff2"]
    assert sync.main(args(kit, dest, "--check")) == 0
    capsys.readouterr()
    (dest / "kit.js").write_bytes(b"export const answer = 43;\n")
    (dest / "extra.css").write_bytes(b"body{}\n")
    assert sync.main(args(kit, dest, "--check")) == 1
    out = capsys.readouterr().out
    assert "changed: kit.js" in out and "not in MANIFEST.json: extra.css" in out


@needs_git_and_tar
def test_sync_kit_refuses_a_folder_that_is_not_a_kit_copy(tool, kit, tmp_path):
    dest = tmp_path / "web" / "kit"
    dest.mkdir(parents=True)
    (dest / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        tool("sync_kit").main(args(kit, dest))
    assert caught.value.code == 2
    assert (dest / "notes.txt").is_file()


@needs_git_and_tar
def test_sync_kit_rejects_a_kit_that_breaks_its_own_manifest(tool, kit, tmp_path):
    (kit["path"] / "dist" / "kit.js").write_bytes(b"tampered\n")
    git(kit["path"], "add", "-A")
    broken = dict(kit, tree=git(kit["path"], "write-tree"))
    with pytest.raises(SystemExit) as caught:
        tool("sync_kit").main(args(broken, tmp_path / "web" / "kit"))
    assert caught.value.code == 2
    assert not (tmp_path / "web" / "kit").exists()


def test_vendored_kit_matches_its_manifest(tool):
    sync = tool("sync_kit")
    vendored = ROOT / "web" / "kit"
    manifest = json.loads((vendored / "MANIFEST.json").read_text(encoding="utf-8"))
    files = sync.read_tree(vendored)
    assert sync.compare(manifest, files) == []
    assert (vendored / "VERSION").read_text(encoding="utf-8") == "v0.1.0\n"
    assert {"tokens.css", "base.css", "theme-boot.js", "kit.js", "fonts/fonts.css"} <= set(files)


def test_scrub_terms_are_hashes(tool):
    terms = tool("checks/scrub").TERMS
    assert len(terms) == 9
    assert all(len(term) == 64 and set(term) <= set("0123456789abcdef") for term in terms)


def test_scrub_finds_words_hyphenations_pairs_and_entities(tool):
    scrub = tool("checks/scrub")
    terms = {sha(b"pumpernickel"), sha(b"rye-sourdough"), sha(b"soda-bread")}
    lines = ["Fresh PUMPERNICKEL today", "rye sourdough and Rye-Sourdough", "soda_bread", "wholemeal only"]
    text = "\n".join([*lines, "rye&nbsp;sourdough"]) + "\n"
    assert scrub.find_hits(text, terms) == [1, 2, 3, 5]
    assert scrub.find_hits("sodabread", {sha(b"sodabread")}) == [1]
    assert scrub.find_hits("soda bread", {sha(b"sodabread")}) == [1]


def test_scrub_extra_patterns_report_line_numbers_only(tool, tmp_path, capsys):
    scrub = tool("checks/scrub")
    extra = tmp_path / "banned.txt"
    extra.write_text("# comment\nbaguette\\s+king\n", encoding="utf-8")
    patterns = scrub.load_extra(extra)
    assert [line for line, _ in patterns] == [2]
    assert scrub.find_extra("Ask the Baguette  King\nnothing here\n", patterns) == [(1, 2)]
    assert scrub.main(["--extra", str(tmp_path / "missing.txt")]) == 2
    assert "not found" in capsys.readouterr().err


def test_scrub_reads_text_not_structure(tool, tmp_path):
    scrub = tool("checks/scrub")
    book = Workbook()
    book.active.title = "Pumpernickel notes"
    book.active["D14"] = "rye sourdough"
    path = tmp_path / "book.xlsx"
    book.save(path)
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.endswith(".xml")]
        text = "\n".join(scrub.xml_text(archive.read(name)) for name in members)
    assert "rye sourdough" in text and "Pumpernickel notes" in text and "D14" not in text
    message = EmailMessage()
    message["Subject"] = "weekly pumpernickel"
    message.set_content("plain body")
    payload = b"zz-attachment-bytes"
    message.add_attachment(payload, maintype="application", subtype="octet-stream", filename="a.bin")
    mail = scrub.eml_text(message.as_bytes())
    assert "Subject: weekly pumpernickel" in mail and "plain body" in mail
    assert base64.b64encode(payload).decode("ascii") not in mail
    rules = [(4, re.compile(r"\S+@\S+")), (5, re.compile(r"\bapple\b"))]
    assert scrub.find_extra("finance@cedarline.example\nfont: -apple-system\n", rules) == []
    # \x40 and \x20 keep this source line itself free of an address and of the bare word
    assert scrub.find_extra("someone\x40else.example\nan\x20apple\n", rules) == [(1, 4), (2, 5)]


def test_repository_is_clean(tool, capsys):
    assert tool("checks/scrub").main([]) == 0
    assert capsys.readouterr().out.rstrip().endswith(": CLEAN")


def test_page_weight_counts_the_page_and_reserves_the_previews(tool, tmp_path):
    weight = tool("checks/page_weight")
    web = tmp_path / "web"
    (web / "kit").mkdir(parents=True)
    (web / "latest" / "preview").mkdir(parents=True)
    (web / "index.html").write_bytes(b"x" * 1000)
    (web / "kit" / "kit.js").write_bytes(b"x" * 2000)
    (web / "latest" / "manifest.json").write_bytes(b"x" * 300)
    stem = "Cedarline_Weekly_Report_2025-W38"
    for name in (f"{stem}.xlsx", f"{stem}.eml", f"{stem}.manifest.json", ".gitkeep"):
        (web / "latest" / name).write_bytes(b"x" * 50_000)
    (web / "latest" / "preview" / "summary.png").write_bytes(b"x" * 123)
    (web / "latest" / "preview" / "report-preview.pdf").write_bytes(b"x" * 456)
    total, items = weight.measure(web)
    assert [name for name, _ in items] == ["index.html", "kit/kit.js", "latest/manifest.json"]
    assert total == 3300 + 5 * 400_000
    assert weight.main([str(web)]) == 0
    (web / "heavy.js").write_bytes(b"x" * 1_000_000)
    assert weight.main([str(web)]) == 1


def test_the_page_is_within_the_weight_limit(tool):
    assert tool("checks/page_weight").main([str(ROOT / "web")]) == 0


def test_page_loads_only_local_files():
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    loaded = re.findall(r'<(?:script|link)\b[^>]*?\b(?:src|href)="([^"]+)"', page)
    assert loaded == [
        "kit/fonts/fonts.css",
        "kit/tokens.css",
        "kit/base.css",
        "assets/app.css",
        "assets/icon.svg",
        "kit/theme-boot.js",
        "assets/app.js",
    ]
    links = re.findall(r'\bhref="(https?://[^"]+)"', page)
    assert links and all(link.startswith(REPO_URL) for link in links)
    assert "http://" not in page


def test_page_has_the_sections_the_schedule_and_the_footer():
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for anchor in SECTIONS:
        assert f'id="{anchor}"' in page
    assert len(re.findall(r'role="tab"', page)) == 5
    text = unescape(page)
    for expected in (
        FOOTER,
        CRON_LINE,
        REGISTER,
        'schedule: [{cron: "0 6 * * 1"}]',
        "uv run build-report run --period 2025-W38 --input data/incoming --out reports --notify dry-run",
        "No weekly run yet",
        "LibreOffice renders",
    ):
        assert expected in text, expected


def test_app_reads_only_the_manifest_and_stores_nothing():
    script = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    assert "const MANIFEST_URL = 'latest/manifest.json';" in script
    assert "fetch(MANIFEST_URL" in script
    assert "from '../kit/kit.js'" in script
    for storage in ("localStorage", "sessionStorage", "document.cookie"):
        assert storage not in script
    assert re.search(r"https?://(?!github\.com/HARISPAARTAN/excel-reporting-automation)", script) is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed")
def test_contrast_of_the_page_tokens_and_the_workbook_palette():
    result = subprocess.run(
        ["node", str(ROOT / "tools" / "checks" / "contrast.mjs")],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL 32 PAIRS PASS" in result.stdout
