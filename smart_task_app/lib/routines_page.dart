import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'api_config.dart';

/// จัดการกิจวัตรประจำวัน — รายการ + เพิ่ม/แก้/ลบ/เปิด-ปิด
/// กลับออกมาด้วย `true` ถ้ามีอะไรเปลี่ยน (หน้า timeline จะได้โหลดใหม่)
class RoutinesPage extends StatefulWidget {
  const RoutinesPage({super.key});

  @override
  State<RoutinesPage> createState() => _RoutinesPageState();
}

class _RoutinesPageState extends State<RoutinesPage> {
  List<Map<String, dynamic>>? _routines;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _fetch();
  }

  Future<void> _fetch() async {
    setState(() => _isLoading = true);
    try {
      final resp = await http
          .get(Uri.parse('$apiBase/routines'));
      if (resp.statusCode == 200 && mounted) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        setState(() => _routines = (data['routines'] as List<dynamic>? ?? [])
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList());
      }
    } catch (e) {
      if (mounted) _showMessage('เชื่อมต่อ backend ไม่ได้');
    }
    if (mounted) setState(() => _isLoading = false);
  }

  void _showMessage(String msg) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _saveRoutine({Map<String, dynamic>? existing}) async {
    final titleCtrl = TextEditingController(text: existing?['title'] ?? '');
    final timeCtrl = TextEditingController(text: existing?['time'] ?? '');
    final descCtrl =
        TextEditingController(text: existing?['description'] ?? '');
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(existing == null ? 'เพิ่มกิจวัตร' : 'แก้กิจวัตร'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: titleCtrl,
              decoration: const InputDecoration(
                labelText: 'ชื่อกิจวัตร',
                hintText: 'เช่น ทานยาเช้า',
              ),
            ),
            TextField(
              controller: timeCtrl,
              decoration: const InputDecoration(
                labelText: 'เวลา (HH:MM)',
                hintText: 'เช่น 08:00',
              ),
            ),
            TextField(
              controller: descCtrl,
              decoration: const InputDecoration(labelText: 'รายละเอียด (ไม่บังคับ)'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('ยกเลิก'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('บันทึก'),
          ),
        ],
      ),
    );
    if (saved != true) return;

    final title = titleCtrl.text.trim();
    final time = timeCtrl.text.trim();
    if (title.isEmpty || !RegExp(r'^\d{2}:\d{2}$').hasMatch(time)) {
      _showMessage('ต้องมีชื่อและเวลาแบบ HH:MM');
      return;
    }

    if (existing == null) {
      await http.post(Uri.parse('$apiBase/routines'),
          body: {
            'title': title,
            'time': time,
            'description': descCtrl.text.trim(),
          });
    } else {
      await http.put(Uri.parse('$apiBase/routines/${existing['id']}')
          .replace(queryParameters: {
        'title': title,
        'time': time,
        'description': descCtrl.text.trim(),
      }));
    }
    await _fetch();
  }

  Future<void> _toggle(Map<String, dynamic> r, bool value) async {
    await http.put(Uri.parse('$apiBase/routines/${r['id']}')
        .replace(queryParameters: {'enabled': '$value'}));
    await _fetch();
  }

  Future<void> _delete(Map<String, dynamic> r) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('ลบกิจวัตร?'),
        content: Text('ลบ "${r['title']}" ออกจากรายการ'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('ยกเลิก'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: Theme.of(ctx).colorScheme.error),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('ลบ'),
          ),
        ],
      ),
    );
    if (ok == true) {
      await http.delete(Uri.parse('$apiBase/routines/${r['id']}'));
      await _fetch();
    }
  }

  @override
  Widget build(BuildContext context) {
    final routines = _routines ?? [];
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        Navigator.pop(context, true);
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('กิจวัตรประจำวัน'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () => Navigator.pop(context, true),
          ),
        ),
        body: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _fetch,
                child: ListView(
                  padding: const EdgeInsets.all(12),
                  children: [
                    const Padding(
                      padding: EdgeInsets.only(bottom: 8),
                      child: Text(
                        'กิจวัตรจะขึ้นในไทม์ไลน์ของทุกวัน — ปิดไว้ได้ถ้าอยากพัก',
                        style: TextStyle(color: Colors.grey),
                      ),
                    ),
                    ...routines.map((r) => Card(
                          elevation: 0,
                          margin: const EdgeInsets.only(bottom: 8),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                            side: BorderSide(
                                color: Theme.of(context)
                                    .colorScheme
                                    .outlineVariant),
                          ),
                          child: ListTile(
                            leading: const Icon(Icons.alarm_on,
                                color: Colors.indigo),
                            title: Text(r['title'] ?? '',
                                style: TextStyle(
                                    color: r['enabled'] == true
                                        ? null
                                        : Colors.grey)),
                            subtitle: Text(
                                '${r['time']}'
                                '${r['description'] != null ? ' · ${r['description']}' : ''}',
                                style: const TextStyle(fontSize: 12)),
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.edit, size: 20),
                                  onPressed: () => _saveRoutine(existing: r),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.delete_outline,
                                      size: 20),
                                  onPressed: () => _delete(r),
                                ),
                                Switch(
                                  value: r['enabled'] == true,
                                  onChanged: (v) => _toggle(r, v),
                                ),
                              ],
                            ),
                          ),
                        )),
                  ],
                ),
              ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => _saveRoutine(),
          icon: const Icon(Icons.add),
          label: const Text('เพิ่มกิจวัตร'),
        ),
      ),
    );
  }
}
