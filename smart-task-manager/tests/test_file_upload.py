import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import main
import file_service
from models import Base, Task


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


# ---------- extract_text_from_file ----------

def test_extract_txt_utf8():
    text = file_service.extract_text_from_file("homework.txt", "งานที่ 1\nส่งพรุ่งนี้\n\n".encode("utf-8"))
    assert "งานที่ 1" in text
    assert "ส่งพรุ่งนี้" in text
    # ตัดบรรทัดว่างทิ้ง
    assert "\n\n" not in text


def test_extract_md_and_csv():
    md = file_service.extract_text_from_file("notes.md", "# หัวข้อ\n- รายการ A".encode("utf-8"))
    assert "หัวข้อ" in md and "รายการ A" in md
    csv = file_service.extract_text_from_file("t.csv", "a,b\n1,2".encode("utf-8"))
    assert "1,2" in csv


def test_extract_rtf_strips_control_words():
    rtf = r"{\rtf1\ansi การบ้าน {\b คณิตศาสตร์} \par ส่ง 2026-08-20 }"
    text = file_service.extract_text_from_file("doc.rtf", rtf.encode("utf-8"))
    assert "การบ้าน" in text
    assert "คณิตศาสตร์" in text
    assert r"\b" not in text


def test_extract_pdf_via_pypdf(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "การบ้านฟิสิกส์ ส่ง 2026-08-15"

    class FakeReader:
        def __init__(self, stream):
            self.pages = [FakePage()]

    monkeypatch.setattr(file_service, 'PdfReader', FakeReader)
    text = file_service.extract_text_from_file("doc.pdf", b"%PDF-fake")
    assert "การบ้านฟิสิกส์" in text


def test_extract_docx_via_python_docx(monkeypatch):
    class FakeParagraph:
        def __init__(self, text):
            self.text = text

    class FakeDoc:
        def __init__(self, stream):
            self.paragraphs = [FakeParagraph("รายงานส่งสัปดาห์หน้า")]
            self.tables = []

    monkeypatch.setattr(file_service, 'Document', FakeDoc)
    text = file_service.extract_text_from_file("doc.docx", b"fake")
    assert "รายงานส่งสัปดาห์หน้า" in text


def test_extract_unsupported_raises():
    with pytest.raises(ValueError):
        file_service.extract_text_from_file("song.mp3", b"xxxx")


def test_is_supported_and_image():
    assert file_service.is_supported("a.pdf")
    assert file_service.is_supported("a.txt")
    assert not file_service.is_supported("a.exe")
    assert file_service.is_image_file("photo.jpg")
    assert file_service.is_image_file("photo.PNG")
    assert not file_service.is_image_file("doc.pdf")


# ---------- POST /upload/analyze ----------

def test_upload_txt_preview_not_saved(test_client, monkeypatch):
    fake_result = {
        "summary": "มีงาน 2 อย่าง",
        "tasks": [
            {"title": "การบ้านคณิตศาสตร์", "deadline": "2026-08-20", "estimated_time": 45},
            {"title": "อ่านหนังสือฟิสิกส์", "deadline": "2026-08-22"},
            {"title": "  ", "deadline": "2026-08-30"},   # ของเสีย → ถูกกรอง
            {"deadline": "2026-09-01"},                   # ไม่มี title → ถูกกรอง
        ],
    }
    monkeypatch.setattr(main, 'analyze_file_text', lambda text, today: fake_result)

    resp = test_client.post('/upload/analyze',
                            files={"file": ("homework.txt", "การบ้าน...".encode("utf-8"), "text/plain")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "มีงาน 2 อย่าง"
    assert len(data["tasks"]) == 2
    assert data["tasks"][0]["deadline"] == "2026-08-20"
    assert data["tasks"][0]["deadline_time"] == "23:59"  # ไม่ได้ระบุเวลา → default
    # ยังไม่บันทึก — preview เท่านั้น
    assert test_client.get('/tasks').json() == []


def test_upload_image_uses_vision(test_client, monkeypatch):
    fake_result = {"summary": "สกรีนช็อตตารางงาน", "tasks": [{"title": "ส่งรายงานโครงงาน"}]}
    monkeypatch.setattr(main, 'analyze_image_file',
                        lambda data, filename, today: fake_result)
    resp = test_client.post('/upload/analyze',
                            files={"file": ("syllabus.jpg", b"\xff\xd8fake", "image/jpeg")})
    assert resp.status_code == 200
    assert resp.json()["tasks"][0]["title"] == "ส่งรายงานโครงงาน"


def test_upload_unsupported_extension(test_client):
    resp = test_client.post('/upload/analyze',
                            files={"file": ("notes.exe", b"xxx", "application/octet-stream")})
    assert resp.status_code == 200
    assert "tasks" in resp.json()
    assert resp.json()["tasks"] == []


def test_upload_ai_failure_falls_back_to_excerpt(test_client, monkeypatch):
    def boom(text, today):
        raise Exception("groq down")

    monkeypatch.setattr(main, 'analyze_file_text', boom)
    resp = test_client.post('/upload/analyze',
                            files={"file": ("data.txt", "เนื้อหาดิบมีอยู่".encode("utf-8"), "text/plain")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tasks"] == []
    assert "warning" in data
    assert "เนื้อหาดิบ" in data["text_excerpt"]


# ---------- POST /tasks/bulk ----------

def test_bulk_create_tasks(test_client):
    resp = test_client.post('/tasks/bulk', json=[
        {"title": "งาน A", "deadline": "2026-08-20", "deadline_time": "14:00", "estimated_time": 45},
        {"title": "งาน B"},
        {"title": ""},
        {"title": "งาน C", "deadline": "ไม่ใช่วันที่"},
        "junk ไม่ใช่ dict",
    ])
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    created = data["created"]
    # งาน A เก็บ deadline + เวลาได้ครบ
    a = next(t for t in created if t["title"] == "งาน A")
    assert a["deadline"] == "2026-08-20"
    assert a["deadline_time"] == "14:00"
    assert a["estimated_time"] == 45
    # งาน C วันที่ไม่ถูกต้อง → deadline เป็น None ไม่ crash
    c = next(t for t in created if t["title"] == "งาน C")
    assert c["deadline"] is None


def test_bulk_tasks_visible_in_list(test_client):
    test_client.post('/tasks/bulk', json=[{"title": "งาน X"}])
    tasks = test_client.get('/tasks').json()
    assert any(t["title"] == "งาน X" for t in tasks)


# ---------- _clean_json_text (qwen3.6-27b ใส่ <think>…</think> ใน content) ----------

def test_clean_json_strips_think_block():
    from ai_service import _clean_json_text
    raw = '\n<think>\nผู้ใช้ถาม... ฉันวิเคราะห์แล้ว\n</think>\n\n{"summary": "งานมี 2 อย่าง", "tasks": [{"title": "ล้างจาน"}]}'
    assert _clean_json_text(raw) == '{"summary": "งานมี 2 อย่าง", "tasks": [{"title": "ล้างจาน"}]}'


def test_clean_json_think_with_braces_inside():
    from ai_service import _clean_json_text
    raw = '<think>เห็น {วงเล็บ} ใน reasoning ไม่ควรตัดเพี้ยน</think>\n[{"title": "งาน A"}]'
    assert _clean_json_text(raw) == '[{"title": "งาน A"}]'


def test_clean_json_fence_plus_think():
    from ai_service import _clean_json_text
    raw = '```json\n<think>คิดก่อน</think>\n{"tasks": []}\n```'
    assert _clean_json_text(raw) == '{"tasks": []}'
