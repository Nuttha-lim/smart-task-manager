import 'package:flutter/material.dart';

/// Dialog ตรวจงานที่ AI สร้างก่อนยืนยัน — แก้ชื่อ/กำหนดส่ง/เวลา/เวลาที่ใช้ได้
///
/// รับ tasks เป็น `List<Map<String, dynamic>>` แต่ละตัวมี key:
///   title, description (optional), deadline ("YYYY-MM-DD"), deadline_time ("HH:MM"), estimated_time (int)
/// คืนรายการที่ผู้ใช้ยืนยันแล้วผ่าน Navigator.pop (กรองข้อว่างทิ้ง, ค่าที่เว้น = null)
class TaskReviewDialog extends StatefulWidget {
  final String title;
  final String subtitle;
  final String summary;
  final List<Map<String, dynamic>> tasks;

  const TaskReviewDialog({
    super.key,
    required this.title,
    required this.subtitle,
    required this.summary,
    required this.tasks,
  });

  @override
  State<TaskReviewDialog> createState() => _TaskReviewDialogState();
}

class _TaskReviewDialogState extends State<TaskReviewDialog> {
  late final List<TextEditingController> _titleControllers;
  late final List<TextEditingController> _deadlineControllers;
  late final List<TextEditingController> _timeControllers;
  late final List<TextEditingController> _estControllers;

  @override
  void initState() {
    super.initState();
    _titleControllers = widget.tasks
        .map((t) => TextEditingController(text: (t['title'] ?? '').toString()))
        .toList();
    _deadlineControllers = widget.tasks
        .map((t) => TextEditingController(text: (t['deadline'] ?? '').toString()))
        .toList();
    _timeControllers = widget.tasks
        .map((t) => TextEditingController(text: (t['deadline_time'] ?? '').toString()))
        .toList();
    _estControllers = widget.tasks
        .map((t) => TextEditingController(
            text: t['estimated_time'] == null ? '' : t['estimated_time'].toString()))
        .toList();
  }

  @override
  void dispose() {
    for (final c in [..._titleControllers, ..._deadlineControllers,
        ..._timeControllers, ..._estControllers]) {
      c.dispose();
    }
    super.dispose();
  }

  void _removeAt(int index) {
    setState(() {
      _titleControllers.removeAt(index).dispose();
      _deadlineControllers.removeAt(index).dispose();
      _timeControllers.removeAt(index).dispose();
      _estControllers.removeAt(index).dispose();
    });
  }

  void _addEmpty() {
    setState(() {
      _titleControllers.add(TextEditingController());
      _deadlineControllers.add(TextEditingController());
      _timeControllers.add(TextEditingController());
      _estControllers.add(TextEditingController());
    });
  }

  List<Map<String, dynamic>> _confirmed() {
    final result = <Map<String, dynamic>>[];
    for (var i = 0; i < _titleControllers.length; i++) {
      final title = _titleControllers[i].text.trim();
      if (title.isEmpty) continue;
      final deadline = _deadlineControllers[i].text.trim();
      final time = _timeControllers[i].text.trim();
      final est = int.tryParse(_estControllers[i].text.trim());
      result.add({
        'title': title,
        'deadline': _isValidDate(deadline) ? deadline : null,
        'deadline_time': _isValidTime(time) ? time : null,
        'estimated_time': (est != null && est > 0) ? est : null,
      });
    }
    return result;
  }

  bool _isValidDate(String s) => s.isEmpty || (RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(s));
  bool _isValidTime(String s) => s.isEmpty || (RegExp(r'^\d{2}:\d{2}$').hasMatch(s));

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: SizedBox(
        width: 560,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(widget.subtitle,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
              const SizedBox(height: 4),
              if (widget.summary.isNotEmpty)
                Text(widget.summary,
                    style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
              const SizedBox(height: 12),
              for (var i = 0; i < _titleControllers.length; i++) ...[
                _taskRow(i),
                const SizedBox(height: 8),
              ],
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: _addEmpty,
                  icon: const Icon(Icons.add),
                  label: const Text('เพิ่มงาน'),
                ),
              ),
              const SizedBox(height: 4),
              Text('กำหนดส่ง ใช้รูปแบบ YYYY-MM-DD, เวลา HH:MM (24 ชม.) — เว้นไว้ได้ถ้ายังไม่รู้',
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

  Widget _taskRow(int index) {
    final deadOk = _isValidDate(_deadlineControllers[index].text);
    final timeOk = _isValidTime(_timeControllers[index].text);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _titleControllers[index],
                decoration: InputDecoration(
                  isDense: true,
                  border: const OutlineInputBorder(),
                  labelText: 'งาน ${index + 1}',
                ),
              ),
            ),
            IconButton(
              tooltip: 'ลบงานนี้',
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
                controller: _deadlineControllers[index],
                decoration: InputDecoration(
                  isDense: true,
                  border: const OutlineInputBorder(),
                  labelText: 'กำหนดส่ง (YYYY-MM-DD)',
                  errorText: deadOk ? null : 'รูปแบบวันที่ไม่ถูก',
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: _timeControllers[index],
                decoration: InputDecoration(
                  isDense: true,
                  border: const OutlineInputBorder(),
                  labelText: 'เวลา (HH:MM)',
                  errorText: timeOk ? null : 'รูปแบบเวลาไม่ถูก',
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: _estControllers[index],
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  isDense: true,
                  border: OutlineInputBorder(),
                  labelText: 'ใช้เวลากี่นาที',
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
