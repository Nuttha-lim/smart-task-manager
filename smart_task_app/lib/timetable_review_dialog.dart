import 'package:flutter/material.dart';

const List<String> _dayNames = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์'];

/// Dialog ตรวจตารางเรียนที่ AI อ่านได้ ก่อนยืนยันบันทึก
///
/// รับ entries เป็น `List<Map<String, dynamic>>` แต่ละตัวมี key:
///   day_of_week (1-7), start_time ("HH:MM"), end_time ("HH:MM"), subject, location (optional)
/// คืนรายการที่ผู้ใช้ยืนยันแล้วผ่าน Navigator.pop (กรองแถวที่ข้อมูลไม่ครบ/เวลาผิดทิ้ง)
class TimetableReviewDialog extends StatefulWidget {
  final String? title;
  final String? subtitle;
  final List<Map<String, dynamic>> entries;

  const TimetableReviewDialog({
    super.key,
    this.title,
    this.subtitle,
    required this.entries,
  });

  @override
  State<TimetableReviewDialog> createState() => _TimetableReviewDialogState();
}

class _TimetableReviewDialogState extends State<TimetableReviewDialog> {
  late final List<int> _days;
  late final List<TextEditingController> _startCtrls;
  late final List<TextEditingController> _endCtrls;
  late final List<TextEditingController> _subjectCtrls;
  late final List<TextEditingController> _locationCtrls;

  @override
  void initState() {
    super.initState();
    _days = widget.entries.map((e) {
      final d = e['day_of_week'];
      return (d is int && d >= 1 && d <= 7) ? d : 1;
    }).toList();
    _startCtrls = widget.entries
        .map((e) => TextEditingController(text: (e['start_time'] ?? '').toString()))
        .toList();
    _endCtrls = widget.entries
        .map((e) => TextEditingController(text: (e['end_time'] ?? '').toString()))
        .toList();
    _subjectCtrls = widget.entries
        .map((e) => TextEditingController(text: (e['subject'] ?? '').toString()))
        .toList();
    _locationCtrls = widget.entries
        .map((e) => TextEditingController(text: (e['location'] ?? '').toString()))
        .toList();
  }

  @override
  void dispose() {
    for (final c in [..._startCtrls, ..._endCtrls, ..._subjectCtrls, ..._locationCtrls]) {
      c.dispose();
    }
    super.dispose();
  }

  void _removeAt(int index) {
    setState(() {
      _days.removeAt(index);
      _startCtrls.removeAt(index).dispose();
      _endCtrls.removeAt(index).dispose();
      _subjectCtrls.removeAt(index).dispose();
      _locationCtrls.removeAt(index).dispose();
    });
  }

  void _addEmpty() {
    setState(() {
      _days.add(1);
      _startCtrls.add(TextEditingController());
      _endCtrls.add(TextEditingController());
      _subjectCtrls.add(TextEditingController());
      _locationCtrls.add(TextEditingController());
    });
  }

  bool _isValidTime(String s) => RegExp(r'^\d{2}:\d{2}$').hasMatch(s);

  List<Map<String, dynamic>> _confirmed() {
    final result = <Map<String, dynamic>>[];
    for (var i = 0; i < _subjectCtrls.length; i++) {
      final subject = _subjectCtrls[i].text.trim();
      final start = _startCtrls[i].text.trim();
      final end = _endCtrls[i].text.trim();
      final loc = _locationCtrls[i].text.trim();
      if (subject.isEmpty) continue;
      if (!_isValidTime(start) || !_isValidTime(end)) continue;
      if (start.compareTo(end) >= 0) continue;
      result.add({
        'day_of_week': _days[i],
        'start_time': start,
        'end_time': end,
        'subject': subject,
        'location': loc.isEmpty ? null : loc,
      });
    }
    return result;
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title ?? 'ตรวจตารางเรียนก่อนบันทึก'),
      content: SizedBox(
        width: 620,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                widget.subtitle ?? 'แก้ไข/เพิ่ม/ลบคาบได้ตามที่ต้องการ — บันทึกจะแทนที่ตารางเดิม',
                style: TextStyle(fontSize: 13, color: Colors.grey.shade700),
              ),
              const SizedBox(height: 12),
              for (var i = 0; i < _subjectCtrls.length; i++) ...[
                _row(i),
                const SizedBox(height: 8),
              ],
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: _addEmpty,
                  icon: const Icon(Icons.add),
                  label: const Text('เพิ่มคาบ'),
                ),
              ),
              const SizedBox(height: 4),
              Text('เวลาใช้รูปแบบ HH:MM (เช่น 09:00, 13:30) — เวลาจบต้องหลังเวลาเริ่ม',
                  style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('ยกเลิก'),
        ),
        ElevatedButton(
          onPressed: () => Navigator.of(context).pop(_confirmed()),
          child: const Text('ยืนยันและบันทึก'),
        ),
      ],
    );
  }

  Widget _row(int index) {
    final startOk = _startCtrls[index].text.isEmpty || _isValidTime(_startCtrls[index].text);
    final endOk = _endCtrls[index].text.isEmpty || _isValidTime(_endCtrls[index].text);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            DropdownButton<int>(
              value: _days[index],
              items: [
                for (var i = 0; i < _dayNames.length; i++)
                  DropdownMenuItem(value: i + 1, child: Text(_dayNames[i])),
              ],
              onChanged: (v) => setState(() => _days[index] = v ?? 1),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: _subjectCtrls[index],
                decoration: const InputDecoration(
                  isDense: true,
                  border: OutlineInputBorder(),
                  labelText: 'วิชา',
                ),
              ),
            ),
            IconButton(
              tooltip: 'ลบคาบนี้',
              icon: const Icon(Icons.remove_circle_outline),
              onPressed: () => _removeAt(index),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _startCtrls[index],
                decoration: InputDecoration(
                  isDense: true,
                  border: const OutlineInputBorder(),
                  labelText: 'เริ่ม (HH:MM)',
                  errorText: startOk ? null : 'รูปแบบเวลาไม่ถูก',
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: _endCtrls[index],
                decoration: InputDecoration(
                  isDense: true,
                  border: const OutlineInputBorder(),
                  labelText: 'จบ (HH:MM)',
                  errorText: endOk ? null : 'รูปแบบเวลาไม่ถูก',
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: _locationCtrls[index],
                decoration: const InputDecoration(
                  isDense: true,
                  border: OutlineInputBorder(),
                  labelText: 'ห้อง/สถานที่',
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
