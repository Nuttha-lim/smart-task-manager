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
from ai_service import assess_breakdown


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


# ---------- assess_breakdown (pure, deterministic) ----------

def test_good_breakdown_is_good():
    a = assess_breakdown(["อ่านหนังสือบทที่ 1", "ทำแบบฝึกหัด", "สรุปเนื้อหา", "ทวนโจทย์เก่า"])
    assert a["verdict"] == "good"
    assert a["issues"] == []


def test_blank_tasks_ignored():
    a = assess_breakdown(["อ่านบทที่ 1", None, "   ", "สรุปเนื้อหา", "ทวนโจทย์"])
    assert a["verdict"] == "good"
    assert a["issues"] == []


def test_too_short_flagged():
    a = assess_breakdown(["อ่าน", "ทำ", "สรุป"])
    assert a["verdict"] == "needs_review"
    assert any(i["type"] == "too_short" for i in a["issues"])


def test_too_long_flagged():
    a = assess_breakdown(["x" * 61, "ทำแบบฝึกหัด"])
    assert any(i["type"] == "too_long" for i in a["issues"])


def test_duplicate_flagged():
    a = assess_breakdown(["อ่านบทที่ 1", "อ่านบทที่ 1", "ทำแบบฝึกหัด"])
    dups = [i for i in a["issues"] if i["type"] == "duplicate"]
    assert len(dups) == 1
    assert "ซ้ำกับข้อ 1" in dups[0]["message"]


def test_too_few_warning():
    a = assess_breakdown(["อ่านบทที่ 1"])
    assert a["verdict"] == "needs_review"
    assert any("น้อยไป" in w for w in a["warnings"])


def test_too_many_warning():
    a = assess_breakdown([f"งานย่อยที่ {i}" for i in range(1, 10)])
    assert any("เยอะไป" in w for w in a["warnings"])


# ---------- endpoints ----------

def test_decompose_preview_returns_assessment(test_client, monkeypatch):
    monkeypatch.setattr(main, 'decompose_goal', lambda title: ["อ่านบทที่ 1", "ทำแบบฝึกหัด", "สรุป"])
    resp = test_client.post('/goals/decompose?title=' + 'สอบปลายภาค')
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "สอบปลายภาค"
    assert len(data["tasks"]) == 3
    assert data["assessment"]["verdict"] == "good"


def test_decompose_preview_does_not_save(test_client, monkeypatch):
    monkeypatch.setattr(main, 'decompose_goal', lambda title: ["อ่านบทที่ 1", "ทำแบบฝึกหัด"])
    test_client.post('/goals/decompose?title=' + 'สอบปลายภาค')
    resp = test_client.get('/goals')
    assert resp.json() == []


def test_decompose_preview_survives_ai_failure(test_client, monkeypatch):
    def boom(title):
        raise RuntimeError("AI ดับ")
    monkeypatch.setattr(main, 'decompose_goal', boom)
    resp = test_client.post('/goals/decompose?title=' + 'สอบปลายภาค')
    assert resp.status_code == 200
    data = resp.json()
    assert data["tasks"] == []
    assert data["assessment"]["verdict"] == "needs_review"


def test_create_goal_with_confirmed_tasks(test_client):
    resp = test_client.post(
        '/goals?title=' + 'สอบปลายภาค',
        json=["อ่านบทที่ 1", "ทำแบบฝึกหัด", "สรุปเนื้อหา"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tasks"]) == 3

    resp2 = test_client.get('/goals')
    goals = resp2.json()
    assert len(goals) == 1
    assert len(goals[0]["tasks"]) == 3


def test_create_goal_filters_blank_tasks(test_client):
    resp = test_client.post(
        '/goals?title=' + 'สอบปลายภาค',
        json=["อ่านบทที่ 1", "", "   ", "สรุปเนื้อหา"],
    )
    assert len(resp.json()["tasks"]) == 2


def test_create_goal_falls_back_to_ai_without_body(test_client, monkeypatch):
    monkeypatch.setattr(main, 'decompose_goal', lambda title: ["AI ข้อ 1", "AI ข้อ 2"])
    resp = test_client.post('/goals?title=' + 'สอบปลายภาค')
    assert resp.status_code == 200
    assert len(resp.json()["tasks"]) == 2
