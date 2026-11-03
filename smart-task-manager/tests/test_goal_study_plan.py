import os
import sys
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import main
from models import Base, Goal, Task
from plan_service import build_goal_plan


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


def today():
    # ตรงกับ plan_service.build_goal_plan ที่ใช้ utcnow().date()
    return datetime.datetime.utcnow().date()


def create_goal(client, title="สอบปลายภาค", target_date=None, tasks=None):
    url = f'/goals?title={title}'
    if target_date:
        url += f'&target_date={target_date}'
    resp = client.post(url, json=tasks if tasks is not None else ["อ่านบทที่ 1", "ทำโจทย์", "สรุป"])
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------- เป้าหมาย + target_date ----------

def test_create_goal_with_target_date(test_client):
    g = create_goal(test_client, target_date=str(today() + datetime.timedelta(days=10)))
    assert g['id']

    goals = test_client.get('/goals').json()
    assert goals[0]['target_date'] == str(today() + datetime.timedelta(days=10))


def test_create_goal_without_target_date_is_none(test_client):
    g = create_goal(test_client)
    goals = test_client.get('/goals').json()
    assert goals[0]['target_date'] is None


def test_bad_target_date_ignored(test_client):
    # วันที่อ่านไม่ได้ → เก็บ null ไม่ crash (หลัก §9)
    g = create_goal(test_client, target_date='not-a-date')
    goals = test_client.get('/goals').json()
    assert goals[0]['target_date'] is None


# ---------- study plan ----------

def test_study_plan_distributes_over_days(test_client):
    target = today() + datetime.timedelta(days=5)
    g = create_goal(test_client, target_date=str(target), tasks=[f"งานย่อยที่ {i}" for i in range(1, 9)])
    goal_id = g['id']

    resp = test_client.get(f'/goals/{goal_id}/study-plan')
    assert resp.status_code == 200
    plan = resp.json()
    assert plan['goal_id'] == goal_id
    assert plan['target_date'] == str(target)
    assert plan['days_left'] == 5
    # ระดับ 3 = 150 นาที/วัน, งานละ 30 นาที → วันละ 5 งาน, 8 งาน = 2 วัน
    assert len(plan['days']) == 2
    day1 = plan['days'][0]
    assert day1['date'] == str(today() + datetime.timedelta(days=1))
    assert len(day1['tasks']) == 5
    assert day1['total_minutes'] == 150
    total = sum(d['total_minutes'] for d in plan['days'])
    assert total == 8 * 30
    assert plan['leftover'] == []


def test_study_plan_no_target_date_400(test_client):
    g = create_goal(test_client)
    resp = test_client.get(f"/goals/{g['id']}/study-plan")
    assert resp.status_code == 400
    assert 'วันเป้าหมาย' in resp.json()['detail']


def test_study_plan_expired_target_400(test_client):
    target = today() - datetime.timedelta(days=1)
    g = create_goal(test_client, target_date=str(target))
    resp = test_client.get(f"/goals/{g['id']}/study-plan")
    assert resp.status_code == 400


def test_study_plan_goal_not_found_404(test_client):
    resp = test_client.get('/goals/no-such-id/study-plan')
    assert resp.status_code == 404


def test_study_plan_excludes_done_subtasks(test_client):
    target = today() + datetime.timedelta(days=5)
    g = create_goal(test_client, target_date=str(target), tasks=["อ่านบทที่ 1", "ทำโจทย์", "สรุป"])
    goal_id = g['id']

    # ทำ "อ่านบทที่ 1" เสร็จ
    for t in g['tasks']:
        if t['title'] == 'อ่านบทที่ 1':
            test_client.patch(f"/tasks/{t['id']}")
            break

    plan = test_client.get(f'/goals/{goal_id}/study-plan').json()
    titles = [t['title'] for d in plan['days'] for t in d['tasks']]
    assert 'อ่านบทที่ 1' not in titles
    assert 'ทำโจทย์' in titles


def test_study_plan_no_tasks_returns_empty_days(test_client):
    target = today() + datetime.timedelta(days=5)
    g = create_goal(test_client, target_date=str(target), tasks=[])
    plan = test_client.get(f"/goals/{g['id']}/study-plan").json()
    assert plan['days'] == []
    assert plan['leftover'] == []


def test_build_goal_plan_returns_none_without_target(test_client):
    db = main.SessionLocal()
    goal = Goal(id='g1', title='ไม่ตั้งวัน')
    db.add(goal)
    db.commit()
    assert build_goal_plan(db, goal) is None
    goal.target_date = today() - datetime.timedelta(days=3)
    db.commit()
    assert build_goal_plan(db, goal) is None
    db.close()


def test_build_goal_plan_big_task_fits_whole(test_client):
    """งานชิ้นเดียวใหญ่กว่ากำลังวัน → ไม่ผ่าครึ่ง วางทั้งชิ้นในวันถัดไปที่ไม่มีงานลงพอดี"""
    db = main.SessionLocal()
    goal = Goal(id='g2', title='สอบคณิต', target_date=today() + datetime.timedelta(days=3))
    db.add(goal)
    db.add(Task(id='t-big', title='ทำข้อสอบเก่าทั้งฉบับ', goal_id='g2', estimated_time=200))
    db.add(Task(id='t-small', title='ทบทวนสูตร', goal_id='g2', estimated_time=30))
    db.commit()

    plan = build_goal_plan(db, goal, energy_level=3)  # 150 นาที/วัน
    assert plan['days_left'] == 3
    day1_titles = [t['title'] for t in plan['days'][0]['tasks']]
    assert day1_titles == ['ทบทวนสูตร']  # งานเล็กได้วันแรก
    assert plan['days'][0]['total_minutes'] == 30
    day2_titles = [t['title'] for t in plan['days'][1]['tasks']]
    assert day2_titles == ['ทำข้อสอบเก่าทั้งฉบับ']  # งานใหญ่ลงทั้งชิ้น ไม่ผ่าครึ่ง
    assert plan['days'][1]['total_minutes'] == 200
    assert plan['leftover'] == []
    db.close()
