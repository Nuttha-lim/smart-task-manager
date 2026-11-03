# Smart Task Manager interface

The Flutter interface includes chat-based task entry, a dashboard, calendar views, energy check-ins and planning tools. It connects to the FastAPI backend through the URL configured in `lib/api_config.dart`.

See the [project README](../README.md) for backend setup and local run instructions.

## Run the web interface

```powershell
flutter pub get
flutter run -d chrome --web-port 5173 --dart-define=API_BASE=http://127.0.0.1:8000
```

## Test and build

```powershell
flutter test
flutter build web --release
```
