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
from models import Base, Task, EnergyLog, Holiday, ClassSchedule
from calendar_service import (
    seed_holidays,
    list_holidays,
    parse_timetable_text,
    create_schedules,
)


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


# ---------- seed_holidays ----------

def test_seed_holidays_idempotent():
    db = make_session()()
    added1 = seed_holidays(db, 2026)
    added2 = seed_holidays(db, 2026)
    assert added1 > 0
    assert added2 == 0
    # วันหยุดประจำปี 15 รายการ + เฉพาะปี 2026 อีก 8 รายการ
    assert db.query(Holiday).filter(
        Holiday.date >= datetime.date(2026, 1, 1),
        Holiday.date <= datetime.date(2026, 12, 31)).count() == 15 + 8


def test_seed_holidays_other_year():
    db = make_session()()
    seed_holidays(db, 2027)
    # ปี 2027 มีวันจันทรคติเพิ่ม 4 วัน → วันหยุดประจำปี 15 + เฉพาะปี 4
    assert db.query(Holiday).filter(
        Holiday.date >= datetime.date(2027, 1, 1),
        Holiday.date <= datetime.date(2027, 12, 31)).count() == 15 + 4


def test_seed_holidays_2027_lunar_dates():
    db = make_session()()
    seed_holidays(db, 2027)
    names = {h.date.isoformat(): h.name for h in db.query(Holiday).all()}
    assert names["2027-02-21"] == "วันมาฆบูชา"
    assert names["2027-05-20"] == "วันวิสาขบูชา"
    assert names["2027-07-18"] == "วันอาสาฬหบูชา"
    assert names["2027-07-19"] == "วันเข้าพรรษา"


def test_list_holidays_contains_key_dates():
    db = make_session()()
    holidays = list_holidays(db, 2026)
    names = {h["date"]: h["name"] for h in holidays}
    assert names["2026-01-01"] == "วันขึ้นปีใหม่"
    assert names["2026-03-03"] == "วันมาฆบูชา"          # เฉพาะปี (ตามจันทรคติ)
    assert names["2026-04-13"] == "วันสงกรานต์"
    assert names["2026-05-31"] == "วันวิสาขบูชา"
    assert names["2026-07-29"] == "วันอาสาฬหบูชา"
    assert names["2026-12-10"] == "วันรัฐธรรมนูญ"
    assert names["2026-12-31"] == "วันสิ้นปี"


def test_holidays_endpoint(test_client):
    resp = test_client.get('/holidays?year=2026')
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(h['date'] == '2026-07-29' for h in data)
    assert all(h['date'].startswith('2026-') for h in data)


def test_holidays_endpoint_default_year(test_client):
    resp = test_client.get('/holidays')
    assert resp.status_code == 200
    data = resp.json()
    # seed เองอัตโนมัติปีปัจจุบัน (timezone ที่ตั้งไว้)
    assert len(data) >= 15


# ---------- parse_timetable_text ----------

def test_parse_simple_line():
    r = parse_timetable_text("จันทร์ 09:00-10:30 คณิตศาสตร์ ห้อง 301")
    assert len(r["entries"]) == 1
    e = r["entries"][0]
    assert e["day_of_week"] == 1
    assert e["start_time"] == "09:00"
    assert e["end_time"] == "10:30"
    assert e["subject"] == "คณิตศาสตร์"
    assert e["location"] == "ห้อง 301"


def test_parse_multiple_lines_and_english_days():
    text = "จันทร์ 09:00-10:30 คณิตศาสตร์\nWed 13:00 ถึง 15:00 ฟิสิกส์ ห้องฟ้า\nศุกร์ 8:00–9:30 อังกฤษ"
    r = parse_timetable_text(text)
    assert len(r["entries"]) == 3
    assert r["entries"][1]["day_of_week"] == 3
    assert r["entries"][1]["start_time"] == "13:00"
    assert r["entries"][2]["day_of_week"] == 5


def test_parse_skips_bad_lines():
    text = "จันทร์ 09:00-10:30 คณิตศาสตร์\nกาก ๆ ไม่รู้จัก\nศุกร์ 8:00-9:30\nศุกร์ 10:00-09:00 ผิดเวลา"
    r = parse_timetable_text(text)
    assert len(r["entries"]) == 1
    assert len(r["skipped"]) == 3


def test_parse_strips_number_prefix():
    r = parse_timetable_text("1. จันทร์ 09:00-10:30 คณิตศาสตร์")
    assert len(r["entries"]) == 1
    assert r["entries"][0]["subject"] == "คณิตศาสตร์"


def test_parse_empty():
    r = parse_timetable_text("")
    assert r["entries"] == []
    assert r["skipped"] == []


def test_parse_endpoint_preview_not_saved(test_client):
    resp = test_client.post('/timetable/parse',
                            json={"text": "จันทร์ 09:00-10:30 คณิตศาสตร์"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 1
    # ยังไม่บันทึก — GET /timetable ต้องว่าง
    assert test_client.get('/timetable').json() == []


# ---------- POST /timetable (ยืนยันแล้ว) ----------

def test_save_timetable(test_client):
    entries = [{
        "day_of_week": 1, "start_time": "09:00", "end_time": "10:30",
        "subject": "คณิตศาสตร์", "location": "ห้อง 301",
    }]
    resp = test_client.post('/timetable', json=entries)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["created"][0]["subject"] == "คณิตศาสตร์"


def test_save_timetable_filters_invalid(test_client):
    entries = [
        {"day_of_week": 1, "start_time": "09:00", "end_time": "10:30",
         "subject": "ดี"},
        {"day_of_week": 9, "start_time": "09:00", "end_time": "10:30",
         "subject": "วันไม่ถูก"},
        {"day_of_week": 2, "start_time": "10:00", "end_time": "09:00",
         "subject": "เวลากลับด้าน"},
        {"day_of_week": 3, "start_time": "09:00", "end_time": "10:30",
         "subject": ""},
        "ไม่ใช่ dict",
    ]
    resp = test_client.post('/timetable', json=entries)
    assert resp.json()["count"] == 1


def test_timetable_sorted_and_delete(test_client):
    test_client.post('/timetable', json=[
        {"day_of_week": 2, "start_time": "09:00", "end_time": "10:30",
         "subject": "A"},
        {"day_of_week": 1, "start_time": "11:00", "end_time": "12:00",
         "subject": "B"},
    ])
    data = test_client.get('/timetable').json()
    assert [s["subject"] for s in data] == ["B", "A"]  # เรียงตามวัน

    sid = data[0]["id"]
    resp = test_client.delete(f'/timetable/{sid}')
    assert resp.json()["deleted"] is True
    assert len(test_client.get('/timetable').json()) == 1


# ---------- GET /calendar ----------

def test_calendar_aggregates(test_client):
    db = main.SessionLocal()
    t = Task(id=str(uuid.uuid4()), title="ส่งรายงาน",
             status="TODO",
             deadline=datetime.datetime(2026, 8, 15, 12, 0))
    e = EnergyLog(id=str(uuid.uuid4()), energy_level=4,
                  log_date=datetime.date(2026, 8, 10))
    db.add_all([t, e])
    db.commit()
    db.close()
    test_client.post('/timetable', json=[{
        "day_of_week": 6, "start_time": "09:00", "end_time": "10:30",
        "subject": "โปรแกรมมิ่ง", "location": "ห้อง 5",
    }])

    resp = test_client.get('/calendar?month=2026-08')
    assert resp.status_code == 200
    data = resp.json()
    assert data["month"] == "2026-08"
    assert any(x["date"] == "2026-08-15" and x["title"] == "ส่งรายงาน"
               for x in data["tasks"])
    assert any(x["date"] == "2026-08-10" and x["energy_level"] == 4
               for x in data["energy_logs"])
    # สงกรานต์ไม่อยู่เดือนนี้ แต่วันแม่ (12 ส.ค.) ต้องมี
    assert any(x["date"] == "2026-08-12" for x in data["holidays"])
    assert len(data["schedules"]) == 1


def test_calendar_default_month(test_client):
    resp = test_client.get('/calendar')
    assert resp.status_code == 200
    data = resp.json()
    assert "month" in data
    assert "tasks" in data and "holidays" in data and "schedules" in data


def test_calendar_bad_month_falls_back(test_client):
    resp = test_client.get('/calendar?month=abc')
    assert resp.status_code == 200
    assert "month" in resp.json()


# ---------- เปิด/ปิดวันหยุดในปฏิทิน (/settings/holidays) ----------

def test_holidays_setting_default_on(test_client):
    resp = test_client.get('/settings/holidays')
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_holidays_setting_toggle_off(test_client):
    resp = test_client.post('/settings/holidays?enabled=false')
    assert resp.json()["enabled"] is False
    assert test_client.get('/settings/holidays').json()["enabled"] is False


def test_holidays_setting_toggle_on(test_client):
    test_client.post('/settings/holidays?enabled=false')
    resp = test_client.post('/settings/holidays?enabled=true')
    assert resp.json()["enabled"] is True


def test_calendar_hides_holidays_when_disabled(test_client):
    test_client.post('/settings/holidays?enabled=false')
    data = test_client.get('/calendar?month=2026-08').json()
    assert data["holidays_enabled"] is False
    assert data["holidays"] == []


def test_calendar_shows_holidays_when_enabled(test_client):
    data = test_client.get('/calendar?month=2026-08').json()
    assert data["holidays_enabled"] is True
    assert any(h["date"] == "2026-08-12" for h in data["holidays"])
