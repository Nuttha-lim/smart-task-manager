# Smart Task Manager

A Flutter and FastAPI application for organizing tasks around available time and daily energy levels. It combines task tracking, calendar planning and AI-assisted task entry, with PostgreSQL for storage.

[Web deployment](https://github.com/whyohkay/stm-web) · [Portfolio](https://github.com/Nuttha-lim/portfolio)

## My contribution

I built the application with AI assistance, working with Flutter/Dart, FastAPI, PostgreSQL and Docker. The project helped me understand how the interface connects to an API and how the backend stores and retrieves data.

## Features

- Create and review tasks from chat messages or uploaded files
- Check daily energy levels and plan tasks around available time
- Manage calendars, class timetables and recurring routines
- Track goals, completed tasks, points and rewards
- Review AI-generated travel plans and related preparation tasks
- Receive task notifications through background processing and web push

## Source structure

| Directory | Contents |
| --- | --- |
| `smart_task_app/` | Flutter interface and widget tests |
| `smart-task-manager/` | FastAPI endpoints, planning services and database models |
| `smart-task-manager/alembic/` | Database migrations |
| `smart-task-manager/tests/` | Backend tests |
| `smart-task-manager/workers/` | Notification worker |

## Run locally

The web target uses Flutter 3.44.8 and Dart 3.12.2. The backend requires Python and PostgreSQL 16; Docker Compose starts the local database.

Clone the repository:

```powershell
git clone https://github.com/Nuttha-lim/smart-task-manager.git
cd smart-task-manager
```

### Backend

From the repository root, create a virtual environment and install the backend dependencies:

```powershell
cd smart-task-manager
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
docker compose up -d
.\.venv\Scripts\python.exe scripts/run_migrations.py
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --env-file .env
```

Set `GROQ_API_KEY` in `.env` to use AI features. The API runs at `http://127.0.0.1:8000`, with its interactive reference at `/docs`.

### Flutter interface

Open a second terminal at the repository root:

```powershell
cd smart_task_app
flutter pub get
flutter run -d chrome --web-port 5173 --dart-define=API_BASE=http://127.0.0.1:8000
```

The example environment file allows the local frontend on port 5173. Adjust `API_BASE` and `ALLOWED_ORIGINS` when using other addresses.

## Tests and build

Backend tests use in-memory SQLite databases and mocked AI responses. From the backend directory, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:DATABASE_URL = "sqlite:///:memory:"
$env:BACKGROUND_WORKER = "0"
.\.venv\Scripts\python.exe -m pytest tests -q
```

From `smart_task_app`, run the Flutter checks:

```powershell
flutter test
flutter build web --release
```

See [test results](docs/TEST_RESULTS.md) for the checked environment and scope.
