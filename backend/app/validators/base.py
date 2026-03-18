from __future__ import annotations

from typing import Any, Iterable, List, Tuple

from pydantic import BaseModel

from app.schemas.common import (
    DataQualityReport,
    FieldStats,
    ValidationIssue,
    ValidationSeverity,
)


class ValidationResult(BaseModel):
    """Structured validation outcome."""

    report: DataQualityReport
    field_stats: Tuple[FieldStats, ...] = ()
    normalized_samples: List[Any] = []  # List of validated Pydantic models

    @property
    def is_valid(self) -> bool:
        return not self.report.has_errors()

    def first_error(self) -> str | None:
        for issue in self.report.issues:
            if issue.level == ValidationSeverity.ERROR:
                return issue.message
        return None

    class Config:
        arbitrary_types_allowed = True
