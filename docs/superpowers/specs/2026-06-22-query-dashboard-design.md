# Query Mode Guangdong Data Overview Dashboard Design

## Objective

Upgrade the current query mode from a chat-first page into a Guangdong data overview dashboard with an AI chat overlay.

The first screen should restore the previous data-overview habit: users see a province-wide operational view before asking a question. After the user asks, the page should switch or highlight the relevant data modules, while the AI answer presents conclusions, evidence, and traceable data sources.

## Confirmed Decisions

- The first phase includes both default overview and question-driven dashboard linkage.
- Default overview data must come from real online queries.
- The page uses partial degradation: successful modules render first, failed modules show local errors and missing-data impact.
- Dashboard linkage is driven by structured metadata returned by tools or Agent events, not by parsing AI answer text.
- GIS uses the existing AMap route and project map configuration.
- Overview data should be obtained by orchestrating the existing data query tools, not by building a separate duplicate data-ingestion path.

## Existing Context

The current query mode shares the ReAct page stack:

- `frontend/src/views/ReactAnalysisView.vue`
- `frontend/src/components/reactAnalysis/MainLayout.vue`
- `frontend/src/components/reactAnalysis/ChatArea.vue`
- `frontend/src/components/reactAnalysis/RightPanelContainer.vue`
- `frontend/src/components/VisualizationPanel.vue`
- `frontend/src/stores/reactStore.js`

The existing stack already supports:

- mode-specific messages and sessions;
- tool result streaming;
- visualization history;
- source panels;
- map/chart/table/image visual blocks;
- session recovery.

The new dashboard should reuse these capabilities but change query mode's primary layout. Other modes should keep their current behavior.

## Product Experience

When the user enters query mode:

1. The main canvas shows a Guangdong AMap GIS dashboard.
2. The page starts online queries for default overview modules.
3. The dashboard shows module-level loading states.
4. Successful modules render immediately.
5. Failed modules remain visible with error state, retry action, and missing-data explanation.
6. The AI chat appears as a bottom floating panel over the dashboard.

Default modules:

- Realtime overview: latest province, city, and station air quality values.
- Current-month accumulation: city ranking, pollutant averages, attainment rate, comparison indicators when available.
- Year-to-date accumulation: city ranking, composite index, major pollutant contribution, accumulated attainment view.
- GIS layers: city metric layer, station distribution layer, monitoring heat layer.
- Source and freshness indicators: update time, query time, data source, record count, data IDs.

After the user asks a question:

1. The Agent calls existing query tools as needed.
2. Tool results or final Agent events return structured dashboard focus metadata.
3. The frontend applies this focus to the dashboard.
4. The map highlights matching cities, stations, pollutants, and time windows.
5. Related metric cards, charts, tables, and source entries are promoted or highlighted.
6. The AI answer shows conclusion, evidence, and traceable sources.

## Frontend Architecture

Add a query-mode-only workspace under the existing ReAct layout:

- `QueryDashboardWorkspace`
  - Owns query dashboard state and coordinates child panels.
  - Receives existing messages, session ID, analyzing state, input state, and send/pause handlers.
  - Embeds or wraps existing chat components as a floating bottom panel.

- `GuangdongOverviewMap`
  - Uses existing AMap loader and map config.
  - Centers on Guangdong by default.
  - Renders city, station, heat, and selected-focus layers.
  - Supports layer toggles and focus updates.

- `DashboardMetricLayer`
  - Floating metric cards for realtime, month-to-date, and year-to-date modules.
  - Each card has `loading`, `success`, `error`, and `stale` states.
  - Cards expose source and refresh actions.

- `DashboardLayerControl`
  - Toggles city metrics, stations, heatmap, and focus overlays.
  - Shows current layer freshness and missing-layer warnings.

- `DashboardFocusPanel`
  - Shows the currently active AI-linked focus:
    - scope;
    - city or station;
    - pollutant;
    - time range;
    - linked dashboard modules;
    - linked source data IDs.

- `DashboardSourceDrawer`
  - Opens from metric cards, AI evidence links, or map selections.
  - Shows query tool name, parameters, data ID, record count, update time, and sampled records.

- `FloatingChatPanel`
  - Reuses existing `ReActMessageList` and `InputBox` behavior.
  - Appears at the bottom of the dashboard.
  - Can collapse to give more map space.

`MainLayout` should branch only for query mode:

- Query mode renders `QueryDashboardWorkspace`.
- Non-query modes continue rendering current `ChatArea` plus optional right panels.

The existing `VisualizationPanel` remains available for historical visuals or expanded chart inspection, but it is not the default query-mode primary surface.

## Data Orchestration

Default overview data should be fetched through a backend orchestration endpoint that calls existing data query tools internally.

Proposed endpoint:

```http
GET /api/query-dashboard/guangdong-overview
```

Optional query parameters:

- `include=realtime,month_to_date,year_to_date,layers`
- `force_refresh=true|false`
- `city=...` for future scoped refresh
- `pollutant=...` for future scoped refresh

The endpoint should not duplicate low-level data client logic. It should reuse existing tools such as the Guangdong Suncere query tool and related normalization/context machinery where appropriate.

Response shape:

```json
{
  "success": true,
  "generated_at": "2026-06-22T10:00:00+08:00",
  "region": "广东省",
  "modules": {
    "realtime": {
      "status": "success",
      "summary": {},
      "cities": [],
      "stations": [],
      "sources": []
    },
    "month_to_date": {
      "status": "success",
      "summary": {},
      "rankings": [],
      "sources": []
    },
    "year_to_date": {
      "status": "error",
      "error": {
        "message": "查询超时",
        "impact": "全年累计模块暂不可验证"
      },
      "sources": []
    },
    "layers": {
      "status": "partial",
      "city_metrics": [],
      "stations": [],
      "heat_points": [],
      "sources": []
    }
  },
  "sources": [
    {
      "source_id": "src_001",
      "tool_name": "query_gd_suncere",
      "data_id": "air_quality_unified:v1:...",
      "query_params": {},
      "record_count": 21,
      "updated_at": "2026-06-22T09:55:00+08:00"
    }
  ],
  "errors": []
}
```

## Agent Linkage Protocol

Tool results or final Agent events should include dashboard metadata:

```json
{
  "dashboard_focus": {
    "scope": "city|station|province|pollutant|time_range",
    "cities": ["广州"],
    "stations": [],
    "pollutants": ["O3_8h"],
    "time_range": {
      "start": "2026-06-01",
      "end": "2026-06-22",
      "label": "本月"
    },
    "modules": ["month_to_date", "city_ranking", "trend"],
    "layer_state": {
      "city_metrics": true,
      "stations": false,
      "heatmap": true
    },
    "source_data_ids": ["air_quality_unified:v1:..."]
  },
  "answer_evidence": {
    "claims": [
      {
        "text": "广州本月臭氧贡献偏高",
        "metrics": ["O3_8h"],
        "source_data_ids": ["air_quality_unified:v1:..."]
      }
    ],
    "query_params": {}
  }
}
```

Frontend rules:

- Prefer `dashboard_focus` from the latest complete answer.
- If a selected message has its own `dashboard_focus`, selecting that message restores its focus.
- Do not infer dashboard focus from free-form AI text in phase one.
- If linked data is unavailable or failed, show the focus but mark evidence as unverified.

## Partial Degradation

Each module has an independent lifecycle:

- `idle`
- `loading`
- `success`
- `partial`
- `error`
- `stale`

Rules:

- The map shell renders even before data arrives.
- One failed module does not block the dashboard.
- Failed modules keep their screen location to avoid layout shifts.
- AI answer evidence must indicate missing or failed sources.
- Users can refresh all modules or a single module.
- Module headers show last successful update time when available.

## Data Accuracy And Traceability

Every visible metric should provide a source path:

- tool name;
- query parameters;
- source API or data domain when available;
- data ID;
- record count;
- query timestamp;
- source update timestamp when available;
- sampled raw records or normalized records.

AI answers should include:

- conclusion;
- evidence bullets;
- source links or source IDs;
- missing-data caveats if any required module failed.

## Phase Plan

### Phase 1: Core Closed Loop

Deliver:

- Query-mode-only dashboard workspace.
- Guangdong AMap overview canvas.
- Online default overview query via existing data query tools.
- Realtime, month-to-date, and year-to-date module cards.
- City, station, and heat layer plumbing.
- Partial degradation states.
- Source drawer with data IDs and query params.
- Agent `dashboard_focus` and `answer_evidence` protocol.
- Frontend focus application after AI answers.
- Session recovery for current dashboard focus.

Acceptance criteria:

- Entering query mode starts online overview loading automatically.
- Successful modules render even if another module fails.
- Failed modules show visible error and retry action.
- Asking a city or pollutant question highlights the related map area and metric module from structured metadata.
- AI answer includes conclusion, evidence, and source identifiers.
- Existing non-query modes are unchanged.

### Phase 2: Analysis Depth

Deliver:

- City and station drill-down.
- Time slider for heatmap and trend comparison.
- Month-to-date and year-to-date ranking change views.
- More complete source drawer with sampled records.
- Message selection restores historical dashboard focus.
- Better caching of last successful module results for session restoration, while preserving real online refresh on entry.

### Phase 3: Command Dashboard

Deliver:

- Full-screen command display mode.
- Configurable dashboard templates.
- Alert and anomaly overlays.
- Export current dashboard plus AI analysis into a report.
- Role-specific default views.

## Testing Strategy

Frontend:

- Unit tests for focus metadata normalization.
- Component tests for module status rendering.
- Store tests for query-mode focus persistence.
- E2E smoke test for entering query mode, seeing dashboard shell, and applying mocked focus.

Backend:

- Endpoint tests with mocked existing query tools.
- Partial failure tests for each module.
- Contract tests for `dashboard_focus` and source metadata shape.
- Regression tests ensuring existing query tools are called rather than bypassed.

Manual verification:

- Load query mode with all modules succeeding.
- Load with one module failing.
- Ask a city-level question.
- Ask a pollutant-level question.
- Open source drawer from an AI evidence item.
- Restore a session and confirm focus state is preserved.

## Open Implementation Notes

- The exact existing tool calls for realtime, month-to-date, and year-to-date should be selected during implementation by inspecting current query tool capabilities and parameter conventions.
- The first implementation can use a stable dashboard response adapter around existing tool outputs, then refine module details as real data shape is verified.
- If AMap heatmap support is limited in the current loader, phase one can render city metric points first and add dense heat rendering behind a feature flag.
