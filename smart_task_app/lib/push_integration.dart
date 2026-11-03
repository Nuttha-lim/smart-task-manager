// Native (Android/iOS) push integration using Firebase Cloud Messaging (FCM).
//
// ไฟล์นี้ถูกใช้เฉพาะตอน build native — ผ่าน conditional import ใน push_service.dart
// (`push_service_stub.dart` ใช้บน web กับ Web Push VAPID แทน ไม่แตะ Firebase)
//
// โฟลว์: main.dart เรียก PushService.init() → Firebase.initializeApp() →
// ลงทะเบียน local notifications (แสดงตอนแอปเปิดอยู่) → ถ้าผู้ใช้เคยเปิดไว้
// ให้ขอ token + ส่ง POST /devices (platform=android/ios)
//
// ทุกอย่าง guarded (หลัก "ช่วยไม่กดดัน" §9): ถ้ายังไม่ได้ตั้งค่า Firebase project
// (google-services.json / GoogleService-Info.plist) แอปก็เปิดได้ปกติ
// แค่สวิตช์ push เปิดไม่ได้ + แจ้งผลใน snackbar — ไม่ crash
import 'dart:convert';
import 'dart:io' show Platform;

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'api_config.dart';

class PushService {
  PushService._();
  static final PushService instance = PushService._();

  static const String _storageKey = 'push_enabled';

  static bool _enabled = false; // cache ค่า (mirror localStorage ของ web)
  static bool? _firebaseReady; // null = ยังไม่ลอง, true/false = init firebase สำเร็จ/ล้ม

  static final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  static Future<void> init() async {
    _enabled = await _readStoredEnabled();
    if (!await _ensureFirebase()) return;
    await _setupLocalNotifications();
    // แสดง notification เองตอนแอปเปิดอยู่ (FCM แสดงให้เองเฉพาะตอน background)
    FirebaseMessaging.onMessage.listen(_onForegroundMessage);
    // ถ้าผู้ใช้เคยเปิดไว้ → re-register (token อาจเปลี่ยน/หมดอายุ)
    if (_enabled) {
      await _refreshRegistration();
    }
  }

  static bool isSupported() {
    // Android/iOS รองรับ push เสมอ — Firebase ยังไม่พร้อมก็แค่เปิดไม่ได้ (ดู requestSubscribe)
    return true;
  }

  static bool isEnabled() => isSupported() && _enabled;

  static Future<bool> requestSubscribe() async {
    if (!isSupported()) return false;
    if (!await _ensureFirebase()) return false;
    try {
      final fm = FirebaseMessaging.instance;
      final settings = await fm.requestPermission();
      final allowed = settings.authorizationStatus == AuthorizationStatus.authorized ||
          settings.authorizationStatus == AuthorizationStatus.provisional;
      if (!allowed) return false;
      final token = await fm.getToken();
      if (token == null || token.isEmpty) return false;
      await registerTokenWithServer(token);
      _enabled = true;
      await _storeEnabled(true);
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<void> unsubscribe() async {
    try {
      await FirebaseMessaging.instance.deleteToken();
    } catch (_) {
      // token ยังไม่มี/ลบไม่ได้ — เงียบ ยังถือว่าปิด
    }
    _enabled = false;
    await _storeEnabled(false);
  }

  static Future<void> registerTokenWithServer(String token) async {
    if (token.isEmpty) return;
    try {
      final platform = Platform.isIOS ? 'ios' : 'android';
      await http.post(
        Uri.parse('$apiBase/devices'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'device_token': token, 'platform': platform}),
      );
    } catch (_) {
      // offline / backend ลง — ข้าม ครั้งหน้า init จะลองใหม่
    }
  }

  // ---------- internals ----------

  static Future<bool> _ensureFirebase() async {
    if (_firebaseReady != null) return _firebaseReady!;
    try {
      // ไม่ส่ง options — ให้อ่านจาก google-services.json (Android) /
      // GoogleService-Info.plist (iOS) ถ้ายังไม่มี → FirebaseException → จับเงียบ
      await Firebase.initializeApp();
      _firebaseReady = true;
    } catch (_) {
      _firebaseReady = false;
    }
    return _firebaseReady!;
  }

  static Future<void> _setupLocalNotifications() async {
    try {
      const android = AndroidInitializationSettings('@mipmap/ic_launcher');
      const ios = DarwinInitializationSettings(
        requestAlertPermission: false,
        requestBadgePermission: false,
        requestSoundPermission: false,
      );
      await _localNotifications.initialize(
        settings: const InitializationSettings(android: android, iOS: ios),
      );
      // Android 13+ ต้องขอ permission แสดง notification แยกต่างหาก
      await _localNotifications
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
    } catch (_) {
      // แสดงในแอปไม่ได้ก็ไม่เป็นไร — FCM ยังส่งตอน background ได้
    }
  }

  static void _onForegroundMessage(RemoteMessage message) {
    final title = message.notification?.title ?? 'Smart Task Manager';
    final body = message.notification?.body ?? message.messageId ?? '';
    try {
      _localNotifications.show(
        id: 0,
        title: title,
        body: body,
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            'stm_default',
            'การแจ้งเตือน',
            channelDescription: 'การแจ้งเตือนจาก Smart Task Manager',
            importance: Importance.high,
            priority: Priority.high,
          ),
          iOS: DarwinNotificationDetails(),
        ),
      );
    } catch (_) {}
  }

  static Future<void> _refreshRegistration() async {
    try {
      final token = await FirebaseMessaging.instance.getToken();
      if (token != null && token.isNotEmpty) {
        await registerTokenWithServer(token);
      }
    } catch (_) {}
  }

  static Future<bool> _readStoredEnabled() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getBool(_storageKey) ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<void> _storeEnabled(bool value) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_storageKey, value);
    } catch (_) {}
  }
}
