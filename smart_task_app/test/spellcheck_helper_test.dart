import 'package:flutter_test/flutter_test.dart';
import 'package:smart_task_app/spellcheck_helper.dart';

void main() {
  group('applySpellcheckChanges', () {
    const original = 'ทำ homwork วันศุกร์';
    final changes = [
      {'original': 'homwork', 'corrected': 'homework'},
      {'original': 'ศุกร์', 'corrected': 'ศุกร์'},
    ];

    test('ใช้คำใหม่ทั้งหมด', () {
      expect(
        applySpellcheckChanges(original, changes, {0, 1}),
        'ทำ homework วันศุกร์',
      );
    });

    test('ใช้คำเดิมทั้งหมด', () {
      expect(
        applySpellcheckChanges(original, changes, {}),
        original,
      );
    });

    test('เลือกแก้บางคำ', () {
      expect(
        applySpellcheckChanges(original, changes, {0}),
        'ทำ homework วันศุกร์',
      );
    });
  });

  group('buildSpellcheckPreview', () {
    const original = 'ทำ homwork';
    const corrected = 'ทำ homework';
    final changes = [
      {'original': 'homwork', 'corrected': 'homework'},
    ];

    test('เลือกครบใช้ corrected_text จาก API', () {
      expect(
        buildSpellcheckPreview(
          originalText: original,
          correctedText: corrected,
          changes: changes,
          useCorrected: {0},
        ),
        corrected,
      );
    });

    test('ไม่เลือกเลยใช้ข้อความเดิม', () {
      expect(
        buildSpellcheckPreview(
          originalText: original,
          correctedText: corrected,
          changes: changes,
          useCorrected: {},
        ),
        original,
      );
    });
  });
}
