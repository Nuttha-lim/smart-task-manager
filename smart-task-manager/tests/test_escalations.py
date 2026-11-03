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

# local now (ตรงกับ get_local_now() ใน main.py เมื่อ tz_offset default = 7.0)
def local_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=7)


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


def make_task(db, title, deadline, estimated_time=30):
    # deadline_time ต้องตรงกับ deadline จริง ไม่งั้น compute_urgency จะรวมเป็น
    # "date 23:59" ทำให้ classification เพี้ยน (ดู escalation.task_deadline_datetime)
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


def test_escalation_urgencies(test_client):
    now = local_now()
    buffer_minutes = 60
    est = 30
    total = est + buffer_minutes  # 90 นาที

    db = main.SessionLocal()
    make_task(db, "งานเลยกำหนด", now - datetime.timedelta(hours=1), est)          # overdue
    make_task(db, "งานวิกฤติ", now + datetime.timedelta(minutes=total) - datetime.timedelta(minutes=5), est)  # critical
    make_task(db, "งานด่วน", now + datetime.timedelta(minutes=total + 30), est)   # high (latest_start +30m)
    make_task(db, "งานปานกลาง", now + datetime.timedelta(minutes=total + 120), est)  # medium (latest_start +2h)
    make_task(db, "งานชิล", now + datetime.timedelta(hours=48, minutes=total), est)   # low (latest_start +48h)
    db.close()

    resp = test_client.get(f'/tasks/escalations?buffer_minutes={buffer_minutes}')
    assert resp.status_code == 200
    data = resp.json()
    by_title = {d['title']: d for d in data}

    assert by_title['งานเลยกำหนด']['urgency'] == 'overdue'
    assert by_title['งานวิกฤติ']['urgency'] == 'critical'
    assert by_title['งานด่วน']['urgency'] == 'high'
    assert by_title['งานปานกลาง']['urgency'] == 'medium'
    assert by_title['งานชิล']['urgency'] == 'low'

    # ตรวจว่า response มี field ที่ frontend/worker ต้องใช้
    for d in data:
        assert 'latest_start' in d
        assert 'seconds_to_latest_start' in d
        assert 'seconds_to_deadline' in d
        assert d['estimated_time'] == est

    # ตรวจความสัมพันธ์ seconds กับ urgency (overdue ต้องมี deadline ผ่านแล้ว)
    assert by_title['งานเลยกำหนด']['seconds_to_deadline'] < 0


def test_escalation_uses_deadline_time(test_client):
    """deadline_time ต้องมีผล: deadline = วันนี้แต่ deadline_time ผ่านไปแล้ว → overdue
    (เดิมใช้เที่ยงคืนของวัน งานเลยถูกมองว่า "ยังไม่เลยกำหนด" ผิด)"""
    from escalation import task_deadline_datetime
    now = local_now()
    today = now.date()
    db = main.SessionLocal()
    t = Task(
        id=str(uuid.uuid4()),
        title="ส่งช่วงบ่าย",
        deadline=datetime.datetime(today.year, today.month, today.day),
        deadline_time=now.strftime('%H:%M'),
        estimated_time=30,
    )
    db.add(t)
    db.commit()

    combined = task_deadline_datetime(t)
    assert combined < now  # moment ส่งจริงผ่านไปแล้ว

    resp = test_client.get('/tasks/escalations?buffer_minutes=0')
    by_title = {d['title']: d for d in resp.json()}
    assert by_title['ส่งช่วงบ่าย']['urgency'] == 'overdue'
    db.close()


def test_compute_urgency_shared_module(test_client):
    """compute_urgency ต้องมาจาก escalation.py จุดเดียว (main/worker/celery ใช้ร่วม)"""
    from escalation import compute_urgency, todo_tasks_with_deadline
    now = local_now()
    db = main.SessionLocal()
    make_task(db, "งานวิกฤติ", now + datetime.timedelta(minutes=89), 30)  # est+buffer=90 → critical
    make_task(db, "งานชิล", now + datetime.timedelta(days=3), 30)

    tasks = todo_tasks_with_deadline(db)
    assert len(tasks) == 2

    t_critical = next(t for t in tasks if t.title == "งานวิกฤติ")
    _, _, _, urgency = compute_urgency(t_critical, 60, now)
    assert urgency == 'critical'

    t_low = next(t for t in tasks if t.title == "งานชิล")
    _, _, _, urgency = compute_urgency(t_low, 60, now)
    assert urgency == 'low'
    db.close()


def test_escalations_skip_done_and_no_deadline(test_client):
    db = main.SessionLocal()
    now = local_now()
    done_task = Task(
        id=str(uuid.uuid4()),
        title="เสร็จแล้ว",
        status="DONE",
        deadline=now + datetime.timedelta(hours=1),
    )
    no_deadline = Task(
        id=str(uuid.uuid4()),
        title="ไม่มีกำหนดส่ง",
    )
    db.add_all([done_task, no_deadline])
    db.commit()
    db.close()

    resp = test_client.get('/tasks/escalations')
    assert resp.status_code == 200
    assert resp.json() == []


def test_task_dict_includes_estimated_time(test_client):
    db = main.SessionLocal()
    t = Task(
        id=str(uuid.uuid4()),
        title="มีเวลาโดยประมาณ",
        estimated_time=45,
        deadline=local_now() + datetime.timedelta(days=1),
        deadline_time="17:00",
    )
    db.add(t)
    db.commit()
    db.close()

    resp = test_client.get('/tasks')
    assert resp.status_code == 200
    task = resp.json()[0]
    assert task['estimated_time'] == 45
    assert task['deadline'] is not None
    assert task['deadline_time'] == '17:00'
