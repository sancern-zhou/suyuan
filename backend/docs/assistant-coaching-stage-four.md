# Project capability discovery and assistant coaching

The social Agent now has manage_assistant_coaching. The shared coach contract is
appended even to project prompt overrides, and omitted if the tool is disabled
in the project's disabled_tools. Other modes do not automatically gain this tool.
No new model call, scheduler, frontend navigation or notification channel is added.

## Interaction

discover reads current manifest frontend.agent_modes and per-mode tool whitelists,
then intersects them with enabled registered tools. Unknown obsolete mode entries
are omitted. Broken project configuration fails closed. Direct tools, professional
workspaces and permitted child roles have distinct capability IDs. Professional
query/expert/report modes are workspace entries only, never delegated children.
Child recommendations also obey the existing social parent delegation policy.
The catalog describes configured tool availability, not successful remote data
access or credentials; actual execution retains its existing runtime checks.

The Agent chooses relevance from the current user goal, not a keyword classifier
or fixed workflow. It offers one or two concrete suggestions only when useful.
propose requires a live human turn and stores goal, reason, proposed request and
missing inputs. list is owner/project scoped and paginated. accept/dismiss require
an actual current user choice and the queried suggestion version. User identity
comes from the server conversation catalog, never model parameters.

accept revalidates the capability revision and returns next_action with
execution_state=not_started. For direct tools the current Agent continues the
already-authorized task using existing tools; for delegation it retains existing
delegation checks; for workspace entries it provides the mode and prepared prompt.
It cannot switch the App UI or start a professional workspace automatically.
Suggested text is a model-generated plan, not a new human authorization. Acceptance
does not create matters, schedule analysis, or permit cross-user messages. Each
actual execution still needs the existing tool's complete inputs and authority.
Do not tell users that acceptance alone started or completed their work.

## Persistence and concurrency

assistant_suggestions and assistant_coaching_owners live in business DATABASE_URL.
The latter is a per-project/user write fence, including first-use insert races.
It serializes the five-pending budget and competing accept/dismiss choices across
workers. Suggestions deduplicate on capability ID plus whitespace-normalized,
case-folded goal. This is exact normalized deduplication, not semantic paraphrase
detection. The prompt forbids rewriting goals to evade dismissal; there is no
background suggestion generation or recurring coaching notification.

Resolved records retain their dedup keys and original decision message. Repeated
identical decisions do not increment versions or overwrite original consent.
Opposite decisions and stale pending versions fail. A changed or disabled capability
blocks acceptance (including repeated acceptance); dismissal remains possible.
A database failure never falls back to an unscoped JSON file.

For an existing installation, apply
backend/app/db/migrations/024_create_assistant_coaching.sql to its own DATABASE_URL
before using persistence. Fresh database init registers both models. The migration
only adds tables and is repeatable. No real database migration was applied here.

## Validation boundary

Focused tests use temporary SQLite databases, actual project manifests, fake tool
availability and the real tool entrypoint. They cover ownership, request expiry,
pending limits under concurrency, competing choices, transaction rollback,
restart persistence, live capability changes, prompt overrides and migration
column parity. They do not prove a real PostgreSQL multi-process deployment,
LLM recommendation quality, remote data access, or App end-to-end interaction.
No new App coaching panel is implemented in this backend increment.

See third_party/hermes-assistant-coaching.md for the pinned source reference and
MIT license. Existing task/reminder/analysis stage documentation still applies.
