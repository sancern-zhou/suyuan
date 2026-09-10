from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from app.services import task_review as service
from app.tools.task_management.submit_task_review import SubmitTaskReviewTool


@pytest.fixture(autouse=True)
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'get_data_registry', lambda: tmp_path)
    monkeypatch.setattr('app.tools.resource_declarations.get_data_registry', lambda: tmp_path)


def payload(**changes):
    return dict(subject_id='event-1', category='工单审核', title='待确认结果', summary='结论摘要',
                decision='approve', comment='依据充分', checks=[dict(name='事实一致性', status='pass', basis='已核实')], **changes)


def source(execution='exec-1'):
    return dict(task_id='task-1', execution_id=execution, task_name='审核任务')


def human(record, **changes):
    return dict(version=record['version'], action='confirm', decision='approve', comment='人工已核验', data_impact=[], **changes)


def test_submission_validated_and_idempotent():
    with pytest.raises(ValueError):
        service.submit_review({**payload(), 'checks': []}, source())
    with pytest.raises(ValueError):
        service.submit_review(payload(), {})
    record = service.submit_review(payload(), source())
    assert service.submit_review(payload(), source()) == record
    assert len(service.list_reviews()) == 1
    with pytest.raises(ValueError):
        service.submit_review({**payload(), 'summary': '偷偷覆盖'}, source())


def test_confirm_then_new_execution_reopens_without_losing_history():
    record = service.submit_review(payload(), source())
    result = service.decide_review(record['review_id'], human(record), {'username': 'operator'})
    assert result['status'] == 'archived'
    assert service.list_reviews() == []
    assert service.submit_review(payload(), source())['status'] == 'archived'
    reopened = service.submit_review(payload(), source('exec-2'))
    assert reopened['status'] == 'pending_review'
    assert reopened['history'][0]['human_decision']['comment'] == '人工已核验'
    with pytest.raises(ValueError):
        service.decide_review(reopened['review_id'], human(record), {})


def test_concurrent_submit_produces_one_record():
    with ThreadPoolExecutor(4) as pool:
        records = list(pool.map(lambda _: service.submit_review(payload(), source()), range(8)))
    assert len({record['review_id'] for record in records}) == 1
    assert len(service.list_reviews()) == 1


def test_disposal_lifecycle_and_category():
    record = service.submit_review(payload(), source())
    decision = {**human(record), 'action': 'start_disposal', 'decision': 'needs_action'}
    record = service.decide_review(record['review_id'], decision, {})
    assert service.list_reviews(category='工单审核')[0]['status'] == 'in_disposal'
    assert not service.list_reviews(category='智能事件')
    with pytest.raises(ValueError):
        service.decide_review(record['review_id'], human(record), {})
    record = service.decide_review(record['review_id'], {**human(record), 'action': 'complete'}, {})
    assert record['human_feedback']['status'] == 'pending'
    assert not service.list_reviews()


def test_data_exclusion_validation_and_confirmation():
    impact = dict(pollutant='SO2', decision='exclude', basis='仪器故障', start='2026-09-10T01:00:00+08:00', end='2026-09-10T03:00:00+08:00')
    with pytest.raises(ValueError):
        service.submit_review(payload(data_impact=[impact]), source())
    impact.update(boundary_sources=['设备日志'], reasonableness_status='pass', reasonableness_basis='恢复后正常')
    record = service.submit_review(payload(data_impact=[impact]), source())
    decision = {**human(record), 'data_impact': record['data_impact']}
    with pytest.raises(ValueError):
        service.decide_review(record['review_id'], decision, {})
    decision['intervals_confirmed'] = True
    assert service.decide_review(record['review_id'], decision, {})['status'] == 'archived'


@pytest.mark.asyncio
async def test_tool_failure_has_no_card_and_success_has_generic_resource():
    tool = SubmitTaskReviewTool()
    assert not (await tool.execute(**payload()))['success']
    result = await tool.execute(context=SimpleNamespace(scheduled_task_context=source()), **payload())
    assert result['success']
    assert result['visuals'][0]['type'] == 'task_review'
    assert result['resources']


@pytest.mark.asyncio
async def test_historical_feedback_is_consumed_without_overwriting_new_result(tmp_path, monkeypatch):
    from app.services import task_review_learning
    from app.scheduled_tasks.storage.task_case_storage import TaskCaseStorage
    record = service.submit_review(payload(), source())
    record = service.decide_review(record['review_id'], human(record), {})
    feedback_id = record['human_feedback']['feedback_id']
    reopened = service.submit_review(payload(), source('exec-2'))
    async def distill(task, memory, review):
        return {'case_brief': '人工核验完成', 'findings': []}, '# 任务记忆\n人工核验经验'
    monkeypatch.setattr(task_review_learning, '_distill', distill)
    task = SimpleNamespace(task_id='task-1', history_learning=SimpleNamespace(consolidation_timeout_seconds=5, memory_char_budget=1000))
    storage = TaskCaseStorage('task-1', base_dir=tmp_path / 'learning')
    await task_review_learning.consume_feedback(record['review_id'], task, storage, feedback_id=feedback_id)
    latest = service.load_review(record['review_id'])
    assert latest['execution_id'] == 'exec-2'
    assert latest['status'] == 'pending_review'
    assert latest['history'][0]['human_feedback']['status'] == 'completed'
    await task_review_learning.consume_feedback(record['review_id'], task, storage, feedback_id=feedback_id)
    assert len(storage.read_cases()) == 1


def test_single_timestamp_impact_is_valid_but_reversed_range_is_rejected():
    impact = dict(pollutant='SO2', decision='keep', basis='单小时记录', start='2026-09-10T01:00:00+08:00', end='2026-09-10T01:00:00+08:00')
    assert service.DataImpact.model_validate(impact).start == service.DataImpact.model_validate(impact).end
    with pytest.raises(ValueError):
        service.DataImpact.model_validate({**impact, 'end': '2026-09-10T00:00:00+08:00'})
