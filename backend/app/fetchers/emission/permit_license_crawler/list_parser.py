from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

BASE_URL = "https://permit.mee.gov.cn"


@dataclass(frozen=True)
class PermitListRecord:
    source_data_id: str
    province_name: str
    city_name: str
    permit_number: str
    enterprise_name: str
    industry_category: str
    valid_from: date | None
    valid_to: date | None
    issue_date: date | None
    management_category: str
    detail_url: str


@dataclass(frozen=True)
class PermitListPage:
    page_no: int
    total_pages: int
    records: tuple[PermitListRecord, ...]


class _ListTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.rows: list[list[tuple[str, str | None]]] = []
        self._row: list[tuple[str, str | None]] = []
        self._cell_text: list[str] = []
        self._cell_title: str | None = None
        self._row_href = ""
        self.page_no = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and "tabtd" in (attributes.get("class") or "").split():
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.in_row = True
            self._row = []
            self._row_href = ""
        elif self.in_row and tag in {"td", "th"}:
            self.in_cell = True
            self._cell_text = []
            self._cell_title = attributes.get("title")
        elif self.in_cell and tag == "a" and attributes.get("href"):
            self._row_href = attributes["href"] or ""
        elif tag == "input" and attributes.get("id") == "pageNo":
            try:
                self.page_no = int(attributes.get("value") or "1")
            except ValueError:
                self.page_no = 1

    def handle_endtag(self, tag: str) -> None:
        if self.in_cell and tag in {"td", "th"}:
            text = " ".join("".join(self._cell_text).split())
            self._row.append((text, self._cell_title))
            self.in_cell = False
        elif self.in_row and tag == "tr":
            if self._row:
                self._row.append((self._row_href, None))
                self.rows.append(self._row)
            self.in_row = False
        elif self.in_table and tag == "table":
            self.in_table = False

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self._cell_text.append(data)


def _date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _validity(value: str) -> tuple[date | None, date | None]:
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", value)
    if len(dates) < 2:
        return None, None
    return _date(dates[0]), _date(dates[1])


def _cell_value(cell: tuple[str, str | None]) -> str:
    text, title = cell
    return (title if title is not None else text).strip()


def parse_list_page(html: str) -> PermitListPage:
    parser = _ListTableParser()
    parser.feed(html)
    page_match = re.search(r"\bpagesum\s*=\s*(\d+)", html)
    total_pages = int(page_match.group(1)) if page_match else parser.page_no
    records: list[PermitListRecord] = []
    for row in parser.rows:
        if len(row) < 10 or _cell_value(row[0]) == "省/直辖市":
            continue
        href = row[-1][0]
        query = parse_qs(urlparse(href).query)
        data_id = query.get("dataid", [""])[0]
        if not data_id:
            continue
        valid_from, valid_to = _validity(_cell_value(row[5]))
        records.append(
            PermitListRecord(
                source_data_id=data_id,
                province_name=_cell_value(row[0]),
                city_name=_cell_value(row[1]),
                permit_number=_cell_value(row[2]),
                enterprise_name=_cell_value(row[3]),
                industry_category=_cell_value(row[4]),
                valid_from=valid_from,
                valid_to=valid_to,
                issue_date=_date(_cell_value(row[6])),
                management_category=_cell_value(row[7]),
                detail_url=urljoin(BASE_URL, href),
            )
        )
    return PermitListPage(
        page_no=parser.page_no,
        total_pages=total_pages,
        records=tuple(records),
    )
