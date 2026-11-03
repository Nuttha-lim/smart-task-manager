/// Base URL ของ backend — set ตอน build/run ด้วย:
///   flutter run -d chrome --dart-define=API_BASE=http://192.168.1.5:8000
///   flutter build web --dart-define=API_BASE=https://your-api.onrender.com
/// ไม่ set = dev ใช้ localhost
const String apiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://127.0.0.1:8000',
);
