# Assistant and office roles

This increment supersedes the tool-union design in assistant-web-stage-five.md.

## Runtime identities

- `social`: personal assistant, displayed as 助手模式. Handles user intent,
  delegation, matters, coaching, followups, personal memory and notifications.
- `office`: daily office executor, displayed as 办公模式. Handles document reading,
  file editing, spreadsheet cleanup/reconciliation, light computation and HTML
  outputs. It is a leaf child of `social`, not another top-level Web entry.
- Historical backend `assistant` execution is normalized to `office`. Its old
  prompt import and tool registry lookup remain compatibility aliases. Web's
  existing UI ID/request alias `assistant` still enters `social`; Web session
  storage names and LLM message role `assistant` are not renamed.

No sessions, account IDs, memory directories or persisted task tables are migrated.
Existing office child sessions can be continued explicitly by session ID.
Fresh office jobs do not automatically reuse unrelated previous child sessions.

## Tool boundaries

Assistant has no SQL, weather query, Python, business chart, report-generation or
knowledge-QA tools. It retains bounded coordination, resource handoff, personal
memory editing, lightweight Web lookup, skill discovery and existing notification
and scheduling tools. Project overrides cannot reintroduce professional executors.

Office has file/resource tools, Python for supplied office files, lightweight Web
lookup, HTML output and skill draft tools. It has no business database or weather
tools, chart/report generators, knowledge-QA, further delegation or scheduling.
Skill-selected and restored extra tools cannot expand either role's registry.

The assistant's run executor contains only its own tools. An internal delegation
registry preserves the configured tool implementations for child construction;
the existing child capability policy filters this registry by target mode,
explicit allow/deny lists and leaf restrictions before the child starts.
This avoids either exposing professional execution to the coordinator or starving
its delegated office/professional executors of their tools.

Professional child roles remain subject to existing project availability and
primary-mode rules. `query`, `expert` and `report` remain primary entrypoints;
specialized query/expert children and `knowledge` may execute delegated work.
Formal report requests are handed to the report entry with the available context.
No report child or nonexistent chart mode is introduced.

## Validation boundary

Focused tests cover role whitelists under project overrides, extra-tool rejection,
delegation schema/parent/leaf guards, explicit office session reuse and a fake
office runtime receiving its own tools while inheriting the parent's model chain.
Existing Web assistant actions and account isolation regressions remain included.
Browser tests use intercepted APIs; they do not validate real model task quality.
No deployment, real migration, feature-flag enablement or Android changes occur.
