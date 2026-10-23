# nanobot reference and adaptation

Source: https://github.com/HKUDS/nanobot
Commit: b702ac633f149ada9ea123a8bfda5871d7ef6033
Reference: nanobot/agent/goal_permission.py; nanobot/session/goal_state.py
Additional stage-two reference: nanobot/cron/binding.py (binding_revision).
Related upstream tests: tests/agent/test_goal_permission.py; tests/session/test_goal_state.py

assistant_request.py adapts the default-deny ContextVar and token-reset lifetime pattern.
The adapter binds authority at authenticated transport ingress to an exact session and
request, retaining the original human message. Tools do not accept caller identity or
authorization flags. The local task service uses SQLAlchemy, owner/project filters,
idempotent creation, optimistic updates and transactional audit events; it does not
copy nanobot's session metadata persistence or add its Agent runtime as a dependency.
Local tests cover default denial, background-session isolation, exception cleanup,
database restart persistence, concurrent versions and owner/project isolation.
assistant_schedule.definition_hash adapts the editable-state hash pattern from
binding_revision, excluding runtime state and binding to the granted matter scope.
Reminder plan fields are immutable. Scheduling uses the project's existing
APScheduler; the SQL occurrence/outbox implementation is local integration code.

MIT License

Copyright (c) 2025-present Xubin Ren and the nanobot contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
