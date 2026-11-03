"""Background notification poller — รันในโปรเซสเดียวกับ FastAPI (daemon thread).

ใช้แทน Celery/Redis บน hosting ฟรี (Render free tier ไม่มี Redis พร้อมใช้):
ถ้าตั้ง env `BACKGROUND_WORKER=1` ตอน start จะมี thread ข้างหลังคอย:
1. ไล่หางาน TODO ที่มี deadline และเข้าเกณฑ์ด่วน (high/critical/overdue)
2. สร้าง Notification record (กันซ้ำด้วย was_notified_recently)
3. ส่ง Web Push ไปทุก device ที่ลงทะเบียน (push_service.push_notification)

Local dev ที่รัน workers/notification_worker.py แยกอยู่แล้ว → ตั้ง BACKGROUND_WORKER=0
(หรือไม่ตั้ง) เพื่อไม่ให้ notify ซ้ำสอง
"""
import threading
import time
import uuid
import datetime
import logging

from database import SessionLocal
from models import AppSetting, Notification
from escalation import (
    compute_urgency,
    todo_tasks_with_deadline,
    was_notified_recently,
    NOTIFY_URGENCIES,
)

logger = logging.getLogger(__name__)

POLL_SECONDS = 60
BUFFER_MINUTES = 60


def get_tz_offset(db):
    setting = db.query(AppSetting).filter(AppSetting.key == "tz_offset_hours").first()
    return float(setting.value) if setting else 7.0


def get_local_now(db):
    offset = get_tz_offset(db)
    return datetime.datetime.utcnow() + datetime.timedelta(hours=offset)


def run_once():
    """หนึ่งรอบของ poller — แยกฟังก์ชันไว้ให้เทสต์ได้ ไม่ crash ถ้า DB ล้ม"""
    db = SessionLocal()
    sent_ids = []
    try:
        now = get_local_now(db)
        for t in todo_tasks_with_deadline(db):
            latest_start, _sl, _sd, urgency = compute_urgency(t, BUFFER_MINUTES, now)
            if urgency not in NOTIFY_URGENCIES:
                continue
            if was_notified_recently(db, t, urgency, now):
                continue
            note = Notification(
                id=str(uuid.uuid4()),
                task_id=t.id,
                message=f"งาน '{t.title}' ควรเริ่มก่อน {latest_start.strftime('%H:%M %d/%m')}",
                urgency=urgency,
                read=False,
            )
            db.add(note)
            db.flush()
            sent_ids.append(note.id)
        db.commit()
    except Exception as e:
        logger.exception("background worker error: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass

    # ส่ง push หลัง commit — ไม่ crash ถ้าไม่มี device / push ล้ม (ลบ sub ตายใน push_service)
    for note_id in sent_ids:
        try:
            from push_service import push_notification
            db2 = SessionLocal()
            try:
                notif = db2.query(Notification).filter(Notification.id == note_id).first()
                if notif:
                    push_notification(db2, notif)
            finally:
                db2.close()
        except Exception as e:
            logger.warning("push send error: %s", e)


def _loop():
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("background worker loop error")
        time.sleep(POLL_SECONDS)


def start_if_enabled():
    """เรียกตอน start ของ FastAPI — เริ่ม thread ก็ต่อเมื่อ env BACKGROUND_WORKER=1"""
    import os
    if os.getenv("BACKGROUND_WORKER", "0") == "1":
        t = threading.Thread(target=_loop, name="notification-poller", daemon=True)
        t.start()
        logger.info("background notification poller started (every %ss)", POLL_SECONDS)
