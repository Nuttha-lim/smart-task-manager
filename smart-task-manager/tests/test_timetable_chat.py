import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import main
from models import Base
from ai_service import classify_chat
from calendar_service import (
    parse_timetable_command,
    detect_timetable,
    build_timetable_proposal,
    clean_timetable_entries,
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


# ---------- classify_chat: intent ใหม่ ----------

def test_classify_timetable_intents():
    assert classify_chat("ตารางเรียนของฉัน") == "set_timetable"
    assert classify_chat("ช่วยอ่านตารางสอนให้หน่อย") == "set_timetable"
    assert classify_chat("เพิ่มวิชาเคมี") == "update_timetable"
    assert classify_chat("ลบวิชาคณิต") == "update_timetable"
    assert classify_chat("ย้ายวิชาฟิสิกส์ไปวันพุธ") == "update_timetable"
    assert classify_chat("ล้างตาราง") == "update_timetable"


def test_classify_timetable_not_overriding_others():
    assert classify_chat("จัดตารางงานวันนี้") == "plan_daily"
    assert classify_chat("แพลนเที่ยวเชียงใหม่") == "plan_trip"
    assert classify_chat("ล้างจานพรุ่งนี้เช้า") == "create_task"
    assert classify_chat("ส่งการบ้านวิชาคณิต") == "create_task"


# ---------- detect_timetable ----------

def test_detect_timetable_true_for_schedule():
    text = "จันทร์ 09:00-10:30 คณิตศาสตร์\nอังคาร 10:00-11:30 ฟิสิกส์\nพุธ 13:00-14:30 เคมี"
    assert detect_timetable(text)


def test_detect_timetable_false_for_homework():
    assert not detect_timetable("ทำการบ้านคณิตศาสตร์ส่งพรุ่งนี้")
    assert not detect_timetable("")


# ---------- parse_timetable_command ----------

def test_command_add():
    c = parse_timetable_command("เพิ่มวิชาเคมี วันอังคาร 10:00-11:30 ห้อง 201")
    assert c["kind"] == "add"
    assert c["subject"] == "เคมี"
    assert c["day"] == 2
    assert c["start_time"] == "10:00"
    assert c["end_time"] == "11:30"
    assert c["location"] == "201"


def test_command_add_english_day_short():
    c = parse_timetable_command("เพิ่มคาบภาษาอังกฤษ Thu 13:00-14:30")
    assert c["kind"] == "add"
    assert c["day"] == 4
    assert c["start_time"] == "13:00"


def test_command_move():
    c = parse_timetable_command("ย้ายวิชาคณิตศาสตร์ จากวันจันทร์ ไปวันพฤหัสบดี 09:00-10:30")
    assert c["kind"] == "move"
    assert c["subject"] == "คณิตศาสตร์"
    assert c["from_day"] == 1
    assert c["to_day"] == 4


def test_command_move_single_day_is_destination():
    c = parse_timetable_command("ย้ายวิชาคณิตศาสตร์ ไปวันพุธ")
    assert c["kind"] == "move"
    assert c["from_day"] is None
    assert c["to_day"] == 3


def test_command_delete_with_day():
    c = parse_timetable_command("ลบวิชาคณิตศาสตร์วันจันทร์")
    assert c["kind"] == "delete"
    assert c["subject"] == "คณิตศาสตร์"
    assert c["day"] == 1


def test_command_clear_and_none():
    assert parse_timetable_command("ล้างตาราง")["kind"] == "clear"
    assert parse_timetable_command("ลบตารางเรียนทั้งหมด")["kind"] == "clear"
    assert parse_timetable_command("สวัสดี")["kind"] == "none"
    assert parse_timetable_command("")["kind"] == "none"


# ---------- build_timetable_proposal ----------

SCHEDULES = [
    {"id": "1", "day_of_week": 1, "start_time": "09:00", "end_time": "10:30",
     "subject": "คณิตศาสตร์", "location": "ห้อง 301"},
    {"id": "2", "day_of_week": 2, "start_time": "10:00", "end_time": "11:30",
     "subject": "ฟิสิกส์", "location": None},
]


def test_proposal_add_ok():
    p = build_timetable_proposal(parse_timetable_command("เพิ่มวิชาเคมี วันอังคาร 10:00-11:30 ห้อง 201"), [])
    assert p["ok"] is True
    assert p["entry"]["subject"] == "เคมี"


def test_proposal_add_missing_info():
    p = build_timetable_proposal(parse_timetable_command("เพิ่มวิชาอังกฤษ"), [])
    assert p["ok"] is False
    assert "ยังไม่ครบ" in p["summary"]


def test_proposal_delete_match():
    p = build_timetable_proposal(parse_timetable_command("ลบวิชาคณิต"), SCHEDULES)
    assert p["ok"] is True
    assert len(p["matched"]) == 1
    assert p["matched"][0]["id"] == "1"


def test_proposal_delete_no_match():
    p = build_timetable_proposal(parse_timetable_command("ลบวิชาประวัติศาสตร์"), SCHEDULES)
    assert p["ok"] is False
    assert "ไม่เจอ" in p["summary"]


def test_proposal_move():
    p = build_timetable_proposal(parse_timetable_command("ย้ายวิชาคณิตศาสตร์ ไปวันพุธ"), SCHEDULES)
    assert p["ok"] is True
    assert len(p["matched"]) == 1


def test_proposal_clear():
    p = build_timetable_proposal({"kind": "clear"}, SCHEDULES)
    assert p["ok"] is True
    assert len(p["matched"]) == 2


def test_clean_timetable_entries():
    clean = clean_timetable_entries([
        {"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": "คณิต"},
        {"day_of_week": 9, "start_time": "09:00", "end_time": "10:30", "subject": "เสีย"},
        {"day_of_week": 1, "start_time": "11:00", "end_time": "10:00", "subject": "เวลากลับ"},
        {"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": ""},
        "ไม่ใช่ dict",
    ])
    assert len(clean) == 1
    assert clean[0]["subject"] == "คณิต"


# ---------- /chat: ข้อความตารางเรียน ----------

def test_chat_set_timetable_text(test_client):
    resp = test_client.post('/chat', data={
        "text": "ตารางเรียน\nจันทร์ 09:00-10:30 คณิตศาสตร์ ห้อง 301\nอังคาร 10:00-11:30 ฟิสิกส์",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "set_timetable"
    assert len(data["entries"]) == 2
    assert data["entries"][0]["subject"] == "คณิตศาสตร์"
    assert data["entries"][0]["day_of_week"] == 1
    # ยังไม่บันทึก
    assert test_client.get('/timetable').json() == []


def test_chat_set_timetable_ai_fallback(test_client, monkeypatch):
    # parse_timetable_text ได้ 0-1 คาบ แต่ AI extract เจอทั้งตาราง
    def fake_extract(text, today=None):
        return {"entries": [{"day_of_week": 1, "start_time": "08:00", "end_time": "09:00", "subject": "A"},
                            {"day_of_week": 2, "start_time": "09:00", "end_time": "10:00", "subject": "B"}],
                "skipped": []}
    monkeypatch.setattr(main, 'extract_timetable', fake_extract)
    resp = test_client.post('/chat', data={"text": "ตารางเรียนวิชา\nวันจันทร์ A 08.00-09.00"})
    data = resp.json()
    assert data["intent"] == "set_timetable"
    assert len(data["entries"]) == 2


def test_chat_timetable_not_enough_is_chat(test_client):
    resp = test_client.post('/chat', data={"text": "ตารางเรียน"})
    data = resp.json()
    assert data["intent"] == "chat"
    assert "ตาราง" in data["reply"]


# ---------- /chat: คำสั่งแก้ตาราง ----------

def test_chat_update_timetable_add(test_client):
    resp = test_client.post('/chat', data={
        "text": "เพิ่มวิชาเคมี วันอังคาร 10:00-11:30 ห้อง 201"})
    data = resp.json()
    assert data["intent"] == "update_timetable"
    assert data["ok"] is True
    assert data["action"]["kind"] == "add"
    assert data["entry"]["subject"] == "เคมี"
    # ยังไม่เซฟ (รอผู้ใช้ยืนยัน)
    assert test_client.get('/timetable').json() == []


def test_chat_update_timetable_delete_matches(test_client):
    test_client.post('/timetable', json=[
        {"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": "คณิตศาสตร์"}])
    resp = test_client.post('/chat', data={"text": "ลบวิชาคณิต"})
    data = resp.json()
    assert data["intent"] == "update_timetable"
    assert data["ok"] is True
    assert len(data["matched"]) == 1


def test_chat_update_timetable_unknown_command(test_client):
    resp = test_client.post('/chat', data={"text": "เพิ่มวิชา X"})
    data = resp.json()
    assert data["intent"] == "update_timetable"
    assert data["ok"] is False


# ---------- /chat: ไฟล์ตารางเรียน ----------

def test_chat_timetable_file_deterministic(test_client):
    content = "จันทร์ 09:00-10:30 คณิตศาสตร์ ห้อง 301\nอังคาร 10:00-11:30 ฟิสิกส์\nพุธ 13:00-14:30 เคมี".encode("utf-8")
    resp = test_client.post('/chat', files=[('files', ('timetable.txt', content, 'text/plain'))])
    data = resp.json()
    assert data["intent"] == "set_timetable"
    assert len(data["entries"]) == 3
    assert data["suggested_actions"] == ["apply_timetable"]


def test_chat_timetable_file_ai_extract(test_client, monkeypatch):
    # เนื้อหาแบบตาราง (pipe) ที่ parse แบบบรรทัดไม่ได้ → AI ช่วย
    content = "วัน | เวลา | วิชา\nจันทร์ | 09:00-10:30 | คณิตศาสตร์\nอังคาร | 10:00-11:30 | ฟิสิกส์".encode("utf-8")

    def fake_extract(text, today=None):
        assert "จันทร์" in text
        return {"entries": [{"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": "คณิตศาสตร์"},
                            {"day_of_week": 2, "start_time": "10:00", "end_time": "11:30", "subject": "ฟิสิกส์"}],
                "skipped": []}
    monkeypatch.setattr(main, 'extract_timetable', fake_extract)
    resp = test_client.post('/chat', files=[('files', ('timetable.txt', content, 'text/plain'))])
    data = resp.json()
    assert data["intent"] == "set_timetable"
    assert len(data["entries"]) == 2


def test_chat_timetable_image(test_client, monkeypatch):
    # analyze_file_image ไม่เจองาน → ลองเป็นตารางเรียนด้วย vision
    monkeypatch.setattr(main, 'analyze_image_file', lambda *a, **k: {"summary": "", "tasks": []})
    monkeypatch.setattr(main, 'extract_timetable_image',
                        lambda *a, **k: {"entries": [{"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": "คณิต"},
                                                     {"day_of_week": 3, "start_time": "11:00", "end_time": "12:00", "subject": "ฟิสิกส์"}],
                                         "skipped": []})
    resp = test_client.post('/chat', files=[('files', ('timetable.png', b'fake-png', 'image/png'))])
    data = resp.json()
    assert data["intent"] == "set_timetable"
    assert len(data["entries"]) == 2


def test_chat_normal_file_still_analyze(test_client, monkeypatch):
    # ไฟล์ปกติที่ไม่ได้เป็นตาราง → ยังเป็น analyze_file เหมือนเดิม
    monkeypatch.setattr(main, 'analyze_file_text',
                        lambda text, today=None: {"summary": "เอกสาร", "tasks": [{"title": "งาน A"}]})
    resp = test_client.post('/chat', files=[('files', ('note.txt', 'ทบทวนบทเรียน'.encode('utf-8'), 'text/plain'))])
    data = resp.json()
    assert data["intent"] == "analyze_file"
    assert data["tasks"][0]["title"] == "งาน A"


# ---------- POST /timetable?replace + apply-change ----------

def test_timetable_replace(test_client):
    test_client.post('/timetable', json=[{"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": "เก่า"}])
    resp = test_client.post('/timetable?replace=true', json=[
        {"day_of_week": 2, "start_time": "10:00", "end_time": "11:30", "subject": "ใหม่"}])
    assert resp.json()["count"] == 1
    data = test_client.get('/timetable').json()
    assert len(data) == 1
    assert data[0]["subject"] == "ใหม่"


def test_apply_change_add(test_client):
    resp = test_client.post('/timetable/apply-change', json={
        "kind": "add", "subject": "เคมี", "day": 2, "start_time": "10:00", "end_time": "11:30"})
    assert "เพิ่ม" in resp.json()["summary"]
    assert len(resp.json()["schedules"]) == 1


def test_apply_change_delete(test_client):
    test_client.post('/timetable', json=[
        {"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": "คณิตศาสตร์"}])
    resp = test_client.post('/timetable/apply-change', json={"kind": "delete", "subject": "คณิต"})
    assert "ลบ" in resp.json()["summary"]
    assert resp.json()["schedules"] == []


def test_apply_change_delete_not_found(test_client):
    resp = test_client.post('/timetable/apply-change', json={"kind": "delete", "subject": "อะไรนะ"})
    assert "ไม่เจอ" in resp.json()["summary"]


def test_apply_change_move(test_client):
    test_client.post('/timetable', json=[
        {"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": "คณิตศาสตร์"}])
    resp = test_client.post('/timetable/apply-change', json={
        "kind": "move", "subject": "คณิต", "to_day": 3, "start_time": "13:00", "end_time": "14:30"})
    assert "ย้าย" in resp.json()["summary"]
    s = resp.json()["schedules"][0]
    assert s["day_of_week"] == 3
    assert s["start_time"] == "13:00"


def test_apply_change_clear(test_client):
    test_client.post('/timetable', json=[
        {"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": "คณิต"}])
    resp = test_client.post('/timetable/apply-change', json={"kind": "clear"})
    assert "ล้าง" in resp.json()["summary"]
    assert resp.json()["schedules"] == []
    assert test_client.get('/timetable').json() == []


def test_chat_full_flow_set_and_modify(test_client):
    # วางตาราง → บันทึกแทนที่ → สั่งลบวิชาผ่านแชท → ยืนยันผ่าน apply-change
    test_client.post('/chat', data={"text": "ตารางเรียน\nจันทร์ 09:00-10:30 คณิตศาสตร์\nอังคาร 10:00-11:30 ฟิสิกส์"})
    assert len(test_client.get('/timetable').json()) == 0  # ยังไม่เซฟ
    test_client.post('/timetable?replace=true', json=[
        {"day_of_week": 1, "start_time": "09:00", "end_time": "10:30", "subject": "คณิตศาสตร์"},
        {"day_of_week": 2, "start_time": "10:00", "end_time": "11:30", "subject": "ฟิสิกส์"}])
    assert len(test_client.get('/timetable').json()) == 2
    test_client.post('/chat', data={"text": "ลบวิชาฟิสิกส์"})
    resp = test_client.post('/timetable/apply-change', json={"kind": "delete", "subject": "ฟิสิกส์"})
    assert len(resp.json()["schedules"]) == 1


# ---------- รูปภาพ: ตารางเรียนต้องชนะงาน (AGENTS.md gotcha #16) ----------

def test_image_timetable_wins_over_tasks(test_client, monkeypatch):
    # สกรีนช็อตตารางเรียนมีวิชา+เวลา → analyze_image_file มองเป็น "งาน" ผิดทาง
    # ต้องลองอ่านเป็นตารางก่อน ไม่งั้น chat ไม่เข้าทาง set_timetable เลย
    called = {"analyze": False}

    def fake_extract(*a, **k):
        return {"entries": [{"day_of_week": 1, "start_time": "09:00", "end_time": "12:00", "subject": "คณิต"},
                            {"day_of_week": 2, "start_time": "13:00", "end_time": "16:00", "subject": "ฟิสิกส์"}],
                "skipped": []}

    def fake_analyze(*a, **k):
        called["analyze"] = True
        return {"summary": "", "tasks": [{"title": "งานปลอม"}]}

    monkeypatch.setattr(main, 'extract_timetable_image', fake_extract)
    monkeypatch.setattr(main, 'analyze_image_file', fake_analyze)
    resp = test_client.post('/chat', files=[('files', ('timetable.png', b'fake', 'image/png'))])
    data = resp.json()
    assert data["intent"] == "set_timetable"
    assert len(data["entries"]) == 2
    assert called["analyze"] is False  # อ่านตารางเจอแล้วไม่ต้องวิเคราะห์งานต่อ


def test_image_not_timetable_falls_to_analyze(test_client, monkeypatch):
    # รูปที่ไม่ใช่ตาราง → extract คืนว่าง → ไป analyze หางานตามปกติ
    monkeypatch.setattr(main, 'extract_timetable_image',
                        lambda *a, **k: {"entries": [], "skipped": []})
    monkeypatch.setattr(main, 'analyze_image_file',
                        lambda *a, **k: {"summary": "ใบงาน", "tasks": [{"title": "ทำแบบฝึกหัด"}]})
    resp = test_client.post('/chat', files=[('files', ('homework.png', b'fake', 'image/png'))])
    data = resp.json()
    assert data["intent"] == "analyze_file"
    assert data["tasks"][0]["title"] == "ทำแบบฝึกหัด"


def test_image_timetable_single_entry_not_enough(test_client, monkeypatch):
    # AI อ่านได้แค่ 1 คาบ (ไม่ชัวร์ว่าใช่ตารางไหม) → ไม่เข้าทางตาราง ไปหางานแทน
    monkeypatch.setattr(main, 'extract_timetable_image',
                        lambda *a, **k: {"entries": [{"day_of_week": 1, "start_time": "09:00",
                                                      "end_time": "12:00", "subject": "คณิต"}],
                                         "skipped": []})
    monkeypatch.setattr(main, 'analyze_image_file',
                        lambda *a, **k: {"summary": "", "tasks": [{"title": "งาน A"}]})
    resp = test_client.post('/chat', files=[('files', ('x.png', b'fake', 'image/png'))])
    assert resp.json()["intent"] == "analyze_file"


# ---------- _normalize_timetable_result (กันโครงสร้างเพี้ยน) ----------

def test_normalize_timetable_result():
    from ai_service import _normalize_timetable_result
    good = {"entries": [{"subject": "A"}], "skipped": []}
    assert _normalize_timetable_result(good) == good
    # object วิชาเดียว (ไม่มี entries) → ห่อเป็น array
    assert _normalize_timetable_result({"subject": "A", "day_of_week": 1}) == {
        "entries": [{"subject": "A", "day_of_week": 1}], "skipped": []}
    # ของเสีย → ว่าง ไม่ crash
    assert _normalize_timetable_result("ขยะ") == {"entries": [], "skipped": []}
    assert _normalize_timetable_result(None) == {"entries": [], "skipped": []}
