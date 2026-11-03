// Web Push (VAPID) implementation for Flutter web (Chrome).
//
// โฟลว์: user เปิดสวิตช์ใน Settings → `requestSubscribe()` ขอ permission →
// register `/serviceworker.js` → ดึง VAPID public key จาก backend →
// `PushManager.subscribe` → ส่ง subscription (JSON) ไป `POST /devices`.
//
// `init()` ที่ main.dart เรียกตอนเปิดแอปจะเงียบ ๆ: ไม่ขอ permission เอง
// (สอดคล้องหลัก "ช่วยไม่กดดัน" §9) — ถ้าผู้ใช้เคยเปิดไว้แล้ว (localStorage flag)
// ก็แค่ ensure subscription ยังลงทะเบียนกับเซิร์ฟเวอร์อยู่
import 'dart:convert';
import 'dart:js_interop';

import 'package:http/http.dart' as http;
import 'package:web/web.dart' as web;
import 'api_config.dart';

class PushService {
  PushService._();
  static final PushService instance = PushService._();

  static const String _baseUrl = apiBase;
  static const String _storageKey = 'push_enabled';

  static Future<void> init() async {
    if (!isSupported() || !_wasEnabled()) return;
    try {
      final navigator = web.window.navigator;
      final reg = await navigator.serviceWorker.ready.toDart;
      final sub = await reg.pushManager.getSubscription().toDart;
      if (sub != null) {
        await _registerWithServer(sub);
      }
    } catch (_) {
      // เงียบ ไม่ขัดจังหวะการเปิดแอป
    }
  }

  static bool isSupported() {
    try {
      return web.window.isSecureContext;
    } catch (_) {
      return false;
    }
  }

  static bool isEnabled() => isSupported() && _wasEnabled();

  static bool _wasEnabled() =>
      web.window.localStorage.getItem(_storageKey) == '1';

  static void _setEnabled(bool value) {
    web.window.localStorage.setItem(_storageKey, value ? '1' : '0');
  }

  static Future<bool> requestSubscribe() async {
    if (!isSupported()) return false;
    try {
      final navigator = web.window.navigator;
      final permission = await web.Notification.requestPermission().toDart;
      if (permission.toDart != 'granted') return false;

      await navigator.serviceWorker.register('serviceworker.js'.toJS).toDart;
      final reg = await navigator.serviceWorker.ready.toDart;

      final publicKey = await _fetchVapidPublicKey();
      if (publicKey == null) return false;

      final sub = await _getOrCreateSubscription(reg, publicKey);
      if (sub == null) return false;

      await _registerWithServer(sub);
      _setEnabled(true);
      return true;
    } catch (_) {
      return false;
    }
  }

  static Future<void> unsubscribe() async {
    try {
      final navigator = web.window.navigator;
      final reg = await navigator.serviceWorker.ready.toDart;
      final sub = await reg.pushManager.getSubscription().toDart;
      if (sub != null) await sub.unsubscribe().toDart;
    } catch (_) {
      // เงียบ
    }
    _setEnabled(false);
  }

  static Future<String?> _fetchVapidPublicKey() async {
    final resp = await http.get(Uri.parse('$_baseUrl/push/vapid-public-key'));
    if (resp.statusCode != 200) return null;
    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    final key = data['public_key'] as String?;
    return (key == null || key.isEmpty) ? null : key;
  }

  static Future<web.PushSubscription?> _getOrCreateSubscription(
      web.ServiceWorkerRegistration reg, String publicKey) async {
    var sub = await reg.pushManager.getSubscription().toDart;
    if (sub != null) return sub;
    final keyBytes = base64Url.decode(base64Url.normalize(publicKey));
    return reg.pushManager
        .subscribe(web.PushSubscriptionOptionsInit(
          userVisibleOnly: true,
          applicationServerKey: keyBytes.toJS,
        ))
        .toDart;
  }

  static Future<void> _registerWithServer(web.PushSubscription sub) async {
    await http.post(
      Uri.parse('$_baseUrl/devices'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'device_token': _subToJson(sub),
        'platform': 'web',
      }),
    );
  }

  static String _subToJson(web.PushSubscription sub) => jsonEncode({
        'endpoint': sub.endpoint,
        'expirationTime': sub.expirationTime,
        'keys': {
          'p256dh': _keyToB64(sub.getKey('p256dh')),
          'auth': _keyToB64(sub.getKey('auth')),
        },
      });

  static String? _keyToB64(JSArrayBuffer? buf) {
    if (buf == null) return null;
    return base64UrlEncode(buf.toDart.asUint8List()).replaceAll('=', '');
  }
}
