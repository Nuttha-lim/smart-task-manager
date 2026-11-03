import os
import sys
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import main
from models import Base, Device, Notification
import push_service


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


WEB_SUB = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-123",
    "keys": {"p256dh": "BP4X9h", "auth": "k2H1c"},
    "expirationTime": None,
}


# ---------- VAPID keys ----------

def test_get_vapid_keys_generates_and_idempotent():
    db = make_session()()
    pub1, priv1 = push_service.get_vapid_keys(db)
    assert pub1 and priv1
    pub2, priv2 = push_service.get_vapid_keys(db)
    assert pub1 == pub2 and priv1 == priv2  # ครั้งที่ 2 ได้ key เดิม (เก็บใน AppSetting)


def test_vapid_public_key_endpoint(test_client):
    resp = test_client.get('/push/vapid-public-key')
    assert resp.status_code == 200
    key = resp.json()['public_key']
    assert key and len(key) == 87  # uncompressed EC point (65 bytes) base64url


# ---------- send_web_push ----------

def test_send_web_push_calls_webpush(monkeypatch):
    db = make_session()()
    _, priv = push_service.get_vapid_keys(db)
    calls = {}

    def fake_webpush(**kwargs):
        calls['subscription'] = kwargs['subscription_info']
        calls['data'] = kwargs['data']
        calls['has_vapid'] = kwargs.get('vapid_private_key') is not None
        calls['claims'] = kwargs.get('vapid_claims')

    monkeypatch.setattr(push_service, 'webpush', fake_webpush)
    ok, expired = push_service.send_web_push(WEB_SUB, "หัว", "ข้อความ", priv)
    assert ok is True and expired is False
    assert calls['subscription'] == WEB_SUB
    assert calls['has_vapid'] is True
    assert calls['claims']['sub'].startswith('mailto:')
    payload = json.loads(calls['data'])
    assert payload['title'] == "หัว" and payload['body'] == "ข้อความ"


def test_send_web_push_expired_410(monkeypatch):
    db = make_session()()
    _, priv = push_service.get_vapid_keys(db)

    class FakeResp:
        status_code = 410

    FakeWebPushException = type('FakeWebPushException', (Exception,), {})
    monkeypatch.setattr(push_service, 'WebPushException', FakeWebPushException)

    class FakeErr(FakeWebPushException):
        response = FakeResp()

    monkeypatch.setattr(push_service, 'webpush', lambda **kw: (_ for _ in ()).throw(FakeErr()))
    ok, expired = push_service.send_web_push(WEB_SUB, "t", "b", priv)
    assert ok is False and expired is True


def test_send_web_push_missing_key():
    ok, expired = push_service.send_web_push(WEB_SUB, "t", "b", None)
    assert ok is False and expired is False


# ---------- push_notification ----------

def test_push_notification_sends_to_web_devices(monkeypatch):
    db = make_session()()
    db.add(Device(id=str(uuid.uuid4()), device_token=json.dumps(WEB_SUB), platform='web'))
    # native token ต้องถูกข้ามไป (ยังไม่มี native build)
    db.add(Device(id=str(uuid.uuid4()), device_token='legacy-fcm-token', platform='android'))
    db.commit()
    note = Notification(id=str(uuid.uuid4()), task_id='t1', message='งาน x ต้องเริ่มก่อน',
                        urgency='critical', read=False)
    db.add(note)
    db.commit()

    sent_ok = []

    def fake_webpush(**kwargs):
        sent_ok.append(kwargs['subscription_info'])

    monkeypatch.setattr(push_service, 'webpush', fake_webpush)
    sent = push_service.push_notification(db, note)
    assert sent == 1  # ส่งแค่ device web ไม่รวม android


def test_push_notification_deletes_expired_subscription(monkeypatch):
    db = make_session()()
    d = Device(id=str(uuid.uuid4()), device_token=json.dumps(WEB_SUB), platform='web')
    db.add(d)
    db.commit()
    note = Notification(id=str(uuid.uuid4()), task_id='t1', message='msg', urgency='high')
    db.add(note)
    db.commit()

    class FakeResp:
        status_code = 404

    FakeWebPushException = type('FakeWebPushException', (Exception,), {})
    monkeypatch.setattr(push_service, 'WebPushException', FakeWebPushException)

    class FakeErr(FakeWebPushException):
        response = FakeResp()

    monkeypatch.setattr(push_service, 'webpush', lambda **kw: (_ for _ in ()).throw(FakeErr()))
    sent = push_service.push_notification(db, note)
    assert sent == 0
    assert db.query(Device).count() == 0  # subscription ตาย → ลบ device ทิ้ง


def test_push_notification_no_devices_ok(monkeypatch):
    db = make_session()()
    note = Notification(id=str(uuid.uuid4()), task_id='t1', message='msg', urgency='high')
    db.add(note)
    db.commit()
    monkeypatch.setattr(push_service, 'webpush', lambda **kw: None)
    assert push_service.push_notification(db, note) == 0


# ---------- FCM v1 (native Android/iOS) ----------

def test_push_notification_sends_fcm_to_native_devices(monkeypatch):
    db = make_session()()
    db.add(Device(id=str(uuid.uuid4()), device_token='fcm-token-a', platform='android'))
    db.add(Device(id=str(uuid.uuid4()), device_token='fcm-token-b', platform='ios'))
    db.commit()
    note = Notification(id=str(uuid.uuid4()), task_id='t1', message='msg', urgency='high')
    db.add(note)
    db.commit()

    calls = []

    def fake_fcm(token, title, body):
        calls.append((token, title, body))
        return True, False

    monkeypatch.setattr(push_service, 'send_fcm_v1', fake_fcm)
    sent = push_service.push_notification(db, note)
    assert sent == 2
    assert calls[0][0] == 'fcm-token-a'
    assert calls[1][0] == 'fcm-token-b'
    assert all(c[1] == 'Smart Task Manager' for c in calls)


def test_push_notification_deletes_unregistered_fcm(monkeypatch):
    db = make_session()()
    db.add(Device(id=str(uuid.uuid4()), device_token='fcm-token', platform='android'))
    db.commit()
    note = Notification(id=str(uuid.uuid4()), task_id='t1', message='msg', urgency='high')
    db.add(note)
    db.commit()

    monkeypatch.setattr(push_service, 'send_fcm_v1', lambda tok, t, b: (False, True))
    sent = push_service.push_notification(db, note)
    assert sent == 0
    assert db.query(Device).count() == 0  # token ตาย → ลบ device ทิ้ง


def test_send_fcm_v1_no_config_ok(monkeypatch):
    monkeypatch.setattr(push_service, '_get_firebase_app', lambda: None)
    ok, expired = push_service.send_fcm_v1('token', 't', 'b')
    assert ok is False and expired is False


def test_send_fcm_v1_success(monkeypatch):
    class FakeApp:
        pass

    monkeypatch.setattr(push_service, '_get_firebase_app', lambda: FakeApp())
    sent = []

    def fake_send(*args, **kwargs):
        sent.append(args)

    fake_fcm = type('FakeFCM', (), {
        'Message': lambda **kw: kw,
        'Notification': lambda **kw: kw,
        'send': fake_send,
        'UnregisteredError': Exception,
    })
    monkeypatch.setattr(push_service, '_fcm', fake_fcm)
    ok, expired = push_service.send_fcm_v1('token', 't', 'b')
    assert ok is True and expired is False
    assert len(sent) == 1


def test_send_fcm_v1_unregistered(monkeypatch):
    class FakeApp:
        pass

    monkeypatch.setattr(push_service, '_get_firebase_app', lambda: FakeApp())

    class FakeUnregistered(Exception):
        pass

    fake_fcm = type('FakeFCM', (), {
        'Message': lambda **kw: kw,
        'Notification': lambda **kw: kw,
        'send': lambda *a, **kw: (_ for _ in ()).throw(FakeUnregistered()),
        'UnregisteredError': FakeUnregistered,
    })
    monkeypatch.setattr(push_service, '_fcm', fake_fcm)
    ok, expired = push_service.send_fcm_v1('token', 't', 'b')
    assert ok is False and expired is True


# ---------- /devices endpoint ----------

def test_register_web_device(test_client):
    resp = test_client.post('/devices', json={
        'device_token': json.dumps(WEB_SUB), 'platform': 'web',
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data['platform'] == 'web'
    assert data['device_token'] == json.dumps(WEB_SUB)


def test_register_device_dedup(test_client):
    body = {'device_token': json.dumps(WEB_SUB), 'platform': 'web'}
    first = test_client.post('/devices', json=body).json()
    second = test_client.post('/devices', json=body).json()
    assert first['id'] == second['id']  # ครั้งที่ 2 ได้ device ตัวเดิม ไม่สร้างแถวใหม่
    assert second['duplicate'] is True
