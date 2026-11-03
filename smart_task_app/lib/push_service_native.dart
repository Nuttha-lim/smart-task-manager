import 'push_integration.dart' as impl;

/// Native (Android/iOS) push — ตัวจริงอยู่ใน push_integration.dart (FCM)
/// ไฟล์นี้แค่ delegate ให้ interface เดียวกับ web stub (push_service_stub.dart)
class PushService {
  PushService._();
  static final PushService instance = PushService._();

  static Future<void> init() => impl.PushService.init();
  static Future<void> registerTokenWithServer(String token) =>
      impl.PushService.registerTokenWithServer(token);

  static bool isSupported() => impl.PushService.isSupported();
  static bool isEnabled() => impl.PushService.isEnabled();
  static Future<bool> requestSubscribe() => impl.PushService.requestSubscribe();
  static Future<void> unsubscribe() => impl.PushService.unsubscribe();
}
