import 'package:flutter/foundation.dart';

/// สัญญาณกลางบอกว่า "การแสดงวันหยุดในปฏิทินเปลี่ยนแล้ว"
///
/// SettingsPage เรียก `changed()` หลังผู้ใช้เปิด/ปิดวันหยุด —
/// CalendarPage ฟังตัวนี้แล้วโหลด `/calendar` ใหม่ (backend กรองวันหยุดตาม setting)
class HolidayNotifier extends ChangeNotifier {
  HolidayNotifier._();

  static final HolidayNotifier instance = HolidayNotifier._();

  void changed() => notifyListeners();
}
