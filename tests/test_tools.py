import json
import shutil

import pytest
from openpyxl import load_workbook

from conftest import STEM


@pytest.fixture()
def report_dir(tmp_path, demo_run):
    folder = tmp_path / "report"
    shutil.copytree(demo_run["dir"], folder)
    return folder


def test_publish_latest_replaces_the_folder(tool, report_dir, tmp_path, capsys):
    target = tmp_path / "latest"
    (target / "preview").mkdir(parents=True)
    (target / ".gitkeep").write_bytes(b"")
    (target / "Cedarline_Weekly_Report_2025-W37.xlsx").write_bytes(b"old")
    (target / "preview" / "summary.png").write_bytes(b"old")
    assert tool("publish_latest").main([str(report_dir), str(target)]) == 0
    assert capsys.readouterr().out == "2025-W38\n"
    assert sorted(path.name for path in target.iterdir()) == sorted(
        [".gitkeep", f"{STEM}.xlsx", f"{STEM}.eml", f"{STEM}.manifest.json", "manifest.json"]
    )
    assert (target / "manifest.json").read_bytes() == (report_dir / f"{STEM}.manifest.json").read_bytes()
    assert (target / f"{STEM}.xlsx").read_bytes() == (report_dir / f"{STEM}.xlsx").read_bytes()


def test_publish_latest_refuses_a_blocked_or_missing_report(tool, report_dir, tmp_path):
    publish = tool("publish_latest").main
    assert publish([str(tmp_path / "empty"), str(tmp_path / "latest")]) == 1
    manifest_path = report_dir / f"{STEM}.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "blocked"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert publish([str(report_dir), str(tmp_path / "latest")]) == 1
    manifest["status"] = "built"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (report_dir / f"{STEM}.eml").unlink()
    assert publish([str(report_dir), str(tmp_path / "latest")]) == 1


def test_render_copy_cuts_the_data_table(tool, demo_run, tmp_path):
    render = tool("render_sheets")
    target = tmp_path / "render.xlsx"
    assert render.make_render_copy(demo_run["xlsx"], target, rows=40) == 2945
    book = load_workbook(target)
    data = book["Data"]
    assert data.max_row == 42
    assert data["A42"].value == "first 40 of 2,945 rows; the full table is in the workbook"
    table = data.tables["tblWeekly"]
    assert table.ref == "A1:H41" and table.autoFilter.ref == "A1:H41"
    assert book.sheetnames == ["Summary", "Branches", "Products", "Data", "Run info"]
    assert len(book["Summary"]._charts) == 3
    assert book["Branches"]["D16"].value == "=SUM(D4:D15)"


def test_profile_sets_recalculation_to_always(tool, tmp_path):
    uri = tool("render_sheets").write_profile(tmp_path / "lo-profile")
    assert uri.startswith("file:")
    text = (tmp_path / "lo-profile" / "user" / "registrymodifications.xcu").read_text(encoding="utf-8")
    for name in ("OOXMLRecalcMode", "ODFRecalcMode"):
        assert f'<prop oor:name="{name}" oor:op="fuse"><value>0</value></prop>' in text


def test_soffice_command_lines(tool, tmp_path):
    render = tool("render_sheets")
    pdf = render.pdf_command("soffice", "file:///tmp/lo-profile", tmp_path / "render.xlsx", tmp_path)
    assert pdf[:4] == ["soffice", "--headless", "--norestore", "-env:UserInstallation=file:///tmp/lo-profile"]
    assert pdf[4:6] == [
        "--convert-to",
        'pdf:calc_pdf_Export:{"SinglePageSheets":{"type":"boolean","value":"true"}}',
    ]
    recalc = render.recalc_command(
        "soffice", "file:///tmp/lo-profile", tmp_path / "report.xlsx", tmp_path / "recalc"
    )
    assert recalc[4:6] == ["--convert-to", "xlsx:Calc MS Excel 2007 XML"]


def test_rename_pages(tool, tmp_path):
    for number in range(1, 6):
        (tmp_path / f"sheet-{number}.png").write_bytes(b"png")
    names = [path.name for path in tool("render_sheets").rename_pages(tmp_path)]
    assert names == ["summary.png", "branches.png", "products.png", "data.png", "run-info.png"]


def test_check_recalc_compares_every_formula_cell(tool, cfg, demo_run, demo_result, tmp_path):
    from buildreport.workbook import formula_cells

    render = tool("render_sheets")
    simulated = load_workbook(demo_run["xlsx"])
    cells = formula_cells(cfg, demo_result)
    for cell in cells:
        simulated[cell.sheet][cell.ref] = "" if cell.expected is None else cell.expected
    good = tmp_path / "good.xlsx"
    simulated.save(good)
    assert render.check_recalc(demo_run["xlsx"], good, cfg) == []
    simulated["Branches"]["D16"] = cells[0].expected * 1.01
    bad = tmp_path / "bad.xlsx"
    simulated.save(bad)
    problems = render.check_recalc(demo_run["xlsx"], bad, cfg)
    assert len(problems) == 1 and problems[0].startswith("Branches!D16: =SUM(D4:D15) gives")


def test_render_needs_libreoffice(tool, demo_run, tmp_path, monkeypatch, capsys):
    render = tool("render_sheets")
    monkeypatch.setattr(render.shutil, "which", lambda name: None)
    assert render.main([str(demo_run["xlsx"]), "--out", str(tmp_path / "preview")]) == 1
    assert "LibreOffice" in capsys.readouterr().err


def test_render_needs_exactly_one_existing_workbook(tool, tmp_path, capsys):
    render = tool("render_sheets")
    assert (
        render.main([str(tmp_path / "Cedarline_Weekly_Report_*.xlsx"), "--out", str(tmp_path / "preview")])
        == 1
    )
    assert "no workbook" in capsys.readouterr().err
