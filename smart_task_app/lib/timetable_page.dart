import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app_bar_actions.dart';
import 'api_config.dart';

/// Class Timetable Import — ตารางเรียนรายสัปดาห์
/// เพิ่มเอง หรือวางข้อความมาให้ parse แล้วตรวจก่อนบันทึก (ตามหลัก confirmation ก่อนเซฟ)
class TimetablePage extends StatefulWidget {
  const TimetablePage({super.key});

  @override
  State<TimetablePage> createState() => _TimetablePageState();
}

class _TimetablePageState extends State<TimetablePage> {
  static const List<String> _dayNames = [
    '', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์',
  ];
  static const List<String> _dayShort = [
    '', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัส', 'ศุกร์', 'เสาร์', 'อาทิตย์',
  ];

  bool _isLoading = true;
  List<dynamic> _schedules = [];
  List<dynamic> _cancellations = [];

  @override
  void initState() {
    super.initState();
    _fetch();
  }

  Future<void> _fetch() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/timetable'));
      if (resp.statusCode == 200) {
        setState(() => _schedules = jsonDecode(resp.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    try {
      final resp = await http.get(
          Uri.parse('$apiBase/timetable/cancellations'));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        setState(() => _cancellations = (data['cancellations'] as List<dynamic>? ?? []));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    if (mounted) setState(() => _isLoading = false);
  }

  List<dynamic> _onDay(int day) =>
      _schedules.where((s) => s['day_of_week'] == day).toList();

  // ---------- เพิ่มเอง ----------

  Future<void> _showAddDialog() async {
    final startController = TextEditingController(text: '09:00');
    final endController = TextEditingController(text: '10:30');
    final subjectController = TextEditingController();
    final locationController = TextEditingController();
    int day = 1;

    await showDialog(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: const Text('เพิ่มคาบเรียน'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<int>(
                initialValue: day,
                decoration: const InputDecoration(
                    labelText: 'วัน', border: OutlineInputBorder()),
                items: List.generate(7, (i) => i + 1)
                    .map((d) => DropdownMenuItem(
                        value: d, child: Text(_dayNames[d])))
                    .toList(),
                onChanged: (v) => setDialogState(() => day = v ?? 1),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: startController,
                      decoration: const InputDecoration(
                          labelText: 'เริ่ม (HH:MM)',
                          border: OutlineInputBorder(),
                          isDense: true),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      controller: endController,
                      decoration: const InputDecoration(
                          labelText: 'จบ (HH:MM)',
                          border: OutlineInputBorder(),
                          isDense: true),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              TextField(
                controller: subjectController,
                decoration: const InputDecoration(
                    labelText: 'วิชา', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: locationController,
                decoration: const InputDecoration(
                    labelText: 'สถานที่ (ไม่บังคับ)',
                    border: OutlineInputBorder()),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('ยกเลิก'),
            ),
            ElevatedButton(
              onPressed: () async {
                final subject = subjectController.text.trim();
                final start = startController.text.trim();
                final end = endController.text.trim();
                if (subject.isEmpty || start.isEmpty || end.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('กรอกวิชาและเวลาให้ครบก่อน')));
                  return;
                }
                await http.post(Uri.parse('$apiBase/timetable'),
                    headers: {'Content-Type': 'application/json'},
                    body: jsonEncode([
                      {
                        'day_of_week': day,
                        'start_time': start,
                        'end_time': end,
                        'subject': subject,
                        'location': locationController.text.trim().isEmpty
                            ? null
                            : locationController.text.trim(),
                      }
                    ]));
                if (dialogContext.mounted) Navigator.pop(dialogContext);
                _fetch();
              },
              child: const Text('บันทึก'),
            ),
          ],
        ),
      ),
    );
  }

  // ---------- import (วางข้อความ) ----------

  Future<void> _showImportDialog() async {
    final textController = TextEditingController();
    List<dynamic> preview = [];
    List<dynamic> skipped = [];

    await showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: const Text('วางตารางเรียน'),
          content: SizedBox(
            width: double.maxFinite,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                    'วาง/พิมพ์ทีละบรรทัด เช่น\n'
                    '"จันทร์ 09:00-10:30 คณิตศาสตร์ ห้อง 301"\n'
                    'แถวที่อ่านไม่ออกจะถูกข้ามไป (ไม่ลบข้อมูลเดิม)'),
                const SizedBox(height: 12),
                TextField(
                  controller: textController,
                  maxLines: 8,
                  decoration: const InputDecoration(
                    hintText: 'จันทร์ 09:00-10:30 คณิตศาสตร์',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                if (preview.isNotEmpty) ...[
                  const Text('จะเพิ่มรายการต่อไปนี้',
                      style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  ...preview.map((e) => Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Text(
                          '• ${_dayShort[e['day_of_week']]} '
                          '${e['start_time']}-${e['end_time']} '
                          '${e['subject']}'
                          '${e['location'] != null ? ' (${e['location']})' : ''}',
                        ),
                      )),
                ],
                if (skipped.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text('อ่านไม่ออก ${skipped.length} แถว — จะไม่แตะข้อมูลเดิม',
                      style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('ยกเลิก'),
            ),
            if (preview.isNotEmpty)
              ElevatedButton(
                onPressed: () async {
                  await http.post(Uri.parse('$apiBase/timetable'),
                      headers: {'Content-Type': 'application/json'},
                      body: jsonEncode(preview));
                  if (dialogContext.mounted) Navigator.pop(dialogContext);
                  _fetch();
                },
                child: const Text('ยืนยันบันทึก'),
              ),
            TextButton(
              onPressed: () async {
                final resp = await http.post(
                    Uri.parse('$apiBase/timetable/parse'),
                    headers: {'Content-Type': 'application/json'},
                    body: jsonEncode({'text': textController.text}));
                if (resp.statusCode == 200) {
                  final data = jsonDecode(resp.body);
                  setDialogState(() {
                    preview = (data['entries'] as List<dynamic>? ?? []);
                    skipped = (data['skipped'] as List<dynamic>? ?? []);
                  });
                }
              },
              child: const Text('ตรวจดูรายการ'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _delete(String id) async {
    try {
      await http.delete(Uri.parse('$apiBase/timetable/$id'));
      _fetch();
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  Future<void> _undoCancellation(String id) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('คืนคาบเรียนวันนั้น?'),
        content: const Text('การยกเว้นนี้จะถูกลบ — คาบเรียนวันนั้นกลับมาแสดงตามตารางปกติ'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('ไม่คืน'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('คืนคาบเรียน'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await http.delete(
          Uri.parse('$apiBase/timetable/cancellations/$id'));
      _fetch();
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  String _cancelLabel(dynamic c) {
    final s = c['start_time']?.toString() ?? '';
    final e = c['end_time']?.toString() ?? '';
    if (s == '00:00' && e == '23:59') return 'ทั้งวัน';
    return '$s – $e';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('ตารางเรียน'),
        actions: [
          IconButton(
            icon: const Icon(Icons.paste),
            tooltip: 'วางตารางเรียน',
            onPressed: _showImportDialog,
          ),
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'เพิ่มคาบเรียน',
            onPressed: _showAddDialog,
          ),
          ...buildStandardAppBarActions(context),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _fetch,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  for (var day = 1; day <= 7; day++) ...[
                    if (_onDay(day).isNotEmpty) ...[
                      Padding(
                        padding: const EdgeInsets.only(top: 8, bottom: 4),
                        child: Text(_dayNames[day],
                            style: const TextStyle(
                                fontSize: 15, fontWeight: FontWeight.bold)),
                      ),
                      ..._onDay(day).map((s) => Card(
                            margin: const EdgeInsets.only(bottom: 6),
                            child: ListTile(
                              leading: const Icon(Icons.school, color: Colors.teal),
                              title: Text(s['subject']),
                              subtitle: Text(
                                '${s['start_time']} - ${s['end_time']}'
                                '${s['location'] != null ? ' · ${s['location']}' : ''}',
                              ),
                              trailing: IconButton(
                                icon: const Icon(Icons.delete_outline),
                                onPressed: () => _delete(s['id']),
                                tooltip: 'ลบ',
                              ),
                            ),
                          )),
                    ],
                  ],
                  if (_schedules.isEmpty)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(24),
                        child: Center(
                          child: Text('ยังไม่มีตารางเรียน — กดวางตารางเรียนหรือเพิ่มคาบเรียนได้เลย'),
                        ),
                      ),
                    ),
                  if (_cancellations.isNotEmpty) ...[
                    const Padding(
                      padding: EdgeInsets.only(top: 16, bottom: 4),
                      child: Text('ยกเลิกคาบเฉพาะวัน',
                          style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
                    ),
                    ..._cancellations.map((c) => Card(
                          margin: const EdgeInsets.only(bottom: 6),
                          child: ListTile(
                            leading: const Icon(Icons.event_busy, color: Colors.grey),
                            title: Text('${c['date']}  ${_cancelLabel(c)}'),
                            subtitle: Text(
                                (c['reason']?.toString().isNotEmpty ?? false)
                                    ? 'เหตุผล: ${c['reason']}'
                                    : 'ยกเลิกคาบเรียนเฉพาะวันนี้'),
                            trailing: IconButton(
                              icon: const Icon(Icons.undo),
                              tooltip: 'คืนคาบเรียน',
                              onPressed: () => _undoCancellation(c['id']),
                            ),
                          ),
                        )),
                  ],
                ],
              ),
            ),
    );
  }
}
