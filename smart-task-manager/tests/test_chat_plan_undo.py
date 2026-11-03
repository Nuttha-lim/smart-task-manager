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
from models import Base, Task
from ai_service import classify_chat, suggest_reward_cost, generate_reward_ideas
from plan_service import preview_plan, build_daily_plan


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


# ---------- classify_chat (pure) ----------

def test_classify_create_task_default():
    assert classify_chat("ล้างจานพรุ่งนี้เช้า 30 นาที") == "create_task"
    assert classify_chat("ส่งการบ้านคณิต") == "create_task"


def test_classify_plan_daily():
    assert classify_chat("แพลนวันนี้หน่อย") == "plan_daily"
    assert classify_chat("ช่วยจัดตารางงานวันนี้") == "plan_daily"
    assert classify_chat("แพลน") == "plan_daily"


def test_classify_plan_trip():
    assert classify_chat("ไปเที่ยวเชียงใหม่") == "plan_trip"
    assert classify_chat("อยากได้แพลนเที่ยว") == "plan_trip"


def test_classify_chat_greeting():
    assert classify_chat("สวัสดี") == "chat"
    assert classify_chat("hi") == "chat"
    assert classify_chat("ขอบคุณ") == "chat"


def test_classify_plan_daily_wins_over_create():
    # "แพลน" ควรชนะงานธรรมดา
    assert classify_chat("แพลนงานวันนี้") == "plan_daily"


# ---------- suggest_reward_cost / generate_reward_ideas (pure) ----------

def test_suggest_reward_cost_keywords():
    assert suggest_reward_cost("ดูหนัง 1 เรื่อง") == 80
    assert suggest_reward_cost("ซื้อขนม") == 30
    assert suggest_reward_cost("ไปเที่ยวทะเล") == 200


def test_suggest_reward_cost_fallback():
    assert suggest_reward_cost("รางวัลแปลก ๆ ที่ไม่รู้จัก") == 50


def test_generate_reward_ideas_count_and_limits():
    ideas = generate_reward_ideas(5)
    assert len(ideas) >= 5
    for idea in ideas:
        assert idea["title"]
        assert idea["point_cost"] > 0
        assert idea["max_per_day"] >= 1
        assert idea["max_per_month"] >= idea["max_per_day"]
        assert idea["max_per_year"] >= idea["max_per_month"]


# ---------- Undo task (ยกเลิกว่ายังทำไม่เสร็จ) ----------

def post_task(client, title, estimated_time=None):
    params = {'title': title}
    if estimated_time is not None:
        params['estimated_time'] = estimated_time
    return client.post('/tasks', params=params)


def test_undo_complete_reverses_points(test_client):
    c = post_task(test_client, 'งานทดสอบ', 30)
    task_id = c.json()['id']
    done = test_client.patch(f'/tasks/{task_id}')
    assert done.json()['status'] == 'DONE'
    earned = done.json()['points_earned']
    assert earned > 0
    points_after_done = test_client.get('/points').json()['points']

    undo = test_client.post(f'/tasks/{task_id}/undo')
    assert undo.json()['status'] == 'TODO'
    assert undo.json()['points_reversed'] == earned
    points_after_undo = test_client.get('/points').json()['points']
    assert points_after_undo == points_after_done - earned


def test_undo_non_done_task_returns_error(test_client):
    c = post_task(test_client, 'ยังไม่เสร็จ')
    task_id = c.json()['id']
    resp = test_client.post(f'/tasks/{task_id}/undo')
    assert 'error' in resp.json()


def test_undo_missing_task_returns_error(test_client):
    resp = test_client.post('/tasks/not-exist/undo')
    assert 'error' in resp.json()


def test_task_dict_includes_completed_at_and_points_awarded(test_client):
    c = post_task(test_client, 'งานมีเวลา')
    task_id = c.json()['id']
    test_client.patch(f'/tasks/{task_id}')
    resp = test_client.get('/tasks').json()
    done = next(t for t in resp if t['id'] == task_id)
    assert done['completed_at'] is not None
    assert done['points_awarded'] is not None
    assert done['status'] == 'DONE'


# ---------- Rewards: AI กำหนดแต้ม + limit ----------

def test_create_reward_ai_cost(test_client):
    resp = test_client.post('/rewards?title=' + 'ดูหนัง')
    data = resp.json()
    assert data['point_cost'] == 80  # จาก keyword hint
    assert data['source'] == 'user'
    assert 'id' in data


def test_create_reward_with_limits(test_client):
    resp = test_client.post('/rewards?title=เล่นเกม&max_per_day=1&max_per_month=10&max_per_year=50')
    data = resp.json()
    assert data['max_per_day'] == 1
    assert data['max_per_month'] == 10
    assert data['max_per_year'] == 50
    assert data['point_cost'] == 60


def test_reward_ideas_endpoint(test_client):
    resp = test_client.get('/rewards/ideas?n=5')
    ideas = resp.json()['ideas']
    assert len(ideas) >= 5
    for idea in ideas:
        assert idea['point_cost'] > 0


def test_add_reward_from_idea(test_client):
    resp = test_client.post('/rewards/ideas?title=' + 'ดูหนัง/ซีรีส์ 1 ตอน')
    data = resp.json()
    assert data['source'] == 'ai'
    assert data['point_cost'] == 80
    assert data['max_per_day'] == 1


def test_redeem_limited_by_day(test_client):
    resp = test_client.post('/rewards?title=เล่นเกม&max_per_day=1&max_per_month=10&max_per_year=50')
    reward_id = resp.json()['id']
    # เติมแต้มให้พอ (รางวัล 60 แต้ม)
    for i in range(7):
        c = post_task(test_client, f'งานสร้างแต้ม {i}')
        test_client.patch(f"/tasks/{c.json()['id']}")
    first = test_client.post(f'/rewards/{reward_id}/redeem')
    assert first.json()['redeemed'] is True
    second = test_client.post(f'/rewards/{reward_id}/redeem')
    assert 'error' in second.json()
    assert 'วันนี้' in second.json()['error']


def test_list_rewards_includes_usage_and_available(test_client):
    test_client.post('/rewards?title=ขนม&max_per_day=1')
    rewards = test_client.get('/rewards').json()
    assert len(rewards) >= 1
    r = rewards[0]
    assert 'usage' in r
    assert 'available' in r
    assert 'day' in r['usage']


# ---------- Daily Plan ----------

def test_plan_preview_lists_energy_levels(test_client):
    resp = test_client.get('/plan/preview')
    data = resp.json()
    assert 'levels' in data
    assert len(data['levels']) == 5
    assert 'free_minutes' in data


def test_plan_preview_bad_date(test_client):
    resp = test_client.get('/plan/preview?date=not-a-date')
    assert 'error' in resp.json()


def test_daily_plan_with_tasks(test_client):
    c = post_task(test_client, 'งาน A', 60)
    task_id = c.json()['id']
    resp = test_client.post('/plan/daily?energy_level=3')
    data = resp.json()
    assert data['energy_level'] == 3
    assert 'task_slots' in data
    assert 'schedules' in data
    assert 'next_day' in data
    placed_ids = [slot['task_id'] for slot in data['task_slots']]
    assert task_id in placed_ids


def test_daily_plan_respects_energy_capacity(test_client):
    for i in range(10):
        post_task(test_client, f'งาน {i}', 60)
    low = test_client.post('/plan/daily?energy_level=1').json()
    high = test_client.post('/plan/daily?energy_level=5').json()
    assert low['total_est'] < high['total_est']


# ---------- Chat endpoint ----------

def test_chat_create_task(test_client, monkeypatch):
    monkeypatch.setattr(main, 'parse_tasks_text', lambda text, today=None: [
        {'title': 'ล้างจาน', 'estimated_time': 30,
         'deadline': '2026-08-10', 'deadline_time': '09:00'},
    ])
    resp = test_client.post('/chat', data={'text': 'ล้างจานพรุ่งนี้เช้า 30 นาที'})
    data = resp.json()
    assert data['intent'] == 'create_task'
    assert data['task']['title'] == 'ล้างจาน'
    assert data['task']['estimated_time'] == 30
    assert main.SessionLocal().query(Task).count() == 0


def test_chat_greeting(test_client):
    resp = test_client.post('/chat', data={'text': 'สวัสดี'})
    assert resp.json()['intent'] == 'chat'


def test_chat_plan_daily(test_client):
    resp = test_client.post('/chat', data={'text': 'แพลนวันนี้'})
    data = resp.json()
    assert data['intent'] == 'plan_daily'
    assert 'plan_preview' in data


def test_chat_plan_trip(test_client):
    resp = test_client.post('/chat', data={'text': 'ไปเที่ยวเชียงใหม่'})
    assert resp.json()['intent'] == 'plan_trip'


def test_chat_empty_text(test_client):
    resp = test_client.post('/chat', data={'text': ''})
    assert resp.json()['intent'] == 'chat'


def test_chat_file_txt(test_client, monkeypatch):
    monkeypatch.setattr(main, 'analyze_file_text', lambda text, today=None: {
        'summary': 'ประชุมและทำงานบ้าน',
        'tasks': [{'title': 'ประชุม'}, {'title': 'ล้างห้องน้ำ'}],
    })
    content = "ประชุม 20/08 09:00\nล้างห้องน้ำ 21/08"
    resp = test_client.post('/chat', files={'file': ('note.txt', content, 'text/plain')})
    data = resp.json()
    assert data['intent'] == 'analyze_file'
    assert data['filename'] == 'note.txt'
    assert isinstance(data['tasks'], list)
    assert [task['title'] for task in data['tasks']] == ['ประชุม', 'ล้างห้องน้ำ']


def test_chat_unsupported_file(test_client):
    resp = test_client.post('/chat', files={'file': ('data.xyz', b'abc', 'application/octet-stream')})
    data = resp.json()
    assert data['intent'] == 'chat'
    assert 'อ่าน' in data['reply']


def test_chat_multiple_files(test_client, monkeypatch):
    monkeypatch.setattr(main, 'analyze_file_text', lambda text, today=None: {
        'summary': 'สรุปจากไฟล์',
        'tasks': [{'title': 'งาน A', 'estimated_time': 30},
                  {'title': 'งาน B', 'estimated_time': 45}],
    })
    resp = test_client.post('/chat', files=[
        ('files', ('one.txt', 'หนึ่ง'.encode('utf-8'), 'text/plain')),
        ('files', ('two.txt', 'สอง'.encode('utf-8'), 'text/plain')),
    ])
    data = resp.json()
    assert data['intent'] == 'analyze_file'
    assert len(data['tasks']) == 4  # 2 ไฟล์ × 2 งาน
    assert len(data['files']) == 2
    assert data['files'][0]['ok'] is True
    assert 'add_tasks' in data['suggested_actions']


def test_chat_file_ai_failure_keeps_others(test_client, monkeypatch):
    def fake(text, today=None):
        if 'good' in text:
            return {'summary': 'อ่านได้', 'tasks': [{'title': 'งานดี'}]}
        raise RuntimeError('AI หายใจไม่ออก')
    monkeypatch.setattr(main, 'analyze_file_text', fake)
    resp = test_client.post('/chat', files=[
        ('files', ('bad.txt', b'bad', 'text/plain')),
        ('files', ('good.txt', b'good', 'text/plain')),
    ])
    data = resp.json()
    assert data['intent'] == 'analyze_file'  # ยังมีไฟล์ที่อ่านได้ → ไม่ตายทั้งชุด
    assert len(data['files']) == 2
    assert len(data['tasks']) == 1
    assert 'อ่านไม่ได้' in data['reply']


def test_chat_file_all_fail_is_chat(test_client, monkeypatch):
    def boom(text, today=None):
        raise RuntimeError('boom')
    monkeypatch.setattr(main, 'analyze_file_text', boom)
    resp = test_client.post('/chat', files={'file': ('bad.txt', b'x', 'text/plain')})
    data = resp.json()
    assert data['intent'] == 'chat'
    assert 'อ่าน' in data['reply']
