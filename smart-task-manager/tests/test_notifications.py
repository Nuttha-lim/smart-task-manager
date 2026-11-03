import os
import sys
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import main
from models import Base, Notification, Device

@pytest.fixture
def test_client(monkeypatch):
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, 'SessionLocal', TestingSessionLocal)
    return TestClient(main.app)


def test_list_notifications_and_ack(test_client):
    db = main.SessionLocal()
    note = Notification(id=str(uuid.uuid4()), task_id=None, message='ทดสอบแจ้งเตือน', urgency='high', read=False)
    db.add(note)
    db.commit()
    note_id = note.id
    db.close()

    response = test_client.get('/notifications')
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]['message'] == 'ทดสอบแจ้งเตือน'
    assert data[0]['read'] is False

    ack_response = test_client.post(f'/notifications/{note_id}/ack')
    assert ack_response.status_code == 200
    assert ack_response.json() == {'ack': True}

    response_after = test_client.get('/notifications')
    assert response_after.json()[0]['read'] is True


def test_register_device(test_client):
    response = test_client.post('/devices', json={'device_token': 'token123', 'platform': 'android'})
    assert response.status_code == 200
    payload = response.json()
    assert payload['platform'] == 'android'
    assert 'id' in payload
    assert payload['id']
