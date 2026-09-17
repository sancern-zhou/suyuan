from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.scheduled_tasks.models import TaskEvent
from app.scheduled_tasks.service import EventDispatchResult
from app.scheduled_tasks.storage.event_claim_storage import EventClaimStorage
from app.services.jiangsu_smart_event import JiangsuSmartEventService, normalize_alarm_event, _event_fingerprint
from app.services.jiangsu_smart_event_automation import (
    JiangsuSmartEventAutomation, evidence_signature, update_initial_assessment,
)


class Evidence:
    def __init__(self):
        self.rows = {}
        self.calls = []

    async def fetch(self, event, **kwargs):
        self.calls.append(event['event_id'])
        row = {'timePoint': '2026-09-10 08:00:00', 'SO2': 10, 'NO2': 20, 'CO': 1,
               'O3': 30, 'PM10': 40, 'PM2.5': 20}
        row.update(self.rows.get(event['site_id'], {}))
        return {'status': 'success', 'sources': {'monitoring': {'status': 'success',
            'data': {'station_hour': {'success': True, 'status': 'success', 'data': [row]}}}}}


class Scheduler:
    def __init__(self, root):
        self.task = SimpleNamespace(task_id='jiangsu_smart_event_ai_judgment', enabled=True, timeout_seconds=1200)
        self.claim_storage = EventClaimStorage(root / 'claims')
        self.events = []
        self.executions = {}
        self._event_tasks = set()
        self.fail = False

    def get_task(self, task_id):
        return self.task

    def get_execution(self, execution_id):
        return self.executions.get(execution_id)

    async def publish_event(self, event, *, wait=False, force_retry=False):
        if self.fail:
            raise RuntimeError('dispatch transport failed')
        previous = self.claim_storage.get(self.task.task_id, event.event_id)
        if previous and previous.status in {'claimed', 'running'}:
            return EventDispatchResult(matched_task_ids=[self.task.task_id], duplicate_task_ids=[self.task.task_id])
        if previous:
            assert force_retry
            self.claim_storage.reopen(self.task.task_id, event.event_id)
        else:
            self.claim_storage.try_claim(self.task.task_id, event)
        self.events.append(event)
        return EventDispatchResult(matched_task_ids=[self.task.task_id], accepted_task_ids=[self.task.task_id])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr('app.services.task_review.get_data_registry', lambda: tmp_path)
    evidence = Evidence()
    service = JiangsuSmartEventService(data_root=tmp_path, evidence_fetcher=evidence)
    scheduler = Scheduler(tmp_path)
    monkeypatch.setattr('app.scheduled_tasks.get_scheduled_task_service', lambda: scheduler)
    return service, evidence, scheduler


async def seed(service, rows):
    store, *_ = service._upsert_events([normalize_alarm_event({'id': identity, 'code': site,
         'alarmtime': '2026-09-10 08:00:00', 'ddRuleType': '仪器报警'}) for identity, site in rows])
    await service._collect_event_evidence(store, store['events'])


def test_initial_impact_does_not_confuse_exceedance_or_unavailable_data():
    event = {'clue_tags': [{'tag_id': 'exceed', 'tag_category': '超限', 'tag_name': '小时超限'}],
             'ai_data_impact': '有数据影响'}
    package = {'sources': {'monitoring': {'data': {'station_hour': {'success': True, 'data': [{'PM10': 300}]}}}}}
    update_initial_assessment(event, package)
    assert event['system_data_impact'] == '无数据影响'
    assert event['ai_task_priority'] == 'normal'
    assert event['data_impact_conflict'] is True
    assert event['ai_data_impact'] == '有数据影响'
    update_initial_assessment(event, {'sources': {}})
    assert event['system_data_impact'] == '待确认'
    event['clue_tags'].append({'tag_id': 'missing', 'tag_name': '断数报警'})
    update_initial_assessment(event, {'sources': {}})
    assert event['system_data_impact'] == '有数据影响'
    assert event['ai_task_priority'] == 'urgent'


def test_evidence_signature_ignores_collection_metadata_but_detects_new_records():
    package = {'sources': {'monitoring': {'status': 'success', 'data': {
        'station_hour': {'data': [{'PM10': 1}], 'metadata': {'queried_at': 'old'}, 'summary': 'old'}}}}}
    changed = deepcopy(package)
    changed['sources']['monitoring']['data']['station_hour'].update(metadata={'queried_at': 'new'}, summary='new')
    assert evidence_signature(changed) == evidence_signature(package)
    changed['sources']['monitoring']['data']['station_hour']['data'][0]['PM10'] = 2
    assert evidence_signature(changed) != evidence_signature(package)


@pytest.mark.asyncio
async def test_queue_prioritizes_impact_respects_capacity_and_persists_across_instances(setup):
    service, evidence, scheduler = setup
    evidence.rows['urgent'] = {'PM10': -1}
    await seed(service, [(1, 'normal'), (2, 'urgent'), (3, 'normal2')])
    service.save_config({'ai_max_concurrency': 1})
    now = datetime.now().astimezone()
    result = await JiangsuSmartEventAutomation(service).dispatch_queue(now=now)
    assert result['dispatched'] == 1
    assert [event.event_id for event in scheduler.events] == ['alarm:2']
    assert scheduler.events[0].attributes['ai_task_priority'] == 'urgent'
    assert scheduler.events[0].payload['smart_event']['system_data_impact'] == '有数据影响'
    restarted = JiangsuSmartEventService(data_root=service.store_path.parent.parent, evidence_fetcher=evidence)
    assert (await JiangsuSmartEventAutomation(restarted).dispatch_queue(now=now))['dispatched'] == 0
    cards = restarted.list_tasks()
    assert sum(card['status'] == '执行中' for card in cards) == 1
    assert sum(card['status'] == '待执行' for card in cards) == 2


@pytest.mark.asyncio
async def test_transport_failure_retries_with_backoff_and_stops_at_limit(setup):
    service, _, scheduler = setup
    await seed(service, [(1, 'A')])
    service.save_config({'ai_max_retries': 1})
    scheduler.fail = True
    queue = JiangsuSmartEventAutomation(service)
    now = datetime.now().astimezone()
    await queue.dispatch_queue(now=now)
    card = service.list_tasks()[0]
    assert card['status'] == '执行失败'
    assert card['automatic_attempts'] == 1
    due = datetime.fromisoformat(card['next_retry_at'])
    assert (await queue.dispatch_queue(now=due - timedelta(seconds=1)))['dispatched'] == 0
    await queue.dispatch_queue(now=due + timedelta(seconds=1))
    card = service.list_tasks()[0]
    assert card['automatic_attempts'] == 2
    assert card['retry_exhausted'] is True
    assert card['next_retry_at'] is None
    assert (await queue.dispatch_queue(now=due + timedelta(days=1)))['dispatched'] == 0
    assert service._load_store()['events'][0]['event_status'] == '未研判'


@pytest.mark.asyncio
async def test_execution_failure_callback_schedules_retry_and_recovery_finds_missed_callback(setup):
    service, _, scheduler = setup
    await seed(service, [(1, 'A')])
    now = datetime.now().astimezone()
    queue = JiangsuSmartEventAutomation(service)
    await queue.dispatch_queue(now=now)
    event = scheduler.events[0]
    execution = SimpleNamespace(execution_id='failure', event_attributes=event.attributes, status='failed',
                                completed_at=now, error_message='worker interrupted')
    scheduler.executions['failure'] = execution
    claim = scheduler.claim_storage.get(scheduler.task.task_id, event.event_id)
    scheduler.claim_storage.mark_status(claim.claim_id, 'failed', execution_id='failure')
    # A restarted scheduler reconciles the terminal claim without needing the original callback.
    await JiangsuSmartEventAutomation(service).dispatch_queue(now=now)
    card = service.list_tasks()[0]
    assert card['status'] == '执行失败'
    assert card['last_error'] == 'worker interrupted'
    due = datetime.fromisoformat(card['next_retry_at'])
    await queue.dispatch_queue(now=due + timedelta(seconds=1))
    assert len(scheduler.events) == 2
    assert service.list_tasks()[0]['automatic_attempts'] == 2


@pytest.mark.asyncio
async def test_recovery_applies_resumed_execution_with_stale_dispatch_token(setup):
    """重启恢复的执行携带旧 claim 快照 token 时，终态补偿仍应回填结果。"""
    from app.services.task_review import submit_review
    service, _, scheduler = setup
    await seed(service, [(1, 'A')])
    now = datetime.now().astimezone()
    queue = JiangsuSmartEventAutomation(service)
    await queue.dispatch_queue(now=now)
    event = scheduler.events[0]
    card = service.list_tasks()[0]
    submit_review({'subject_id': 'alarm:1', 'event_id': 'alarm:1', 'category': '智能事件',
        'title': '恢复执行', 'summary': '重启后恢复执行的结论', 'decision': 'needs_action', 'comment': '待核查',
        'checks': [{'name': '核验', 'status': 'pass', 'basis': '日志'}],
        'sections': [{'title': '结论', 'fields': [{'key': 'event_type', 'label': '类型', 'value': '疑似仪器故障'}]}]},
        {'task_id': scheduler.task.task_id, 'execution_id': 'resumed'})
    execution = SimpleNamespace(execution_id='resumed', event_attributes={
        'smart_event_task_id': card['task_id'],
        'smart_event_dispatch_token': 'stale-token-from-first-attempt',
    }, status='success', completed_at=now + timedelta(seconds=30), started_at=now + timedelta(seconds=30))
    scheduler.executions['resumed'] = execution
    claim = scheduler.claim_storage.get(scheduler.task.task_id, event.event_id)
    scheduler.claim_storage.mark_status(claim.claim_id, 'succeeded', execution_id='resumed')

    await queue.dispatch_queue(now=now + timedelta(minutes=1))

    updated = service.list_tasks()[0]
    assert updated['status'] == '已完成'
    judged = service._load_store()['events'][0]['ai_judgment']
    assert judged['execution_id'] == 'resumed'
    assert judged['final_response'] == '重启后恢复执行的结论'


@pytest.mark.asyncio
async def test_late_clues_are_not_consumed_by_old_ai_execution(setup):
    from app.services.task_review import submit_review
    service, _, scheduler = setup
    await seed(service, [(1, 'A')])
    now = datetime.now().astimezone()
    queue = JiangsuSmartEventAutomation(service)
    await queue.dispatch_queue(now=now)
    sent = scheduler.events[0]
    service._upsert_events([normalize_alarm_event({'id': 2, 'code': 'A', 'alarmtime': '2026-09-10 18:00:00', 'ddRuleType': '供电报警'})])
    submit_review({'subject_id': 'alarm:1', 'event_id': 'alarm:1', 'category': '智能事件',
        'title': '第一轮', 'summary': '原始证据结论', 'decision': 'needs_action', 'comment': '待核查',
        'checks': [{'name': '核验', 'status': 'pass', 'basis': '日志'}],
        'sections': [{'title': '结论', 'fields': [{'key': 'event_type', 'label': '类型', 'value': '疑似仪器故障'}]}]},
        {'task_id': scheduler.task.task_id, 'execution_id': 'success'})
    execution = SimpleNamespace(execution_id='success', event_attributes=sent.attributes, status='success', completed_at=now)
    service.apply_task_execution('alarm:1', scheduler.task, execution)
    event = service._load_store()['events'][0]
    assert event['judged_clue_ids'] == ['alarm:1:alarm']
    assert event['pending_delta']['clue_ids'] == ['alarm:2:alarm']
    claim = scheduler.claim_storage.get(scheduler.task.task_id, 'alarm:1')
    scheduler.claim_storage.mark_status(claim.claim_id, 'succeeded', execution_id='success')
    await service.collect_event_evidence('alarm:1')
    await queue.dispatch_queue(now=now)
    assert len(scheduler.events) == 2
    assert scheduler.events[-1].payload['continuity_context']['new_clue_count'] == 1


@pytest.mark.asyncio
async def test_scan_recovers_yesterday_clues_and_refreshes_unchanged_open_evidence(setup, monkeypatch):
    service, evidence, _ = setup
    service.save_config({'auto_ai_enabled': False})
    await seed(service, [(1, 'A'), (2, 'archived')])
    store = service._load_store()
    store['events'][1]['archived'] = True
    store['events'][1]['event_status'] = '已归档'
    store['events'][0].pop('evidence_checked_at', None)
    service._save_store(store)
    scans, days = [], []
    async def scan(**kwargs):
        scans.append(kwargs)
        service._upsert_events([normalize_alarm_event({'id': 3, 'code': 'A', 'alarmtime': '2026-09-10 19:00:00'})])
        return {'stored_event_count': 2}
    async def compliance(**kwargs):
        days.append(kwargs['date'])
        return {'status': 'synced'}
    monkeypatch.setattr(service, 'sync_alarm_events', scan)
    monkeypatch.setattr(service, 'sync_compliance_clues', compliance)
    evidence.calls.clear()
    now = datetime.fromisoformat('2026-09-11T00:05:00+08:00')
    automation = JiangsuSmartEventAutomation(service)
    await automation.tick(now=now)
    assert scans[0]['start_time'] == '2026-09-10T00:05:00+08:00'
    assert scans[0]['end_time'] == now.isoformat()
    assert days == ['2026-09-10', '2026-09-11']
    assert evidence.calls == ['alarm:1']
    await automation.tick(now=now + timedelta(minutes=1))
    assert len(scans) == 1
    assert service._load_store()['events'][0]['clue_count'] == 2


@pytest.mark.asyncio
async def test_auto_disabled_and_archived_events_never_dispatch(setup):
    service, _, scheduler = setup
    await seed(service, [(1, 'A')])
    service.save_config({'auto_ai_enabled': False})
    queue = JiangsuSmartEventAutomation(service)
    now = datetime.now().astimezone()
    assert (await queue.dispatch_queue(now=now))['status'] == 'disabled'
    service.save_config({'auto_ai_enabled': True})
    store = service._load_store()
    store['events'][0]['archived'] = True
    store['events'][0]['event_status'] = '已归档'
    service._save_store(store)
    assert (await queue.dispatch_queue(now=now))['dispatched'] == 0
    assert scheduler.events == []


@pytest.mark.asyncio
async def test_review_reject_rerun_dispatches_even_when_auto_ai_disabled(setup):
    service, evidence, scheduler = setup
    await seed(service, [(1, 'A')])
    store = service._load_store()
    event = store['events'][0]
    event['ai_event_type'] = '数据异常待研判'
    event['event_status'] = '待复核'
    for card in store.get('tasks', []):
        if card.get('event_id') == event['event_id']:
            card['status'] = '已完成'
    service._save_store(store)

    service.save_config({'auto_ai_enabled': False})
    card = service.queue_review_reject_feedback(
        event['event_id'], feedback='真实外界环境污染',
        actor={'user_id': '1', 'username': 'tester'},
        human_decision={'action': 'reject', 'comment': '真实外界环境污染'},
    )
    assert card is not None
    assert card['continuity']['feedback']['source'] == 'review_reject'

    now = datetime.now().astimezone()
    result = await JiangsuSmartEventAutomation(service).dispatch_queue(now=now)
    assert result['status'] != 'disabled'
    assert result['dispatched'] == 1
    assert [item.event_id for item in scheduler.events] == [event['event_id']]


@pytest.mark.asyncio
async def test_frozen_alarm_sync_dispatches_human_rerun_without_fetching(setup, monkeypatch):
    service, evidence, scheduler = setup
    await seed(service, [(1, 'A')])
    store = service._load_store()
    event = store['events'][0]
    event['ai_event_type'] = '数据异常待研判'
    event['event_status'] = '待复核'
    for card in store.get('tasks', []):
        if card.get('event_id') == event['event_id']:
            card['status'] = '已完成'
    service._save_store(store)
    service.save_config({'auto_ai_enabled': False})
    service.queue_review_reject_feedback(
        event['event_id'], feedback='真实外界环境污染',
        actor={'user_id': '1', 'username': 'tester'},
        human_decision={'action': 'reject', 'comment': '真实外界环境污染'},
    )
    fetched_before = list(evidence.calls)
    monkeypatch.setenv('JIANGSU_DEMO_FREEZE_DATE', '2026-09-10')
    from app.fetchers.jiangsu_smart_event_alarm_sync import JiangsuSmartEventAlarmSyncFetcher

    result = await JiangsuSmartEventAlarmSyncFetcher(service=service).fetch_and_store()
    assert result.get('demo_freeze') is True
    assert [item.event_id for item in scheduler.events] == [event['event_id']]
    assert evidence.calls == fetched_before  # 冻结期间不抓新数据


@pytest.mark.parametrize('values', [{'ai_max_retries': -1}, {'ai_max_concurrency': 0},
    {'rescan_lookback_hours': 1000}, {'auto_ai_enabled': 'false'}])
def test_invalid_automation_config_is_rejected(setup, values):
    with pytest.raises(ValueError):
        setup[0].save_config(values)


@pytest.mark.asyncio
async def test_late_callback_from_previous_attempt_cannot_fail_current_attempt(setup):
    service, _, scheduler = setup
    await seed(service, [(1, 'A')])
    queue = JiangsuSmartEventAutomation(service)
    now = datetime.now().astimezone()
    await queue.dispatch_queue(now=now)
    previous = scheduler.events[0]
    failure = SimpleNamespace(execution_id='first-failure', event_attributes=previous.attributes,
                              status='failed', completed_at=now, error_message='first failed')
    service.apply_task_execution('alarm:1', scheduler.task, failure)
    due = datetime.fromisoformat(service.list_tasks()[0]['next_retry_at'])
    claim = scheduler.claim_storage.get(scheduler.task.task_id, 'alarm:1')
    scheduler.claim_storage.mark_status(claim.claim_id, 'failed')
    await queue.dispatch_queue(now=due + timedelta(seconds=1))
    before = service.store_path.read_bytes()
    service.apply_task_execution('alarm:1', scheduler.task, SimpleNamespace(
        execution_id='old-delayed-callback', event_attributes=previous.attributes,
        status='failed', completed_at=now, error_message='stale'))
    assert service.store_path.read_bytes() == before
    assert service.list_tasks()[0]['status'] == '执行中'
    assert service.list_tasks()[0]['automatic_attempts'] == 2


@pytest.mark.asyncio
async def test_automation_lock_skips_overlapping_worker_tick(setup):
    import fcntl
    service, _, _ = setup
    service.store_path.parent.mkdir(parents=True, exist_ok=True)
    with (service.store_path.parent / '.automation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert (await JiangsuSmartEventAutomation(service).tick())['status'] == 'already_running'
