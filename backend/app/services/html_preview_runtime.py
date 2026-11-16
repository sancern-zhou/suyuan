"""Serve-side runtime injected into inline HTML previews.

Interactive HTML artifacts (html_artifact previews, report package previews)
are rendered inside a sandboxed iframe with an opaque origin: no fetch, no
localStorage, no same-origin access. The host therefore sizes the frame from
content-reported height instead of assuming a fixed viewport. This module
injects a tiny, dependency-free runtime that observes document size and
postMessage-reports it upward, mirroring the Gen-UI contract used by desktop
clients (default 240px frame, content-driven growth, host clamps the value).

The runtime must stay ES2017-conservative: preview pages also render on
intranet Kylin workstations running Firefox ESR 78.
"""
from __future__ import annotations

RUNTIME_SOURCE = "suyuan-html-runtime"
RUNTIME_MARKER = f"data-{RUNTIME_SOURCE}"

_RUNTIME_JS = """
(function () {
  if (window.__suyuanHtmlRuntimeLoaded) return;
  window.__suyuanHtmlRuntimeLoaded = true;
  var lastHeight = 0;
  var pending = false;
  function measure() {
    var doc = document.documentElement;
    var body = document.body;
    if (!body) return 0;
    var height = Math.max(
      body.scrollHeight || 0,
      doc ? doc.scrollHeight || 0 : 0
    );
    return Math.ceil(height);
  }
  function report(force) {
    var height = measure();
    if (!height) return;
    if (!force && Math.abs(height - lastHeight) < 2) return;
    lastHeight = height;
    try {
      window.parent.postMessage({
        source: '%SOURCE%',
        type: 'height',
        height: height
      }, '*');
    } catch (err) { /* parent unreachable: host will keep its current size */ }
  }
  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () {
      pending = false;
      report(false);
    });
  }
  function start() {
    report(true);
    if (typeof ResizeObserver !== 'undefined' && document.body) {
      new ResizeObserver(schedule).observe(document.body);
    }
    new MutationObserver(schedule).observe(document.documentElement, {
      childList: true,
      subtree: true
    });
    window.addEventListener('resize', schedule);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
""".replace("%SOURCE%", RUNTIME_SOURCE).strip()

RUNTIME_SCRIPT_TAG = f"<script {RUNTIME_MARKER}>\n{_RUNTIME_JS}\n</script>"


def inject_html_runtime(html: str) -> str:
    """Insert the height-report runtime into a complete HTML document.

    Idempotent: documents already carrying the marker are returned unchanged
    (hand-written pages that embed the runtime themselves, or double injection
    across versions).
    """
    if RUNTIME_MARKER in html:
        return html
    tag = RUNTIME_SCRIPT_TAG
    lowered = html.lower()
    for closer in ("</body>", "</html>"):
        index = lowered.rfind(closer)
        if index != -1:
            return html[:index] + tag + html[index:]
    return html + tag
