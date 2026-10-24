"""Conversation-recorded incident feedback; explicit closure beats silent drops."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.utils.path_config import format_agent_path, get_data_registry
from .core import MonitorStore, TZ, local_time

FAR_PAST = datetime(1970, 1, 1, tzinfo=TZ)
FAR_FUTURE = datetime(9999, 12, 31, 23, tzinfo=TZ)


def feedback_path(root=None):
    return (Path(root) if root else get_data_registry() / 'station_operation_monitor') / 'event_feedback.json'


def load_feedback(root=None):
    path = feedback_path(root)
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding='utf-8'))
    return records if isinstance(records, list) else []


def save_feedback(records, root=None):
    path = feedback_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def _span(feedback):
    start = local_time(feedback['start']) if feedback.get('start') else FAR_PAST
    end = local_time(feedback['end']) if feedback.get('end') else FAR_FUTURE
    return start, end


def match_feedback(records, code, offline_start, offline_end):
    """Latest feedback whose window (if any) overlaps the event span."""
    start, end = local_time(offline_start), local_time(offline_end)
    best = None
    for feedback in records:
        if feedback.get('code') != code:
            continue
        fs, fe = _span(feedback)
        if fs <= end and fe >= start:
            if best is None or local_time(feedback['feedback_at']) > local_time(best['feedback_at']):
                best = feedback
    return best


def closed_unrecoverable(root=None):
    """Station code -> covering spans that must stop being re-fetched."""
    out = {}
    for feedback in load_feedback(root):
        if not feedback.get('unrecoverable'):
            continue
        out.setdefault(feedback['code'], []).append(_span(feedback))
    return out


def record_feedback(config=None, *, station, reason, unrecoverable, start=None, end=None,
                    feedback_by='用户', feedback_at=None, root=None):
    if config is None:
        from .runtime import load_config
        config = load_config()
    if not str(reason or '').strip():
        raise ValueError('缺少缺失原因，请先向用户确认')
    key = str(station or '').strip()
    match = next((s for s in config['stations'] if s['code'] == key or s['name'] == key), None)
    if match is None:
        raise ValueError(f'站点 {key} 不在已配置站点名录中，请核对编码或名称')
    root = Path(root) if root else get_data_registry() / 'station_operation_monitor'
    stamp = local_time(feedback_at) if feedback_at else local_time()
    record = {
        'code': match['code'], 'name': match['name'], 'city': match['city'],
        'start': local_time(start).isoformat() if start else None,
        'end': local_time(end).isoformat() if end else None,
        'reason': str(reason).strip(),
        'unrecoverable': bool(unrecoverable),
        'feedback_by': str(feedback_by or '').strip() or '用户',
        'feedback_at': stamp.isoformat(),
    }
    records = load_feedback(root)
    records.append(record)
    save_feedback(records, root)
    store = MonitorStore(root / 'monitor.sqlite3')
    spans = store.open_gaps(match['code'])
    if start is None and end is None:
        matched = spans
    else:
        s, e = local_time(start) if start else FAR_PAST, local_time(end) if end else FAR_FUTURE
        matched = [span for span in spans
                   if local_time(span['end']) >= s and local_time(span['start']) <= e]
    return {'record': record, 'matched_events': matched,
            'feedback_path': format_agent_path(feedback_path(root))}
