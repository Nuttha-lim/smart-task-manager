import os
import sys
import uuid
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import main
from models import Base, Task

now_utc = datetime.datetime.utcnow


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


def make_task(db, title, status="TODO", deadline=None, last_check=None, created_at=None):
    t = Task(
        id=str(uuid.uuid4()),
        title=title,
        status=status,
        deadline=deadline,
        last_deadline_check=last_check,
        created_at=created_at or now_utc(),
    )
    db.add(t)
    db.commit()
    return t


def titles(response):
    return [d['title'] for d in response.json()]


def test_never_asked_returned(test_client):
    db = main.SessionLocal()
    make_task(db, "งานที่ยังไม่เคยถาม")
    db.close()

    resp = test_client.get('/tasks/needs-deadline-check')
    assert resp.status_code == 200
    assert titles(resp) == ["งานที่ยังไม่เคยถาม"]


def test_with_deadline_excluded(test_client):
    db = main.SessionLocal()
    make_task(db, "มีกำหนดส่งแล้ว", deadline=now_utc() + datetime.timedelta(days=3))
    db.close()

    resp = test_client.get('/tasks/needs-deadline-check')
    assert titles(resp) == []


def test_done_excluded(test_client):
    db = main.SessionLocal()
    make_task(db, "เสร็จแล้ว", status="DONE")
    db.close()

    resp = test_client.get('/tasks/needs-deadline-check')
    assert titles(resp) == []


def test_recently_checked_skipped(test_client):
    db = main.SessionLocal()
    make_task(db, "เพิ่งถามไป", last_check=now_utc() - datetime.timedelta(days=1))
    db.close()

    resp = test_client.get('/tasks/needs-deadline-check')
    assert titles(resp) == []


def test_stale_check_returned_again(test_client):
    db = main.SessionLocal()
    make_task(db, "ถามไปนานแล้ว", last_check=now_utc() - datetime.timedelta(days=8))
    db.close()

    resp = test_client.get('/tasks/needs-deadline-check')
    assert titles(resp) == ["ถามไปนานแล้ว"]


def test_oldest_first(test_client):
    db = main.SessionLocal()
    make_task(db, "งานใหม่", created_at=now_utc())
    make_task(db, "งานเก่า", created_at=now_utc() - datetime.timedelta(days=10))
    db.close()

    resp = test_client.get('/tasks/needs-deadline-check')
    assert titles(resp) == ["งานเก่า", "งานใหม่"]


def test_respond_deadline_sets_fields(test_client):
    db = main.SessionLocal()
    t = make_task(db, "จะตั้ง deadline")
    task_id = t.id
    db.close()

    deadline = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    resp = test_client.post(f'/tasks/{task_id}/deadline-check?deadline={deadline}')
    assert resp.status_code == 200
    assert resp.json()['deadline'] == deadline

    db = main.SessionLocal()
    updated = db.query(Task).filter(Task.id == task_id).first()
    assert updated.deadline is not None
    assert updated.last_deadline_check is not None
    db.close()

    resp = test_client.get('/tasks/needs-deadline-check')
    assert titles(resp) == []


def test_respond_skip_keeps_no_deadline(test_client):
    db = main.SessionLocal()
    t = make_task(db, "ยังไม่ทราบจริงๆ")
    task_id = t.id
    db.close()

    resp = test_client.post(f'/tasks/{task_id}/deadline-check?skip=true')
    assert resp.status_code == 200

    db = main.SessionLocal()
    updated = db.query(Task).filter(Task.id == task_id).first()
    assert updated.deadline is None
    assert updated.last_deadline_check is not None
    db.close()

    # เพิ่งถามไป ไม่ควรโผล่มาอีก
    resp = test_client.get('/tasks/needs-deadline-check')
    assert titles(resp) == []
