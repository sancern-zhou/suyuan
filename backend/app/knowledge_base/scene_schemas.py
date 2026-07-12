"""Business-facing contracts for scene-driven graph configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BusinessObject(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    aliases: list[str] = Field(default_factory=list)


class BusinessLogic(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,119}$")
    statement: str = Field(min_length=1, max_length=1000)
    source_key: str
    relation_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,119}$")
    target_key: str
    policy: Literal["required", "allowed", "forbidden"] = "allowed"


class SceneDraft(BaseModel):
    scene_goal: str = Field(min_length=5, max_length=2000)
    desired_questions: list[str] = Field(default_factory=list)
    business_objects: list[BusinessObject]
    business_logic: list[BusinessLogic]
    ignored_content: list[str] = Field(default_factory=list)
    source_document_ids: list[str] = Field(min_length=1)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class SceneDiscoveryRequest(BaseModel):
    scene_goal: str = Field(min_length=5, max_length=2000)
    desired_questions: list[str] = Field(default_factory=list)


class SceneConfirmationRequest(BaseModel):
    business_objects: list[BusinessObject]
    business_logic: list[BusinessLogic]
    ignored_content: list[str] = Field(default_factory=list)


class StructuredBusinessRule(BaseModel):
    kind: Literal[
        "relationship_constraint",
        "conditional_constraint",
        "normalization",
        "exclusion",
    ]
    summary: str = Field(min_length=1, max_length=1000)
    applies_to: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    required_logic: list[str] = Field(default_factory=list)
    forbidden_logic: list[str] = Field(default_factory=list)


class BusinessRuleParseRequest(BaseModel):
    text: str = Field(min_length=2, max_length=4000)


class BusinessRuleConfirmRequest(BaseModel):
    expected_version: int = Field(ge=1)


class UserFactEntity(BaseModel):
    local_id: str
    entity_type: str
    name: str = Field(min_length=1, max_length=512)


class UserFactDraft(BaseModel):
    subject: UserFactEntity
    relation_type: str
    object: UserFactEntity
    statement: str


class UserFactParseRequest(BaseModel):
    text: str = Field(min_length=2, max_length=4000)


class UserFactConfirmRequest(BaseModel):
    resolutions: dict[str, str] = Field(default_factory=dict)
