import 'package:flutter/foundation.dart';

/// สัญญาณกลางบอกว่า "ระดับพลังงานวันนี้เปลี่ยนแล้ว"
///
/// EnergyBadge เรียก `changed()` หลังผู้ใช้เลือกพลังงานใหม่ —
/// Dashboard ฟังตัวนี้แล้วโหลด `/dashboard/today` ใหม่ (แพลนวันนี้ขึ้นอยู่กับพลังงาน)
class EnergyNotifier extends ChangeNotifier {
  EnergyNotifier._();

  static final EnergyNotifier instance = EnergyNotifier._();

  void changed() => notifyListeners();
}
