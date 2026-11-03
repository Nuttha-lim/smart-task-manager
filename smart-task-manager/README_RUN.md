# Run instructions (backend)

1. Create and activate a virtualenv (Windows PowerShell):

```powershell
cd smart-task-manager
python -m venv venv
venv\Scripts\Activate
pip install -r requirements.txt
```

2. Start PostgreSQL (via Docker Compose):

```powershell
docker compose up -d
```

2.5 Apply DB migrations (Alembic):

```powershell
python scripts\run_migrations.py
```

3. Run the FastAPI app:

```powershell
uvicorn main:app --reload
```

3.5 Run background worker (separate terminal/process):

```powershell
python workers\notification_worker.py
```

4. Queue-based worker (Celery + Redis) - optional (recommended for production)

Install Redis (example via Docker):

```powershell
docker run -d --name redis -p 6379:6379 redis:7
```

Install Celery dependencies (in your venv):

```powershell
python -m pip install -r requirements-celery.txt
```

Start the Celery worker with beat scheduler (runs periodic tasks):

```powershell
cd smart-task-manager
celery -A celery_app worker -B -l info
```

Notes:
- The Celery beat schedule runs `process_notifications` once per minute by default.
- Use `CELERY_BROKER_URL` env var to point to a different Redis instance.

Start DB + Redis + Celery together using compose (merge files):

```powershell
docker compose -f docker-compose.yml -f docker-compose.celery.yml up --build
```

This composes the existing `db` service from `docker-compose.yml` with the `redis` and `celery_worker` services defined in `docker-compose.celery.yml`.

Backend endpoints for push integration (Web Push / VAPID — ไม่ต้องใช้ Firebase):
- `GET /push/vapid-public-key` — คืน applicationServerKey ให้ browser ใช้ subscribe (สร้าง VAPID key อัตโนมัติครั้งแรก)
- `POST /devices` — register device subscription: `device_token` (web = subscription JSON), `platform` ("web").

Server will enqueue push sends via Celery when notifications are created. Push payloads
go straight to the browser over the Web Push API (pywebpush) — no FCM server key needed.


4. Run smoke tests (after backend is running):

```powershell
python scripts\smoke_test.py
```
