"""Standalone notification worker.

Run this in a separate terminal or as a service:

python workers\\notification_worker.py

This polls TODO tasks, computes escalation urgency, inserts
Notification records for high/critical/overdue items, and sends
a Web Push (VAPID) to registered devices.
"""
import time
import uuid
import datetime
import sys
import os

# Import project modules (assumes current working dir is project root)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database
from models import Notification, AppSetting
from escalation import (
    compute_urgency,
    todo_tasks_with_deadline,
    was_notified_recently,
    NOTIFY_URGENCIES,
)

SessionLocal = database.SessionLocal


def get_tz_offset(db):
    setting = db.query(AppSetting).filter(AppSetting.key == "tz_offset_hours").first()
    return float(setting.value) if setting else 7.0


def get_local_now(db):
    offset = get_tz_offset(db)
    return datetime.datetime.utcnow() + datetime.timedelta(hours=offset)


def run(poll_seconds: int = 60, buffer_minutes: int = 60):
    print('Notification worker started')
    while True:
        db = SessionLocal()
        sent_ids = []
        try:
            tasks = todo_tasks_with_deadline(db)
            now = get_local_now(db)
            for t in tasks:
                latest_start, _sl, _sd, urgency = compute_urgency(t, buffer_minutes, now)

                if urgency not in NOTIFY_URGENCIES:
                    continue
                if was_notified_recently(db, t, urgency, now):
                    continue
                note = Notification(
                    id=str(uuid.uuid4()),
                    task_id=t.id,
                    message=f"งาน '{t.title}' ต้องเริ่มภายใน {latest_start}",
                    urgency=urgency,
                    read=False,
                )
                db.add(note)
                db.flush()
                sent_ids.append(note.id)
            db.commit()
        except Exception as e:
            print('Worker error:', e)
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass
        # ส่ง Web Push หลัง commit (กัน push หลุดเมื่อ transaction ล้ม) — ไม่ crash ถ้าไม่มี device
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
                print('Push send error:', e)
        time.sleep(poll_seconds)


if __name__ == '__main__':
    run()
