# Project Manifest Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立共享的项目清单、模块目录和前后端启用判断，使当前 Suyuan 默认部署行为保持不变，同时为后续逐个迁移大气、噪声等业务模块提供稳定协议。

**Architecture:** 仓库根目录的 `projects/<project>/project.yaml` 是部署选择的唯一声明，`modules/<module>/module.yaml` 是模块目录。后端在应用组装前严格加载并校验清单，前端由 Vite 在唯一构建入口中读取同一清单并注入只读配置；第一阶段把现有能力统一归为 `legacy` 模块，后续计划再逐个拆出业务模块。

**Tech Stack:** Python 3.11、Pydantic 2、PyYAML、FastAPI、Vue 3、Vite 5、Node test runner、pytest、ruff

---

## Scope Boundary

本计划只实现项目清单基础设施和当前入口的模块感知，不移动现有工具、抓取器、Skill、知识库或定时任务。完成后：

- `PROJECT=default` 与当前系统行为一致；
- 无效项目名、未知模块、缺失依赖和重复条目会在启动或构建阶段失败；
- 后端路由注册表可以声明所属模块；
- 前端路由和侧边栏模块可以声明所属模块；
- 前后端使用同一份 `project.yaml`，不会维护两套项目配置。

后续分别为大气模块、噪声模块、招投标模块、知识库配方和定时任务迁移编写独立计划。

## File Map

### New files

- `projects/default/project.yaml`：保持现有功能全部启用的默认部署清单。
- `modules/legacy/module.yaml`：迁移期现有功能的模块声明。
- `backend/app/project_config/__init__.py`：对外导出项目上下文加载 API。
- `backend/app/project_config/models.py`：Pydantic 清单模型和标识符约束。
- `backend/app/project_config/loader.py`：从仓库根目录加载、校验项目和模块依赖。
- `backend/app/api/project_config_routes.py`：公开非敏感运行时项目摘要。
- `backend/tests/project_config/test_loader.py`：清单加载和失败关闭测试。
- `backend/tests/project_config/test_routing.py`：后端路由模块过滤测试。
- `backend/tests/api/test_project_runtime_config.py`：运行时项目摘要契约测试。
- `frontend/scripts/projectManifest.mjs`：Vite 使用的 YAML 加载和校验器。
- `frontend/scripts/projectManifest.test.mjs`：前端构建清单测试。
- `frontend/src/config/projectConfig.js`：前端只读项目配置和启用判断。
- `frontend/src/config/projectConfig.test.js`：前端配置归一化测试。
- `frontend/src/router/projectRoutes.js`：按模块过滤 Vue 路由的纯函数。
- `frontend/src/router/projectRoutes.test.js`：路由过滤测试。
- `frontend/src/components/sidebarProjectModules.js`：按模块过滤侧边栏条目的纯函数。
- `frontend/src/components/sidebarProjectModules.test.js`：侧边栏过滤测试。

### Modified files

- `backend/config/settings.py`：增加 `PROJECT` 环境选择。
- `backend/app/core/routing.py`：为 `RouterSpec` 增加模块所有权并在导入前过滤。
- `backend/.env.example`：记录默认项目选择；实施时保留该文件已有未提交改动。
- `frontend/package.json`、`frontend/package-lock.json`：增加 YAML 构建依赖和项目配置测试命令。
- `frontend/vite.config.js`：读取清单并注入 `__SUYUAN_PROJECT_CONFIG__`。
- `frontend/src/router/index.js`：在 `createRouter` 前过滤声明了模块的路由。
- `frontend/src/components/AssistantSidebar.vue`：只展示当前项目启用的侧边栏能力。
- `deploy/nginx/README.md`：记录项目化构建和部署校验命令。

## Task 1: Backend Manifest Models and Loader

**Files:**

- Create: `projects/default/project.yaml`
- Create: `modules/legacy/module.yaml`
- Create: `backend/app/project_config/__init__.py`
- Create: `backend/app/project_config/models.py`
- Create: `backend/app/project_config/loader.py`
- Test: `backend/tests/project_config/test_loader.py`

- [ ] **Step 1: Write failing loader contract tests**

Create `backend/tests/project_config/test_loader.py`:

```python
from pathlib import Path

import pytest

from app.project_config.loader import ProjectConfigError, load_project_context


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_default_project_loads_legacy_module():
    context = load_project_context("default", repo_root=REPO_ROOT)

    assert context.manifest.project == "default"
    assert context.enabled_modules == frozenset({"core", "legacy"})
    assert context.manifest.frontend.theme == "default"


def test_unknown_module_fails_closed(tmp_path: Path):
    (tmp_path / "projects" / "broken").mkdir(parents=True)
    (tmp_path / "modules").mkdir()
    (tmp_path / "projects" / "broken" / "project.yaml").write_text(
        "schema_version: 1\nproject: broken\nmodules: [missing]\n",
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="unknown module: missing"):
        load_project_context("broken", repo_root=tmp_path)


def test_missing_dependency_fails_closed(tmp_path: Path):
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    (tmp_path / "modules" / "noise").mkdir(parents=True)
    (tmp_path / "projects" / "demo" / "project.yaml").write_text(
        "schema_version: 1\nproject: demo\nmodules: [noise]\n",
        encoding="utf-8",
    )
    (tmp_path / "modules" / "noise" / "module.yaml").write_text(
        "schema_version: 1\nmodule: noise\ndependencies: [atmosphere]\n",
        encoding="utf-8",
    )

    with pytest.raises(ProjectConfigError, match="noise requires atmosphere"):
        load_project_context("demo", repo_root=tmp_path)


@pytest.mark.parametrize("project_id", ["../secret", "a/b", "", "UPPER CASE"])
def test_unsafe_project_identifier_is_rejected(project_id: str, tmp_path: Path):
    with pytest.raises(ProjectConfigError, match="invalid project identifier"):
        load_project_context(project_id, repo_root=tmp_path)
```

- [ ] **Step 2: Run the loader tests and verify the missing package failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/project_config/test_loader.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.project_config'`.

- [ ] **Step 3: Add the default project and legacy module manifests**

Create `projects/default/project.yaml`:

```yaml
schema_version: 1
project: default
modules:
  - legacy
frontend:
  theme: default
  features: {}
backend:
  tools: []
knowledge:
  collections: []
scheduled_tasks: []
```

Create `modules/legacy/module.yaml`:

```yaml
schema_version: 1
module: legacy
dependencies: []
```

- [ ] **Step 4: Implement strict Pydantic manifest models**

Create `backend/app/project_config/models.py`:

```python
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
    features: dict[str, bool] = Field(default_factory=dict)


class BackendManifest(StrictModel):
    tools: list[str] = Field(default_factory=list)

    _unique_tools = field_validator("tools")(unique)


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
```

- [ ] **Step 5: Implement repository-rooted loading and dependency validation**

Create `backend/app/project_config/loader.py`:

```python
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import ModuleManifest, ProjectContext, ProjectManifest, validate_identifier


class ProjectConfigError(RuntimeError):
    pass


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ProjectConfigError(f"manifest not found: {path}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProjectConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectConfigError(f"manifest must be an object: {path}")
    return value


def load_project_context(project_id: str, *, repo_root: Path | None = None) -> ProjectContext:
    try:
        validate_identifier(project_id)
    except ValueError as exc:
        raise ProjectConfigError(str(exc)) from exc

    root = (repo_root or repository_root()).resolve()
    project_path = root / "projects" / project_id / "project.yaml"
    try:
        project = ProjectManifest.model_validate(_read_yaml(project_path))
    except ValidationError as exc:
        raise ProjectConfigError(f"invalid project manifest {project_path}: {exc}") from exc
    if project.project != project_id:
        raise ProjectConfigError(
            f"project manifest id {project.project!r} does not match directory {project_id!r}"
        )

    modules: dict[str, ModuleManifest] = {}
    for module_id in project.modules:
        module_path = root / "modules" / module_id / "module.yaml"
        if not module_path.is_file():
            raise ProjectConfigError(f"unknown module: {module_id}")
        try:
            module = ModuleManifest.model_validate(_read_yaml(module_path))
        except ValidationError as exc:
            raise ProjectConfigError(f"invalid module manifest {module_path}: {exc}") from exc
        if module.module != module_id:
            raise ProjectConfigError(
                f"module manifest id {module.module!r} does not match directory {module_id!r}"
            )
        modules[module_id] = module

    selected = set(project.modules)
    for module_id, module in modules.items():
        for dependency in module.dependencies:
            if dependency not in selected:
                raise ProjectConfigError(f"{module_id} requires {dependency}")

    return ProjectContext(
        manifest=project,
        module_manifests=modules,
        enabled_modules=frozenset({"core", *selected}),
    )
```

Create `backend/app/project_config/__init__.py`:

```python
from .loader import ProjectConfigError, load_project_context
from .models import ProjectContext

__all__ = ["ProjectConfigError", "ProjectContext", "load_project_context"]
```

- [ ] **Step 6: Run focused tests and lint**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/project_config/test_loader.py -q
conda run -p /root/miniconda3/envs/backend_py311 ruff check backend/app/project_config backend/tests/project_config/test_loader.py
```

Expected: all loader tests pass and ruff reports no errors.

- [ ] **Step 7: Commit the manifest contract**

```bash
git add projects/default/project.yaml modules/legacy/module.yaml backend/app/project_config backend/tests/project_config/test_loader.py
git commit -m "feat: add project manifest contract"
```

## Task 2: Backend Project Selection and Public Runtime Summary

**Files:**

- Modify: `backend/config/settings.py`
- Modify: `backend/.env.example`
- Create: `backend/app/api/project_config_routes.py`
- Modify: `backend/app/core/routing.py`
- Test: `backend/tests/auth/test_auth_settings.py`
- Test: `backend/tests/api/test_project_runtime_config.py`

- [ ] **Step 1: Write failing settings and runtime summary tests**

Append to `backend/tests/auth/test_auth_settings.py`:

```python
def test_project_environment_selects_deployment(monkeypatch):
    monkeypatch.setenv("PROJECT", "jiyuan")

    value = Settings(_env_file=None)

    assert value.project_id == "jiyuan"
```

Create `backend/tests/api/test_project_runtime_config.py`:

```python
from app.api.project_config_routes import runtime_project_config
from app.project_config.loader import load_project_context


def test_runtime_project_config_contains_only_public_manifest_data():
    context = load_project_context("default")

    payload = runtime_project_config(context=context)

    assert payload == {
        "schemaVersion": 1,
        "project": "default",
        "modules": ["core", "legacy"],
        "frontend": {"theme": "default", "features": {}},
    }
```

- [ ] **Step 2: Run the tests and verify they fail for missing project support**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/auth/test_auth_settings.py::test_project_environment_selects_deployment backend/tests/api/test_project_runtime_config.py -q
```

Expected: failure because `Settings.project_id` and `project_config_routes` do not exist.

- [ ] **Step 3: Add the project selector to backend settings**

Add the following field near the server configuration fields in `backend/config/settings.py`:

```python
    project_id: str = Field(
        default="default",
        validation_alias="PROJECT",
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Deployment manifest selected from projects/<id>/project.yaml",
    )
```

Add this non-secret default to `backend/.env.example`, preserving all existing local edits:

```dotenv
PROJECT=default
```

- [ ] **Step 4: Implement a cached project context and public endpoint**

Create `backend/app/api/project_config_routes.py`:

```python
from functools import lru_cache

from fastapi import APIRouter, Depends

from app.project_config.loader import load_project_context
from app.project_config.models import ProjectContext
from config.settings import settings


router = APIRouter(prefix="/api/project", tags=["project-config"])


@lru_cache(maxsize=1)
def get_project_context() -> ProjectContext:
    return load_project_context(settings.project_id)


@router.get("/runtime-config")
def runtime_project_config(
    context: ProjectContext = Depends(get_project_context),
) -> dict:
    manifest = context.manifest
    return {
        "schemaVersion": manifest.schema_version,
        "project": manifest.project,
        "modules": sorted(context.enabled_modules),
        "frontend": manifest.frontend.model_dump(),
    }
```

Add this entry at the start of `ROUTER_REGISTRY` in `backend/app/core/routing.py`:

```python
    RouterSpec("app.api.project_config_routes", description="Project runtime configuration"),
```

- [ ] **Step 5: Run settings and endpoint tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/auth/test_auth_settings.py backend/tests/api/test_project_runtime_config.py -q
conda run -p /root/miniconda3/envs/backend_py311 ruff check backend/config/settings.py backend/app/api/project_config_routes.py
```

Expected: all selected tests pass and ruff reports no errors.

- [ ] **Step 6: Commit project selection and diagnostics**

```bash
git add backend/config/settings.py backend/.env.example backend/app/api/project_config_routes.py backend/app/core/routing.py backend/tests/auth/test_auth_settings.py backend/tests/api/test_project_runtime_config.py
git commit -m "feat: expose selected project configuration"
```

## Task 3: Module-Aware Backend Router Registration

**Files:**

- Modify: `backend/app/core/routing.py`
- Test: `backend/tests/project_config/test_routing.py`

- [ ] **Step 1: Write failing pure router-selection tests**

Create `backend/tests/project_config/test_routing.py`:

```python
from app.core.routing import RouterSpec, select_router_specs


def test_router_selection_keeps_core_and_enabled_modules():
    specs = [
        RouterSpec("app.core_route", owner="core"),
        RouterSpec("app.air_route", owner="atmosphere"),
        RouterSpec("app.noise_route", owner="noise"),
    ]

    selected = select_router_specs(specs, frozenset({"core", "noise"}))

    assert [spec.module for spec in selected] == ["app.core_route", "app.noise_route"]


def test_every_registered_router_has_an_explicit_owner():
    from app.core.routing import ROUTER_REGISTRY

    assert ROUTER_REGISTRY
    assert all(spec.owner in {"core", "legacy"} for spec in ROUTER_REGISTRY)
```

- [ ] **Step 2: Run the router tests and verify the missing owner failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/project_config/test_routing.py -q
```

Expected: failure because `RouterSpec.owner` and `select_router_specs` do not exist.

- [ ] **Step 3: Add explicit ownership and import-time filtering**

Update `RouterSpec` in `backend/app/core/routing.py`:

```python
@dataclass(frozen=True)
class RouterSpec:
    """Declarative router registration entry."""

    module: str
    attr: str = "router"
    prefix: Optional[str] = None
    optional: bool = False
    description: str = ""
    owner: str = "legacy"
```

Mark only `app.api.project_config_routes`, authentication, and system routes as `owner="core"`; leave every other current entry explicitly or implicitly owned by `legacy`. Add the pure selector:

```python
def select_router_specs(
    specs: list[RouterSpec],
    enabled_modules: frozenset[str],
) -> list[RouterSpec]:
    return [spec for spec in specs if spec.owner in enabled_modules]
```

Replace `include_routers` with:

```python
def include_routers(app: FastAPI) -> None:
    """Register routers enabled by the selected project manifest."""
    from app.api.project_config_routes import get_project_context

    context = get_project_context()
    for spec in select_router_specs(ROUTER_REGISTRY, context.enabled_modules):
        try:
            module = import_module(spec.module)
            router = getattr(module, spec.attr)
            if spec.prefix:
                app.include_router(router, prefix=spec.prefix)
            else:
                app.include_router(router)
            logger.info(
                "router_registered",
                module=spec.module,
                owner=spec.owner,
                project=context.manifest.project,
                prefix=spec.prefix,
                description=spec.description,
            )
        except Exception as exc:
            if spec.optional:
                logger.warning(
                    "optional_router_registration_failed",
                    module=spec.module,
                    owner=spec.owner,
                    error=str(exc),
                )
                continue
            raise
```

- [ ] **Step 4: Run router and startup contract tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/project_config/test_routing.py backend/tests/auth/test_uvicorn_startup_contract.py -q
conda run -p /root/miniconda3/envs/backend_py311 ruff check backend/app/core/routing.py backend/tests/project_config/test_routing.py
```

Expected: all selected tests pass and ruff reports no errors.

- [ ] **Step 5: Commit module-aware backend routing**

```bash
git add backend/app/core/routing.py backend/tests/project_config/test_routing.py
git commit -m "feat: filter backend routes by project modules"
```

## Task 4: Vite Project Manifest Loading

**Files:**

- Create: `frontend/scripts/projectManifest.mjs`
- Create: `frontend/scripts/projectManifest.test.mjs`
- Create: `frontend/src/config/projectConfig.js`
- Create: `frontend/src/config/projectConfig.test.js`
- Modify: `frontend/vite.config.js`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Install the YAML parser from the frontend source directory**

Run:

```bash
cd /home/xckj/suyuan/frontend
npm install --save-dev yaml@^2.8.1
```

Expected: `frontend/package.json` and `frontend/package-lock.json` record `yaml` as a dev dependency.

- [ ] **Step 2: Write failing Node tests for build-time loading**

Create `frontend/scripts/projectManifest.test.mjs`:

```javascript
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { resolve } from 'node:path'

import { loadProjectBuildConfig } from './projectManifest.mjs'


const repoRoot = resolve(import.meta.dirname, '../..')


test('default project enables core and legacy', () => {
  const config = loadProjectBuildConfig({ projectId: 'default', repoRoot })

  assert.equal(config.project, 'default')
  assert.deepEqual(config.modules, ['core', 'legacy'])
  assert.deepEqual(config.frontend, { theme: 'default', features: {} })
})


test('unsafe project identifiers fail before file access', () => {
  assert.throws(
    () => loadProjectBuildConfig({ projectId: '../secret', repoRoot }),
    /invalid project identifier/
  )
})
```

Create `frontend/src/config/projectConfig.test.js`:

```javascript
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { createProjectConfig } from './projectConfig.js'


test('project config exposes module and feature predicates', () => {
  const config = createProjectConfig({
    schemaVersion: 1,
    project: 'demo',
    modules: ['core', 'noise'],
    frontend: { theme: 'demo', features: { noiseMap: true } }
  })

  assert.equal(config.hasModule('noise'), true)
  assert.equal(config.hasModule('atmosphere'), false)
  assert.equal(config.hasFeature('noiseMap'), true)
  assert.equal(config.hasFeature('missing'), false)
})
```

- [ ] **Step 3: Run tests and verify missing modules fail**

Run:

```bash
cd /home/xckj/suyuan/frontend
node --test scripts/projectManifest.test.mjs src/config/projectConfig.test.js
```

Expected: failures because both imported files are absent.

- [ ] **Step 4: Implement the build-time YAML loader**

Create `frontend/scripts/projectManifest.mjs`:

```javascript
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { parse } from 'yaml'


const IDENTIFIER = /^[a-z][a-z0-9_-]*$/


function readYaml(path) {
  const value = parse(readFileSync(path, 'utf8'))
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`manifest must be an object: ${path}`)
  }
  return value
}


function uniqueStrings(values, field) {
  if (!Array.isArray(values) || !values.every(value => typeof value === 'string')) {
    throw new Error(`${field} must be an array of strings`)
  }
  if (new Set(values).size !== values.length) {
    throw new Error(`${field} contains duplicate entries`)
  }
  return values
}


export function loadProjectBuildConfig({ projectId, repoRoot }) {
  if (!IDENTIFIER.test(projectId)) {
    throw new Error(`invalid project identifier: ${projectId}`)
  }
  const manifest = readYaml(resolve(repoRoot, 'projects', projectId, 'project.yaml'))
  if (manifest.schema_version !== 1 || manifest.project !== projectId) {
    throw new Error(`invalid project manifest identity: ${projectId}`)
  }
  const selected = uniqueStrings(manifest.modules ?? [], 'modules')
  for (const moduleId of selected) {
    if (!IDENTIFIER.test(moduleId)) throw new Error(`invalid module identifier: ${moduleId}`)
    const moduleManifest = readYaml(resolve(repoRoot, 'modules', moduleId, 'module.yaml'))
    if (moduleManifest.schema_version !== 1 || moduleManifest.module !== moduleId) {
      throw new Error(`invalid module manifest identity: ${moduleId}`)
    }
    const dependencies = uniqueStrings(moduleManifest.dependencies ?? [], 'dependencies')
    for (const dependency of dependencies) {
      if (!selected.includes(dependency)) throw new Error(`${moduleId} requires ${dependency}`)
    }
  }
  return {
    schemaVersion: 1,
    project: projectId,
    modules: ['core', ...selected].sort(),
    frontend: {
      theme: manifest.frontend?.theme ?? 'default',
      features: manifest.frontend?.features ?? {}
    }
  }
}
```

- [ ] **Step 5: Implement the browser-side read-only facade**

Create `frontend/src/config/projectConfig.js`:

```javascript
export function createProjectConfig(value) {
  const modules = new Set(value.modules)
  const features = Object.freeze({ ...value.frontend.features })
  return Object.freeze({
    schemaVersion: value.schemaVersion,
    project: value.project,
    modules: Object.freeze([...modules]),
    theme: value.frontend.theme,
    features,
    hasModule: moduleId => modules.has(moduleId),
    hasFeature: featureId => features[featureId] === true
  })
}


const injected = typeof __SUYUAN_PROJECT_CONFIG__ === 'undefined'
  ? {
      schemaVersion: 1,
      project: 'default',
      modules: ['core', 'legacy'],
      frontend: { theme: 'default', features: {} }
    }
  : __SUYUAN_PROJECT_CONFIG__


export const projectConfig = createProjectConfig(injected)
```

- [ ] **Step 6: Inject the selected project from Vite and add a focused test script**

Update `frontend/vite.config.js` so the config callback loads the manifest before returning Vite options:

```javascript
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { loadProjectBuildConfig } from './scripts/projectManifest.mjs'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const projectConfig = loadProjectBuildConfig({
    projectId: env.PROJECT || 'default',
    repoRoot: resolve(__dirname, '..')
  })
  return {
    base: env.VITE_APP_BASE_PATH || '/',
    define: {
      __SUYUAN_PROJECT_CONFIG__: JSON.stringify(projectConfig)
    },
    plugins: [vue()],
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src')
      }
    },
    server: {
      port: 5174,
      host: '0.0.0.0',
      proxy: {
        '/api/auth': {
          target: env.VITE_AUTH_PROXY_TARGET || 'http://10.10.204.80:8025',
          changeOrigin: true,
          secure: false
        },
        '/api/suyuan/ws': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
          rewrite: path => path.replace(/^\/api\/suyuan/, '')
        },
        '/api/suyuan': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
          rewrite: path => path.replace(/^\/api\/suyuan/, '/api')
        },
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          secure: false
        }
      }
    }
  }
})
```

Add to `frontend/package.json` scripts:

```json
"test:project-config": "node --test scripts/projectManifest.test.mjs src/config/projectConfig.test.js"
```

- [ ] **Step 7: Run the manifest tests and default build**

Run:

```bash
cd /home/xckj/suyuan/frontend
npm run test:project-config
PROJECT=default npm run build:standalone
```

Expected: Node tests pass; Vite completes the standalone build into `frontend/dist`.

- [ ] **Step 8: Commit frontend manifest loading**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/scripts/projectManifest.mjs frontend/scripts/projectManifest.test.mjs frontend/src/config/projectConfig.js frontend/src/config/projectConfig.test.js
git commit -m "feat: load project manifest during frontend build"
```

## Task 5: Frontend Route and Sidebar Filtering

**Files:**

- Create: `frontend/src/router/projectRoutes.js`
- Create: `frontend/src/router/projectRoutes.test.js`
- Modify: `frontend/src/router/index.js`
- Create: `frontend/src/components/sidebarProjectModules.js`
- Create: `frontend/src/components/sidebarProjectModules.test.js`
- Modify: `frontend/src/components/AssistantSidebar.vue`

- [ ] **Step 1: Write failing pure filtering tests**

Create `frontend/src/router/projectRoutes.test.js`:

```javascript
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { filterProjectRoutes } from './projectRoutes.js'


test('routes without a requirement and enabled module routes remain', () => {
  const routes = [
    { path: '/login' },
    { path: '/air', meta: { requiredModule: 'atmosphere' } },
    { path: '/noise', meta: { requiredModule: 'noise' } }
  ]

  assert.deepEqual(
    filterProjectRoutes(routes, moduleId => moduleId === 'noise').map(route => route.path),
    ['/login', '/noise']
  )
})
```

Create `frontend/src/components/sidebarProjectModules.test.js`:

```javascript
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { filterSidebarModules } from './sidebarProjectModules.js'


test('sidebar excludes modules owned by disabled business modules', () => {
  const modules = [
    { id: 'new-task' },
    { id: 'air-map', requiredModule: 'atmosphere' },
    { id: 'noise-map', requiredModule: 'noise' }
  ]

  assert.deepEqual(
    filterSidebarModules(modules, moduleId => moduleId === 'noise').map(item => item.id),
    ['new-task', 'noise-map']
  )
})
```

- [ ] **Step 2: Run tests and verify missing helper failures**

Run:

```bash
cd /home/xckj/suyuan/frontend
node --test src/router/projectRoutes.test.js src/components/sidebarProjectModules.test.js
```

Expected: both tests fail because the helper modules are absent.

- [ ] **Step 3: Implement the pure filtering helpers**

Create `frontend/src/router/projectRoutes.js`:

```javascript
export function filterProjectRoutes(routes, hasModule) {
  return routes.filter(route => {
    const required = route.meta?.requiredModule
    return !required || hasModule(required)
  })
}
```

Create `frontend/src/components/sidebarProjectModules.js`:

```javascript
export function filterSidebarModules(modules, hasModule) {
  return modules.filter(item => !item.requiredModule || hasModule(item.requiredModule))
}
```

- [ ] **Step 4: Make Vue router creation module-aware without changing default routes**

In `frontend/src/router/index.js`, import the config and filter:

```javascript
import { projectConfig } from '@/config/projectConfig.js'
import { filterProjectRoutes } from './projectRoutes.js'
```

Move the current route array to `const routes = [...]`. Add `meta: { requiredModule: 'legacy' }` to current feature pages such as `/fetchers`, `/knowledge-base`, `/tools-management`, `/skills-management`, `/social-accounts`, and `/expert-deliberation`; keep `/login`, `/`, `/session/:id`, and the catch-all route available as core shell routes. Create the router with:

```javascript
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: filterProjectRoutes(routes, projectConfig.hasModule)
})
```

- [ ] **Step 5: Make the sidebar module list use the same predicate**

In the script section of `frontend/src/components/AssistantSidebar.vue`, add:

```javascript
import { projectConfig } from '@/config/projectConfig.js'
import { filterSidebarModules } from './sidebarProjectModules.js'
```

Rename the current literal to `const allModules = [...]`. Add `requiredModule: 'legacy'` to the existing management entries that are not part of the core conversation shell. Define the filtered list once:

```javascript
const modules = filterSidebarModules(allModules, projectConfig.hasModule)
```

Keep `settingsModules`, `moduleGroups`, icon lookup, and selection logic reading from `modules`, so disabled entries cannot be reached through either sidebar section.

- [ ] **Step 6: Expand the focused project configuration test command**

Update `test:project-config` in `frontend/package.json` after all four test files exist:

```json
"test:project-config": "node --test scripts/projectManifest.test.mjs src/config/projectConfig.test.js src/router/projectRoutes.test.js src/components/sidebarProjectModules.test.js"
```

- [ ] **Step 7: Run frontend filtering and existing sidebar contract tests**

Run:

```bash
cd /home/xckj/suyuan/frontend
npm run test:project-config
node --test src/components/agentPlatform/agentPlatformIntegration.test.js
```

Expected: project filtering tests and the existing sidebar integration contract pass.

- [ ] **Step 8: Commit frontend module filtering**

```bash
git add frontend/src/router/index.js frontend/src/router/projectRoutes.js frontend/src/router/projectRoutes.test.js frontend/src/components/AssistantSidebar.vue frontend/src/components/sidebarProjectModules.js frontend/src/components/sidebarProjectModules.test.js frontend/package.json
git commit -m "feat: filter frontend capabilities by project modules"
```

## Task 6: End-to-End Validation and Deployment Documentation

**Files:**

- Modify: `deploy/nginx/README.md`
- Verify: `frontend/dist/assets/*`

- [ ] **Step 1: Document exact project selection and release identity**

Add this section to `deploy/nginx/README.md`:

````markdown
## Project selection

Backend and frontend must use the same project identifier from `projects/<id>/project.yaml`.

```bash
export PROJECT=default
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 python -c \
  "from app.project_config.loader import load_project_context; print(load_project_context('$PROJECT').model_dump_json())"
cd /home/xckj/suyuan/frontend
npm run build:standalone
```

Record `PROJECT`, the Git commit SHA, and the project manifest checksum with each deployment. A customer release tag identifies a deployment snapshot, for example `jiyuan/v2026.07.1`; it does not create a permanent customer branch.
````

Run the Python validation command from `/home/xckj/suyuan/backend`, because its import root is the backend directory.

- [ ] **Step 2: Run all focused backend tests in the prescribed environment**

Run from `/home/xckj/suyuan`:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/project_config backend/tests/api/test_project_runtime_config.py backend/tests/auth/test_auth_settings.py backend/tests/auth/test_uvicorn_startup_contract.py -q
conda run -p /root/miniconda3/envs/backend_py311 ruff check backend/app/project_config backend/app/api/project_config_routes.py backend/app/core/routing.py backend/config/settings.py backend/tests/project_config backend/tests/api/test_project_runtime_config.py
```

Expected: all selected pytest tests pass and ruff reports no errors.

- [ ] **Step 3: Run all focused frontend tests**

Run:

```bash
cd /home/xckj/suyuan/frontend
npm run test:project-config
node --test src/components/agentPlatform/agentPlatformIntegration.test.js
```

Expected: all Node tests pass with zero failures.

- [ ] **Step 4: Build only from the canonical frontend source directory**

Run:

```bash
cd /home/xckj/suyuan/frontend
PROJECT=default npm run build:standalone
```

Expected: Vite exits successfully and writes the sole production bundle to `/home/xckj/suyuan/frontend/dist`.

- [ ] **Step 5: Verify required resource contracts in the built assets**

Run:

```bash
grep -R "resources?presentation_type=document" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/office-documents" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/visualizations" /home/xckj/suyuan/frontend/dist/assets
```

Expected: the unified resource interface is found; both legacy interface checks return no matches.

- [ ] **Step 6: Reload Nginx after the canonical build**

Run:

```bash
docker exec suyuan-nginx nginx -s reload
```

Expected: Nginx reports a successful reload.

- [ ] **Step 7: Verify backend and frontend report the same project**

With the backend running under `PROJECT=default`, run:

```bash
curl -fsS http://127.0.0.1:8000/api/project/runtime-config
```

Expected JSON fields:

```json
{
  "schemaVersion": 1,
  "project": "default",
  "modules": ["core", "legacy"],
  "frontend": {"theme": "default", "features": {}}
}
```

- [ ] **Step 8: Commit deployment documentation**

```bash
git add deploy/nginx/README.md
git commit -m "docs: document project-aware deployment"
```

## Completion Gate

Before declaring this phase complete, confirm all of the following from fresh command output:

- backend loader, routing, endpoint, settings, and startup tests pass;
- frontend manifest, route, sidebar, and existing sidebar integration tests pass;
- ruff reports no errors in changed Python files;
- `PROJECT=default npm run build:standalone` succeeds from `frontend`;
- the required unified resource string exists in `frontend/dist/assets`;
- the two legacy resource paths do not exist in `frontend/dist/assets`;
- Nginx reload succeeds;
- `git status --short` contains no unexpected files from this implementation;
- every implementation commit contains only the task boundary described above.
