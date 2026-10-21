from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.api.task_review_routes import router
from app.auth.dependencies import require_current_user
from app.services import task_review


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(task_review, 'get_data_registry', lambda: tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(id='operator', username='审核员')
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
