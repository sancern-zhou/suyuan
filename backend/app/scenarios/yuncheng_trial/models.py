from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuleHit:
    rule_id: str
    level: str
    message: str
    rule_basis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "level": self.level,
            "message": self.message,
            "rule_basis": self.rule_basis,
        }


@dataclass
class AlertState:
    city: str
    checked_at: str
    has_alert: bool
    summary: str
    rule_hits: list[RuleHit] = field(default_factory=list)
    supporting_rule_hits: list[RuleHit] = field(default_factory=list)
    alert_id: str | None = None
    alert_level: str | None = None
    alert_type: str | None = None
    target_pollutant: str | None = None
    target_time: str | None = None
    lookback_hours: int = 12
    source_files: list[str] = field(default_factory=list)
    status: str = "silent"

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "checked_at": self.checked_at,
            "has_alert": self.has_alert,
            "alert_id": self.alert_id,
            "alert_level": self.alert_level,
            "alert_type": self.alert_type,
            "target_pollutant": self.target_pollutant,
            "target_time": self.target_time,
            "lookback_hours": self.lookback_hours,
            "summary": self.summary,
            "rule_hits": [hit.to_dict() for hit in self.rule_hits],
            "supporting_rule_hits": [hit.to_dict() for hit in self.supporting_rule_hits],
            "source_files": self.source_files,
            "status": self.status,
        }
