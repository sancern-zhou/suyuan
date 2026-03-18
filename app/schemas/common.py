"Common data schema helpers."

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

from pydantic import BaseModel, Field


class Unit(str, Enum):
    """Measurement units used across datasets."""

    PPB = "ppb"
    PPM = "ppm"
    UG_M3 = "ug_m3"
    MG_M3 = "mg_m3"


class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationIssue(BaseModel):
    """Single validation issue detail."""

    level: ValidationSeverity = Field(..., description="Severity level.")
    code: str = Field(..., description="Machine readable issue code.")
    message: str = Field(..., description="Human readable description.")
    field: Optional[str] = Field(
        default=None, description="Field name related to the issue."
    )
    index: Optional[int] = Field(
        default=None, description="Record index related to the issue."
    )


class DataQualityReport(BaseModel):
    """Aggregated validation result."""

    schema_type: str  # 重命名避免与 BaseModel.schema 属性冲突
    total_records: int = 0
    valid_records: int = 0
    issues: List[ValidationIssue] = Field(default_factory=list)
    missing_rate: float = 0.0
    summary: Optional[str] = None

    def has_errors(self) -> bool:
        return any(issue.level == ValidationSeverity.ERROR for issue in self.issues)

    def to_summary(self) -> str:
        parts: List[str] = [
            f"schema_type={self.schema_type}",
            f"count={self.total_records}",
            f"missing_rate={self.missing_rate:.2%}",
        ]
        if self.summary:
            parts.append(self.summary)
        if self.issues:
            top_issues = ", ".join(f"{i.code}" for i in self.issues[:3])
            parts.append(f"issues={top_issues}")
        return " | ".join(parts)


class FieldStats(BaseModel):
    """Basic statistics for numeric fields."""

    name: str
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    mean: Optional[float] = None
    missing: int = 0
    total: int = 0

    @property
    def missing_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.missing / self.total


class FieldStatsReport(BaseModel):
    """Structured statistics result for downstream reporting."""

    schema_type: str  # 重命名避免与 BaseModel.schema 属性冲突
    fields: Sequence[FieldStats]
