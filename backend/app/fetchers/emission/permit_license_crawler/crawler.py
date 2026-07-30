from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from .client import PermitPlatformClient, PlatformBlockedError
from .detail_parser import classify_current_status, parse_detail_page
from .document_downloader import detect_document_kind, parse_copy_viewer
from .list_parser import parse_list_page
from .models import PermitCrawlRun, PermitLicense
from .pdf_builder import build_pdf
from .repository import PermitRepository
from .storage import FileStorage, safe_component

LIST_URL = "https://permit.mee.gov.cn/perxxgkinfo/syssb/xkgg/xkgg!licenseInformation.action"
PROVINCE_CODE = "410000000000"
CITY_CODE = "411000000000"


class XuchangPermitCrawler:
    def __init__(
        self,
        *,
        client: PermitPlatformClient,
        repository: PermitRepository,
        storage: FileStorage,
    ) -> None:
        self.client = client
        self.repository = repository
        self.storage = storage

    async def crawl_list(self, *, start_page: int, max_pages: int, run: PermitCrawlRun) -> None:
        index = await self.client.get(LIST_URL)
        temp_key = _hidden_value(index.text, "tempReportKey")
        for page_no in range(start_page, start_page + max_pages):
            response = await self.client.post(
                LIST_URL,
                data={
                    "page.pageNo": str(page_no),
                    "page.orderBy": "",
                    "page.order": "",
                    "tempReportKey": temp_key,
                    "province": PROVINCE_CODE,
                    "city": CITY_CODE,
                    "management": "",
                    "registerentername": "",
                    "xkznum": "",
                    "treadname": "",
                    "treadcode": "",
                    "publishtime": "",
                },
                headers={"Referer": LIST_URL},
            )
            page = parse_list_page(response.text)
            if page.page_no != page_no:
                raise ValueError(f"expected list page {page_no}, got {page.page_no}")
            if not page.records:
                raise ValueError(f"list page {page_no} contained no licence records")
            invalid = [
                record
                for record in page.records
                if record.province_name != "河南省" or record.city_name != "许昌市"
            ]
            if invalid:
                raise ValueError(f"list page {page_no} contained records outside Xuchang")
            for record in page.records:
                await self.repository.upsert_list_record(record, list_page_no=page_no)
                run.success_count += 1
            await self.repository.session.commit()
            if page_no >= page.total_pages:
                break

    async def crawl_details(self, *, max_licenses: int, resume: bool, run: PermitCrawlRun) -> None:
        rows = await self.repository.list_pending_licenses(limit=max_licenses, resume=resume)
        for license_row in rows:
            license_id = license_row.id
            detail_url = license_row.detail_url
            try:
                await self._crawl_one_detail(license_row)
                run.success_count += 1
                await self.repository.session.commit()
            except PlatformBlockedError:
                await self.repository.session.rollback()
                raise
            except Exception as exc:
                await self.repository.session.rollback()
                license_row = await self.repository.session.get(PermitLicense, license_id)
                await self.repository.record_failure(
                    run,
                    stage="detail",
                    error=exc,
                    license_row=license_row,
                    request_url=detail_url,
                )
                run.failure_count += 1
                await self.repository.session.commit()

    async def _crawl_one_detail(self, license_row: PermitLicense) -> None:
        response = await self.client.get(license_row.detail_url, headers={"Referer": LIST_URL})
        detail = parse_detail_page(response.text)
        if not detail.versions and all(value is None for value in detail.pollution.values()):
            raise ValueError("detail page did not contain expected permit data")
        directory = safe_component(license_row.permit_number, fallback=license_row.source_data_id)
        detail_stored = self.storage.write_bytes(Path(directory) / "detail.html", response.content)
        await self.repository.save_document(
            license_row,
            document_type="detail_html",
            page_no=0,
            source_url=license_row.detail_url,
            stored=detail_stored,
            mime_type="text/html",
        )
        status, business_type = classify_current_status(detail.versions, as_of=date.today())
        await self.repository.save_detail(
            license_row,
            versions=detail.versions,
            pollution=detail.pollution,
            current_status=status,
            latest_business_type=business_type,
            source_html_sha256=hashlib.sha256(response.content).hexdigest(),
        )
        if detail.original_url:
            await self._download_original(license_row, directory, detail.original_url)
        if detail.copy_url:
            await self._download_copy(license_row, directory, detail.copy_url)
        license_row.documents_status = "complete"

    async def _download_original(self, license_row: PermitLicense, directory: str, url: str) -> None:
        existing = await self.repository.get_complete_document(license_row.id, "original")
        if existing and (self.storage.root / existing.relative_path).is_file():
            return
        response = await self.client.get(url, headers={"Referer": license_row.detail_url})
        kind = detect_document_kind(response.headers.get("content-type", ""), response.content)
        if kind not in {"pdf", "image"}:
            raise ValueError(f"permit original returned {kind} content")
        suffix = ".pdf" if kind == "pdf" else _image_suffix(response.content)
        stored = self.storage.write_bytes(
            Path(directory) / "original" / f"permit_original{suffix}",
            response.content,
        )
        await self.repository.save_document(
            license_row,
            document_type="original",
            page_no=0,
            source_url=url,
            stored=stored,
            mime_type=response.headers.get("content-type", "application/octet-stream"),
        )

    async def _download_copy(self, license_row: PermitLicense, directory: str, url: str) -> None:
        existing_pdf = await self.repository.get_complete_document(license_row.id, "copy_merged_pdf")
        if existing_pdf and (self.storage.root / existing_pdf.relative_path).is_file():
            return
        response = await self.client.get(url, headers={"Referer": license_row.detail_url})
        kind = detect_document_kind(response.headers.get("content-type", ""), response.content)
        pdf_relative = Path(directory) / "copy" / "permit_copy.pdf"
        if kind == "pdf":
            stored = self.storage.write_bytes(pdf_relative, response.content)
            await self.repository.save_document(
                license_row,
                document_type="copy_merged_pdf",
                page_no=0,
                source_url=url,
                stored=stored,
                mime_type="application/pdf",
            )
            return
        if kind != "html":
            raise ValueError(f"permit copy returned {kind} content")
        viewer = parse_copy_viewer(response.text)
        page_paths: list[Path] = []
        for page_no, page_url in enumerate(viewer.page_urls, start=1):
            existing = await self.repository.get_complete_document(
                license_row.id, "copy_page", page_no
            )
            if existing and (self.storage.root / existing.relative_path).is_file():
                page_paths.append(self.storage.root / existing.relative_path)
                continue
            page_response = await self.client.get(page_url, headers={"Referer": url})
            if detect_document_kind(
                page_response.headers.get("content-type", ""), page_response.content
            ) != "image":
                raise ValueError(f"permit copy page {page_no} was not an image")
            suffix = _image_suffix(page_response.content)
            stored = self.storage.write_bytes(
                Path(directory) / "copy" / "pages" / f"{page_no:03d}{suffix}",
                page_response.content,
            )
            await self.repository.save_document(
                license_row,
                document_type="copy_page",
                page_no=page_no,
                source_url=page_url,
                stored=stored,
                mime_type=page_response.headers.get("content-type", "image/png"),
            )
            await self.repository.session.commit()
            page_paths.append(stored.path)
        pdf_path = self.storage.root / pdf_relative
        build_pdf(page_paths, pdf_path)
        stored_pdf = self.storage.describe(pdf_relative)
        await self.repository.save_document(
            license_row,
            document_type="copy_merged_pdf",
            page_no=0,
            source_url=url,
            stored=stored_pdf,
            mime_type="application/pdf",
        )


def _hidden_value(html: str, name: str) -> str:
    import re

    match = re.search(
        rf'<input[^>]*\bname=["\']{re.escape(name)}["\'][^>]*\bvalue=["\']([^"\']*)',
        html,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _image_suffix(content: bytes) -> str:
    return ".jpg" if content.startswith(b"\xff\xd8\xff") else ".png"
