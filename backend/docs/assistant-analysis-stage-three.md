# Assistant background analysis and feedback wakeups

This increment adds bounded read-only analysis to the existing personal matter
and notification queue. It does not deploy services, scrape WeChat history,
send to other users, or implement coach recommendations.

## User contract

manage_assistant_followups accepts execution_action=remind (the existing default)
or analyze. Only an explicit human instruction can register analyze; historical
content and background activity cannot create or widen that grant. The task's
current version, original human request, scope hash, frozen tool names and
personal recipient are stored. Existing reminder request keys remain compatible.

Analysis supports now, once, interval, cron, or feedback. A feedback plan waits for
future manage_assistant_tasks feedback writes for that exact matter. The feedback
event and queued occurrence commit or roll back together. New feedback supersedes
older queued feedback work; periodic analysis also coalesces queued occurrences.
Neither mechanism cancels an already admitted run solely because another timer
slot arrived. New user edits make the admitted result stale and prevent publication.
No WeChat group or file feed is being monitored by this implementation.

The existing worker clock starts at most one local analysis task separately from
notification delivery. Database claims and a partial unique index permit only
one running analysis per matter across workers. Explicitly blocked matters wait
for user resume; cancelled/completed matters do not run. Each analysis has a
fencing token and five-minute lease, a four-minute timeout, 12 model iterations,
and at most 12 tool calls. Expired/interrupted runs are failed visibly, not replayed
automatically. A late result cannot overwrite a finished or revoked claim.

## Execution and result verification

The adapter reuses create_react_agent with a fixed custom tool registry and
enable_memory=False. It clears inherited turn authority and uses a separate
run session with the matter owner as user_identifier. It imports neither an
additional Agent framework nor a second scheduler.

The audited query candidates are execute_sql_query, execute_postgres_sql_query,
query_xcai_city_history and get_weather_data. The actual grant is their intersection
with the current project's social tools and enabled registry entries. At runtime,
the complete frozen set must still be permitted and classified read-only. Every
query checks enabled/project status and source-account ownership/binding again.
The existing query implementations retain SQL/table validation and data access.
Infrastructure may persist query caches or session artifacts; read-only here means
no business writes, code execution, arbitrary file access, delegation or messaging.
An empty tool grant can reason from provided feedback but cannot fetch new sources.

Input includes the matter scope, explicit instructions, and up to 20 recent feedback
records capped at 12,000 characters total. Excerpts are marked truncated. Successful
query returns receive tool evidence ids; feedback uses immutable event versions.
Strict JSON output must contain status, summary, next_step, evidence and
should_notify. Unknown evidence ids and malformed output fail verification.

Statuses are progress, waiting_input, and ready_for_review. The last requires at
least one supplied evidence id. It is a model proposal for human acceptance, not
proof of factual correctness or automatic matter completion. The matter is left
waiting for input/review; completion remains the existing explicit human operation.
This is reference validation, not an automated verifier of every factual sentence.

Before publication, the queue locks the matter and rechecks project, task binding,
scope, version, enabled plan, fencing token and lease. A successful result, versioned
background audit event (not a fabricated human message), and optional outbox record
commit in one transaction. A changed matter supersedes the result. Failures remain
in the run record and can produce one generic personal notice without raw errors.

Progress can remain silent when the model sees no reason to notify. Missing-input
and review results notify when their status/summary/next_step text differs from the
last notice for that plan. Exact text hashes suppress duplicates; semantic paraphrase
deduplication is not claimed. Notifications reuse the stage-two inbox/WeChat adapter,
including current ownership checks, single-attempt transport and unknown outcomes.

## Local validation and future enablement

Both ASSISTANT_FOLLOWUPS_ENABLED and ASSISTANT_ANALYSIS_ENABLED default to false.
The matching web/worker pair must use consistent flags when this is eventually
enabled. Apply migration 023 after 021/022 to DATABASE_URL before using followups
with this code: new model columns are read even on reminder-only paths. create_all
does not upgrade an existing table's columns. No deployment environment was edited
and no non-test database was migrated during implementation.

Tests use temporary SQLite databases, a fake model, fake query functions and fake
delivery. They cover transactional feedback, scoped/concurrent claims, cancellation,
user edits during analysis, interrupted leases, output/evidence validation, bounded
tools, status/audit/outbox rollback, and a local feedback-analysis-inbox flow.
The real ReAct factory and executor clone also run locally to verify empty grants.
ToolExecutor now distinguishes an explicit empty registry from None; previously
an empty registry silently loaded default tools, defeating the custom boundary.
PostgreSQL locking, deployed process lifecycle, real model behavior and actual
channel delivery still require integration acceptance before enablement.

## Source reuse

The existing ReAct/custom registry, APScheduler, query validators and delivery
implementation carry the runtime. Scope binding follows the pinned nanobot
cron/binding.py reference documented in third_party/nanobot-assistant-tasks.md.
Deep Agents commit 97f856dcb08264ef78722a4687cab9133ec5fb7a's subagent middleware
was reviewed for explicit tools and
separate execution context; its LangGraph runtime was not imported or copied.
The SQL lease, feedback queue and result/outbox bridge are local integration code,
covered by local tests, not represented as upstream-tested framework code.
