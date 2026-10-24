"""Configured HTTP collection and deterministic report artifacts; no project defaults."""
from __future__ import annotations

import gzip
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import requests

from app.utils.path_config import format_agent_path, get_data_registry, resolve_agent_path
from .core import MonitorStore, hour_key, local_time, merge_hour_spans
from .feedback import closed_unrecoverable, load_feedback, match_feedback


def config_path():
    return get_data_registry() / 'station_operation_monitor' / 'config.json'


def load_config(path=None):
    path = resolve_agent_path(path) if path else config_path()
    config = json.loads(path.read_text(encoding='utf-8'))
    if not config.get('stations') or not config.get('sources'):
        raise ValueError('station monitor requires an explicit station roster and sources')
    codes = [s['code'] for s in config['stations']]
    if len(set(codes)) != len(codes):
        raise ValueError('duplicate station codes in monitor configuration')
    names = [s['name'] for s in config['sources']]
    if len(set(names)) != len(names):
        raise ValueError('duplicate source names')
    if not set(config['national_sources'] + [config['provincial_source']]) <= set(names):
        raise ValueError('unknown configured source')
    return config


class StationHourHTTPSource:
    """The existing station-hour API protocol, with endpoints and credentials supplied by config."""

    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.token = None

    def authenticate(self):
        config = self.config
        username = os.environ.get(config['username_env'], '')
        password = os.environ.get(config['password_env'], '')
        if not username or not password:
            raise RuntimeError('station API credentials not configured')
        params = {'UserName': username, 'Pwd': password}
        url = config['base_url'].rstrip('/') + config['token_endpoint']
        response = self.session.get(url, params=params, headers=config.get('headers', {}), timeout=15)
        response.raise_for_status()
        body = response.json()
        if not body.get('success') or not isinstance(body.get('result'), str):
            raise RuntimeError('station API authentication failed')
        self.token = body['result']

    def fetch(self, codes, start, end):
        if self.token is None:
            self.authenticate()
        url = self.config['base_url'].rstrip('/') + self.config['hour_endpoint']
        body = {'codes': codes, 'timePoint': [local_time(start).strftime('%Y-%m-%d %H:%M:%S'),
                local_time(end).strftime('%Y-%m-%d %H:%M:%S')],
                'dataType': self.config.get('data_type', 0), 'nsType': self.config.get('ns_type', 2),
                'skipCount': 0, 'maxResultCount': 1000}
        headers = {**self.config.get('headers', {}), 'Authorization': 'Bearer ' + self.token}
        response = self.session.post(url, json=body, headers=headers, timeout=45)
        if response.status_code == 401:
            self.authenticate()
            headers['Authorization'] = 'Bearer ' + self.token
            response = self.session.post(url, json=body, headers=headers, timeout=45)
        response.raise_for_status()
        result = response.json()
        if not result.get('success') or not isinstance(result.get('result'), list):
            raise RuntimeError('station hourly query failed')
        records = result['result']
        # Pagination was ignored by the tested endpoint. Bound requests to <= 800
        # expected rows and reject responses at the advertised cap instead.
        if len(records) >= 1000:
            raise RuntimeError('possible truncated response; smaller slice required')
        if not records:
            raise RuntimeError('empty city/source response; station states not updated')
        return records


def collect(config=None, *, now=None, end=None, source_factory=StationHourHTTPSource, root=None):
    config = config or load_config()
    now = local_time(now)
    eligible_end = local_time(hour_key(now - timedelta(minutes=config.get('arrival_grace_minutes', 20))))
    end = local_time(end) if end else eligible_end
    if end > eligible_end:
        raise ValueError('hour data has not passed its arrival grace period')
    root = Path(root) if root else get_data_registry() / 'station_operation_monitor'
    store = MonitorStore(root / 'monitor.sqlite3')
    store.seed(config['stations'])
    bootstrap = not (root / 'initialized.json').exists()
    lookback = config.get('bootstrap_hours', 48) if bootstrap else config.get('lookback_hours', 6)
    start = end - timedelta(hours=lookback)
    run_id = now.strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8]
    raw_root = root / 'snapshots' / run_id
    raw_root.mkdir(parents=True, exist_ok=True)
    pending = store.pending_hours()
    # User-confirmed unrecoverable spans leave the re-check rotation entirely.
    closed = closed_unrecoverable(root)
    def _still_tracked(item):
        start_span, end_span = local_time(item['start']), local_time(item['end'])
        return not any(fs <= start_span and fe >= end_span for fs, fe in closed.get(item['code'], []))
    pending = [item for item in pending if _still_tracked(item)]
    successes, failures = [], []
    for source_config in config['sources']:
        source = source_factory(source_config)
        try:
            cities = sorted({s['city'] for s in config['stations'] if s['type'] in source_config.get('station_types', ['国控','省控'])})
            for city in cities:
                stations = [s for s in config['stations'] if s['city'] == city and s['type'] in source_config.get('station_types', ['国控','省控'])]
                codes = [s['code'] for s in stations if not s.get('confirmed') or s.get('active')]
                if not codes:
                    continue
                windows = [(start, end)]
                for span in merge_hour_spans(item for item in pending
                        if item['city'] == city and item['source'] == source_config['name']
                        and local_time(item['start']) <= start):
                    windows.append((local_time(span['start']) - timedelta(hours=1),
                                    min(local_time(span['end']), start)))
                # Query recent intervals after old intervals so end-hour health reflects the
                # final attempt. Each slice has at most 800 expected station/hour rows.
                windows.sort()
                slice_hours = max(1, min(24, 800 // len(codes) - 1))
                for window_start, window_end in windows:
                    cursor = window_start
                    while cursor < window_end:
                        next_end = min(cursor + timedelta(hours=slice_hours), window_end)
                        detail = ''
                        try:
                            records = source.fetch(codes, cursor, next_end)
                            success = True
                        except Exception as exc:
                            # Never persist an HTTP exception string: it can include auth query parameters.
                            records, success, detail = [], False, f'取数失败（{type(exc).__name__}），状态待核实'
                        try:
                            stored = store.ingest(source=source_config['name'], city=city, start=cursor, end=next_end,
                                                  records=records, observed_at=now, success=success, detail=detail,
                                                  station_types=source_config.get('station_types', ['国控','省控']))
                            if not stored:
                                success = False
                                detail = detail or '返回数据格式错误，状态待核实'
                        except (ValueError, TypeError):
                            success, detail = False, '站点编码或数据格式异常，状态待核实'
                            store.ingest(source=source_config['name'], city=city, start=cursor, end=next_end,
                                         records=[], observed_at=now, success=False, detail=detail)
                        envelope = {'source': source_config['name'], 'city': city, 'observed_at': now.isoformat(),
                                    'start': cursor.isoformat(), 'end': next_end.isoformat(),
                                    'success': success, 'detail': detail, 'records': records}
                        path = raw_root / f'{len(successes)+len(failures):04d}.json.gz'
                        with gzip.open(path, 'wt', encoding='utf-8') as handle:
                            json.dump(envelope, handle, ensure_ascii=False)
                        (successes if success else failures).append({k:v for k,v in envelope.items() if k!='records'})
                        cursor = next_end
        finally:
            if hasattr(source, 'session'):
                source.session.close()
    if not failures:
        (root / 'initialized.json').write_text(json.dumps({'initialized_at': now.isoformat()}))
    return {'success': not failures, 'run_id': run_id, 'end': end.isoformat(),
            'successful_slices': len(successes), 'failed_slices': failures,
            'snapshot_path': format_agent_path(raw_root), 'state_path': format_agent_path(store.path)}


def generate_report(config=None, *, date=None, now=None, root=None, refresh=True):
    config = config or load_config()
    now = local_time(now)
    end = local_time(date).replace(hour=10, minute=0, second=0, microsecond=0) if date else now.replace(hour=10, minute=0, second=0, microsecond=0)
    if now < end + timedelta(minutes=config.get('arrival_grace_minutes', 20)):
        raise ValueError('daily report cutoff has not arrived')
    root = Path(root) if root else get_data_registry() / 'station_operation_monitor'
    collection = collect(config, now=now, end=end, root=root) if refresh else None
    store = MonitorStore(root / 'monitor.sqlite3')
    data = store.report(end, national_sources=config['national_sources'],
                        provincial_source=config['provincial_source'],
                        min_missing_hours=config.get('min_missing_hours', 4))
    # "Unable to backfill" is an explicit, attributable confirmation, never a
    # duration-based guess. A completed backfill overrides an obsolete confirmation.
    for entry in data['entries']:
        if entry['type'] != '省控' or entry['backfill_status'] != '待回补':
            continue
        for confirmation in config.get('unrecoverable_confirmations', []):
            if (confirmation.get('code') == entry['code']
                and confirmation.get('reason') and confirmation.get('evidence')
                and confirmation.get('confirmed_by') and confirmation.get('confirmed_at')
                and local_time(confirmation['confirmed_at']) <= now
                and local_time(confirmation['start']) <= local_time(entry['offline_start'])
                and local_time(confirmation['end']) >= local_time(entry['offline_end'])):
                entry['backfill_status'] = '无法回补'
                entry['unrecoverable_confirmation'] = confirmation
                break
    # Conversation feedback attributes a reason and closes tracking. Feedback
    # recorded on the report day stays visible once, earlier closures drop out.
    feedbacks = load_feedback(root)
    kept_entries = []
    for entry in data['entries']:
        feedback = match_feedback(feedbacks, entry['code'], entry['offline_start'], entry['offline_end'])
        if feedback is not None:
            if local_time(feedback['feedback_at']).date() < end.date():
                continue
            entry['issue_reason'] = feedback['reason']
            entry['feedback'] = feedback
            if feedback.get('unrecoverable'):
                entry['backfill_status'] = '无法回补'
        kept_entries.append(entry)
    data['entries'] = kept_entries
    data['collection'] = collection
    if collection and not collection['success']:
        data['report_ready'] = False
    # Immutable report runs: rerunning one day must not overwrite a delivered report.
    output = root / 'reports' / (end.strftime('%Y%m%d') + '_' + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=True)
    report_input = output / 'report_input.json'
    report_input.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    from .word import write_word
    word_path = write_word(data, config, output / '站点运行监控日报.docx')
    format_validation = word_path.with_suffix('.format.json') if config.get('template_path') else None
    return {'success': True, 'report_ready': data['report_ready'],
            'format_validation_path': format_agent_path(format_validation) if format_validation else None,
            'report_input_path': format_agent_path(report_input), 'word_path': format_agent_path(word_path),
            'station_counts': data['station_counts'], 'incident_count': len(data['entries']),
            'unverified_station_count': len(data['unverified_stations']),
            'collection_errors': data['collection_errors'], 'limitations': data['limitations']}
