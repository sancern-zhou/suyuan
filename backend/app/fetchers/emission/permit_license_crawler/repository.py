from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .detail_parser import PermitVersion
from .list_parser import PermitListRecord
from .models import (
    PermitCrawlFailure,
    PermitCrawlRun,
    PermitDocument,
    PermitLicense,
    PermitLicenseVersion,
    PermitPollutionDetail,
)
from .storage import StoredFile


def _credit_code(permit_number: str) -> str | None:
    candidate = permit_number[:18].upper()
    return candidate if len(candidate) == 18 and candidate.isalnum() else None


class PermitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(self, *, phase: str, start_page: int | None, max_pages: int | None, max_licenses: int | None) -> PermitCrawlRun:
        run = PermitCrawlRun(
            phase=phase,
            start_page=start_page,
            max_pages=max_pages,
            max_licenses=max_licenses,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def finish_run(self, run: PermitCrawlRun, *, status: str, reason: str | None = None) -> None:
        run.status = status
        run.stop_reason = reason
        run.finished_at = datetime.utcnow()
        await self.session.flush()

    async def upsert_list_record(self, record: PermitListRecord, *, list_page_no: int) -> PermitLicense:
        row = await self.session.scalar(
            select(PermitLicense).where(PermitLicense.source_data_id == record.source_data_id)
        )
        now = datetime.utcnow()
        values = {
            "province_name": record.province_name,
            "city_name": record.city_name,
            "permit_number": record.permit_number,
            "unified_social_credit_code": _credit_code(record.permit_number),
            "enterprise_name": record.enterprise_name,
            "industry_category": record.industry_category,
            "valid_from": record.valid_from,
            "valid_to": record.valid_to,
            "issue_date": record.issue_date,
            "management_category": record.management_category,
            "detail_url": record.detail_url,
            "list_page_no": list_page_no,
            "last_seen_at": now,
            "updated_at": now,
        }
        if row is None:
            row = PermitLicense(source_data_id=record.source_data_id, **values)
            self.session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        await self.session.flush()
        return row

    async def list_pending_licenses(self, *, limit: int, resume: bool = True) -> list[PermitLicense]:
        del resume
        result = await self.session.scalars(
            select(PermitLicense)
            .where(
                or_(
                    PermitLicense.detail_status != "complete",
                    PermitLicense.documents_status != "complete",
                )
            )
            .order_by(PermitLicense.list_page_no, PermitLicense.id)
            .limit(limit)
        )
        return list(result)

    async def next_list_page(self, *, start_page: int) -> int:
        last_page = await self.session.scalar(select(func.max(PermitLicense.list_page_no)))
        return max(start_page, (last_page or 0) + 1)

    async def save_detail(
        self,
        license_row: PermitLicense,
        *,
        versions: list[PermitVersion] | tuple[PermitVersion, ...],
        pollution: dict[str, str | None],
        current_status: str,
        latest_business_type: str | None,
        source_html_sha256: str,
    ) -> None:
        await self.session.execute(
            delete(PermitLicenseVersion).where(PermitLicenseVersion.license_id == license_row.id)
        )
        self.session.add_all(
            [
                PermitLicenseVersion(
                    license_id=license_row.id,
                    version_no=version.version_no,
                    permit_number=version.permit_number,
                    business_type=version.business_type,
                    completion_date=version.completion_date,
                    valid_from=version.valid_from,
                    valid_to=version.valid_to,
                    source_order=version.source_order,
                )
                for version in versions
            ]
        )
        detail = await self.session.get(PermitPollutionDetail, license_row.id)
        values = {
            **pollution,
            "parsed_at": datetime.utcnow(),
            "source_html_sha256": source_html_sha256,
        }
        if detail is None:
            detail = PermitPollutionDetail(license_id=license_row.id, **values)
            self.session.add(detail)
        else:
            for key, value in values.items():
                setattr(detail, key, value)
        license_row.current_status = current_status
        license_row.latest_business_type = latest_business_type
        license_row.detail_status = "complete"
        await self.session.flush()

    async def save_document(
        self,
        license_row: PermitLicense,
        *,
        document_type: str,
        page_no: int,
        source_url: str,
        stored: StoredFile,
        mime_type: str,
    ) -> PermitDocument:
        row = await self.session.scalar(
            select(PermitDocument).where(
                PermitDocument.license_id == license_row.id,
                PermitDocument.document_type == document_type,
                PermitDocument.page_no == page_no,
            )
        )
        values = {
            "source_url": source_url,
            "relative_path": stored.relative_path.as_posix(),
            "mime_type": mime_type,
            "size_bytes": stored.size_bytes,
            "sha256": stored.sha256,
            "status": "complete",
            "downloaded_at": datetime.utcnow(),
        }
        if row is None:
            row = PermitDocument(
                license_id=license_row.id,
                document_type=document_type,
                page_no=page_no,
                **values,
            )
            self.session.add(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        await self.session.flush()
        return row

    async def get_complete_document(self, license_id: str, document_type: str, page_no: int = 0) -> PermitDocument | None:
        return await self.session.scalar(
            select(PermitDocument).where(
                PermitDocument.license_id == license_id,
                PermitDocument.document_type == document_type,
                PermitDocument.page_no == page_no,
                PermitDocument.status == "complete",
            )
        )

    async def record_failure(
        self,
        run: PermitCrawlRun,
        *,
        stage: str,
        error: Exception,
        license_row: PermitLicense | None = None,
        request_url: str | None = None,
    ) -> None:
        self.session.add(
            PermitCrawlFailure(
                run_id=run.id,
                license_id=license_row.id if license_row else None,
                stage=stage,
                request_url=request_url,
                error_type=type(error).__name__,
                error_summary=str(error)[:2000],
            )
        )
        await self.session.flush()
