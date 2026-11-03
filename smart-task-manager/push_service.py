"""Push notification service — Web Push (VAPID) สำหรับ browser + FCM v1 สำหรับ native.

Web: สร้าง VAPID key เองในเครื่อง, browser subscribe ผ่าน PushManager แล้ว backend ส่ง
push ตรง ๆ ผ่าน pywebpush — ไม่ต้องมี Firebase project สำหรับ web

Native (Android/iOS): ส่งผ่าน Firebase Cloud Messaging HTTP v1 (firebase-admin) —
ต้องตั้ง env `FIREBASE_SERVICE_ACCOUNT` (path ไฟล์ service account JSON หรือ JSON string
ตรง ๆ; ใช้ `GOOGLE_APPLICATION_CREDENTIALS` เป็น fallback) — ไม่ได้ตั้ง/ไม่ติดตั้ง
firebase-admin → ส่ง native ไม่ได้ แต่ไม่ crash (หลัก §9)

Device/platform เดิมใช้ต่อได้: web = subscription JSON, android/ios = FCM token
"""
import base64
import json
import logging
import os

from cryptography.hazmat.primitives import serialization

try:
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush
    PY_WEBPUSH_AVAILABLE = True
except Exception:
    PY_WEBPUSH_AVAILABLE = False
    Vapid = None
    WebPushException = None
    webpush = None

try:
    import firebase_admin
    from firebase_admin import messaging as _fcm
    FIREBASE_ADMIN_AVAILABLE = True
except Exception:
    FIREBASE_ADMIN_AVAILABLE = False
    firebase_admin = None
    _fcm = None

from gamification import get_setting, set_setting

logger = logging.getLogger(__name__)

VAPID_SUBJECT = "mailto:smart-task-manager@localhost"

_FIREBASE_APP = None  # None = ยังไม่ลอง init, False = init ล้ม (กันลองซ้ำทุก push)


def get_vapid_keys(db):
    """คืน (public_b64, private_pem) — สร้างครั้งแรกแล้วเก็บใน AppSetting (idempotent).
    public_b64 ใช้เป็น applicationServerKey ของ browser (uncompressed point, base64url);
    private_pem ใช้เซ็น VAPID header ตอนส่ง push"""
    pub = get_setting(db, "vapid_public_key")
    priv = get_setting(db, "vapid_private_key")
    if pub and priv:
        return pub, priv
    if not PY_WEBPUSH_AVAILABLE or Vapid is None:
        return None, None
    v = Vapid()
    v.generate_keys()
    private_pem = v.private_pem().decode("utf-8")
    raw = v.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public_b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    set_setting(db, "vapid_public_key", public_b64)
    set_setting(db, "vapid_private_key", private_pem)
    db.commit()
    return public_b64, private_pem


def get_vapid_public_key(db):
    pub, _ = get_vapid_keys(db)
    return pub


def send_web_push(subscription, title, body, private_pem):
    """ส่ง push ไปยัง subscription เดียว — ไม่ crash
    คืน (ok: bool, expired: bool) — expired=True = subscription หมดอายุ (404/410)"""
    if not PY_WEBPUSH_AVAILABLE or not subscription or not private_pem:
        return False, False
    try:
        vapid = Vapid.from_pem(private_pem.encode("utf-8"))
        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body}, ensure_ascii=False),
            vapid_private_key=vapid,
            vapid_claims={"sub": VAPID_SUBJECT},
        )
        return True, False
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        logger.warning("webpush failed status=%s sub=%s", status, subscription.get("endpoint", "")[:50])
        return False, status in (404, 410)
    except Exception:
        logger.exception("webpush unexpected error")
        return False, False


def _get_firebase_app():
    """คืน Firebase app (lazy init จาก env) — ไม่ได้ตั้งค่า / init ล้ม → None (ไม่ crash)
    credential จาก FIREBASE_SERVICE_ACCOUNT (path หรือ JSON string) หรือ
    GOOGLE_APPLICATION_CREDENTIALS (path) — app เป็น singleton กัน init ซ้ำ"""
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return _FIREBASE_APP
    if not FIREBASE_ADMIN_AVAILABLE:
        return None
    cred_source = os.getenv("FIREBASE_SERVICE_ACCOUNT") or os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_source:
        return None
    try:
        if cred_source.strip().startswith("{"):
            cred = firebase_admin.credentials.Certificate(json.loads(cred_source))
        else:
            cred = firebase_admin.credentials.Certificate(cred_source)
        _FIREBASE_APP = firebase_admin.initialize_app(cred, name="smart-task-manager-fcm")
    except Exception:
        logger.exception("firebase admin init failed")
        _FIREBASE_APP = False
    return _FIREBASE_APP if _FIREBASE_APP else None


def send_fcm_v1(device_token, title, body):
    """ส่ง push ผ่าน FCM HTTP v1 (Android/iOS) — device_token = FCM registration token
    คืน (ok: bool, expired: bool) — expired=True = token ไม่มีแล้ว (UNREGISTERED)"""
    if not device_token:
        return False, False
    app = _get_firebase_app()
    if app is None:
        return False, False
    try:
        message = _fcm.Message(
            notification=_fcm.Notification(title=title, body=body),
            token=device_token,
        )
        _fcm.send(message, app=app)
        return True, False
    except _fcm.UnregisteredError:
        return False, True
    except Exception:
        logger.exception("fcm v1 send failed token=%s", str(device_token)[:30])
        return False, False


def push_notification(db, notification):
    """ส่ง push ของ notification หนึ่งให้ทุก device ที่ลงทะเบียนไว้
    (web = subscription JSON, android/ios = FCM token) — ไม่ crash,
    ลบ device ที่ token/subscription หมดอายุทิ้ง
    คืนจำนวนที่ส่งสำเร็จ"""
    from models import Device
    devices = db.query(Device).all()
    _pub, priv = get_vapid_keys(db)
    sent = 0
    for d in devices:
        token = d.device_token or ""
        if not token.strip():
            continue
        if d.platform == "web":
            if not token.strip().startswith("{") or not priv:
                continue
            try:
                subscription = json.loads(token)
            except Exception:
                continue
            ok, expired = send_web_push(subscription, "Smart Task Manager",
                                        notification.message, priv)
        elif d.platform in ("android", "ios"):
            ok, expired = send_fcm_v1(token, "Smart Task Manager",
                                      notification.message)
        else:
            continue
        if expired:
            db.delete(d)
        elif ok:
            sent += 1
    db.commit()
    return sent
