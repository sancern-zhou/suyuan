from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
POLLUTANTS = ('sO2', 'nO2', 'pM10', 'co', 'o3', 'pM2_5')


def local_time(value=None):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    value = value or datetime.now(TZ)
    return value.replace(tzinfo=TZ) if value.tzinfo is None else value.astimezone(TZ)


def hour_key(value):
    return local_time(value).replace(minute=0, second=0, microsecond=0).isoformat()


def hours(start, end):
    """Hour-ending labels: (start, end], never 25 labels for a daily window."""
    current = local_time(start).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while current <= local_time(end):
        yield hour_key(current)
        current += timedelta(hours=1)


def parse_value(value):
    """Keep numeric availability separate from quality flags and invalid sentinels."""
    match = re.fullmatch(r'\s*([+-]?\d+(?:\.\d+)?)(?:\(([^)]*)\))?\s*', str(value))
    if not match:
        return None, None
    number = float(match[1])
    return (number if math.isfinite(number) and number >= 0 else None), match[2]


def normalize(record):
    code = str(record.get('code') or record.get('station_code') or '').strip()
    stamp = record.get('timePoint') or record.get('timestamp')
    if not code or not stamp:
        raise ValueError('station code and hourly timestamp are required')
    timestamp = local_time(stamp)
    if timestamp.minute or timestamp.second or timestamp.microsecond:
        raise ValueError('non-hourly timestamp')
    values, marks = {}, {}
    for field in POLLUTANTS:
        values[field], embedded = parse_value(record.get(field))
        mark_field = 'cO_Mark' if field == 'co' else field + '_Mark'
        marks[field] = record.get(mark_field) or embedded
    return {
        'code': code, 'hour': hour_key(timestamp), 'values': values, 'marks': marks,
        'present': any(v is not None for v in values.values()),
        'data_complete': all(v is not None for v in values.values()),
        'quality_complete': all(v is not None and not marks[k] for k, v in values.items()),
        'raw': record,
    }


class MonitorStore:
    """SQLite transactions serialize collector/report calls without losing first observations."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS stations (
                  code TEXT PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL,
                  type TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
                  confirmed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS cells (
                  code TEXT NOT NULL, source TEXT NOT NULL, hour TEXT NOT NULL,
                  present INTEGER NOT NULL, data_complete INTEGER NOT NULL, quality_complete INTEGER NOT NULL,
                  observed_at TEXT NOT NULL, first_missing_at TEXT,
                  recovered_at TEXT, first_present_at TEXT, completed_at TEXT, raw TEXT,
                  PRIMARY KEY(code, source, hour));
                CREATE TABLE IF NOT EXISTS runs (
                  id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL,
                  source TEXT NOT NULL, city TEXT NOT NULL, start TEXT NOT NULL,
                  end TEXT NOT NULL, success INTEGER NOT NULL, detail TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS cells_missing ON cells(first_missing_at, present);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=60)
        db.row_factory = sqlite3.Row
        return db

    def seed(self, stations):
        with self.connect() as db:
            for station in stations:
                if station['type'] not in ('国控', '省控'):
                    raise ValueError('unsupported station type')
                db.execute('''INSERT INTO stations(code,name,city,type,active,confirmed)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET
                    name=excluded.name,city=excluded.city,type=excluded.type,
                    confirmed=excluded.confirmed,
                    active=CASE WHEN excluded.confirmed=1 THEN excluded.active ELSE stations.active END''',
                    (station['code'], station['name'], station['city'], station['type'],
                     int(station.get('active', False)), int(station.get('confirmed', False))))

    def stations(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM stations ORDER BY type,city,code')]

    def ingest(self, *, source, city, start, end, records, observed_at, success=True, detail='', station_types=('国控', '省控')):
        observed_at = local_time(observed_at).isoformat()
        start, end = local_time(start), local_time(end)
        if end > local_time(observed_at):
            raise ValueError('cannot observe future hourly labels')
        grid = set(hours(start, end))
        normalized = {}
        try:
            for record in records:
                cell = normalize(record)
                if cell['hour'] in grid:
                    key = (cell['code'], cell['hour'])
                    if key in normalized and normalized[key]['raw'] != cell['raw']:
                        raise ValueError('conflicting duplicate station/hour rows')
                    normalized[key] = cell
        except (ValueError, TypeError):
            success, detail = False, '返回记录格式错误或存在冲突，未用于离线判定'
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO runs(observed_at,source,city,start,end,success,detail) VALUES(?,?,?,?,?,?,?)',
                       (observed_at, source, city, start.isoformat(), end.isoformat(), int(success), detail))
            if not success:
                return False
            roster = [row for row in db.execute('SELECT * FROM stations WHERE city=?', (city,)) if row['type'] in station_types]
            known = {row['code'] for row in roster}
            if any(code not in known for code, _ in normalized):
                raise ValueError('response includes unexpected station codes')
            # Bootstrap membership only from stations actually observed. Never turn old,
            # never-seen candidate stations into offline incidents.
            seen = {code for code, _ in normalized}
            for row in roster:
                if row['code'] in seen and not row['confirmed']:
                    db.execute('UPDATE stations SET active=1 WHERE code=?', (row['code'],))
                if not row['active'] and row['code'] not in seen:
                    continue
                for hour in sorted(grid):
                    cell = normalized.get((row['code'], hour))
                    present = bool(cell and cell['present'])
                    first_missing = None if present else observed_at
                    raw = json.dumps(cell['raw'], ensure_ascii=False) if cell else None
                    db.execute('''INSERT INTO cells(code,source,hour,present,data_complete,quality_complete,
                        observed_at,first_missing_at,recovered_at,first_present_at,completed_at,raw) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(code,source,hour) DO UPDATE SET
                        first_missing_at=COALESCE(cells.first_missing_at,excluded.first_missing_at),
                        recovered_at=CASE WHEN excluded.present=1 AND cells.first_missing_at IS NOT NULL
                          THEN COALESCE(cells.recovered_at,excluded.observed_at) ELSE cells.recovered_at END,
                        first_present_at=COALESCE(cells.first_present_at,excluded.first_present_at),
                        completed_at=CASE WHEN excluded.data_complete=1 AND cells.data_complete=0
                          THEN excluded.observed_at ELSE cells.completed_at END,
                        present=excluded.present,data_complete=excluded.data_complete,quality_complete=excluded.quality_complete,
                        observed_at=excluded.observed_at,raw=excluded.raw
                        WHERE excluded.observed_at >= cells.observed_at''',
                        (row['code'], source, hour, int(present), int(bool(cell and cell['data_complete'])), int(bool(cell and cell['quality_complete'])),
                         observed_at, first_missing, None, observed_at if present else None,
                         observed_at if cell and cell['data_complete'] else None, raw))

        return True

    def pending_hours(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('''SELECT s.city,c.source,MIN(c.hour) AS start,
                MAX(c.hour) AS end FROM cells c JOIN stations s ON s.code=c.code
                WHERE c.first_missing_at IS NOT NULL AND c.data_complete=0 AND s.active=1
                GROUP BY s.city,c.source''')]

    def report(self, end, *, national_sources, provincial_source, threshold=4):
        end = local_time(end)
        start = end - timedelta(days=1)
        entries, unknown, errors = [], [], []
        with self.connect() as db:
            roster = list(db.execute('SELECT * FROM stations ORDER BY type,city,code'))
            for station in roster:
                if not station['active']:
                    if not station['confirmed']:
                        unknown.append(dict(station))
                    continue
                sources = national_sources if station['type'] == '国控' else [provincial_source]
                main_source = sources[0]
                # Keep originally observed holes, including those subsequently backfilled.
                missing = list(db.execute('''SELECT * FROM cells WHERE code=? AND source=?
                    AND first_missing_at IS NOT NULL AND hour<=? ORDER BY hour''',
                    (station['code'], main_source, end.isoformat())))
                groups = []
                for cell in missing:
                    if groups and local_time(cell['hour']) - local_time(groups[-1][-1]['hour']) == timedelta(hours=1):
                        groups[-1].append(cell)
                    else:
                        groups.append([cell])
                for group in groups:
                    if len(group) <= threshold:
                        continue
                    event_start = local_time(group[0]['hour']) - timedelta(hours=1)
                    event_end = local_time(group[-1]['hour'])
                    complete_sources, remaining, backfill_observations = [], {}, []
                    for source in sources:
                        holes = []
                        for cell in group:
                            latest = db.execute('SELECT data_complete,completed_at FROM cells WHERE code=? AND source=? AND hour=?',
                                                (station['code'], source, cell['hour'])).fetchone()
                            if latest is None or not latest['data_complete']:
                                holes.append(cell['hour'])
                            elif latest['completed_at']:
                                backfill_observations.append(latest['completed_at'])
                        remaining[source] = holes
                        if not holes:
                            complete_sources.append(source)
                    backfilled = bool(complete_sources)
                    latest = db.execute('''SELECT hour,present,observed_at FROM cells
                        WHERE code=? AND source=? AND hour<=? ORDER BY hour DESC LIMIT 1''',
                        (station['code'], main_source, end.isoformat())).fetchone()
                    recovered = bool(latest and latest['present'] and local_time(latest['hour']) >= event_end)
                    # Carry open incidents from any preceding date. Closed old events remain
                    # visible on the day their backfill was observed, then leave the daily list.
                    changed_today = any(start < local_time(stamp) for stamp in backfill_observations)
                    if event_end <= start and recovered and backfilled and not changed_today:
                        continue
                    entries.append({
                        **dict(station), 'source': main_source,
                        'offline_start': event_start.isoformat(), 'offline_end': event_end.isoformat(),
                        'affected_hours': len(group),
                        'window_affected_hours': sum(start < local_time(c['hour']) <= end for c in group),
                        'first_observed_at': min(c['first_missing_at'] for c in group),
                        'recovered': recovered, 'status_as_of': latest['hour'] if latest else None,
                        'backfill_status': '已回补' if backfilled else '待回补',
                        'backfill_sources': complete_sources, 'remaining_hours': remaining,
                        'carry_over': event_start < start,
                        'evidence_kind': '小时数据缺失，设备离线原因待核实',
                    })
                # A successful collect must cover the end hour; stale or failed collection
                # makes the result incomplete, never a blanket "all normal" conclusion.
                latest = db.execute('SELECT observed_at FROM cells WHERE code=? AND source=? AND hour=?',
                                    (station['code'], main_source, end.isoformat())).fetchone()
                if latest is None or local_time(latest['observed_at']) < end:
                    errors.append({'code': station['code'], 'city': station['city'], 'reason': '截止小时取数未完成'})
            recent_runs = list(db.execute('SELECT * FROM runs WHERE observed_at>? ORDER BY id', (start.isoformat(),)))
            # The last attempt for each city/source determines query health; earlier transient
            # errors resolved by a later successful request should not block the report.
            last = {}
            for run in recent_runs:
                last[(run['city'], run['source'])] = run
            errors.extend({'city': r['city'], 'source': r['source'], 'reason': r['detail']}
                          for r in last.values() if not r['success'])
            counts = {kind: sum(s['active'] and s['type'] == kind for s in roster) for kind in ('国控', '省控')}
        return {
            'schema_version': 'station_operation_daily/v1', 'window_start': start.isoformat(),
            'window_end': end.isoformat(), 'generated_at': local_time().isoformat(),
            'entries': entries, 'station_counts': counts, 'unverified_stations': unknown,
            'membership_confirmed': all(s['confirmed'] for s in roster),
            'collection_errors': errors, 'report_ready': not errors,
            'national_sources': national_sources, 'provincial_source': provincial_source,
            'limitations': [
                '小时数据缺失用于运行监控，不能直接证明设备离线或无法回补。',
                '首次采集前已回补的历史缺口无法还原；离线起止时间为已观察缺失时段。',
            ] + ([] if len(national_sources) > 1 else ['国控目前仅接入省控小时接口，独立发布源未接入。'])
              + ([] if all(s['confirmed'] for s in roster) else ['在运名单尚未人工确认，无记录候选站点单列待核实。']),
        }
