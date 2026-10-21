# Hermes coaching reference

Reference: https://github.com/NousResearch/hermes-agent

Pinned revision: 9e01b44dd23978f9ff40b7837467f3a9f1582130.
Inspected cron/suggestions.py, cron/suggestion_catalog.py and tools/skills_tool.py.
The local assistant_coaching implementation adapts the pending/accepted/dismissed
lifecycle, five-pending budget, and stable dismissal deduplication. The capability
catalog uses our existing project manifests and enabled registry rather than
Hermes' starter cron catalog. No Hermes runtime dependency is introduced.

Local differences: transactional project/user ownership, an owner-row write fence
across workers, optimistic choice versions, server-resolved identity, a fresh
human request for mutations, and live capability revalidation before acceptance.
Acceptance prepares an action route; it does not create a cron job, execute an
Agent, or expand message/background authority. This is a deliberate fit to the
existing assistant's execution and permission tools, not a claim of full Hermes
compatibility. The upstream framework's complete test suite was not run here.

## Upstream license

MIT License

Copyright (c) 2025 Nous Research

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
