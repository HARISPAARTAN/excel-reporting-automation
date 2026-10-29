"""Render checks: need LibreOffice and poppler, so they run only in the ci.yml render job (pytest -m render)."""

import shutil

import pytest

pytestmark = pytest.mark.render


@pytest.fixture(scope="module")
def rendered(tool, demo_run, tmp_path_factory):
    if shutil.which("soffice") is None or shutil.which("pdftoppm") is None:
        pytest.fail("the render tests need LibreOffice and poppler-utils (installed by the CI render job)")
    out = tmp_path_factory.mktemp("render")
    code = tool("render_sheets").main([str(demo_run["xlsx"]), "--out", str(out), "--check-recalc"])
    return code, out


def test_render_succeeds_with_recalculated_totals(rendered):
    code, out = rendered
    assert code == 0
    assert any((out / "recalc").glob("*.xlsx"))


def test_pdf_has_one_page_per_sheet(tool, rendered):
    _, out = rendered
    assert tool("render_sheets").pdf_pages(out / "report-preview.pdf") == 5


def test_five_pngs_within_the_size_limit(rendered):
    _, out = rendered
    names = ["summary.png", "branches.png", "products.png", "data.png", "run-info.png"]
    for name in names:
        path = out / name
        assert path.is_file(), name
        assert path.stat().st_size <= 400_000, (name, path.stat().st_size)
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
