"""Content rules for every text file in the repository and the XML parts of any workbook in it.

No e-mail address outside the .example domain (the GitHub bot address excepted), no phone number and no street
address: the client, the branches and the staff are fictional and must not look like real contact data.
"""

import functools
import os
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_FILES = 8
ADDRESS = re.compile(r"[A-Za-z0-9._%+\-\[\]]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
ALLOWED = {"41898282+github-actions[bot]@users.noreply.github.com"}
PHONE = re.compile(
    # international: a plus, the country code, then seven or more digits with spaces, brackets, dots or hyphens
    r"(?<![\w.])\+\d[\d ().-]{6,}\d"
    # a country prefix in brackets, with a plus or two zeros
    r"|\((?:\+|00)\d{1,3}\)"
    # a country prefix written with two zeros, then the number
    r"|(?<![\w.])00\d{1,3}[ .-]\d{3,}"
    # national: a leading zero and an area code (brackets optional), then the number
    r"|(?<![\w.])\(?0\d{2,5}\)?[ /.-]\d{3,}"
    # an area code in brackets, then the number
    r"|(?<![\w.])\(\d{2,5}\)[ /.-]?\d{3,}"
    # any other run of digit groups joined by spaces, slashes or hyphens with seven or more digits in all;
    # an ISO date is not a phone number, and neither is a run that continues into a word, a time or a longer run
    r"|(?<![\w.:/+-])(?!\d{4}-\d{2}-\d{2}\b)(?=(?:[ /-]?\d){7})\d{1,10}(?:[ /-]\d{1,10})+(?![\w:]|[ /-]\d)"
)
STREET = re.compile(
    # German: a word that ends in the street suffix, then the house number
    r"\b[^\W\d_]+[ \t-]?(?i:stra(?:ß|ss)e|str\.)[ \t]*\d+[A-Za-z]?\b"
    # English, number last: a capitalised name, the street word, then the house number
    r"|\b[A-Z][^\W\d_]+[ \t]+(?:Street|Road|Avenue|Lane)[ \t]*,?[ \t]*\d+[A-Za-z]?\b"
    # English, number first: the house number, a capitalised name, then the street word
    r"|\b\d+[A-Za-z]?[ \t]+[A-Z][^\W\d_]+[ \t]+(?:Street|Road|Avenue|Lane)\b"
)
SKIP_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".hypothesis",
    "__pycache__",
    "build",
    "reports",
    "dist",
    "_kit",
    "node_modules",
}
BINARY = {".png", ".pdf", ".woff2", ".ico"}
WORKBOOK_PARTS = (".xml", ".rels")


def iter_texts(root=ROOT):
    """Yield (file, where, text) for every text file and every XML or relationship part of a workbook."""
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(folder) / name
            suffix = path.suffix.lower()
            if suffix in BINARY:
                continue
            if suffix == ".xlsx":
                try:
                    with zipfile.ZipFile(path) as archive:
                        for member in archive.namelist():
                            if member.lower().endswith(WORKBOOK_PARTS):
                                text = archive.read(member).decode("utf-8", "replace")
                                yield path, f"{path}!{member}", text
                    continue
                except zipfile.BadZipFile:
                    pass  # not a workbook after all: scan it like any other file
            try:
                yield path, str(path), path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue


@functools.cache
def scanned_texts():
    """The texts of the repository, read once; a walk that finds too few files cannot pass by finding nothing."""
    found = tuple(iter_texts())
    count = len({path for path, _, _ in found})
    assert count >= MIN_FILES, f"only {count} files were scanned; the walk skips too much"
    return found


def address_offenders(texts):
    hits = []
    for _, where, text in texts:
        for address in ADDRESS.findall(text):
            if address in ALLOWED or address.lower().endswith(".example"):
                continue
            hits.append(f"{where}: {address}")
    return hits


def pattern_offenders(texts, pattern):
    return [f"{where}: {hit.group().strip()}" for _, where, text in texts for hit in pattern.finditer(text)]


def test_enough_files_are_scanned():
    count = len({path for path, _, _ in scanned_texts()})
    assert count >= MIN_FILES


def test_every_address_ends_in_example():
    assert address_offenders(scanned_texts()) == []


def test_no_phone_numbers():
    assert pattern_offenders(scanned_texts(), PHONE) == []


def test_no_street_addresses():
    assert pattern_offenders(scanned_texts(), STREET) == []


def test_phone_pattern_finds_phone_numbers_and_leaves_dates_alone():
    # The examples are assembled here so that this file does not contain them in one piece.
    numbers = [
        " ".join(["+49", "123", "456789"]),
        " ".join(["0123", "4567890"]),
        " ".join(["".join(["(", "0049", ")"]), "123", "456789"]),
        " ".join(["(030)", "1234567"]),
        "/".join(["030", "1234567"]),
        "-".join(["555", "123", "4567"]),
        " ".join(["49", "123", "456789"]),
        "".join(["Call ", "+353 ", "1 ", "234 ", "5678"]),
    ]
    for number in numbers:
        assert PHONE.search(number), number
    harmless = [
        "2025-09-22",
        "2025-09-22 06:00",
        "2025-09-22T06:00:00Z",
        "2025-W38",
        "29.10.2026",
        "version 3.12.4 on 10.0.26200",
        "127.0.0.1",
        "0.060 and 0.320",
        "CL-12",
        "sha256:0f5e1c9ab2d4",
        "in 38 weeks, 12 branches, 6 groups",
    ]
    for text in harmless:
        assert PHONE.search(text) is None, text


def test_street_pattern_finds_street_addresses():
    addresses = [
        "".join(["Haupt", "straße", " 12"]),
        "".join(["Haupt", "strasse", " 12a"]),
        "".join(["Muster", "str.", " 5"]),
        "".join(["Muster ", "Str. ", "5"]),
        " ".join(["Baker", "Street", "12"]),
        " ".join(["Elm", "Road,", "7"]),
        " ".join(["12", "Baker", "Street"]),
        " ".join(["221B", "Baker", "Street"]),
        " ".join(["Park", "Avenue", "3"]),
        " ".join(["Mill", "Lane", "9"]),
    ]
    for address in addresses:
        assert STREET.search(address), address
    harmless = [
        "Hauptstraße",
        "Main Street",
        "the street was quiet",
        "Road map for 2026",
        "df.str.lower()",
        "Lane 3 of the pool",
    ]
    for text in harmless:
        assert STREET.search(text) is None, text


def test_workbook_parts_are_scanned_whatever_the_case_of_the_extension(tmp_path):
    contact = "".join(["someone", "@", "example.org"])
    with zipfile.ZipFile(tmp_path / "Return.XLSX", "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/_rels/workbook.xml.rels", f'<Relationship Target="mailto:{contact}"/>')
        archive.writestr("xl/media/image1.png", b"\x89PNG")
    with zipfile.ZipFile(tmp_path / "other.xlsx", "w") as archive:
        archive.writestr("docProps/core.xml", "<cp/>")
    (tmp_path / "broken.xlsx").write_text("not a zip file", encoding="utf-8")
    texts = list(iter_texts(tmp_path))
    parts = sorted((path.name, where.partition("!")[2]) for path, where, _ in texts)
    assert parts == [
        ("Return.XLSX", "[Content_Types].xml"),
        ("Return.XLSX", "xl/_rels/workbook.xml.rels"),
        ("Return.XLSX", "xl/workbook.xml"),
        ("broken.xlsx", ""),
        ("other.xlsx", "docProps/core.xml"),
    ]
    offenders = address_offenders(texts)
    assert len(offenders) == 1
    assert offenders[0].endswith(f"Return.XLSX!xl/_rels/workbook.xml.rels: {contact}")
