import os
import sys
import uuid
import urllib.parse
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import main
from models import Base, Task
from spellcheck_service import resolve_text

# พจนานุกรมจำลองสำหรับเทสต์ (กันพึ่ง corpus + เร็ว + กำหนดผลลัพธ์ได้)
CORRECT = {'เสร็จ', 'เตรียม', 'รายงาน', 'ส่ง', 'สวัสดี'}
CORRECTIONS = {
    'เสรจ': ['เสร็จ', 'เสรี'],
    'เตรียมพ': ['เตรียม'],
    'สวสดี': ['สวัสดี'],
}


def fake_spell(word):
    if word in CORRECTIONS:
        return CORRECTIONS[word]
    return [word]


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


@pytest.fixture
def fake_dict(monkeypatch):
    monkeypatch.setattr('spellcheck_service._thai_spell', fake_spell)


# ---------- unit tests: resolve_text ----------

def test_corrects_misspelled_thai(fake_dict):
    result = resolve_text("เสรจ รายงาน", {}, set())
    assert result['final_text'] == "เสร็จ รายงาน"
    assert result['auto_corrected'] == [{'original': 'เสรจ', 'corrected': 'เสร็จ'}]


def test_keeps_correct_words(fake_dict):
    result = resolve_text("เตรียม รายงาน", {}, set())
    assert result['final_text'] == "เตรียม รายงาน"
    assert result['auto_corrected'] == []


def test_keeps_trusted_words_fake_dict(fake_dict):
    # จำนิสัย: เคยพิมพ์ "เสรจ" ไว้ในงานแล้ว -> ไม่ไปแก้
    result = resolve_text("เสรจ รายงาน", {}, {'เสรจ'})
    assert result['final_text'] == "เสรจ รายงาน"
    assert result['auto_corrected'] == []


def test_pref_override_wins_over_spell(fake_dict):
    # ผู้ใช้สั่งให้คงคำเดิม -> ชนะพจนานุกรม
    result = resolve_text("สวสดี", {'สวสดี': None}, set())
    assert result['final_text'] == "สวสดี"
    assert result['auto_corrected'] == []

    # ผู้ใช้สั่งให้แก้ -> ชนะ trusted (ตรวจ pref ก่อน)
    result = resolve_text("สวสดี", {'สวสดี': 'สวัสดี'}, {'สวสดี'})
    assert result['final_text'] == "สวัสดี"


def test_english_and_numbers_kept(fake_dict):
    result = resolve_text("printer 3D", {}, set())
    assert result['final_text'] == "printer 3D"
    assert result['auto_corrected'] == []


def test_fallback_when_pythainlp_unavailable(monkeypatch):
    monkeypatch.setattr('spellcheck_service._PYTHAINLP_OK', False)
    result = resolve_text("สวสดี รายงาน", {}, set())
    assert result['final_text'] == "สวสดี รายงาน"
    assert result['auto_corrected'] == []


# ---------- endpoint tests ----------

def test_auto_resolve_endpoint_corrects(test_client, fake_dict):
    resp = test_client.post('/spellcheck/auto-resolve?text=' + urllib.parse.quote('เตรียมพ สวสดี'))
    assert resp.status_code == 200
    data = resp.json()
    assert data['final_text'] == 'เตรียม สวัสดี'
    assert len(data['auto_corrected']) == 2


def test_auto_resolve_learns_from_task_history(test_client, fake_dict):
    # ผู้ใช้เคยสร้างงานชื่อ "สวสดี" (พิมพ์แบบนี้จริง ๆ) -> ครั้งนี้ไม่ไปแก้
    db = main.SessionLocal()
    db.add(Task(id=str(uuid.uuid4()), title="สวสดี"))
    db.commit()
    db.close()

    resp = test_client.post('/spellcheck/auto-resolve?text=' + urllib.parse.quote('สวสดี'))
    assert resp.status_code == 200
    assert resp.json()['final_text'] == 'สวสดี'


def test_pref_endpoint_correct_and_keep(test_client, fake_dict):
    # ตั้ง pref ให้แก้
    resp = test_client.post('/spellcheck/pref?word=' + urllib.parse.quote('สวสดี')
                            + '&corrected=' + urllib.parse.quote('สวัสดี'))
    assert resp.status_code == 200

    r1 = test_client.post('/spellcheck/auto-resolve?text=' + urllib.parse.quote('สวสดี'))
    assert r1.json()['final_text'] == 'สวัสดี'

    # เปลี่ยนเป็น "คงคำเดิม"
    resp = test_client.post('/spellcheck/pref?word=' + urllib.parse.quote('สวสดี')
                            + '&corrected=')
    assert resp.status_code == 200

    r2 = test_client.post('/spellcheck/auto-resolve?text=' + urllib.parse.quote('สวสดี'))
    assert r2.json()['final_text'] == 'สวสดี'
