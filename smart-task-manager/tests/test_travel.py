import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import main
from models import Base, Task, TripPlan


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


FAKE_PLAN = {
    "days": [
        {"date": "2026-12-24", "title": "วันแรกถึงเชียงใหม่", "items": ["เดินเล่นย่านไนท์บาซาร์", "ทานข้าวค่ำ"]},
        {"date": "2026-12-25", "title": "ดอยสุเทพ", "items": ["ขึ้นดอยสุเทพ", "ชมวิวพระตำหนัก"]},
    ],
    "prep_tasks": [
        {"title": "จองตั๋วเครื่องบิน", "deadline": "2026-12-10", "deadline_time": "20:00", "estimated_time": 30},
        {"title": "จองที่พัก", "deadline": "2026-12-05", "deadline_time": None, "estimated_time": 20},
    ],
}


# ---------- POST /travel/plan (preview ไม่เซฟ) ----------

def test_preview_travel_plan(test_client, monkeypatch):
    monkeypatch.setattr(main, 'plan_trip', lambda d, s, e, n, t: FAKE_PLAN)
    resp = test_client.post('/travel/plan?destination=เชียงใหม่'
                            '&start_date=2026-12-24&end_date=2026-12-25&notes=เที่ยวพักผ่อน')
    assert resp.status_code == 200
    data = resp.json()
    assert data["destination"] == "เชียงใหม่"
    assert len(data["days"]) == 2
    assert data["days"][0]["title"] == "วันแรกถึงเชียงใหม่"
    assert len(data["prep_tasks"]) == 2
    # ยังไม่บันทึก
    assert test_client.get('/travel').json() == []


def test_preview_bad_date(test_client):
    resp = test_client.post('/travel/plan?destination=เชียงใหม่'
                            '&start_date=abc&end_date=2026-12-25')
    assert resp.status_code == 200
    assert "error" in resp.json()


def test_preview_ai_failure_returns_empty(test_client, monkeypatch):
    def boom(d, s, e, n, t):
        raise Exception("groq down")

    monkeypatch.setattr(main, 'plan_trip', boom)
    resp = test_client.post('/travel/plan?destination=เชียงใหม่'
                            '&start_date=2026-12-24&end_date=2026-12-25')
    assert resp.status_code == 200
    data = resp.json()
    assert data["days"] == [] and data["prep_tasks"] == []


# ---------- POST /travel (ยืนยันแล้ว → เซฟแผน + สร้างงาน) ----------

def test_save_travel_plan_creates_tasks(test_client):
    resp = test_client.post(
        '/travel?destination=เชียงใหม่&start_date=2026-12-24&end_date=2026-12-25&notes=เที่ยว',
        json={"days": FAKE_PLAN["days"], "prep_tasks": FAKE_PLAN["prep_tasks"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["destination"] == "เชียงใหม่"
    assert len(data["days"]) == 2
    # สร้างงานจริงจาก prep_tasks
    assert len(data["created_tasks"]) == 2
    tasks = test_client.get('/tasks').json()
    titles = {t["title"] for t in tasks}
    assert "จองตั๋วเครื่องบิน" in titles
    assert "จองที่พัก" in titles


def test_save_travel_filters_invalid_prep_tasks(test_client):
    resp = test_client.post(
        '/travel?destination=เชียงใหม่&start_date=2026-12-24&end_date=2026-12-25',
        json={"days": [], "prep_tasks": [
            {"title": "จองตั๋ว", "deadline": "2026-12-10"},
            {"title": ""},
            {"deadline": "2026-12-11"},
            "junk",
            {"title": "จัดกระเป๋า", "deadline": "2026-13-99"},  # วันที่ไม่ถูก → deadline None
        ]})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["created_tasks"]) == 2
    # GET /travel เก็บ prep_tasks เดิมที่ส่ง (แม้ตัวไหนสร้างงานไม่ได้)
    saved = test_client.get('/travel').json()
    assert len(saved) == 1
    assert len(saved[0]["prep_tasks"]) == 5


def test_travel_list_and_delete(test_client):
    test_client.post(
        '/travel?destination=เชียงใหม่&start_date=2026-12-24&end_date=2026-12-25',
        json={"days": [], "prep_tasks": []})
    plans = test_client.get('/travel').json()
    assert len(plans) == 1
    assert plans[0]["destination"] == "เชียงใหม่"

    plan_id = plans[0]["id"]
    resp = test_client.delete(f'/travel/{plan_id}')
    assert resp.json()["deleted"] is True
    assert test_client.get('/travel').json() == []


def test_travel_plan_rows_stored_in_db(test_client):
    test_client.post(
        '/travel?destination=เชียงใหม่&start_date=2026-12-24&end_date=2026-12-25',
        json={"days": FAKE_PLAN["days"], "prep_tasks": FAKE_PLAN["prep_tasks"]})
    db = main.SessionLocal()
    row = db.query(TripPlan).first()
    assert row.destination == "เชียงใหม่"
    assert str(row.start_date) == "2026-12-24"
    assert "ดอยสุเทพ" in row.days_json
    assert "จองตั๋ว" in row.prep_tasks_json
    db.close()
