import 'package:flutter/foundation.dart';

/// คลาสกลางบอก "รายการงานเปลี่ยนแล้ว" — หน้า Dashboard/History ฟังตัวนี้
///
/// เวลาสร้างงานจากหน้า AI (File Upload, Travel Planning) ให้เรียก
/// `TasksNotifier.instance.changed()` แล้ว Dashboard จะโหลดงานใหม่ทันที
class TasksNotifier extends ChangeNotifier {
  TasksNotifier._();

  static final TasksNotifier instance = TasksNotifier._();

  void changed() {
    notifyListeners();
  }
}
