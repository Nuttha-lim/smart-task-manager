import os
import sys
import uuid
import datetime
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import main
from models import Base, Task
from gamification import (
    DEFAULT_ACHIEVEMENTS,
    level_info,
    compute_task_points,
    update_streak,
    seed_achievements,
    gamification_status,
    get_nudge_settings,
    nudge_status,
    dismiss_nudge,
)

now_utc = datetime.datetime.utcnow


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


def make_task(db, title, status="TODO", estimated_time=None, deadline=None):
    t = Task(
        id=str(uuid.uuid4()),
        title=title,
        status=status,
        estimated_time=estimated_time,
        deadline=deadline,
    )
    db.add(t)
    db.commit()
    return t


def raw_task(title, estimated_time=None, deadline=None):
    return Task(
        id=str(uuid.uuid4()),
        title=title,
        status="TODO",
        estimated_time=estimated_time,
        deadline=deadline,
    )


# ---------- level_info ----------

def test_level_1_at_zero():
    assert level_info(0)["level"] == 1


def test_level_boundaries():
    assert level_info(99)["level"] == 2
    assert level_info(100)["level"] == 2
    assert level_info(299)["level"] == 3
    assert level_info(300)["level"] == 3
    assert level_info(600)["level"] == 4
    assert level_info(601)["level"] == 5


def test_level_progress_fields():
    info = level_info(120)  # อยู่ระหว่าง 100 -> 300 (ระดับ 3)
    assert info["into"] == 20
    assert info["for_next"] == 180  # 300 - 120


# ---------- compute_task_points ----------

def test_points_base_only():
    assert compute_task_points(raw_task("x")) == 10


def test_points_est_bonus():
    t = raw_task("x", estimated_time=90)  # 90//30=3 -> +6
    assert compute_task_points(t) == 16
    t2 = raw_task("x", estimated_time=300)  # min(4,10)//... max 4*2=8
    assert compute_task_points(t2) == 18


def test_points_ontime_bonus():
    future = now_utc() + datetime.timedelta(hours=2)
    t = raw_task("x", deadline=future)
    assert compute_task_points(t) == 15


def test_points_overdue_no_penalty():
    past = now_utc() - datetime.timedelta(hours=2)
    t = raw_task("x", deadline=past)
    assert compute_task_points(t) == 10  # ไม่หัก ไม่บวก


# ---------- streak ----------

def test_streak_new_count():
    db = make_session()()
    assert update_streak(db, datetime.date(2026, 8, 1)) == 1
    assert update_streak(db, datetime.date(2026, 8, 2)) == 2
    assert update_streak(db, datetime.date(2026, 8, 3)) == 3


def test_streak_same_day_no_double_count():
    db = make_session()()
    update_streak(db, datetime.date(2026, 8, 1))
    assert update_streak(db, datetime.date(2026, 8, 1)) == 1


def test_streak_grace_one_day():
    db = make_session()()
    update_streak(db, datetime.date(2026, 8, 1))
    update_streak(db, datetime.date(2026, 8, 2))
    # ข้ามไป 1 วัน (8/3 ไม่ได้ทำ) -> 8/4 ทำ -> ยังไม่หลุด (count คงเดิม)
    assert update_streak(db, datetime.date(2026, 8, 4)) == 2
    assert update_streak(db, datetime.date(2026, 8, 5)) == 3


def test_streak_resets_after_two_missed_days():
    db = make_session()()
    update_streak(db, datetime.date(2026, 8, 1))
    update_streak(db, datetime.date(2026, 8, 2))
    # ข้าม 2 วัน -> เริ่มใหม่
    assert update_streak(db, datetime.date(2026, 8, 5)) == 1


def test_streak_best_tracked():
    db = make_session()()
    update_streak(db, datetime.date(2026, 8, 1))
    update_streak(db, datetime.date(2026, 8, 2))
    update_streak(db, datetime.date(2026, 8, 5))  # reset -> 1
    from gamification import get_setting
    assert int(get_setting(db, "streak_best", 0)) == 2


# ---------- achievements ----------

def test_seed_idempotent():
    db = make_session()()
    seed_achievements(db)
    seed_achievements(db)
    from models import Achievement
    assert db.query(Achievement).count() == len(DEFAULT_ACHIEVEMENTS)


def test_first_task_achievement_on_complete(test_client):
    db = main.SessionLocal()
    t = make_task(db, "งานแรก")
    db.close()
    resp = test_client.patch(f'/tasks/{t.id}')
    assert resp.status_code == 200
    data = resp.json()
    assert data['points_earned'] == 10
    keys = [a['key'] for a in data['unlocked_achievements']]
    assert 'first_task' in keys  # งานแรก -> ก้าวแรก
    # โบนัส 20 แต้ม ถูกเติมให้ lifetime แล้ว
    assert data['total_points'] == 10 + 20


def test_achievement_unlock_only_once(test_client):
    db = main.SessionLocal()
    t1 = make_task(db, "งานหนึ่ง")
    db.close()
    test_client.patch(f'/tasks/{t1.id}')
    db = main.SessionLocal()
    t2 = make_task(db, "งานสอง")
    db.close()
    resp = test_client.patch(f'/tasks/{t2.id}')
    keys = [a['key'] for a in resp.json()['unlocked_achievements']]
    assert 'first_task' not in keys  # ปลดล็อกครั้งเดียว


def test_goal_achievement(test_client):
    resp = test_client.post('/goals?title=' + 'สอบปลายภาค', json=["อ่าน", "ทบทวน", "ทำโจทย์"])
    keys = [a['key'] for a in resp.json()['unlocked_achievements']]
    assert 'goal_1' in keys


def test_energy_achievement(test_client):
    resp = test_client.post('/energy-log?level=3')
    keys = [a['key'] for a in resp.json()['unlocked_achievements']]
    assert 'energy_1' in keys


# ---------- gamification_status ----------

def test_status_shape(test_client):
    resp = test_client.get('/gamification')
    assert resp.status_code == 200
    data = resp.json()
    assert data['level']['level'] >= 1
    assert data['streak']['current'] >= 0
    assert len(data['achievements']) == len(DEFAULT_ACHIEVEMENTS)


# ---------- nudge ----------

def test_nudge_settings_default_and_update(test_client):
    resp = test_client.get('/settings/nudge')
    assert resp.json()['enabled'] is True

    resp = test_client.post('/settings/nudge?enabled=false&times=' + json.dumps(['08:00']))
    assert resp.json()['enabled'] is False
    data = test_client.get('/settings/nudge').json()
    assert data['enabled'] is False
    assert data['times'] == ['08:00']


def test_nudge_hidden_when_disabled(test_client):
    test_client.post('/settings/nudge?enabled=false&times=' + json.dumps(['00:00']))
    db = main.SessionLocal()
    status = nudge_status(db, datetime.date(2026, 8, 9),
                          datetime.datetime(2026, 8, 9, 10, 0))
    db.close()
    assert status['should_show'] is False


def test_nudge_shows_once_per_day(test_client):
    db = main.SessionLocal()
    make_task(db, "งานค้าง")
    db.close()

    today = datetime.date(2026, 8, 9)
    now = datetime.datetime(2026, 8, 9, 10, 0)
    db = main.SessionLocal()
    status = nudge_status(db, today, now)
    assert status['should_show'] is True

    # ปิดวันนี้แล้ว -> ไม่เด้งซ้ำ
    dismiss_nudge(db, today)
    status2 = nudge_status(db, today, now)
    db.close()
    assert status2['should_show'] is False


def test_nudge_no_pending_tasks(test_client):
    db = main.SessionLocal()
    status = nudge_status(db, datetime.date(2026, 8, 9),
                          datetime.datetime(2026, 8, 9, 10, 0))
    db.close()
    assert status['should_show'] is False


def test_nudge_endpoint(test_client):
    db = main.SessionLocal()
    make_task(db, "งานค้าง")
    db.close()
    resp = test_client.get('/nudge')
    assert resp.status_code == 200
    assert 'should_show' in resp.json()


def test_nudge_dismiss_endpoint(test_client):
    resp = test_client.post('/nudge/dismiss')
    assert resp.status_code == 200
    assert resp.json()['dismissed'] is True


# ---------- rewards ----------

def test_delete_reward(test_client):
    create = test_client.post('/rewards?title=' + 'ดูหนัง' + '&point_cost=50')
    reward_id = create.json()['id']
    resp = test_client.delete(f'/rewards/{reward_id}')
    assert resp.json()['deleted'] is True
    remaining = test_client.get('/rewards').json()
    assert all(r['id'] != reward_id for r in remaining)
