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
from models import Base, Task, Routine
from calendar_service import (
    seed_default_routines,
    list_routines,
    create_routine,
    update_routine,
    delete_routine,
)
from ai_service import classify_chat


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


def make_task(db, title, status="TODO", deadline=None):
    t = Task(
        id=str(uuid.uuid4()),
        title=title,
        status=status,
        deadline=deadline,
    )
    db.add(t)
    db.commit()
    return t


# ---------- Routines: helpers (pure-ish) ----------

def test_seed_default_routines_on_empty_db():
    db = make_session()()
    seed_default_routines(db)
    names = [r["title"] for r in list_routines(db)]
    assert names[0] == "ตื่นนอน"
    assert names[-1] == "เข้านอน"


def test_seed_default_routines_idempotent():
    db = make_session()()
    seed_default_routines(db)
    seed_default_routines(db)
    assert len(list_routines(db)) == 5


def test_list_routines_excludes_disabled():
    db = make_session()()
    seed_default_routines(db)
    r = db.query(Routine).first()
    update_routine(db, r.id, enabled=False)
    assert len(list_routines(db)) == 4
    assert len(list_routines(db, include_disabled=True)) == 5


def test_create_routine_valid():
    db = make_session()()
    r = create_routine(db, "อ่านหนังสือ", "21:00", "ก่อนนอน")
    assert r["title"] == "อ่านหนังสือ"
    assert r["time"] == "21:00"
    assert r["enabled"] is True


def test_create_routine_invalid_time_returns_none():
    db = make_session()()
    assert create_routine(db, "อ่านหนังสือ", "ตีสอง") is None
    assert create_routine(db, "", "21:00") is None


def test_update_routine_partial():
    db = make_session()()
    r = create_routine(db, "อ่านหนังสือ", "21:00")
    updated = update_routine(db, r["id"], time="22:30", description="พักผ่อน")
    assert updated["time"] == "22:30"
    assert updated["title"] == "อ่านหนังสือ"
    assert updated["description"] == "พักผ่อน"


def test_update_routine_invalid_time_ignored():
    db = make_session()()
    r = create_routine(db, "อ่านหนังสือ", "21:00")
    updated = update_routine(db, r["id"], time="ไม่ใช่เวลา")
    assert updated["time"] == "21:00"


def test_delete_routine():
    db = make_session()()
    r = create_routine(db, "อ่านหนังสือ", "21:00")
    assert delete_routine(db, r["id"]) is True
    assert delete_routine(db, r["id"]) is False
    assert len(list_routines(db)) == 5  # กลับเป็น seed พื้นฐาน


# ---------- Routines: endpoints ----------

def test_get_calendar_routines_endpoint(test_client):
    resp = test_client.get('/calendar/routines')
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["routines"]) == 5


def test_get_routines_all_include_disabled(test_client):
    resp = test_client.get('/routines')
    assert resp.status_code == 200
    assert len(resp.json()["routines"]) == 5


def test_post_routines_endpoint(test_client):
    resp = test_client.post('/routines', params={'title': 'จ๊อกกิ้ง', 'time': '06:30'})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["routine"]["title"] == "จ๊อกกิ้ง"


def test_post_routines_invalid_time(test_client):
    resp = test_client.post('/routines', params={'title': 'จ๊อกกิ้ง', 'time': 'เช้า'})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_put_routines_endpoint(test_client):
    r = test_client.post('/routines', params={'title': 'จ๊อกกิ้ง', 'time': '06:30'}).json()["routine"]
    resp = test_client.put(f"/routines/{r['id']}", params={'time': '06:45'})
    assert resp.json()["ok"] is True
    assert resp.json()["routine"]["time"] == "06:45"


def test_delete_routines_endpoint(test_client):
    r = test_client.post('/routines', params={'title': 'จ๊อกกิ้ง', 'time': '06:30'}).json()["routine"]
    resp = test_client.delete(f"/routines/{r['id']}")
    assert resp.json()["ok"] is True


def test_delete_routines_not_found(test_client):
    resp = test_client.delete('/routines/not-exist-id')
    assert resp.json()["ok"] is False


def test_calendar_payload_includes_routines(test_client):
    resp = test_client.get('/calendar', params={'month': '2026-08'})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["routines"], list)
    assert len(data["routines"]) >= 5


# ---------- cancel_task: classify + chat flow ----------

def test_classify_cancel_task():
    assert classify_chat("ยกเลิกงานล้างจาน") == "cancel_task"
    assert classify_chat("ลบงานอ่านหนังสือ") == "cancel_task"
    assert classify_chat("เอางานออกหน่อย") == "cancel_task"
    assert classify_chat("ลบการบ้านคณิต") == "cancel_task"


def test_classify_cancel_does_not_steal_timetable():
    # "ลบวิชา..." = แก้ตารางเรียน ไม่ใช่ยกเลิกงาน
    assert classify_chat("ลบวิชาคณิตศาสตร์") == "update_timetable"
    assert classify_chat("ล้างตารางเรียนทั้งหมด") == "update_timetable"


def test_chat_cancel_task_finds_match(test_client):
    db = main.SessionLocal()
    make_task(db, "ล้างจาน")
    make_task(db, "กวาดบ้าน")
    resp = test_client.post('/chat', data={'text': 'ยกเลิกงานล้างจาน'})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "cancel_task"
    titles = [t["title"] for t in data["tasks"]]
    assert "ล้างจาน" in titles
    assert "กวาดบ้าน" not in titles


def test_chat_cancel_task_no_match_falls_back_chat(test_client):
    db = main.SessionLocal()
    make_task(db, "ล้างจาน")
    resp = test_client.post('/chat', data={'text': 'ยกเลิกงานzzzqqq'})
    data = resp.json()
    assert data["intent"] == "chat"
    assert "หาไม่เจอ" in data["reply"]


def test_chat_cancel_task_no_tasks(test_client):
    resp = test_client.post('/chat', data={'text': 'ยกเลิกงานล้างจาน'})
    data = resp.json()
    assert data["intent"] == "chat"


def test_chat_cancel_generic_returns_recent(test_client):
    db = main.SessionLocal()
    make_task(db, "ล้างจาน")
    make_task(db, "กวาดบ้าน")
    resp = test_client.post('/chat', data={'text': 'ยกเลิกงาน'})
    data = resp.json()
    assert data["intent"] == "cancel_task"
    assert len(data["tasks"]) == 2


def test_chat_cancel_ignores_done_tasks(test_client):
    db = main.SessionLocal()
    make_task(db, "ล้างจาน", status="DONE")
    resp = test_client.post('/chat', data={'text': 'ยกเลิกงานล้างจาน'})
    data = resp.json()
    assert data["intent"] == "chat"


def test_cancel_flow_deletes_task(test_client):
    db = main.SessionLocal()
    t = make_task(db, "ล้างจาน")
    resp = test_client.post('/chat', data={'text': 'ยกเลิกงานล้างจาน'})
    task_id = resp.json()["tasks"][0]["id"]
    assert task_id == t.id
    del_resp = test_client.delete(f'/tasks/{task_id}')
    assert del_resp.status_code == 200
    assert db.query(Task).filter(Task.id == task_id).first() is None
