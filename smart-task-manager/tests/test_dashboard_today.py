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
from models import Base, Task, EnergyLog
import ai_service


def make_session():
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    main.SessionLocal = TestingSessionLocal
    return TestingSessionLocal


@pytest.fixture
def test_client(monkeypatch):
    SessionLocal = make_session()
    monkeypatch.setattr(main, 'SessionLocal', SessionLocal)
    return TestClient(main.app)


def make_task(db, title, status="TODO", completed_at=None, deadline=None):
    t = Task(
        id=str(uuid.uuid4()),
        title=title,
        status=status,
        completed_at=completed_at,
        deadline=deadline,
    )
    db.add(t)
    db.commit()
    return t


class FakeCompletions:
    def __init__(self, content):
        self.content = content

    def create(self, model, messages):
        class Choice:
            def __init__(self, c):
                self.message = type('M', (), {'content': c})()

        return type('R', (), {'choices': [Choice(self.content)]})()


def fake_client(monkeypatch, content):
    class FakeClient:
        def __init__(self):
            self.chat = type('C', (), {'completions': FakeCompletions(content)})()

    monkeypatch.setattr(ai_service, 'client', FakeClient())


# ---------- parse_tasks_text (แยกหลายงานจากข้อความเดียว) ----------

def test_parse_tasks_text_splits_multiple(monkeypatch):
    fake_client(monkeypatch,
                '[{"title": "ล้างจาน", "estimated_time": 30}, {"title": "จัดห้อง", "estimated_time": 60}]')
    tasks = ai_service.parse_tasks_text('ล้างจานและจัดห้อง', datetime.date(2026, 8, 9))
    assert len(tasks) == 2
    assert tasks[0]['title'] == 'ล้างจาน'
    assert tasks[1]['estimated_time'] == 60


def test_parse_tasks_text_wraps_single_object(monkeypatch):
    fake_client(monkeypatch, '{"title": "งานเดียว", "estimated_time": 30}')
    tasks = ai_service.parse_tasks_text('งานเดียว', datetime.date(2026, 8, 9))
    assert len(tasks) == 1
    assert tasks[0]['title'] == 'งานเดียว'


def test_parse_tasks_text_bad_json_returns_empty(monkeypatch):
    fake_client(monkeypatch, 'ขอโทษครับ ไม่มี JSON')
    assert ai_service.parse_tasks_text('อะไรก็ได้', datetime.date(2026, 8, 9)) == []


def test_parse_tasks_text_ignores_non_dict_items(monkeypatch):
    fake_client(monkeypatch, '[{"title": "งาน ก"}, "ขยะ", 123]')
    tasks = ai_service.parse_tasks_text('งาน ก', datetime.date(2026, 8, 9))
    assert len(tasks) == 1
    assert tasks[0]['title'] == 'งาน ก'


# ---------- /chat คืน tasks หลายตัว (compat เก็บ task ตัวแรกไว้) ----------

def test_chat_create_task_multiple_tasks(test_client, monkeypatch):
    fake_client(monkeypatch,
                '[{"title": "งาน ก", "estimated_time": 30}, {"title": "งาน ข", "estimated_time": 60}]')
    resp = test_client.post('/chat', data={'text': 'ทำงาน ก แล้วก็ทำงาน ข'})
    data = resp.json()
    assert data['intent'] == 'create_task'
    assert len(data['tasks']) == 2
    assert data['tasks'][0]['title'] == 'งาน ก'
    assert data['tasks'][1]['title'] == 'งาน ข'
    assert data['task']['title'] == 'งาน ก'  # compat เดิม


def test_chat_create_task_no_valid_tasks(test_client, monkeypatch):
    fake_client(monkeypatch, '[{"title": ""}, {"estimated_time": 10}]')
    resp = test_client.post('/chat', data={'text': 'อะไรนะ'})
    data = resp.json()
    assert data['intent'] == 'create_task'
    assert data['tasks'] == []
    assert data['task'] is None


# ---------- /dashboard/today ----------

def test_dashboard_today_done_todo_and_plan(test_client):
    db = main.SessionLocal()
    from models import AppSetting
    db.add(AppSetting(key="tz_offset_hours", value="0"))
    db.commit()
    db.close()

    # ใช้ "วันนี้" จริง (ตาม timezone ที่ตั้ง 0) — เดิม hardcode 2026-08-09 ซึ่งพัง
    # พอเครื่องเดินวันที่ไป (ทดสอบแบบนี้ต้องผูกกับ real clock — gotcha: อย่า hardcode วันที่)
    today = main.get_local_today()
    yesterday = today - datetime.timedelta(days=1)
    tomorrow = today + datetime.timedelta(days=1)

    db = main.SessionLocal()
    make_task(db, 'เสร็จแล้ววันนี้', status='DONE',
              completed_at=datetime.datetime.combine(today, datetime.time(2, 0)))
    make_task(db, 'เสร็จเมื่อวาน', status='DONE',
              completed_at=datetime.datetime.combine(yesterday, datetime.time(2, 0)))
    make_task(db, 'ต้องส่งวันนี้', deadline=datetime.datetime.combine(today, datetime.time(18, 0)))
    make_task(db, 'ส่งพรุ่งนี้', deadline=datetime.datetime.combine(tomorrow, datetime.time(18, 0)))
    db.add(EnergyLog(id=str(uuid.uuid4()), energy_level=4, log_date=today))
    db.commit()
    db.close()

    data = test_client.get('/dashboard/today').json()
    assert data['date'] == str(today)
    assert data['energy_level'] == 4
    done = [t['title'] for t in data['done_today']]
    assert done == ['เสร็จแล้ววันนี้']  # ไม่นับของเมื่อวาน
    todo = [t['title'] for t in data['todo_today']]
    assert todo == ['ต้องส่งวันนี้']
    assert data['plan'] is not None
    assert data['plan']['energy_level'] == 4
    assert data['plan']['task_slots'] != []


def test_dashboard_today_no_energy_no_plan(test_client):
    db = main.SessionLocal()
    make_task(db, 'ไม่มีกำหนด', status='TODO')
    db.close()
    data = test_client.get('/dashboard/today').json()
    assert data['energy_level'] is None
    assert data['plan'] is None
    assert data['done_today'] == []
