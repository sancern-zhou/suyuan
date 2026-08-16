import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


def validate_identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"invalid project identifier: {value!r}")
    return value


def unique(values: list[str]) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError("duplicate entries are not allowed")
    return values


def valid_identifier_map(value: dict[str, Any]) -> dict[str, Any]:
    for key in value:
        validate_identifier(key)
    return value


def unique_string_lists(value: dict[str, list[str]]) -> dict[str, list[str]]:
    for key, values in value.items():
        validate_identifier(key)
        unique(values)
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoordinatorQuickPrompt(StrictModel):
    label: str
    prompt: str
    mode: str | None = None


class CoordinatorRoute(StrictModel):
    mode: str
    keywords: list[str] = Field(default_factory=list)

    _unique_keywords = field_validator("keywords")(unique)


class CoordinatorAction(StrictModel):
    label: str
    kind: Literal["ask", "open-agent", "open-task"] = "ask"
    prompt: str | None = None
    mode: str | None = None
    task_id: str | None = None


class CoordinatorAttentionItem(StrictModel):
    id: str
    title: str
    summary: str = ""
    severity: Literal["critical", "high", "medium", "low", "info"] = "info"
    status: str = "new"
    station: str | None = None
    occurred_at: str | None = None
    diagnosis: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    evidence: list[str] = Field(default_factory=list)
    actions: list[CoordinatorAction] = Field(default_factory=list)


class CoordinatorWorkspaceBlock(StrictModel):
    id: str
    type: Literal["metric-grid", "briefing", "attention-list", "activity"]
    title: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)


class CoordinatorManifest(StrictModel):
    name: str = "智能助手"
    role: str = "统筹助手"
    greeting: str = "今天需要我协助处理什么？"
    description: str = "理解需求、组织专业能力并跟踪任务进展。"
    placeholder: str = "输入问题、业务对象或任务……"
    station_image_url: str | None = None
    default_mode: str | None = None
    quick_prompts: list[CoordinatorQuickPrompt] = Field(default_factory=list)
    attention_task_ids: list[str] = Field(default_factory=list)
    routes: list[CoordinatorRoute] = Field(default_factory=list)
    workspace_blocks: list[CoordinatorWorkspaceBlock] = Field(default_factory=list)
    demo_attention_items: list[CoordinatorAttentionItem] = Field(default_factory=list)

    _unique_attention_task_ids = field_validator("attention_task_ids")(unique)


class FrontendManifest(StrictModel):
    theme: str = "default"
    brand_name: str = "风清气智"
    features: dict[str, bool] = Field(default_factory=dict)
    agent_modes: list[str] = Field(default_factory=list)
    default_agent_mode: str | None = None
    agent_mode_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    agent_platform_layout: Literal["scenes", "environment-grid", "coordinator"] = "scenes"
    coordinator: CoordinatorManifest | None = None

    _unique_agent_modes = field_validator("agent_modes")(unique)
    _valid_agent_mode_overrides = field_validator("agent_mode_overrides")(valid_identifier_map)

    @model_validator(mode="after")
    def validate_default_agent_mode(self):
        if self.default_agent_mode is not None:
            validate_identifier(self.default_agent_mode)
            if self.agent_modes and self.default_agent_mode not in self.agent_modes:
                raise ValueError("default_agent_mode must be declared in agent_modes")
        if self.coordinator is not None:
            declared_modes = set(self.agent_modes)
            referenced_modes = {
                entry.mode
                for entry in [*self.coordinator.quick_prompts, *self.coordinator.routes]
                if entry.mode is not None
            }
            referenced_modes.update(
                action.mode
                for item in self.coordinator.demo_attention_items
                for action in item.actions
                if action.mode is not None
            )
            if self.coordinator.default_mode is not None:
                referenced_modes.add(self.coordinator.default_mode)
            unknown_modes = sorted(referenced_modes - declared_modes)
            if unknown_modes:
                raise ValueError(
                    "coordinator modes must be declared in agent_modes: "
                    + ", ".join(unknown_modes)
                )
        return self


class BackendManifest(StrictModel):
    tools: list[str] = Field(default_factory=list)
    # ``None`` preserves the shared legacy directories/registrations.  An
    # explicitly empty list is meaningful: the project owns an empty surface.
    skills_dir: str | None = None
    fetchers: list[str] | None = None
    fetchers_enabled: bool = True
    gis_tools_enabled: bool = True
    mode_prompt_files: dict[str, str] = Field(default_factory=dict)
    agent_mode_tools: dict[str, list[str]] = Field(default_factory=dict)

    _unique_tools = field_validator("tools")(unique)
    _unique_fetchers = field_validator("fetchers")(unique)
    _valid_mode_prompt_files = field_validator("mode_prompt_files")(valid_identifier_map)
    _unique_agent_mode_tools = field_validator("agent_mode_tools")(unique_string_lists)


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
    scheduled_tasks_enabled: bool = True
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
