import os
import sys
import uuid
import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models import Base, Task, Notification
import background_worker


@pytest.fixture
def session(monkeypatch):
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(background_worker, 'SessionLocal', TestingSessionLocal)
    # ไม่ให้แตะ push จริงตอนเทสต์ (run_once import push_service.push_notification ตอนเรียก)
    import push_service
    monkeypatch.setattr(push_service, 'push_notification', lambda db, notif: None)
    return TestingSessionLocal


def make_task(db, title, deadline, estimated_time=30):
    t = Task(
        id=str(uuid.uuid4()),
        title=title,
        deadline=deadline,
        estimated_time=estimated_time,
        deadline_time=deadline.strftime('%H:%M'),
    )
    db.add(t)
    db.commit()
    return t


def local_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=7)


def test_run_once_creates_notification_for_overdue_task(session, monkeypatch):
    db = session()
    make_task(db, "งานเลยกำหนด", local_now() - datetime.timedelta(hours=2))
    db.close()

    background_worker.run_once()

    db = session()
    notes = db.query(Notification).all()
    assert len(notes) == 1
    assert notes[0].urgency in ("critical", "overdue")
    assert "งานเลยกำหนด" in notes[0].message


def test_run_once_ignores_relaxed_task(session):
    db = session()
    make_task(db, "งานชิล", local_now() + datetime.timedelta(days=3))
    db.close()

    background_worker.run_once()

    db = session()
    assert db.query(Notification).count() == 0


def test_run_once_does_not_duplicate_notification(session):
    db = session()
    make_task(db, "งานเลยกำหนด", local_now() - datetime.timedelta(hours=2))
    db.close()

    background_worker.run_once()
    background_worker.run_once()
    background_worker.run_once()

    db = session()
    assert db.query(Notification).count() == 1  # was_notified_recently กันซ้ำ


def test_run_once_sends_push(monkeypatch, session):
    import push_service
    sent = []
    monkeypatch.setattr(push_service, 'push_notification',
                        lambda db, notif: sent.append(notif.id))
    db = session()
    make_task(db, "งานเลยกำหนด", local_now() - datetime.timedelta(hours=2))
    db.close()

    background_worker.run_once()
    assert len(sent) == 1


def test_run_once_db_error_does_not_crash(monkeypatch, session):
    monkeypatch.setattr(background_worker, 'todo_tasks_with_deadline',
                        lambda db: (_ for _ in ()).throw(Exception("db down")))
    background_worker.run_once()  # ไม่ crash


def test_start_if_enabled_respects_env(monkeypatch):
    monkeypatch.setattr(os, 'getenv', lambda k, d="0": "1" if k == "BACKGROUND_WORKER" else d)
    import threading
    started = []
    monkeypatch.setattr(threading, 'Thread', lambda *a, **k: started.append(k) or _FakeThread())

    class _FakeThread:
        def start(self):
            pass

    background_worker.start_if_enabled()
    assert len(started) == 1


def test_start_if_enabled_disabled_by_default(monkeypatch):
    monkeypatch.setattr(os, 'getenv', lambda k, d="0": d)
    import threading
    started = []
    monkeypatch.setattr(threading, 'Thread', lambda *a, **k: started.append(k))
    background_worker.start_if_enabled()
    assert len(started) == 0
