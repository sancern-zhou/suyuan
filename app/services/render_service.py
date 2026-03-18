import os
import uuid
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from backend.app.tools.visualization.scientific_charts.chonggou import render_chonggou_from_payload

# Simple in-process render service with background execution and file caching.
# For production, replace with Celery/RQ and object storage.

TASK_STORE: Dict[str, Dict[str, Any]] = {}
EXECUTOR = ThreadPoolExecutor(max_workers=2)
BASE_OUT = os.path.join("mapout", "render_tasks")
os.makedirs(BASE_OUT, exist_ok=True)


def _save_task_state(task_id: str, state: Dict[str, Any]) -> None:
    TASK_STORE[task_id] = state
    # persist to disk for lightweight durability
    task_dir = os.path.join(BASE_OUT, task_id)
    os.makedirs(task_dir, exist_ok=True)
    with open(os.path.join(task_dir, "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _run_render(task_id: str, visual: Dict[str, Any]) -> None:
    try:
        _save_task_state(task_id, {"status": "running", "visual_id": visual.get("id")})
        payload = visual.get("payload", {})
        v_type = visual.get("type", "")
        out_dir = os.path.join(BASE_OUT, task_id)
        os.makedirs(out_dir, exist_ok=True)
        # routing - extendable
        if v_type == "stacked_time":
            out_path = os.path.join(out_dir, f"{visual.get('id','visual')}.svg")
            saved = render_chonggou_from_payload(payload, out_path, fmt="svg")
        else:
            # generic fallback: still try chonggou renderer for compatibility
            out_path = os.path.join(out_dir, f"{visual.get('id','visual')}.svg")
            saved = render_chonggou_from_payload(payload, out_path, fmt="svg")

        _save_task_state(task_id, {"status": "done", "visual_id": visual.get("id"), "files": saved})
    except Exception as exc:
        tb = traceback.format_exc()
        _save_task_state(task_id, {"status": "failed", "error": str(exc), "traceback": tb})


def submit_render(visual: Dict[str, Any], synchronous: bool = False) -> Dict[str, Any]:
    """
    Submit a visual render task. Returns task info with task_id.
    If synchronous=True, will block until done and return final state.
    """
    task_id = uuid.uuid4().hex
    initial = {"status": "pending", "visual_id": visual.get("id")}
    _save_task_state(task_id, initial)
    if synchronous:
        _run_render(task_id, visual)
        return TASK_STORE[task_id]
    else:
        EXECUTOR.submit(_run_render, task_id, visual)
        return {"task_id": task_id, "status": "pending"}


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    return TASK_STORE.get(task_id)









