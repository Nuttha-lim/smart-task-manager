"""Celery tasks for smart-task-manager.

Contains a periodic task `process_notifications` which checks TODO tasks and
creates `Notification` records for high/critical/overdue urgencies, then
sends a Web Push (VAPID) to registered devices.
"""
from celery_app import app
from database import SessionLocal
from models import Notification, AppSetting
from escalation import (
    compute_urgency,
    todo_tasks_with_deadline,
    was_notified_recently,
    NOTIFY_URGENCIES,
)
import datetime
import uuid


def get_tz_offset(db):
    setting = db.query(AppSetting).filter(AppSetting.key == "tz_offset_hours").first()
    return float(setting.value) if setting else 7.0


def get_local_now(db):
    offset = get_tz_offset(db)
    return datetime.datetime.utcnow() + datetime.timedelta(hours=offset)


@app.task(name='celery_tasks.process_notifications')
def process_notifications(buffer_minutes: int = 60):
    db = SessionLocal()
    try:
        tasks = todo_tasks_with_deadline(db)
        # สำคัญ: deadline เก็บเป็น local-naive ต้องเปรียบกับเวลา local (get_local_now)
        # ไม่ใช่ utcnow() — เคยใช้ utcnow() ทำให้ offset ผิด 7 ชม. (ดู AGENTS.md §6 ข้อ 3)
        now = get_local_now(db)
        for t in tasks:
            latest_start, _sl, _sd, urgency = compute_urgency(t, buffer_minutes, now)

            if urgency not in NOTIFY_URGENCIES:
                continue
            if was_notified_recently(db, t, urgency, now):
                continue
            short_time = latest_start.strftime('%H:%M %d/%m')
            note = Notification(
                id=str(uuid.uuid4()),
                task_id=t.id,
                message=f"งาน '{t.title}' ควรเริ่มก่อน {short_time}",
                urgency=urgency,
                read=False,
            )
            db.add(note)
            db.flush()
            # enqueue push send
            try:
                send_push.delay(note.id)
            except Exception:
                # fallback: try synchronous send if Celery not running
                try:
                    send_push(note.id)
                except Exception:
                    pass
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.task(name='celery_tasks.send_push')
def send_push(notification_id: str):
    """ส่ง Web Push (VAPID) ให้ทุก device ที่ลงทะเบียน — ไม่ crash ถ้าไม่มี device/
    ไม่มีคีย์/ส่ง fail (subscription ตายจะถูกลบใน push_service)"""
    db = SessionLocal()
    try:
        from push_service import push_notification
        notif = db.query(Notification).filter(Notification.id == notification_id).first()
        if not notif:
            return
        push_notification(db, notif)
    finally:
        db.close()
