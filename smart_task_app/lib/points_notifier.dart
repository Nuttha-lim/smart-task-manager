import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'api_config.dart';

/// คลาสกลางสำหรับแต้ม — ทุก PointsBadge ฟังตัวนี้
///
/// เวลาแต้มเปลี่ยน (ทำงานเสร็จ / แลกรางวัล / ปลดล็อก achievement)
/// ให้เรียก `PointsNotifier.instance.refresh()` แล้ว badge ทุกตัวที่เห็นอยู่
/// จะอัปเดตทันทีโดยไม่ต้องสลับหน้า
class PointsNotifier extends ChangeNotifier {
  PointsNotifier._();

  static final PointsNotifier instance = PointsNotifier._();

  int points = 0;

  Future<void> refresh() async {
    try {
      final response = await http.get(Uri.parse('$apiBase/points'));
      final data = jsonDecode(response.body);
      points = data['points'] ?? 0;
      notifyListeners();
    } catch (e) {
      // เงียบไว้ก่อน — ถ้า backend ยังไม่พร้อม badge ก็ค้างค่าเดิม
    }
  }
}
