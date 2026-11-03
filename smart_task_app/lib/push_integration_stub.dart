// Stub สำหรับ platform ที่ไม่ใช่ web และไม่มี Firebase (เช่นเทสต์)
// interface ตรงกับ push_integration.dart (native) — ทุกอย่าง no-op ไม่ crash
class PushService {
  PushService._();
  static final PushService instance = PushService._();

  static Future<void> init() async {}
  static Future<void> registerTokenWithServer(String token) async {}

  static bool isSupported() => false;
  static bool isEnabled() => false;
  static Future<bool> requestSubscribe() async => false;
  static Future<void> unsubscribe() async {}
}
