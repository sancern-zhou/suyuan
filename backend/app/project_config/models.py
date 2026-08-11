import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


def validate_identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"invalid project identifier: {value!r}")
    return value


def unique(values: list[str]) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError("duplicate entries are not allowed")
    return values


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FrontendManifest(StrictModel):
    theme: str = "default"
    brand_name: str = "风清气智"
    features: dict[str, bool] = Field(default_factory=dict)
    agent_modes: list[str] = Field(default_factory=list)
    agent_platform_layout: Literal["scenes", "environment-grid"] = "scenes"

    _unique_agent_modes = field_validator("agent_modes")(unique)


class BackendManifest(StrictModel):
    tools: list[str] = Field(default_factory=list)
    disabled_tools: list[str] = Field(default_factory=list)
    fetchers: list[str] = Field(default_factory=list)
    mode_prompt_files: dict[str, str] = Field(default_factory=dict)

    _unique_tools = field_validator("tools")(unique)
    _unique_disabled_tools = field_validator("disabled_tools")(unique)
    _unique_fetchers = field_validator("fetchers")(unique)


class KnowledgeManifest(StrictModel):
    collections: list[str] = Field(default_factory=list)

    _unique_collections = field_validator("collections")(unique)


class ProjectManifest(StrictModel):
    schema_version: Literal[1]
    project: str
    modules: list[str] = Field(default_factory=list)
    frontend: FrontendManifest = Field(default_factory=FrontendManifest)
    backend: BackendManifest = Field(default_factory=BackendManifest)
    knowledge: KnowledgeManifest = Field(default_factory=KnowledgeManifest)
    scheduled_tasks: list[str] = Field(default_factory=list)

    _valid_project = field_validator("project")(validate_identifier)
    _unique_modules = field_validator("modules")(unique)
    _unique_tasks = field_validator("scheduled_tasks")(unique)


class ModuleManifest(StrictModel):
    schema_version: Literal[1]
    module: str
    dependencies: list[str] = Field(default_factory=list)

    _valid_module = field_validator("module")(validate_identifier)
    _unique_dependencies = field_validator("dependencies")(unique)


class ProjectContext(StrictModel):
    manifest: ProjectManifest
    module_manifests: dict[str, ModuleManifest]
    enabled_modules: frozenset[str]
