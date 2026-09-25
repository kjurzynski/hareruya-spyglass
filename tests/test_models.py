from app.models import CheckRequest, JobStatus

def test_output_modes():
    assert CheckRequest(cards=['Tithe'],output='cheapest').output=='cheapest'
    assert CheckRequest(cards=['Tithe'],output='individual').output=='individual'
    assert CheckRequest(cards=['Tithe'],output='both').output=='both'

def test_job_status_output():
    assert JobStatus(job_id='x',status='complete',completed=1,total=1,output='both').output=='both'


def test_api_create_job_returns_json():
    from fastapi.testclient import TestClient
    from app.main import app

    response = TestClient(app).post(
        '/api/jobs',
        json={'cards': ['Tithe'], 'finish': 'all', 'output': 'cheapest'},
    )
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/json')
    assert 'job_id' in response.json()
