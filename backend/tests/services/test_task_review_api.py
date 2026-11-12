from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.api import task_review_routes
from app.api.task_review_routes import router
from app.auth.dependencies import require_current_user
from app.services import task_review


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(task_review, 'get_data_registry', lambda: tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(id='operator', username='审核员')
    from app.conversations import dependencies as conversation_dependencies

    class ReadableCatalog:
        async def require_read(self, session_id, user):
            if session_id == 'private-session':
                from fastapi import HTTPException
                raise HTTPException(404, 'session_not_found')

    monkeypatch.setattr(conversation_dependencies, '_service', ReadableCatalog())
    return TestClient(app)


def test_list_detail_confirm_and_stale_submission(client):
    record = task_review.submit_review(dict(subject_id='1', category='诊断', title='设备异常', summary='需核验',
        decision='needs_action', comment='请核验', checks=[dict(name='仪器状态', status='uncertain', basis='设备告警')]),
        dict(task_id='task', execution_id='run', task_name='诊断任务'))
    assert client.get('/api/task-reviews').json()['total'] == 1
    assert client.get('/api/task-reviews?category=工单').json()['total'] == 0
    assert client.get('/api/task-reviews/' + record['review_id']).json()['review']['title'] == '设备异常'
    payload = dict(version=1, action='confirm', decision='approve', comment='已核验', data_impact=[])
    response = client.post('/api/task-reviews/' + record['review_id'] + '/decision', json=payload)
    assert response.status_code == 200
    assert response.json()['review']['human_decision']['actor']['username'] == '审核员'
    assert client.get('/api/task-reviews').json()['total'] == 0
    assert client.get('/api/task-reviews?pending_only=false').json()['total'] == 1
    assert client.post('/api/task-reviews/' + record['review_id'] + '/decision', json=payload).status_code == 409
    assert client.get('/api/task-reviews/invalid').status_code == 400


def test_detail_resolves_one_authorized_conversation_without_execution_page(client, monkeypatch):
    record = task_review.submit_review(dict(subject_id='FA1', category='工单审核', title='故障工单', summary='需核验',
        decision='approve', comment='请核验', checks=[dict(name='事实', status='pass', basis='已核验')]),
        dict(task_id='task', execution_id='exec-target', task_name='工单审核'))
    async def resolve(review):
        assert review['execution_id'] == 'exec-target'
        return 'scheduled-session'
    monkeypatch.setattr(task_review_routes, 'resolve_review_conversation_session_id', resolve)

    response = client.get('/api/task-reviews/' + record['review_id'])

    assert response.status_code == 200
    assert response.json()['review']['conversation_session_id'] == 'scheduled-session'
    assert 'conversation_session_id' not in client.get('/api/task-reviews').json()['reviews'][0]


def test_detail_does_not_expose_unreadable_conversation(client, monkeypatch):
    record = task_review.submit_review(dict(subject_id='FA1', category='工单审核', title='故障工单', summary='需核验',
        decision='approve', comment='请核验', checks=[dict(name='事实', status='pass', basis='已核验')]),
        dict(task_id='task', execution_id='exec-private', task_name='工单审核'))
    async def resolve(review):
        return 'private-session'
    monkeypatch.setattr(task_review_routes, 'resolve_review_conversation_session_id', resolve)

    response = client.get('/api/task-reviews/' + record['review_id'])

    assert response.status_code == 200
    assert response.json()['review']['conversation_session_id'] is None
