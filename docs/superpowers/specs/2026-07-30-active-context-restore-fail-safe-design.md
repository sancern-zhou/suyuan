# Active Context Restore Fail-Safe Design

## Goal

Prevent a transient failure while restoring a conversation from turning an unknown
server-side `active_contexts` value into an authoritative empty replacement on the
next send.

## Scope

This change applies only to the composer state used for `active_contexts`. It does
not change the backend protocol, resource pagination, or other composer fields.

## State

The composer tracks two booleans:

- `activeContextsLoaded`: the authoritative server state and the dependencies
  needed to represent it were restored successfully.
- `activeContextsDirty`: the user explicitly changed the active Skill or a fixed
  policy after the latest restore attempt.

These booleans represent three useful states:

1. Not loaded and not dirty: server state is unknown.
2. Loaded and not dirty: the current UI state is authoritative.
3. Dirty: the user explicitly intends to replace the active contexts.

## Sending Rule

The composer sends the current replacement array only when
`activeContextsLoaded || activeContextsDirty`. Otherwise it sends `null`, preserving
the backend's existing "keep current value" semantics.

For a new unsaved conversation, the known initial state is empty, so it starts as
loaded. A session switch resets restoration state before asynchronous requests begin.

## Restore and Editing Behavior

- All required restore requests must succeed before the state is marked loaded.
- A failed restore may still show a local draft, but that draft is not treated as
  authoritative and is not sent as a replacement automatically.
- Skill selection/removal and fixed-policy pin/unpin mark the state dirty.
- Programmatic changes made while restoring do not mark the state dirty.
- After the server accepts a send containing an explicit replacement, loaded becomes
  true and dirty becomes false.

## Tests

Add focused unit coverage for payload resolution:

- unknown and untouched state produces `null`;
- successfully loaded state produces the replacement array;
- explicit user edits after a failed restore produce the replacement array;
- an accepted explicit replacement returns the state to loaded and clean.

Existing composer payload, request-body, and queue tests must continue to pass.

## Deferred Work

Resource pagination beyond the first 100 resources remains outside this change and
is tracked as a lower-probability follow-up.
