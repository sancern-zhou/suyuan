from types import SimpleNamespace

import pytest

from app.services import jiangsu_review_learning as learning
from app.services import jiangsu_work_order_review as reviews
from app.scheduled_tasks.storage.task_case_storage import TaskCaseStorage


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(reviews, 'get_data_registry', lambda: tmp_path)
    review = {'review_id': 'feedback-test', 'status': 'pending_review', 'work_order_code': 'FA-test',
              'work_order_decision': 'approve', 'data_impact': [], 'exclusion_intervals': []}
    reviews.save_review(review)
    task = SimpleNamespace(history_learning=SimpleNamespace(consolidation_timeout_seconds=2, memory_char_budget=8000))
    return review, task, TaskCaseStorage(learning.TASK_ID, base_dir=tmp_path / 'memory')


@pytest.mark.parametrize('action', ['reject', 'needs_evidence'])
def test_return_requires_comment_and_is_one_decision(setup, action):
    review, _, _ = setup
    with pytest.raises(ValueError, match='必须填写审核意见'):
        reviews.mark_human_review(review['review_id'], action=action, actor={}, payload={'review_comment': '  '})
    assert reviews.load_review(review['review_id'])['status'] == 'pending_review'
    result = reviews.mark_human_review(review['review_id'], action=action, actor={'user_id': 'auditor'},
                                      payload={'review_comment': '附件不能证明复测已完成'})
    assert result['status'] == 'rejected'
    feedback = result['human_feedback']
    assert feedback['status'] == 'pending'
    assert feedback['differences']['work_order_decision'] == {'before': 'approve', 'after': 'reject'}
    assert feedback['actor']['user_id'] == 'auditor'


def test_confirm_without_comment_persists_outbox(setup):
    review, _, _ = setup
    result = reviews.mark_human_review(review['review_id'], action='confirm', actor={}, payload={})
    assert result['human_feedback']['differences'] == {}
    assert reviews.load_review(review['review_id'])['human_feedback']['status'] == 'pending'
    with pytest.raises(ValueError, match='已归档'):
        reviews.mark_human_review(review['review_id'], action='reject', actor={}, payload={'reason': '再次提交'})


def test_feedback_consumer_is_registered_only_for_jiangsu():
    from app.project_config.loader import load_project_context
    from app.services.lifecycle_manager import _configured_fetchers
    jiangsu = _configured_fetchers(load_project_context('jiangsu-ops'))
    feedback = next(item for item in jiangsu if item.name == 'jiangsu_review_feedback')
    assert feedback.schedule == '* * * * *'
    assert 'jiangsu_review_feedback' not in [item.name for item in _configured_fetchers(load_project_context('default'))]


def test_confirm_return_cannot_bypass_required_comment(setup):
    review, _, _ = setup
    with pytest.raises(ValueError, match='必须填写审核意见'):
        reviews.mark_human_review(review['review_id'], action='confirm', actor={},
                                  payload={'final_work_order_decision': 'reject'})


def test_differences_ignore_confirmation_flag_but_keep_boundary_changes():
    assert learning._comparable([{'start': '08:00', 'human_confirmed': True}]) == learning._comparable([{'start': '08:00'}])
    assert learning._comparable([{'start': '09:00'}]) != learning._comparable([{'start': '08:00'}])


@pytest.mark.asyncio
async def test_learning_retries_without_duplicate_case_and_preserves_memory_on_failure(setup, monkeypatch):
    review, task, storage = setup
    reviews.mark_human_review(review['review_id'], action='reject', actor={}, payload={'reason': '缺少复测结果'})
    storage.write_memory('原有经验不得丢失', {'version': 1})

    async def failing(*args):
        raise RuntimeError('temporary model failure')
    monkeypatch.setattr(learning, '_distill', failing)
    await learning.consume_feedback(review['review_id'], task, storage)
    assert storage.case_count() == 1
    assert storage.read_memory() == '原有经验不得丢失'
    assert reviews.load_review(review['review_id'])['human_feedback']['status'] == 'failed'

    async def success(*args):
        return {'case_brief': '复测证据不足，人工退回', 'findings': []}, '原有经验不得丢失\n本案反馈待核实'
    monkeypatch.setattr(learning, '_distill', success)
    await learning.consume_feedback(review['review_id'], task, storage)
    await learning.consume_feedback(review['review_id'], task, storage)
    assert storage.case_count() == 1
    assert storage.read_meta()['version'] == 2
    assert reviews.load_review(review['review_id'])['human_feedback']['status'] == 'completed'
    assert storage.read_cases()[0]['distilled']['case_brief'] == '复测证据不足，人工退回'


@pytest.mark.asyncio
async def test_learning_conflict_retries_instead_of_overwriting_new_memory(setup, monkeypatch):
    review, task, storage = setup
    reviews.mark_human_review(review['review_id'], action='confirm', actor={}, payload={})

    async def concurrent(*args):
        storage.write_memory('并发任务刚刚更新的经验', {'version': 1})
        return {'case_brief': '确认', 'findings': []}, '过时的反馈合并结果'
    monkeypatch.setattr(learning, '_distill', concurrent)
    await learning.consume_feedback(review['review_id'], task, storage)
    assert storage.read_memory() == '并发任务刚刚更新的经验'
    assert reviews.load_review(review['review_id'])['human_feedback']['status'] == 'failed'
