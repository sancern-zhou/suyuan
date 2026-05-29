"""Shared data models for operations work order audit."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Issue:
    rule_id: str
    category: str
    severity: str
    field: str
    message: str
    evidence: str
