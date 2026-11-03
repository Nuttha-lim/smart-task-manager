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
from models import Base, ClassSchedule
from calendar_service import (
    schedule_overlaps_cancel,
    find_classes_to_cancel,
    create_cancellation,
    list_cancellations,
    delete_cancellation,
    parse_cancel_request,
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


def make_schedule(db, day_of_week, start, end, subject="คณิตศาสตร์"):
    s = ClassSchedule(id=str(uuid.uuid4()), day_of_week=day_of_week,
                      start_time=start, end_time=end, subject=subject)
    db.add(s)
    db.commit()
    return s


# ---------- classify_chat: รู้ว่า "ไม่มีเรียน" ไม่ใช่งานใหม่ ----------

def test_classify_cancel_classes_morning():
    assert classify_chat("เช้าวันจันทร์ไม่มีเรียน") == "cancel_classes"


def test_classify_cancel_classes_stop_class():
    assert classify_chat("หยุดเรียนวันอังคาร") == "cancel_classes"


def test_classify_cancel_classes_not_cancel_task():
    # "ยกเลิกเรียน" ต้องไปยกเลิกคาบ ไม่ใช่ยกเลิกงาน
    assert classify_chat("ยกเลิกเรียนวันพุธ") == "cancel_classes"


def test_classify_cancel_classes_tomorrow():
    assert classify_chat("พรุ่งนี้บ่ายไม่มีเรียน") == "cancel_classes"


def test_classify_cancel_task_still_works():
    assert classify_chat("ยกเลิกงานล้างจาน") == "cancel_task"


# ---------- parse_cancel_request (deterministic วัน/ช่วง) ----------

def test_parse_next_monday_morning():
    today = datetime.date(2026, 8, 7)  # ศุกร์
    r = parse_cancel_request("เช้าวันจันทร์ไม่มีเรียน", today)
    assert r is not None
    assert r["date"] == datetime.date(2026, 8, 10)  # จันทร์ถัดไป
    assert r["day_name"] == "จันทร์"
    assert r["start_time"] == "00:00"
    assert r["end_time"] == "12:00"


def test_parse_today_whole_day():
    today = datetime.date(2026, 8, 10)  # จันทร์
    r = parse_cancel_request("วันนี้ไม่มีเรียน", today)
    assert r["date"] == today
    assert r["start_time"] == "00:00"
    assert r["end_time"] == "23:59"


def test_parse_tomorrow_afternoon():
    today = datetime.date(2026, 8, 10)
    r = parse_cancel_request("พรุ่งนี้บ่ายหยุดเรียน", today)
    assert r["date"] == datetime.date(2026, 8, 11)
    assert r["start_time"] == "12:00"
    assert r["end_time"] == "18:00"


def test_parse_day_after_tomorrow():
    today = datetime.date(2026, 8, 10)
    r = parse_cancel_request("มะรืนนี้ไม่มีเรียน", today)
    assert r["date"] == datetime.date(2026, 8, 12)


def test_parse_same_weekday_uses_today():
    today = datetime.date(2026, 8, 10)  # จันทร์
    r = parse_cancel_request("วันจันทร์เช้าไม่มีเรียน", today)
    assert r["date"] == today


def test_parse_no_day_returns_none():
    today = datetime.date(2026, 8, 10)
    assert parse_cancel_request("เช้าไม่มีเรียน", today) is None
    assert parse_cancel_request("", today) is None


# ---------- schedule_overlaps_cancel (pure) ----------

def test_overlap_morning_class():
    s = {"start_time": "09:00", "end_time": "10:30"}
    assert schedule_overlaps_cancel(s, "00:00", "12:00")
    assert not schedule_overlaps_cancel(s, "12:00", "18:00")


def test_overlap_boundary():
    # จบ 12:00 ตรงขอบกับช่วงที่เริ่ม 12:00 → ไม่ทับ
    s = {"start_time": "10:30", "end_time": "12:00"}
    assert not schedule_overlaps_cancel(s, "12:00", "18:00")
    # เริ่ม 11:30 จบ 13:00 → ทับทั้งเช้าและบ่าย
    s2 = {"start_time": "11:30", "end_time": "13:00"}
    assert schedule_overlaps_cancel(s2, "00:00", "12:00")
    assert schedule_overlaps_cancel(s2, "12:00", "18:00")


# ---------- find_classes_to_cancel ----------

def test_find_only_matching_slot():
    db = make_session()()
    make_schedule(db, 1, "09:00", "10:30", "คณิต")       # จันทร์เช้า
    make_schedule(db, 1, "13:00", "14:30", "ฟิสิกส์")     # จันทร์บ่าย
    make_schedule(db, 2, "09:00", "10:30", "อังคารวิชา")  # อังคารเช้า
    monday = datetime.date(2026, 8, 10)  # จันทร์
    got = find_classes_to_cancel(db, monday, "00:00", "12:00")
    assert [c["subject"] for c in got] == ["คณิต"]


def test_find_whole_day():
    db = make_session()()
    make_schedule(db, 1, "09:00", "10:30", "คณิต")
    make_schedule(db, 1, "13:00", "14:30", "ฟิสิกส์")
    monday = datetime.date(2026, 8, 10)
    got = find_classes_to_cancel(db, monday)
    assert len(got) == 2


# ---------- CRUD endpoints ----------

def test_create_cancel_endpoint(test_client):
    db = main.SessionLocal()
    make_schedule(db, 1, "09:00", "10:30", "คณิต")
    resp = test_client.post('/timetable/cancel', params={
        'date': '2026-08-10', 'start_time': '00:00', 'end_time': '12:00',
        'reason': 'เช้าวันจันทร์ไม่มีเรียน',
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data['ok'] is True
    assert data['cancellation']['date'] == '2026-08-10'
    assert data['cancellation']['reason'] == 'เช้าวันจันทร์ไม่มีเรียน'
    assert [c['subject'] for c in data['affected']] == ['คณิต']


def test_create_cancel_bad_date(test_client):
    resp = test_client.post('/timetable/cancel', params={'date': 'not-a-date'})
    assert resp.json()['ok'] is False


def test_create_cancel_bad_time(test_client):
    resp = test_client.post('/timetable/cancel', params={
        'date': '2026-08-10', 'start_time': '18:00', 'end_time': '12:00',
    })
    assert resp.json()['ok'] is False


def test_list_and_delete_cancellations(test_client):
    test_client.post('/timetable/cancel', params={
        'date': '2026-08-10', 'start_time': '00:00', 'end_time': '12:00',
        'reason': 'ไม่มีเรียน',
    })
    r = test_client.get('/timetable/cancellations')
    cancels = r.json()['cancellations']
    assert len(cancels) == 1
    cid = cancels[0]['id']
    r = test_client.delete(f'/timetable/cancellations/{cid}')
    assert r.json()['ok'] is True
    assert test_client.get('/timetable/cancellations').json()['cancellations'] == []


def test_delete_missing_cancellation(test_client):
    resp = test_client.delete('/timetable/cancellations/nope')
    assert resp.json()['ok'] is False


# ---------- /calendar รวม cancellations ----------

def test_calendar_includes_cancellations(test_client):
    db = main.SessionLocal()
    make_schedule(db, 1, "09:00", "10:30", "คณิต")
    test_client.post('/timetable/cancel', params={
        'date': '2026-08-10', 'start_time': '00:00', 'end_time': '12:00',
        'reason': 'ไม่มีเรียน',
    })
    r = test_client.get('/calendar?month=2026-08')
    cancels = r.json()['cancellations']
    assert len(cancels) == 1
    assert cancels[0]['date'] == '2026-08-10'


# ---------- /chat flow ----------

def test_chat_cancel_classes_finds_schedule(test_client, monkeypatch):
    monkeypatch.setattr(main, 'get_local_today', lambda: datetime.date(2026, 8, 9))
    db = main.SessionLocal()
    make_schedule(db, 1, "09:00", "10:30", "คณิต")
    make_schedule(db, 1, "13:00", "14:30", "ฟิสิกส์")
    resp = test_client.post('/chat', data={'text': 'เช้าวันจันทร์ไม่มีเรียน'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['intent'] == 'cancel_classes'
    assert data['date'] == '2026-08-10'
    assert [c['subject'] for c in data['classes']] == ['คณิต']
    assert 'cancel_classes_confirm' in data.get('suggested_actions', [])


def test_chat_cancel_classes_no_schedule_that_day(test_client):
    db = main.SessionLocal()
    make_schedule(db, 2, "09:00", "10:30", "อังคารวิชา")  # อังคาร — เสาร์ไม่มี
    resp = test_client.post('/chat', data={'text': 'เสาร์นี้ไม่มีเรียน'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['intent'] == 'chat'  # ไม่ crash — บอกว่าไม่พบคาบ
    assert 'ไม่พบคาบเรียน' in data['reply']


def test_chat_cancel_classes_missing_day(test_client):
    resp = test_client.post('/chat', data={'text': 'เช้าไม่มีเรียน'})
    data = resp.json()
    assert data['intent'] == 'chat'
    assert 'วันให้ชัดขึ้น' in data['reply']


# ---------- helpers ตรง ๆ ----------

def test_create_cancellation_validation():
    db = make_session()()
    assert create_cancellation(db, None) is None
    assert create_cancellation(db, datetime.date(2026, 8, 10), "xx", "12:00") is None
    assert create_cancellation(db, datetime.date(2026, 8, 10), "14:00", "12:00") is None
    c = create_cancellation(db, datetime.date(2026, 8, 10), reason="เช้าไม่มา")
    assert c is not None
    assert list_cancellations(db)[0]["reason"] == "เช้าไม่มา"
    assert delete_cancellation(db, c["id"]) is True
    assert delete_cancellation(db, c["id"]) is False
