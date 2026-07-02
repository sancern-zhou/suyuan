# Query Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the phase-one query-mode Guangdong dashboard: real online overview via existing data query tools, partial degradation, bottom chat overlay, structured Agent-driven focus, and traceable sources.

**Architecture:** Add a backend query-dashboard orchestration layer that calls existing Guangdong query tools and exposes a stable dashboard response contract. Add a query-mode-only frontend workspace under the current ReAct layout, reusing existing message/input behavior while rendering AMap-based overview layers, metric cards, focus state, and source details. Preserve existing non-query mode behavior.

**Tech Stack:** FastAPI, Pydantic v2-compatible models, existing `query_gd_suncere` tools, Vue 3 Composition API, Pinia, AMap loader, existing frontend test style with `.test.mjs`, backend pytest in `/root/miniconda3/envs/backend_py311`.

---

## File Map

Backend files:

- Create `backend/app/schemas/query_dashboard.py`
  - Pydantic response/request contract for overview modules, sources, focus metadata, and evidence metadata.
- Create `backend/app/services/query_dashboard_service.py`
  - Computes date ranges, calls existing Guangdong Suncere query tools, normalizes tool outputs into dashboard modules, and preserves partial failures.
- Create `backend/app/api/query_dashboard_routes.py`
  - FastAPI route for `GET /api/query-dashboard/guangdong-overview`.
- Modify `backend/app/core/routing.py`
  - Register `app.api.query_dashboard_routes` with `/api` prefix.
- Test `backend/tests/test_query_dashboard_service.py`
  - Unit tests for module normalization, source extraction, date range building, and partial failure.
- Test `backend/tests/test_query_dashboard_routes.py`
  - API route contract tests with mocked service.

Frontend files:

- Create `frontend/src/api/queryDashboard.js`
  - Fetch dashboard overview from `/api/query-dashboard/guangdong-overview`.
- Create `frontend/src/components/queryDashboard/dashboardFocus.js`
  - Normalize `dashboard_focus` and `answer_evidence` from messages/events.
- Create `frontend/src/components/queryDashboard/dashboardFocus.test.mjs`
  - Unit tests for focus extraction and fallback behavior.
- Create `frontend/src/components/queryDashboard/QueryDashboardWorkspace.vue`
  - Query-mode shell with map, metric cards, layer control, focus panel, source drawer, and floating chat.
- Create `frontend/src/components/queryDashboard/GuangdongOverviewMap.vue`
  - AMap canvas and layer rendering.
- Create `frontend/src/components/queryDashboard/DashboardMetricLayer.vue`
  - Floating realtime/month/year module cards.
- Create `frontend/src/components/queryDashboard/DashboardLayerControl.vue`
  - Layer toggles.
- Create `frontend/src/components/queryDashboard/DashboardFocusPanel.vue`
  - Current structured focus display.
- Create `frontend/src/components/queryDashboard/DashboardSourceDrawer.vue`
  - Traceability drawer.
- Modify `frontend/src/components/reactAnalysis/MainLayout.vue`
  - Branch query mode to `QueryDashboardWorkspace`; leave other modes unchanged.
- Modify `frontend/src/stores/reactStore.js`
  - Add query dashboard focus state and persist structured metadata from `complete`/`tool_result` events.
- Test `frontend/src/stores/react-store-query-dashboard.test.mjs`
  - Store tests for dashboard metadata propagation.

---

## Task 1: Backend Dashboard Contracts

**Files:**
- Create: `backend/app/schemas/query_dashboard.py`
- Test: `backend/tests/test_query_dashboard_service.py`

- [ ] **Step 1: Write failing schema tests**

Add this initial test file:

```python
from app.schemas.query_dashboard import (
    DashboardFocus,
    DashboardModule,
    DashboardOverviewResponse,
    DashboardSource,
)


def test_dashboard_overview_response_accepts_partial_modules():
    response = DashboardOverviewResponse(
        generated_at="2026-06-22T10:00:00+08:00",
        region="广东省",
        modules={
            "realtime": DashboardModule(
                status="success",
                summary={"AQI": 42},
                cities=[{"city": "广州", "AQI": 42}],
                sources=[
                    DashboardSource(
                        source_id="src_001",
                        tool_name="query_gd_suncere",
                        data_id="air_quality_unified:v1:abc",
                        query_params={"cities": ["广州"]},
                        record_count=1,
                        updated_at="2026-06-22T09:55:00+08:00",
                    )
                ],
            ),
            "year_to_date": DashboardModule(
                status="error",
                error={"message": "查询超时", "impact": "全年累计模块暂不可验证"},
            ),
        },
    )

    payload = response.model_dump()
    assert payload["success"] is True
    assert payload["modules"]["realtime"]["status"] == "success"
    assert payload["modules"]["year_to_date"]["status"] == "error"
    assert payload["modules"]["realtime"]["sources"][0]["data_id"] == "air_quality_unified:v1:abc"


def test_dashboard_focus_defaults_to_empty_lists():
    focus = DashboardFocus(scope="province")

    assert focus.scope == "province"
    assert focus.cities == []
    assert focus.stations == []
    assert focus.pollutants == []
    assert focus.source_data_ids == []
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_query_dashboard_service.py -q
```

Expected: import failure for `app.schemas.query_dashboard`.

- [ ] **Step 3: Add schema implementation**

Create `backend/app/schemas/query_dashboard.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DashboardStatus = Literal["idle", "loading", "success", "partial", "error", "stale"]


class DashboardSource(BaseModel):
    source_id: str
    tool_name: str
    data_id: str | None = None
    data_ids: list[str] = Field(default_factory=list)
    query_params: dict[str, Any] = Field(default_factory=dict)
    record_count: int | None = None
    updated_at: str | None = None
    generated_at: str | None = None
    sample_records: list[dict[str, Any]] = Field(default_factory=list)


class DashboardModule(BaseModel):
    status: DashboardStatus
    summary: dict[str, Any] = Field(default_factory=dict)
    cities: list[dict[str, Any]] = Field(default_factory=list)
    stations: list[dict[str, Any]] = Field(default_factory=list)
    rankings: list[dict[str, Any]] = Field(default_factory=list)
    city_metrics: list[dict[str, Any]] = Field(default_factory=list)
    heat_points: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[DashboardSource] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class DashboardFocusTimeRange(BaseModel):
    start: str | None = None
    end: str | None = None
    label: str | None = None


class DashboardFocus(BaseModel):
    scope: str = "province"
    cities: list[str] = Field(default_factory=list)
    stations: list[str] = Field(default_factory=list)
    pollutants: list[str] = Field(default_factory=list)
    time_range: DashboardFocusTimeRange | None = None
    modules: list[str] = Field(default_factory=list)
    layer_state: dict[str, bool] = Field(default_factory=dict)
    source_data_ids: list[str] = Field(default_factory=list)


class AnswerEvidenceClaim(BaseModel):
    text: str
    metrics: list[str] = Field(default_factory=list)
    source_data_ids: list[str] = Field(default_factory=list)


class AnswerEvidence(BaseModel):
    claims: list[AnswerEvidenceClaim] = Field(default_factory=list)
    query_params: dict[str, Any] = Field(default_factory=dict)


class DashboardOverviewResponse(BaseModel):
    success: bool = True
    generated_at: str
    region: str = "广东省"
    modules: dict[str, DashboardModule] = Field(default_factory=dict)
    sources: list[DashboardSource] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 4: Run schema tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_query_dashboard_service.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/query_dashboard.py backend/tests/test_query_dashboard_service.py
git commit -m "feat: add query dashboard schemas"
```

---

## Task 2: Backend Overview Orchestration Service

**Files:**
- Create: `backend/app/services/query_dashboard_service.py`
- Modify: `backend/tests/test_query_dashboard_service.py`

- [ ] **Step 1: Extend failing service tests**

Append tests to `backend/tests/test_query_dashboard_service.py`:

```python
from datetime import date

import pytest

from app.services.query_dashboard_service import (
    QueryDashboardService,
    build_default_date_ranges,
    extract_dashboard_source,
)


def test_build_default_date_ranges_uses_current_month_and_year():
    ranges = build_default_date_ranges(today=date(2026, 6, 22))

    assert ranges["realtime"]["start"].startswith("2026-06-22")
    assert ranges["month_to_date"] == {"start": "2026-06-01", "end": "2026-06-22"}
    assert ranges["year_to_date"] == {"start": "2026-01-01", "end": "2026-06-22"}


def test_extract_dashboard_source_reads_tool_result_metadata():
    result = {
        "data_id": "air_quality_unified:v1:abc",
        "total_count": 21,
        "metadata": {"query_params": {"cities": ["广州"]}},
        "data": [{"city": "广州", "AQI": 42}],
    }

    source = extract_dashboard_source("src_realtime", "query_gd_suncere", result)

    assert source.source_id == "src_realtime"
    assert source.tool_name == "query_gd_suncere"
    assert source.data_id == "air_quality_unified:v1:abc"
    assert source.record_count == 21
    assert source.query_params == {"cities": ["广州"]}
    assert source.sample_records == [{"city": "广州", "AQI": 42}]


class StubProvider:
    def __init__(self):
        self.calls = []

    def city_hour(self, **kwargs):
        self.calls.append(("city_hour", kwargs))
        return {
            "success": True,
            "data_id": "air_quality_5min:v1:realtime",
            "total_count": 1,
            "data": [{"city": "广州", "AQI": 42, "PM2_5": 18}],
            "metadata": {"query_params": kwargs},
        }

    def city_day(self, **kwargs):
        self.calls.append(("city_day", kwargs))
        return {
            "success": True,
            "data_id": f"air_quality_unified:v1:{kwargs['label']}",
            "total_count": 1,
            "data": [{"city": "广州", "PM2_5": 18, "O3_8h": 122}],
            "metadata": {"query_params": kwargs},
        }

    def station_hour(self, **kwargs):
        self.calls.append(("station_hour", kwargs))
        return {
            "success": True,
            "data_id": "air_quality_5min:v1:stations",
            "total_count": 1,
            "data": [{"station_name": "麓湖", "city": "广州", "lng": 113.29, "lat": 23.15, "AQI": 42}],
            "metadata": {"query_params": kwargs},
        }


def test_build_overview_returns_successful_modules_from_existing_tool_provider():
    provider = StubProvider()
    service = QueryDashboardService(provider=provider, today=date(2026, 6, 22))

    response = service.build_guangdong_overview(include=["realtime", "month_to_date", "year_to_date", "layers"])

    assert response.modules["realtime"].status == "success"
    assert response.modules["month_to_date"].status == "success"
    assert response.modules["year_to_date"].status == "success"
    assert response.modules["layers"].status == "success"
    assert response.modules["layers"].stations[0]["station_name"] == "麓湖"
    assert response.sources[0].tool_name == "query_gd_suncere"
    assert ("city_hour", provider.calls[0][1]) in provider.calls


def test_build_overview_keeps_partial_success_when_module_fails():
    class FailingProvider(StubProvider):
        def city_day(self, **kwargs):
            if kwargs["label"] == "year_to_date":
                raise RuntimeError("统计接口超时")
            return super().city_day(**kwargs)

    service = QueryDashboardService(provider=FailingProvider(), today=date(2026, 6, 22))

    response = service.build_guangdong_overview(include=["realtime", "month_to_date", "year_to_date"])

    assert response.success is True
    assert response.modules["realtime"].status == "success"
    assert response.modules["month_to_date"].status == "success"
    assert response.modules["year_to_date"].status == "error"
    assert response.modules["year_to_date"].error["message"] == "统计接口超时"
    assert response.errors[0]["module"] == "year_to_date"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_query_dashboard_service.py -q
```

Expected: import failure for `app.services.query_dashboard_service`.

- [ ] **Step 3: Add service implementation**

Create `backend/app/services/query_dashboard_service.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from app.schemas.query_dashboard import (
    DashboardModule,
    DashboardOverviewResponse,
    DashboardSource,
)
from app.tools.query.query_gd_suncere.tool import (
    GeoMappingResolver,
    execute_query_gd_suncere_city_day,
    execute_query_gd_suncere_station_hour_real,
    execute_query_gd_suncere_station_hour,
)


DEFAULT_CITY_NAMES = list(dict.fromkeys(GeoMappingResolver.CITY_CODE_MAP.keys()))[:21]


def build_default_date_ranges(today: date | None = None) -> dict[str, dict[str, str]]:
    current = today or date.today()
    current_text = current.isoformat()
    return {
        "realtime": {
            "start": f"{current_text} 00:00:00",
            "end": f"{current_text} 23:59:59",
        },
        "month_to_date": {
            "start": current.replace(day=1).isoformat(),
            "end": current_text,
        },
        "year_to_date": {
            "start": current.replace(month=1, day=1).isoformat(),
            "end": current_text,
        },
    }


def _records_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("records", "items", "rows", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def extract_dashboard_source(source_id: str, tool_name: str, result: dict[str, Any]) -> DashboardSource:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    records = _records_from_result(result)
    return DashboardSource(
        source_id=source_id,
        tool_name=tool_name,
        data_id=result.get("data_id") or metadata.get("data_id"),
        data_ids=result.get("data_ids") or [],
        query_params=metadata.get("query_params") or result.get("query_params") or {},
        record_count=result.get("total_count") or result.get("count") or len(records),
        updated_at=result.get("updated_at") or metadata.get("updated_at"),
        generated_at=datetime.now().astimezone().isoformat(),
        sample_records=records[:10],
    )


class GDSuncereDashboardProvider:
    def city_hour(self, **kwargs: Any) -> dict[str, Any]:
        return execute_query_gd_suncere_station_hour(**kwargs)

    def city_day(self, **kwargs: Any) -> dict[str, Any]:
        return execute_query_gd_suncere_city_day(**kwargs)

    def station_hour(self, **kwargs: Any) -> dict[str, Any]:
        return execute_query_gd_suncere_station_hour_real(**kwargs)


class QueryDashboardService:
    def __init__(self, provider: Any | None = None, today: date | None = None):
        self.provider = provider or GDSuncereDashboardProvider()
        self.today = today

    def build_guangdong_overview(self, include: Iterable[str] | None = None) -> DashboardOverviewResponse:
        requested = set(include or ["realtime", "month_to_date", "year_to_date", "layers"])
        ranges = build_default_date_ranges(self.today)
        modules: dict[str, DashboardModule] = {}
        sources: list[DashboardSource] = []
        errors: list[dict[str, Any]] = []

        builders = {
            "realtime": lambda: self._build_realtime(ranges["realtime"]),
            "month_to_date": lambda: self._build_period("month_to_date", ranges["month_to_date"]),
            "year_to_date": lambda: self._build_period("year_to_date", ranges["year_to_date"]),
            "layers": lambda: self._build_layers(ranges["realtime"]),
        }

        for module_name, builder in builders.items():
            if module_name not in requested:
                continue
            try:
                module = builder()
            except Exception as exc:
                module = DashboardModule(
                    status="error",
                    error={
                        "message": str(exc),
                        "impact": f"{module_name} 模块暂不可验证",
                    },
                )
                errors.append({"module": module_name, "message": str(exc)})
            modules[module_name] = module
            sources.extend(module.sources)

        return DashboardOverviewResponse(
            generated_at=datetime.now().astimezone().isoformat(),
            modules=modules,
            sources=sources,
            errors=errors,
        )

    def _build_realtime(self, time_range: dict[str, str]) -> DashboardModule:
        result = self.provider.city_hour(
            cities=DEFAULT_CITY_NAMES,
            start_time=time_range["start"],
            end_time=time_range["end"],
            label="realtime",
        )
        source = extract_dashboard_source("src_realtime", "query_gd_suncere", result)
        records = _records_from_result(result)
        return DashboardModule(
            status="success",
            summary={"record_count": len(records), "time_range": time_range},
            cities=records,
            sources=[source],
        )

    def _build_period(self, label: str, time_range: dict[str, str]) -> DashboardModule:
        result = self.provider.city_day(
            cities=DEFAULT_CITY_NAMES,
            start_date=time_range["start"],
            end_date=time_range["end"],
            label=label,
        )
        source = extract_dashboard_source(f"src_{label}", "query_gd_suncere", result)
        records = _records_from_result(result)
        return DashboardModule(
            status="success",
            summary={"record_count": len(records), "time_range": time_range},
            rankings=records,
            city_metrics=records,
            sources=[source],
        )

    def _build_layers(self, time_range: dict[str, str]) -> DashboardModule:
        result = self.provider.station_hour(
            stations=[],
            start_time=time_range["start"],
            end_time=time_range["end"],
            label="layers",
        )
        source = extract_dashboard_source("src_layers", "query_gd_suncere", result)
        records = _records_from_result(result)
        heat_points = [
            {
                "lng": row.get("lng") or row.get("longitude"),
                "lat": row.get("lat") or row.get("latitude"),
                "value": row.get("AQI") or row.get("PM2_5") or row.get("O3_8h"),
                "city": row.get("city"),
                "station_name": row.get("station_name") or row.get("name"),
            }
            for row in records
            if (row.get("lng") or row.get("longitude")) and (row.get("lat") or row.get("latitude"))
        ]
        return DashboardModule(
            status="success",
            summary={"record_count": len(records), "time_range": time_range},
            stations=records,
            heat_points=heat_points,
            sources=[source],
        )
```

- [ ] **Step 4: Run service tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_query_dashboard_service.py -q
```

Expected: all tests in this file pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/query_dashboard_service.py backend/tests/test_query_dashboard_service.py
git commit -m "feat: orchestrate query dashboard overview"
```

---

## Task 3: Backend API Route

**Files:**
- Create: `backend/app/api/query_dashboard_routes.py`
- Modify: `backend/app/core/routing.py`
- Test: `backend/tests/test_query_dashboard_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `backend/tests/test_query_dashboard_routes.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import query_dashboard_routes
from app.schemas.query_dashboard import DashboardModule, DashboardOverviewResponse


class StubService:
    def __init__(self):
        self.include = None

    def build_guangdong_overview(self, include=None):
        self.include = include
        return DashboardOverviewResponse(
            generated_at="2026-06-22T10:00:00+08:00",
            modules={
                "realtime": DashboardModule(
                    status="success",
                    summary={"record_count": 1},
                    cities=[{"city": "广州", "AQI": 42}],
                )
            },
        )


def test_get_guangdong_overview_returns_dashboard_contract():
    service = StubService()
    app = FastAPI()
    app.dependency_overrides[query_dashboard_routes.get_query_dashboard_service] = lambda: service
    app.include_router(query_dashboard_routes.router, prefix="/api")

    response = TestClient(app).get("/api/query-dashboard/guangdong-overview?include=realtime,layers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["modules"]["realtime"]["cities"][0]["city"] == "广州"
    assert service.include == ["realtime", "layers"]
```

- [ ] **Step 2: Run route tests to verify failure**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_query_dashboard_routes.py -q
```

Expected: import failure for `app.api.query_dashboard_routes`.

- [ ] **Step 3: Add API route**

Create `backend/app/api/query_dashboard_routes.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.query_dashboard import DashboardOverviewResponse
from app.services.query_dashboard_service import QueryDashboardService

router = APIRouter(prefix="/query-dashboard", tags=["query-dashboard"])


def get_query_dashboard_service() -> QueryDashboardService:
    return QueryDashboardService()


def _parse_include(include: str | None) -> list[str] | None:
    if not include:
        return None
    return [item.strip() for item in include.split(",") if item.strip()]


@router.get("/guangdong-overview", response_model=DashboardOverviewResponse)
def get_guangdong_overview(
    include: str | None = Query(default=None),
    service: QueryDashboardService = Depends(get_query_dashboard_service),
) -> DashboardOverviewResponse:
    return service.build_guangdong_overview(include=_parse_include(include))
```

- [ ] **Step 4: Register router**

Modify `backend/app/core/routing.py` by inserting the query dashboard route after basic API routes:

```python
RouterSpec("app.api.query_dashboard_routes", prefix="/api", description="Query dashboard API"),
```

The surrounding registry should include:

```python
ROUTER_REGISTRY = [
    RouterSpec("app.routers.admin", description="Admin interface"),
    RouterSpec("app.routers.agent", description="ReAct Agent API"),
    RouterSpec("app.api.routes", prefix="/api", description="Basic API routes"),
    RouterSpec("app.api.query_dashboard_routes", prefix="/api", description="Query dashboard API"),
    RouterSpec("app.api.knowledge_base_routes", prefix="/api", description="Knowledge Base API"),
```

- [ ] **Step 5: Run route and service tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_query_dashboard_service.py tests/test_query_dashboard_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/query_dashboard_routes.py backend/app/core/routing.py backend/tests/test_query_dashboard_routes.py
git commit -m "feat: expose query dashboard overview api"
```

---

## Task 4: Frontend API And Focus Utilities

**Files:**
- Create: `frontend/src/api/queryDashboard.js`
- Create: `frontend/src/components/queryDashboard/dashboardFocus.js`
- Test: `frontend/src/components/queryDashboard/dashboardFocus.test.mjs`

- [ ] **Step 1: Write failing frontend tests**

Create `frontend/src/components/queryDashboard/dashboardFocus.test.mjs`:

```javascript
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  extractDashboardFocusFromMessages,
  normalizeDashboardFocus,
  normalizeLayerState
} from './dashboardFocus.js'

test('normalizeDashboardFocus fills stable defaults', () => {
  const focus = normalizeDashboardFocus({
    scope: 'city',
    cities: '广州',
    pollutants: ['O3_8h'],
    layer_state: { heatmap: true }
  })

  assert.equal(focus.scope, 'city')
  assert.deepEqual(focus.cities, ['广州'])
  assert.deepEqual(focus.stations, [])
  assert.deepEqual(focus.pollutants, ['O3_8h'])
  assert.deepEqual(focus.layer_state, { city_metrics: false, stations: false, heatmap: true })
})

test('extractDashboardFocusFromMessages prefers latest final message metadata', () => {
  const messages = [
    { type: 'final', data: { dashboard_focus: { scope: 'province' } } },
    { type: 'tool_result', data: { result: { dashboard_focus: { scope: 'station', stations: ['麓湖'] } } } },
    { type: 'final', data: { dashboard_focus: { scope: 'city', cities: ['广州'] } } }
  ]

  const focus = extractDashboardFocusFromMessages(messages)

  assert.equal(focus.scope, 'city')
  assert.deepEqual(focus.cities, ['广州'])
})

test('normalizeLayerState only enables known layers', () => {
  assert.deepEqual(
    normalizeLayerState({ city_metrics: true, unknown: true }),
    { city_metrics: true, stations: false, heatmap: false }
  )
})
```

- [ ] **Step 2: Run focus tests to verify failure**

Run:

```bash
cd frontend
node --test src/components/queryDashboard/dashboardFocus.test.mjs
```

Expected: import failure for `dashboardFocus.js`.

- [ ] **Step 3: Add focus utilities**

Create `frontend/src/components/queryDashboard/dashboardFocus.js`:

```javascript
const KNOWN_LAYERS = ['city_metrics', 'stations', 'heatmap']

const toList = (value) => {
  if (Array.isArray(value)) return value.filter(Boolean).map(String)
  if (value === null || value === undefined || value === '') return []
  return [String(value)]
}

export const normalizeLayerState = (layerState = {}) => {
  const normalized = {}
  for (const key of KNOWN_LAYERS) {
    normalized[key] = Boolean(layerState?.[key])
  }
  return normalized
}

export const normalizeDashboardFocus = (raw = {}) => ({
  scope: raw.scope || 'province',
  cities: toList(raw.cities),
  stations: toList(raw.stations),
  pollutants: toList(raw.pollutants),
  time_range: raw.time_range || null,
  modules: toList(raw.modules),
  layer_state: normalizeLayerState(raw.layer_state),
  source_data_ids: toList(raw.source_data_ids)
})

const focusFromMessage = (message) => {
  if (!message) return null
  const data = message.data || {}
  return data.dashboard_focus ||
    data.result?.dashboard_focus ||
    data.result?.metadata?.dashboard_focus ||
    null
}

export const extractDashboardFocusFromMessages = (messages = []) => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message?.type !== 'final' && message?.type !== 'tool_result') continue
    const focus = focusFromMessage(message)
    if (focus) return normalizeDashboardFocus(focus)
  }
  return normalizeDashboardFocus()
}
```

- [ ] **Step 4: Add overview API wrapper**

Create `frontend/src/api/queryDashboard.js`:

```javascript
const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function fetchGuangdongOverview(options = {}) {
  const params = new URLSearchParams()
  if (Array.isArray(options.include) && options.include.length > 0) {
    params.set('include', options.include.join(','))
  }
  if (options.forceRefresh) {
    params.set('force_refresh', 'true')
  }
  const query = params.toString()
  const response = await fetch(`${API_BASE_URL}/query-dashboard/guangdong-overview${query ? `?${query}` : ''}`, {
    cache: 'no-store'
  })
  if (!response.ok) {
    throw new Error(`广东总览数据加载失败：${response.status}`)
  }
  return await response.json()
}
```

- [ ] **Step 5: Run focus tests**

Run:

```bash
cd frontend
node --test src/components/queryDashboard/dashboardFocus.test.mjs
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/queryDashboard.js frontend/src/components/queryDashboard/dashboardFocus.js frontend/src/components/queryDashboard/dashboardFocus.test.mjs
git commit -m "feat: add query dashboard frontend helpers"
```

---

## Task 5: Store Query Dashboard Metadata

**Files:**
- Modify: `frontend/src/stores/reactStore.js`
- Test: `frontend/src/stores/react-store-query-dashboard.test.mjs`

- [ ] **Step 1: Write failing store tests**

Create `frontend/src/stores/react-store-query-dashboard.test.mjs`:

```javascript
import assert from 'node:assert/strict'
import test from 'node:test'

function applyDashboardMetadata(state, data = {}) {
  const focus = data.dashboard_focus || data.result?.dashboard_focus || null
  const evidence = data.answer_evidence || data.result?.answer_evidence || null
  if (focus) state.dashboardFocus = focus
  if (evidence) state.answerEvidence = evidence
  return state
}

test('query dashboard metadata can be applied without losing final answer', () => {
  const state = {
    finalAnswer: '广州臭氧偏高',
    dashboardFocus: null,
    answerEvidence: null
  }

  applyDashboardMetadata(state, {
    dashboard_focus: { scope: 'city', cities: ['广州'] },
    answer_evidence: { claims: [{ text: 'O3 偏高' }] }
  })

  assert.equal(state.finalAnswer, '广州臭氧偏高')
  assert.deepEqual(state.dashboardFocus, { scope: 'city', cities: ['广州'] })
  assert.deepEqual(state.answerEvidence, { claims: [{ text: 'O3 偏高' }] })
})
```

This test documents expected state behavior before editing the large store. Add a store-native test if the project already has a helper for instantiating Pinia stores in Node; otherwise keep this focused contract test.

- [ ] **Step 2: Run store contract test**

Run:

```bash
cd frontend
node --test src/stores/react-store-query-dashboard.test.mjs
```

Expected: pass, establishing the contract before store edit.

- [ ] **Step 3: Add state fields to `createEmptyModeState`**

In `frontend/src/stores/reactStore.js`, extend the object returned by `createEmptyModeState()` with:

```javascript
  dashboardFocus: null,
  answerEvidence: null,
  dashboardOverview: null,
```

Place these next to other mode-scoped UI result fields such as `currentVisualization` and `visualizationHistory`.

- [ ] **Step 4: Persist dashboard fields**

In `_persistModeState`, include:

```javascript
        dashboardFocus: modeState.dashboardFocus,
        answerEvidence: modeState.answerEvidence,
        dashboardOverview: modeState.dashboardOverview,
```

In the restore path that rebuilds mode state from saved session data, copy the same fields when present:

```javascript
      if (sessionData.dashboardFocus) {
        this.currentState.dashboardFocus = sessionData.dashboardFocus
      }
      if (sessionData.answerEvidence) {
        this.currentState.answerEvidence = sessionData.answerEvidence
      }
      if (sessionData.dashboardOverview) {
        this.currentState.dashboardOverview = sessionData.dashboardOverview
      }
```

- [ ] **Step 5: Add dashboard metadata helper in store actions**

Inside `actions`, add:

```javascript
    applyDashboardMetadata(data = {}, targetState = this.currentState) {
      const focus = data?.dashboard_focus || data?.result?.dashboard_focus || data?.result?.metadata?.dashboard_focus || null
      const evidence = data?.answer_evidence || data?.result?.answer_evidence || data?.result?.metadata?.answer_evidence || null
      if (focus) {
        targetState.dashboardFocus = focus
      }
      if (evidence) {
        targetState.answerEvidence = evidence
      }
    },
```

- [ ] **Step 6: Call helper for `tool_result` and `complete` events**

In the `tool_result` branch after `const data = event.data || {}` is available and before/after visualization handling, add:

```javascript
          this.applyDashboardMetadata(data, targetState)
```

In the `complete` branch, after `targetState.isComplete = true`, add:

```javascript
          this.applyDashboardMetadata(data, targetState)
```

When merging or adding final messages, include the metadata:

```javascript
              dashboard_focus: data?.dashboard_focus || null,
              answer_evidence: data?.answer_evidence || null,
```

- [ ] **Step 7: Run frontend store and helper tests**

Run:

```bash
cd frontend
node --test src/stores/react-store-query-dashboard.test.mjs src/components/queryDashboard/dashboardFocus.test.mjs
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/stores/reactStore.js frontend/src/stores/react-store-query-dashboard.test.mjs
git commit -m "feat: persist query dashboard focus metadata"
```

---

## Task 6: Query Dashboard Workspace Layout

**Files:**
- Create: `frontend/src/components/queryDashboard/QueryDashboardWorkspace.vue`
- Create: `frontend/src/components/queryDashboard/DashboardMetricLayer.vue`
- Create: `frontend/src/components/queryDashboard/DashboardLayerControl.vue`
- Create: `frontend/src/components/queryDashboard/DashboardFocusPanel.vue`
- Create: `frontend/src/components/queryDashboard/DashboardSourceDrawer.vue`
- Modify: `frontend/src/components/reactAnalysis/MainLayout.vue`

- [ ] **Step 1: Add metric layer component**

Create `frontend/src/components/queryDashboard/DashboardMetricLayer.vue`:

```vue
<template>
  <section class="metric-layer" aria-label="广东省数据总览指标">
    <article
      v-for="module in moduleCards"
      :key="module.key"
      class="metric-card"
      :class="[`status-${module.status}`, { active: activeModules.includes(module.key) }]"
    >
      <header>
        <span>{{ module.title }}</span>
        <button type="button" @click="$emit('open-source', module.key)">来源</button>
      </header>
      <div v-if="module.status === 'loading'" class="metric-state">加载中</div>
      <div v-else-if="module.status === 'error'" class="metric-state error">{{ module.error?.message || '加载失败' }}</div>
      <dl v-else class="metric-values">
        <div v-for="item in module.metrics" :key="item.label">
          <dt>{{ item.label }}</dt>
          <dd>{{ item.value }}</dd>
        </div>
      </dl>
    </article>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modules: {
    type: Object,
    default: () => ({})
  },
  loadingModules: {
    type: Array,
    default: () => []
  },
  activeModules: {
    type: Array,
    default: () => []
  }
})

defineEmits(['open-source'])

const titles = {
  realtime: '实时',
  month_to_date: '当月累计',
  year_to_date: '全年累计'
}

const moduleCards = computed(() => {
  return ['realtime', 'month_to_date', 'year_to_date'].map((key) => {
    const module = props.modules?.[key] || {}
    const status = props.loadingModules.includes(key) ? 'loading' : (module.status || 'idle')
    const summary = module.summary || {}
    return {
      key,
      title: titles[key],
      status,
      error: module.error,
      metrics: [
        { label: '记录数', value: summary.record_count ?? '-' },
        { label: '更新时间', value: summary.time_range?.end || '-' }
      ]
    }
  })
})
</script>

<style scoped>
.metric-layer {
  position: absolute;
  top: 16px;
  left: 16px;
  right: 16px;
  z-index: 20;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  pointer-events: none;
}
.metric-card {
  pointer-events: auto;
  min-height: 88px;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  padding: 10px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}
.metric-card.active {
  border-color: #1976d2;
  box-shadow: 0 0 0 2px rgba(25, 118, 210, 0.14);
}
.metric-card header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
}
.metric-card button {
  border: 0;
  background: transparent;
  color: #1976d2;
  cursor: pointer;
}
.metric-values {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin: 10px 0 0;
}
.metric-values dt {
  color: #64748b;
  font-size: 12px;
}
.metric-values dd {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
}
.metric-state {
  margin-top: 12px;
  color: #64748b;
  font-size: 13px;
}
.metric-state.error {
  color: #b42318;
}
</style>
```

- [ ] **Step 2: Add layer control component**

Create `frontend/src/components/queryDashboard/DashboardLayerControl.vue`:

```vue
<template>
  <aside class="layer-control" aria-label="地图图层控制">
    <label v-for="layer in layers" :key="layer.key">
      <input
        type="checkbox"
        :checked="modelValue[layer.key]"
        @change="$emit('update:layer', { key: layer.key, value: $event.target.checked })"
      />
      <span>{{ layer.label }}</span>
    </label>
  </aside>
</template>

<script setup>
defineProps({
  modelValue: {
    type: Object,
    default: () => ({ city_metrics: true, stations: true, heatmap: false })
  }
})
defineEmits(['update:layer'])

const layers = [
  { key: 'city_metrics', label: '城市指标' },
  { key: 'stations', label: '站点' },
  { key: 'heatmap', label: '热力' }
]
</script>

<style scoped>
.layer-control {
  position: absolute;
  top: 128px;
  right: 16px;
  z-index: 20;
  display: grid;
  gap: 8px;
  min-width: 118px;
  padding: 10px;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}
.layer-control label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
</style>
```

- [ ] **Step 3: Add focus panel and source drawer**

Create `frontend/src/components/queryDashboard/DashboardFocusPanel.vue`:

```vue
<template>
  <aside v-if="focus" class="focus-panel" aria-label="当前问数焦点">
    <strong>{{ scopeLabel }}</strong>
    <span v-if="focus.cities?.length">城市：{{ focus.cities.join('、') }}</span>
    <span v-if="focus.stations?.length">站点：{{ focus.stations.join('、') }}</span>
    <span v-if="focus.pollutants?.length">指标：{{ focus.pollutants.join('、') }}</span>
    <span v-if="focus.time_range?.label">时间：{{ focus.time_range.label }}</span>
  </aside>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  focus: {
    type: Object,
    default: null
  }
})

const scopeLabel = computed(() => {
  const map = { province: '全省焦点', city: '城市焦点', station: '站点焦点', pollutant: '污染物焦点', time_range: '时间焦点' }
  return map[props.focus?.scope] || '当前焦点'
})
</script>

<style scoped>
.focus-panel {
  position: absolute;
  left: 16px;
  bottom: 148px;
  z-index: 20;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  max-width: min(760px, calc(100% - 32px));
  padding: 10px 12px;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  font-size: 13px;
}
</style>
```

Create `frontend/src/components/queryDashboard/DashboardSourceDrawer.vue`:

```vue
<template>
  <aside v-if="visible" class="source-drawer" aria-label="数据来源">
    <header>
      <strong>数据来源</strong>
      <button type="button" @click="$emit('close')">关闭</button>
    </header>
    <div v-if="sources.length === 0" class="empty">暂无来源</div>
    <article v-for="source in sources" :key="source.source_id || source.data_id" class="source-item">
      <h4>{{ source.tool_name || '未知工具' }}</h4>
      <p>data_id：{{ source.data_id || source.data_ids?.join('、') || '-' }}</p>
      <p>记录数：{{ source.record_count ?? '-' }}</p>
      <pre>{{ JSON.stringify(source.query_params || {}, null, 2) }}</pre>
    </article>
  </aside>
</template>

<script setup>
defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  sources: {
    type: Array,
    default: () => []
  }
})
defineEmits(['close'])
</script>

<style scoped>
.source-drawer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 40;
  width: min(420px, 92vw);
  overflow: auto;
  border-left: 1px solid #d9e2ec;
  background: #fff;
  box-shadow: -16px 0 36px rgba(15, 23, 42, 0.14);
}
.source-drawer header {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #e5eaf0;
  background: #fff;
}
.source-drawer button {
  border: 1px solid #d9e2ec;
  border-radius: 6px;
  background: #fff;
  padding: 5px 8px;
  cursor: pointer;
}
.source-item {
  padding: 14px 16px;
  border-bottom: 1px solid #eef2f6;
}
.source-item h4 {
  margin: 0 0 8px;
}
.source-item p {
  margin: 4px 0;
  font-size: 13px;
  color: #475569;
}
.source-item pre {
  overflow: auto;
  padding: 8px;
  border-radius: 6px;
  background: #f8fafc;
  font-size: 12px;
}
.empty {
  padding: 16px;
  color: #64748b;
}
</style>
```

- [ ] **Step 4: Add workspace component**

Create `frontend/src/components/queryDashboard/QueryDashboardWorkspace.vue`:

```vue
<template>
  <section class="query-dashboard">
    <GuangdongOverviewMap
      class="dashboard-map"
      :overview="overview"
      :focus="focus"
      :layers="layers"
    />

    <DashboardMetricLayer
      :modules="overview?.modules || {}"
      :loading-modules="loadingModules"
      :active-modules="focus?.modules || []"
      @open-source="openModuleSources"
    />

    <DashboardLayerControl
      :model-value="layers"
      @update:layer="updateLayer"
    />

    <DashboardFocusPanel :focus="focus" />

    <div class="chat-overlay">
      <ReActMessageList
        :messages="messages"
        :show-reflexion="showReflexion"
        :reflexion-count="reflexionCount"
        :use-markdown="true"
        :assistant-mode="assistantMode"
        :selected-message-id="selectedMessageId"
        :on-message-click="messageId => $emit('select-message', messageId)"
        :has-more-messages="hasMoreMessages"
        :total-message-count="totalMessageCount"
        :loading-more="loadingMore"
        @load-more="$emit('load-more')"
      />
      <InputBox
        :model-value="currentMessage"
        :pending-steering-inputs="pendingSteeringInputs"
        :session-id="sessionId"
        :disabled="inputDisabled"
        :is-analyzing="isAnalyzing"
        :assistant-mode="assistantMode"
        :use-reranker="useReranker"
        @send="$emit('send', $event)"
        @pause="$emit('pause')"
        @update:useReranker="$emit('update:useReranker', $event)"
        @update:agentMode="$emit('update:agentMode', $event)"
      />
    </div>

    <DashboardSourceDrawer
      :visible="sourceDrawerVisible"
      :sources="drawerSources"
      @close="sourceDrawerVisible = false"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import InputBox from '@/components/InputBox.vue'
import ReActMessageList from '@/components/ReActMessageList.vue'
import { fetchGuangdongOverview } from '@/api/queryDashboard'
import { extractDashboardFocusFromMessages, normalizeDashboardFocus } from './dashboardFocus'
import DashboardFocusPanel from './DashboardFocusPanel.vue'
import DashboardLayerControl from './DashboardLayerControl.vue'
import DashboardMetricLayer from './DashboardMetricLayer.vue'
import DashboardSourceDrawer from './DashboardSourceDrawer.vue'
import GuangdongOverviewMap from './GuangdongOverviewMap.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  pendingSteeringInputs: { type: Array, default: () => [] },
  isAnalyzing: { type: Boolean, default: false },
  inputDisabled: { type: Boolean, default: false },
  currentMessage: { type: String, default: '' },
  sessionId: { type: String, default: '' },
  selectedMessageId: { type: String, default: null },
  showReflexion: { type: Boolean, default: false },
  reflexionCount: { type: Number, default: 0 },
  assistantMode: { type: String, default: 'general-agent' },
  useReranker: { type: Boolean, default: false },
  hasMoreMessages: { type: Boolean, default: false },
  totalMessageCount: { type: Number, default: 0 },
  loadingMore: { type: Boolean, default: false },
  dashboardFocus: { type: Object, default: null }
})

defineEmits([
  'send',
  'pause',
  'update:useReranker',
  'update:agentMode',
  'select-message',
  'load-more'
])

const overview = ref(null)
const loadingModules = ref(['realtime', 'month_to_date', 'year_to_date', 'layers'])
const sourceDrawerVisible = ref(false)
const drawerSources = ref([])
const layers = ref({ city_metrics: true, stations: true, heatmap: false })

const focus = computed(() => {
  return props.dashboardFocus
    ? normalizeDashboardFocus(props.dashboardFocus)
    : extractDashboardFocusFromMessages(props.messages)
})

const loadOverview = async () => {
  loadingModules.value = ['realtime', 'month_to_date', 'year_to_date', 'layers']
  try {
    overview.value = await fetchGuangdongOverview({
      include: ['realtime', 'month_to_date', 'year_to_date', 'layers']
    })
  } finally {
    loadingModules.value = []
  }
}

const updateLayer = ({ key, value }) => {
  layers.value = { ...layers.value, [key]: value }
}

const openModuleSources = (moduleKey) => {
  const module = overview.value?.modules?.[moduleKey]
  drawerSources.value = module?.sources || []
  sourceDrawerVisible.value = true
}

onMounted(loadOverview)
</script>

<style scoped>
.query-dashboard {
  position: relative;
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow: hidden;
  background: #eef3f7;
}
.dashboard-map {
  position: absolute;
  inset: 0;
}
.chat-overlay {
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 16px;
  z-index: 30;
  display: grid;
  grid-template-rows: minmax(80px, 180px) auto;
  overflow: hidden;
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.16);
}
.chat-overlay :deep(.message-list),
.chat-overlay :deep(.react-message-list) {
  min-height: 0;
}
</style>
```

- [ ] **Step 5: Branch MainLayout for query mode**

Modify `frontend/src/components/reactAnalysis/MainLayout.vue`.

Add import:

```javascript
import QueryDashboardWorkspace from '@/components/queryDashboard/QueryDashboardWorkspace.vue'
```

In the template inside `.analysis-panel`, render `QueryDashboardWorkspace` before the existing `ChatArea`:

```vue
      <QueryDashboardWorkspace
        v-if="agentMode === 'query'"
        :messages="messages"
        :pending-steering-inputs="pendingSteeringInputs"
        :is-analyzing="isAnalyzing"
        :input-disabled="inputDisabled"
        :current-message="currentMessage"
        :session-id="sessionId"
        :selected-message-id="selectedMessageId"
        :show-reflexion="showReflexion"
        :reflexion-count="reflexionCount"
        :assistant-mode="activeModule"
        :use-reranker="useReranker"
        :has-more-messages="hasMoreMessages"
        :total-message-count="totalMessageCount"
        :loading-more="loadingMore"
        :dashboard-focus="messages?.length ? null : null"
        @send="handleSend"
        @pause="handlePause"
        @update:useReranker="handleRerankerChange"
        @update:agentMode="handleAgentModeChange"
        @select-message="handleSelectMessage"
        @load-more="handleLoadMore"
      />

      <ChatArea
        v-else
```

Keep the rest of the existing `ChatArea` props and slots unchanged.

- [ ] **Step 6: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: build exits 0. Existing Sass/chunk-size warnings are acceptable.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/queryDashboard frontend/src/components/reactAnalysis/MainLayout.vue
git commit -m "feat: add query dashboard workspace"
```

---

## Task 7: AMap Overview Layer Rendering

**Files:**
- Create: `frontend/src/components/queryDashboard/GuangdongOverviewMap.vue`

- [ ] **Step 1: Add AMap component**

Create `frontend/src/components/queryDashboard/GuangdongOverviewMap.vue`:

```vue
<template>
  <div class="guangdong-map">
    <div ref="mapContainer" class="map-container"></div>
    <div v-if="loading" class="map-state">地图加载中</div>
    <div v-if="error" class="map-state error">{{ error }}</div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { loadAMap } from '@/utils/mapLoader'
import { MAP_CONFIG } from '@/config/mapConfig'

const props = defineProps({
  overview: {
    type: Object,
    default: null
  },
  focus: {
    type: Object,
    default: null
  },
  layers: {
    type: Object,
    default: () => ({ city_metrics: true, stations: true, heatmap: false })
  }
})

const mapContainer = ref(null)
const mapInstance = ref(null)
const AMapRef = ref(null)
const loading = ref(false)
const error = ref('')
const overlays = ref([])

const GUANGDONG_CENTER = [113.2668, 23.1333]

const clearOverlays = () => {
  if (mapInstance.value && overlays.value.length > 0) {
    mapInstance.value.remove(overlays.value)
  }
  overlays.value = []
}

const numberValue = (value) => {
  const next = Number(value)
  return Number.isFinite(next) ? next : null
}

const addMarker = ({ lng, lat, title, color = '#1976d2', label = '' }) => {
  const AMap = AMapRef.value
  const longitude = numberValue(lng)
  const latitude = numberValue(lat)
  if (!AMap || longitude === null || latitude === null) return
  const marker = new AMap.Marker({
    position: [longitude, latitude],
    title,
    content: `<div style="min-width:18px;height:18px;border-radius:999px;background:${color};border:2px solid #fff;box-shadow:0 2px 8px rgba(15,23,42,.28);color:#fff;font-size:10px;line-height:18px;text-align:center;">${label}</div>`
  })
  marker.setMap(mapInstance.value)
  overlays.value.push(marker)
}

const renderLayers = () => {
  if (!mapInstance.value || !AMapRef.value) return
  clearOverlays()
  const modules = props.overview?.modules || {}
  if (props.layers.city_metrics) {
    const cities = modules.month_to_date?.city_metrics || modules.realtime?.cities || []
    cities.forEach((city, index) => {
      addMarker({
        lng: city.lng || city.longitude,
        lat: city.lat || city.latitude,
        title: city.city || city.name,
        color: props.focus?.cities?.includes(city.city) ? '#d92d20' : '#1976d2',
        label: String(index + 1)
      })
    })
  }
  if (props.layers.stations) {
    const stations = modules.layers?.stations || []
    stations.forEach((station) => {
      addMarker({
        lng: station.lng || station.longitude,
        lat: station.lat || station.latitude,
        title: station.station_name || station.name,
        color: props.focus?.stations?.includes(station.station_name || station.name) ? '#d92d20' : '#16a34a'
      })
    })
  }
}

const initMap = async () => {
  loading.value = true
  error.value = ''
  try {
    const AMap = await loadAMap()
    AMapRef.value = AMap
    mapInstance.value = new AMap.Map(mapContainer.value, {
      ...MAP_CONFIG,
      center: GUANGDONG_CENTER,
      zoom: 7,
      viewMode: '2D'
    })
    renderLayers()
  } catch (err) {
    error.value = err?.message || '地图加载失败'
  } finally {
    loading.value = false
  }
}

watch(() => [props.overview, props.focus, props.layers], renderLayers, { deep: true })

onMounted(initMap)
onBeforeUnmount(() => {
  clearOverlays()
  mapInstance.value?.destroy?.()
})
</script>

<style scoped>
.guangdong-map,
.map-container {
  width: 100%;
  height: 100%;
}
.map-state {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 10;
  transform: translate(-50%, -50%);
  border: 1px solid #d9e2ec;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  padding: 10px 14px;
  color: #475569;
}
.map-state.error {
  color: #b42318;
}
</style>
```

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: build exits 0.

- [ ] **Step 3: Manual browser check**

Start frontend if not already running:

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

Open the mapped project URL and switch to query mode. Expected:

- Query mode shows a map canvas instead of the normal chat-only page.
- Metric cards appear over the map.
- Bottom chat overlay remains usable.
- If AMap key is missing, the map component shows a visible error instead of a blank page.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/queryDashboard/GuangdongOverviewMap.vue
git commit -m "feat: render guangdong query dashboard map"
```

---

## Task 8: Agent Prompt And Event Metadata Contract

**Files:**
- Modify: `backend/app/agent/prompts/ops_prompt.py` or the query-mode prompt file identified during implementation.
- Modify: `backend/app/routers/agent.py`
- Test: `backend/tests/test_query_dashboard_agent_metadata.py`

- [ ] **Step 1: Write metadata extraction tests**

Create `backend/tests/test_query_dashboard_agent_metadata.py`:

```python
from app.schemas.query_dashboard import DashboardFocus


def test_dashboard_focus_contract_accepts_city_question_metadata():
    focus = DashboardFocus(
        scope="city",
        cities=["广州"],
        pollutants=["O3_8h"],
        modules=["month_to_date", "trend"],
        layer_state={"city_metrics": True, "heatmap": True},
        source_data_ids=["air_quality_unified:v1:abc"],
    )

    payload = focus.model_dump()
    assert payload["scope"] == "city"
    assert payload["cities"] == ["广州"]
    assert payload["source_data_ids"] == ["air_quality_unified:v1:abc"]
```

- [ ] **Step 2: Run metadata contract test**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_query_dashboard_agent_metadata.py -q
```

Expected: pass after Task 1.

- [ ] **Step 3: Update query-mode system instructions**

Find the prompt section that controls query mode. If the project uses `backend/app/agent/prompts/ops_prompt.py` for mode-specific instructions, add a query-mode dashboard instruction block:

```python
QUERY_DASHBOARD_METADATA_INSTRUCTION = """
问数模式回答必须在可用时产出结构化仪表盘联动元数据：
- dashboard_focus.scope: province/city/station/pollutant/time_range
- dashboard_focus.cities: 涉及城市列表
- dashboard_focus.stations: 涉及站点列表
- dashboard_focus.pollutants: 涉及污染物或指标列表
- dashboard_focus.time_range: start/end/label
- dashboard_focus.modules: 应高亮的 dashboard 模块
- dashboard_focus.layer_state: city_metrics/stations/heatmap 图层开关建议
- dashboard_focus.source_data_ids: 支撑结论的数据 ID
- answer_evidence.claims: 每条核心结论对应的指标和数据 ID
禁止只在自然语言里描述来源；必须尽量绑定 data_id。
"""
```

Wire this string into the query-mode prompt path so Agent has explicit output requirements.

- [ ] **Step 4: Preserve dashboard metadata in complete events**

In `backend/app/routers/agent.py`, find the `complete` event handling block around `event["type"] == "complete"`. Ensure if `event_data` contains `dashboard_focus` or `answer_evidence`, those keys remain in the streamed event and final message data. Add:

```python
                                if event_data.get("dashboard_focus"):
                                    final_message["dashboard_focus"] = event_data["dashboard_focus"]
                                if event_data.get("answer_evidence"):
                                    final_message["answer_evidence"] = event_data["answer_evidence"]
```

Place it next to existing `visuals` and `sources` preservation.

- [ ] **Step 5: Run backend metadata and route tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_query_dashboard_agent_metadata.py tests/test_query_dashboard_routes.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/prompts/ops_prompt.py backend/app/routers/agent.py backend/tests/test_query_dashboard_agent_metadata.py
git commit -m "feat: add query dashboard agent metadata contract"
```

---

## Task 9: End-To-End Verification Pass

**Files:**
- Modify only files required by failures found during verification.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest tests/test_query_dashboard_service.py tests/test_query_dashboard_routes.py tests/test_query_dashboard_agent_metadata.py -q
```

Expected: all query-dashboard backend tests pass.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd frontend
node --test src/components/queryDashboard/dashboardFocus.test.mjs src/stores/react-store-query-dashboard.test.mjs
```

Expected: all focused frontend tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: build exits 0. Existing Sass legacy API and chunk-size warnings are acceptable.

- [ ] **Step 4: Run manual smoke**

Use the mapped project frontend URL. Verify:

- Non-query modes still show the existing chat layout.
- Query mode shows the Guangdong dashboard layout.
- Dashboard modules begin loading on entry.
- Partial API failure can be simulated by returning one error module; other cards remain visible.
- Sending a question still reaches the Agent.
- A mocked or real `dashboard_focus` highlights a matching module and focus panel.
- Source drawer opens from a metric card and shows data ID/query params when available.

- [ ] **Step 5: Commit verification fixes**

If fixes were required:

```bash
git add backend frontend
git commit -m "fix: stabilize query dashboard verification"
```

If no fixes were required, do not create an empty commit.

---

## Self-Review Notes

Spec coverage:

- Default real online overview: Tasks 2 and 3.
- Existing data query tools rather than duplicate data path: Task 2 uses existing `query_gd_suncere` entry points behind a provider.
- Partial degradation: Task 2 service tests and Task 6 module states.
- Query-mode-only layout: Task 6 `MainLayout` branch.
- AMap route: Task 7.
- Structured metadata linkage: Tasks 4, 5, and 8.
- Traceable sources: Tasks 1, 2, 3, and 6 source drawer.
- Non-query mode preservation: Task 6 branch and Task 9 manual smoke.

Implementation boundaries:

- Phase one intentionally renders basic city/station point overlays before dense heat rendering.
- The provider abstraction lets tests avoid live API calls while production still uses existing query tools.
- The frontend layout is isolated under `components/queryDashboard` to avoid expanding existing large ReAct files more than necessary.
