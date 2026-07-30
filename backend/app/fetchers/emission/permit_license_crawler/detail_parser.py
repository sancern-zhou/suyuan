from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin

BASE_URL = "https://permit.mee.gov.cn"

POLLUTION_LABELS = {
    "主要污染物类别": "main_pollutant_categories",
    "大气主要污染物种类": "air_pollutant_types",
    "大气污染物排放规律": "air_emission_pattern",
    "大气污染物排放执行标准": "air_emission_standard",
    "废水主要污染物种类": "water_pollutant_types",
    "废水污染物排放规律": "water_emission_pattern",
    "废水污染物排放执行标准": "water_emission_standard",
    "排污权使用和交易信息": "emission_rights_info",
}


@dataclass(frozen=True)
class PermitVersion:
    permit_number: str
    business_type: str
    version_no: int | None
    completion_date: date | None
    valid_from: date | None
    valid_to: date | None
    source_order: int


@dataclass(frozen=True)
class PermitDetail:
    pollution: dict[str, str | None]
    versions: tuple[PermitVersion, ...]
    original_url: str
    copy_url: str


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.table_mode: str | None = None
        self.in_row = False
        self.cell_tag: str | None = None
        self._cell_text: list[str] = []
        self._row: list[tuple[str, str]] = []
        self.version_rows: list[list[tuple[str, str]]] = []
        self.pollution_rows: list[list[tuple[str, str]]] = []
        self._link_href = ""
        self._link_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            classes = (attributes.get("class") or "").split()
            if "tab0" in classes:
                self.table_mode = "versions"
            elif attributes.get("id") == "apply_table":
                self.table_mode = "pollution"
        elif self.table_mode and tag == "tr":
            self.in_row = True
            self._row = []
        elif self.in_row and tag in {"td", "th"}:
            self.cell_tag = tag
            self._cell_text = []
        if tag == "a" and attributes.get("href"):
            self._link_href = attributes["href"] or ""
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if self.cell_tag == tag:
            self._row.append((tag, " ".join("".join(self._cell_text).split())))
            self.cell_tag = None
        elif self.in_row and tag == "tr":
            if self.table_mode == "versions":
                self.version_rows.append(self._row)
            elif self.table_mode == "pollution":
                self.pollution_rows.append(self._row)
            self.in_row = False
        elif self.table_mode and tag == "table":
            self.table_mode = None
        if tag == "a" and self._link_href:
            self.links.append((" ".join("".join(self._link_text).split()), self._link_href))
            self._link_href = ""
            self._link_text = []

    def handle_data(self, data: str) -> None:
        if self.cell_tag:
            self._cell_text.append(data)
        if self._link_href:
            self._link_text.append(data)


def _date(value: str) -> date | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def _validity(value: str) -> tuple[date | None, date | None]:
    values = re.findall(r"\d{4}-\d{2}-\d{2}", value)
    if len(values) < 2:
        return None, None
    return date.fromisoformat(values[0]), date.fromisoformat(values[1])


def parse_detail_page(html: str) -> PermitDetail:
    parser = _DetailParser()
    parser.feed(html)
    pollution: dict[str, str | None] = {value: None for value in POLLUTION_LABELS.values()}
    for row in parser.pollution_rows:
        if len(row) < 2:
            continue
        label = row[0][1].rstrip("：:").strip()
        key = POLLUTION_LABELS.get(label)
        if key:
            pollution[key] = row[1][1]

    versions: list[PermitVersion] = []
    for source_order, row in enumerate(parser.version_rows):
        values = [cell[1] for cell in row]
        if len(values) < 5 or values[0] == "许可证编号":
            continue
        try:
            version_no = int(values[2]) if values[2] else None
        except ValueError:
            version_no = None
        valid_from, valid_to = _validity(values[4])
        versions.append(
            PermitVersion(
                permit_number=values[0],
                business_type=values[1],
                version_no=version_no,
                completion_date=_date(values[3]),
                valid_from=valid_from,
                valid_to=valid_to,
                source_order=source_order,
            )
        )

    original_url = ""
    copy_url = ""
    for text, href in parser.links:
        if "排污许可证正本" in text:
            original_url = urljoin(BASE_URL, href)
        elif "排污许可证副本" in text:
            copy_url = urljoin(BASE_URL, href)
    return PermitDetail(
        pollution=pollution,
        versions=tuple(versions),
        original_url=original_url,
        copy_url=copy_url,
    )


def classify_current_status(
    versions: tuple[PermitVersion, ...] | list[PermitVersion],
    *,
    as_of: date,
) -> tuple[str, str | None]:
    if not versions:
        return "unknown", None
    latest = max(
        versions,
        key=lambda version: (
            version.version_no if version.version_no is not None else -1,
            version.completion_date or date.min,
            version.source_order,
        ),
    )
    if latest.business_type == "注销":
        return "cancelled", latest.business_type
    if latest.valid_from is None or latest.valid_to is None:
        return "unknown", latest.business_type
    if latest.valid_from > as_of:
        return "not_yet_effective", latest.business_type
    if latest.valid_to < as_of:
        return "expired", latest.business_type
    return "valid", latest.business_type
