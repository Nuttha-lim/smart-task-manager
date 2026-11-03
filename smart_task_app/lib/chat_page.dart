import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';

import 'app_bar_actions.dart';
import 'daily_plan_page.dart';
import 'task_review_dialog.dart';
import 'tasks_notifier.dart';
import 'timetable_review_dialog.dart';
import 'travel_page.dart';
import 'api_config.dart';

/// Chat — พูดกับแอปฟรีฟอร์ม แอปแยกแยะเองว่าข้อความคืออะไร:
/// งานใหม่ / ไฟล์ / แพลนวันนี้ / ทริป / ทักทาย
class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final List<Map<String, dynamic>> _messages = [];
  final List<PlatformFile> _pendingFiles = []; // ไฟล์ที่เลือกไว้แต่ยังไม่ส่ง
  bool _isSending = false;

  @override
  void initState() {
    super.initState();
    _messages.add({
      'role': 'assistant',
      'text': 'พิมพ์งานที่ต้องทำ เช่น "ล้างจานพรุ่งนี้เช้า 30 นาที" '
          'หรือส่งไฟล์/รูป (หลายไฟล์ได้) มาให้ช่วยดึงงานออกก็ได้ '
          'แอปจะอ่านให้ แล้วถามว่าจะให้ทำอะไรต่อ',
    });
  }

  Future<void> _sendText() async {
    final text = _inputController.text.trim();
    if (text.isEmpty && _pendingFiles.isEmpty) return;
    _inputController.clear();
    final files = List<PlatformFile>.from(_pendingFiles);
    setState(() => _pendingFiles.clear());
    if (text.isNotEmpty) _addMessage('user', text);
    if (files.isNotEmpty) {
      _addMessage('user', files.length == 1 ? '📎 ${files.first.name}' : '📎 ${files.length} ไฟล์');
    }
    await _post(text: text, files: files);
  }

  Future<void> _attachFile() async {
    // withData: true สำคัญมากบน Flutter web — ไม่ใส่จะได้ PlatformFile ที่ bytes == null
    // (file_picker web ไม่โหลดเนื้อไฟล์ให้เอง) แล้วจะไปตายที่ `if (file.bytes == null) return;`
    final result = await FilePicker.pickFiles(withData: true, allowMultiple: true);
    if (result == null || result.files.isEmpty) return;
    setState(() {
      _pendingFiles.addAll(result.files.where((f) => f.bytes != null));
    });
  }

  Future<void> _post({String? text, List<PlatformFile>? files}) async {
    setState(() => _isSending = true);
    try {
      final request = http.MultipartRequest('POST', Uri.parse('$apiBase/chat'));
      if (text != null && text.isNotEmpty) request.fields['text'] = text;
      for (final f in files ?? <PlatformFile>[]) {
        if (f.bytes == null) continue;
        request.files.add(http.MultipartFile.fromBytes(
          'files',
          f.bytes!,
          filename: f.name,
        ));
      }
      final streamed = await request.send();
      final resp = await http.Response.fromStream(streamed);
      final data = resp.statusCode == 200 ? jsonDecode(resp.body) : {'error': 'backend error ${resp.statusCode}'};
      await _handleResponse(data);
    } catch (e) {
      _addMessage('assistant', 'เชื่อมต่อ backend ไม่ได้ — $e');
    }
    if (mounted) setState(() => _isSending = false);
  }

  Future<void> _handleResponse(Map<String, dynamic> data) async {
    final intent = data['intent'] ?? 'chat';
    final reply = data['reply']?.toString() ?? '';
    _addMessage('assistant', reply);

    if (intent == 'create_task') {
      final tasks = (data['tasks'] as List<dynamic>? ?? [])
          .where((t) => (t['title']?.toString().isNotEmpty ?? false))
          .map((t) => (t as Map).cast<String, dynamic>())
          .toList();
      if (tasks.isNotEmpty) {
        await _openTaskReview('ตรวจงานจากข้อความก่อนยืนยัน', tasks);
      }
    } else if (intent == 'cancel_task') {
      // หางานที่อยากยกเลิกเจอ → ขึ้นปุ่มให้เลือกว่าใช่ตัวไหน (กดแล้วลบ พร้อมยืนยัน)
      final tasks = (data['tasks'] as List<dynamic>? ?? [])
          .where((t) => t is Map && (t['title']?.toString().isNotEmpty ?? false))
          .map((t) => (t as Map).cast<String, dynamic>())
          .toList();
      if (tasks.isNotEmpty) {
        _addMessage('assistant', '', actions: [
          for (final t in tasks)
            {
              'key': 'cancel_task_${t['id']}',
              'label': 'ยกเลิก: ${t['title']}',
              'task_id': t['id'],
              'task_title': t['title'],
            },
        ], payload: {'tasks': tasks});
      }
    } else if (intent == 'cancel_classes') {
      // "เช้าวันจันทร์ไม่มีเรียน" → ขึ้นปุ่มให้ยืนยันว่ายกเลิกคาบช่วงนั้นจริง (เฉพาะวันนั้น)
      final classes = (data['classes'] as List<dynamic>? ?? [])
          .where((c) => c is Map && (c['subject']?.toString().isNotEmpty ?? false))
          .toList();
      if (classes.isNotEmpty) {
        _addMessage('assistant', '', actions: [
          {
            'key': 'cancel_classes_confirm',
            'label': 'ยกเลิกคาบเรียน (${classes.length} คาบ)',
          },
        ], payload: {
          'date': data['date']?.toString() ?? '',
          'start_time': data['start_time']?.toString() ?? '00:00',
          'end_time': data['end_time']?.toString() ?? '23:59',
          'reason': data['reason']?.toString() ?? '',
          'classes': classes,
        });
      }
    } else if (intent == 'analyze_file') {
      // แบบ ChatGPT: ไม่อัดหน้าตรวจให้ทันที — ขึ้นข้อความ + ปุ่มให้ผู้ใช้เลือกว่าจะทำอะไรต่อ
      final tasks = (data['tasks'] as List<dynamic>? ?? [])
          .where((t) => t is Map && (t['title']?.toString().isNotEmpty ?? false))
          .map((t) => (t as Map).cast<String, dynamic>())
          .toList();
      final summary = data['summary']?.toString() ?? '';
      final suggested = (data['suggested_actions'] as List<dynamic>? ?? [])
          .map((a) => a.toString())
          .toList();
      final actions = <Map<String, dynamic>>[];
      if (suggested.contains('add_tasks') && tasks.isNotEmpty) {
        actions.add({'key': 'add_tasks', 'label': 'เพิ่มเป็นงานทั้งหมด (${tasks.length})'});
      }
      if (suggested.contains('summarize') && summary.isNotEmpty) {
        actions.add({'key': 'summarize', 'label': 'สรุปเนื้อหา'});
      }
      if (actions.isNotEmpty) {
        _addMessage('assistant', '', actions: actions,
            payload: {'tasks': tasks, 'summary': summary});
      }
    } else if (intent == 'set_timetable') {
      // อ่านตารางเรียนจากข้อความ/ไฟล์ได้ → ให้ตรวจก่อนบันทึก (แทนที่ตารางเดิม)
      final entries = (data['entries'] as List<dynamic>? ?? [])
          .whereType<Map<String, dynamic>>()
          .toList();
      if (entries.isNotEmpty) {
        _addMessage('assistant', '', actions: [
          {'key': 'apply_timetable', 'label': 'บันทึกตารางเรียน (${entries.length} คาบ)'},
        ], payload: {'entries': entries});
      }
    } else if (intent == 'update_timetable') {
      // คำสั่งแก้ตาราง (เพิ่ม/ลบ/ย้าย/ล้าง) → ให้ผู้ใช้ยืนยันก่อนลงมือจริง
      final ok = data['ok'] == true;
      if (ok) {
        final action = (data['action'] as Map?)?.cast<String, dynamic>() ?? {};
        _addMessage('assistant', '', actions: [
          {'key': 'confirm_timetable_change', 'label': 'ยืนยันการเปลี่ยน'},
        ], payload: {'action': action, 'summary': reply});
      }
    } else if (intent == 'plan_daily') {
      _addMessage('assistant', 'เปิดหน้าแพลนวันนี้ให้แล้ว — เลือกระดับพลังงานได้เลย');
      if (mounted) {
        await Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => DailyPlanPage(initialPreview: (data['plan_preview'] as Map<String, dynamic>?)),
          ),
        );
      }
    } else if (intent == 'plan_trip') {
      _addMessage('assistant', 'เปิดหน้าเดินทางให้แล้ว — กรอกปลายทาง/วันเดินทางได้เลย');
      if (mounted) {
        await Navigator.push(context, MaterialPageRoute(builder: (_) => const TravelPage()));
      }
    }
  }

  Future<void> _runAction(Map<String, dynamic> action, Map<String, dynamic> payload) async {
    switch (action['key']) {
      case 'add_tasks':
        final tasks = (payload['tasks'] as List<Map<String, dynamic>>? ?? []);
        if (tasks.isEmpty) return;
        await _openTaskReview('ตรวจงานจากไฟล์ก่อนยืนยัน', tasks);
        break;
      case 'summarize':
        final summary = payload['summary']?.toString() ?? '';
        if (summary.isNotEmpty) _addMessage('assistant', '📄 สรุปเนื้อหา:\n$summary');
        break;
      case 'apply_timetable':
        final entries = (payload['entries'] as List<Map<String, dynamic>>? ?? []);
        if (entries.isEmpty) return;
        final confirmed = await showDialog<List<Map<String, dynamic>>>(
          context: context,
          barrierDismissible: false,
          builder: (_) => TimetableReviewDialog(
            title: 'ตรวจตารางเรียนก่อนบันทึก',
            subtitle: 'แก้ไข/เพิ่ม/ลบคาบได้ตามที่ต้องการ — บันทึกจะแทนที่ตารางเดิม',
            entries: entries,
          ),
        );
        if (confirmed == null || confirmed.isEmpty || !mounted) {
          if (confirmed == null) _addMessage('assistant', 'โอเค ไม่ได้บันทึกตาราง');
          return;
        }
        await _saveTimetable(confirmed, replace: true);
        break;
      case 'confirm_timetable_change':
        final action = (payload['action'] as Map<String, dynamic>?) ?? {};
        final summary = payload['summary']?.toString() ?? '';
        await _confirmTimetableChange(action, summary);
        break;
      case 'cancel_classes_confirm':
        await _confirmCancelClasses(payload);
        break;
      default:
        final key = action['key']?.toString() ?? '';
        if (key.startsWith('cancel_task_')) {
          await _confirmCancelTask(
              action['task_id']?.toString() ?? '',
              action['task_title']?.toString() ?? 'งานนี้');
        }
        break;
    }
  }

  Future<void> _openTaskReview(String title, List<Map<String, dynamic>> tasks) async {
    if (!mounted) return;
    final confirmed = await showDialog<List<Map<String, dynamic>>>(
      context: context,
      barrierDismissible: false,
      builder: (_) => TaskReviewDialog(
        title: title,
        subtitle: 'งานจาก AI — ตรวจก่อนบันทึก',
        summary: '',
        tasks: tasks,
      ),
    );
    if (confirmed == null || confirmed.isEmpty || !mounted) {
      if (confirmed == null) _addMessage('assistant', 'โอเค ไม่บันทึกอะไร — พิมพ์ใหม่อีกทีได้เลย');
      return;
    }
    try {
      final resp = await http.post(
        Uri.parse('$apiBase/tasks/bulk'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(confirmed),
      );
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        _addMessage('assistant', 'บันทึกแล้ว ${data['count']} รายการ 🎉');
        TasksNotifier.instance.changed();
      } else {
        _addMessage('assistant', 'บันทึกไม่สำเร็จ (${resp.statusCode})');
      }
    } catch (e) {
      _addMessage('assistant', 'บันทึกไม่สำเร็จ: $e');
    }
  }

  Future<void> _saveTimetable(List<Map<String, dynamic>> entries, {bool replace = false}) async {
    try {
      final resp = await http.post(
        Uri.parse('$apiBase/timetable${replace ? '?replace=true' : ''}'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(entries),
      );
      final data = resp.statusCode == 200 ? jsonDecode(resp.body) : {};
      if (resp.statusCode == 200) {
        final count = data['count'] ?? entries.length;
        _addMessage('assistant', 'บันทึกตารางเรียนแล้ว $count คาบ 🎉');
      } else {
        _addMessage('assistant', 'บันทึกตารางเรียนไม่สำเร็จ (${resp.statusCode})');
      }
    } catch (e) {
      _addMessage('assistant', 'บันทึกตารางเรียนไม่สำเร็จ: $e');
    }
  }

  Future<void> _confirmTimetableChange(Map<String, dynamic> action, String summary) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('ยืนยันการแก้ตารางเรียน'),
        content: Text(summary),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('ยกเลิก'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('ยืนยัน'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      final resp = await http.post(
        Uri.parse('$apiBase/timetable/apply-change'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(action),
      );
      final data = resp.statusCode == 200 ? jsonDecode(resp.body) : {};
      _addMessage('assistant', data['summary']?.toString() ?? 'แก้ตารางเรียนแล้ว');
    } catch (e) {
      _addMessage('assistant', 'แก้ตารางเรียนไม่สำเร็จ: $e');
    }
  }

  Future<void> _confirmCancelClasses(Map<String, dynamic> payload) async {
    final classes = (payload['classes'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    final dateStr = payload['date']?.toString() ?? '';
    final subjectList = classes
        .map((c) => c['subject']?.toString() ?? '')
        .where((s) => s.isNotEmpty)
        .join(' · ');
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('ยกเลิกคาบเรียนเฉพาะวันนี้?'),
        content: Text(
            'จะยกเลิก ${classes.length} คาบของวันที่ $dateStr:\n$subjectList\n\n'
            'ตารางประจำสัปดาห์ไม่เปลี่ยน — แก้ย้อนหลังได้ที่หน้าตารางเรียน'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('ไม่ยกเลิก'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('ยืนยัน'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      final uri = Uri.parse('$apiBase/timetable/cancel').replace(queryParameters: {
        'date': dateStr,
        'start_time': payload['start_time']?.toString() ?? '00:00',
        'end_time': payload['end_time']?.toString() ?? '23:59',
        'reason': payload['reason']?.toString() ?? '',
      });
      final resp = await http.post(uri);
      final data = resp.statusCode == 200 ? jsonDecode(resp.body) : {};
      if (resp.statusCode == 200 && data['ok'] == true) {
        _addMessage('assistant', 'ยกเลิกคาบเรียนวันนั้นแล้ว ✅ ดู/แก้ย้อนหลังได้ที่หน้าตารางเรียน');
      } else {
        _addMessage('assistant', 'ยกเลิกไม่สำเร็จ (${resp.statusCode})');
      }
    } catch (e) {
      _addMessage('assistant', 'ยกเลิกไม่สำเร็จ: $e');
    }
  }

  Future<void> _confirmCancelTask(String taskId, String title) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('ยกเลิกงานนี้?'),
        content: Text('ลบ "$title" ออกจากรายการ — ทำแล้วจะกลับมาไม่ได้'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('ไม่ลบ'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.error),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('ลบเลย'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      final resp = await http
          .delete(Uri.parse('$apiBase/tasks/$taskId'));
      if (resp.statusCode == 200) {
        _addMessage('assistant', 'ลบ "$title" แล้ว 🎉');
        TasksNotifier.instance.changed();
      } else {
        _addMessage('assistant', 'ลบไม่สำเร็จ (${resp.statusCode})');
      }
    } catch (e) {
      _addMessage('assistant', 'ลบไม่สำเร็จ: $e');
    }
  }

  void _addMessage(String role, String text,
      {List<Map<String, dynamic>>? actions, Map<String, dynamic>? payload}) {
    setState(() {
      _messages.add({
        'role': role,
        'text': text,
        if (actions != null && actions.isNotEmpty) 'actions': actions,
        'payload': ?payload,
      });
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('แชทกับแอป'),
        actions: buildStandardAppBarActions(context),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length,
              itemBuilder: (context, index) => _bubble(_messages[index]),
            ),
          ),
          _pendingFilesBar(),
          _inputBar(),
        ],
      ),
    );
  }

  Widget _pendingFilesBar() {
    if (_pendingFiles.isEmpty) return const SizedBox.shrink();
    return Container(
      height: 40,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: ListView(
        scrollDirection: Axis.horizontal,
        children: _pendingFiles.map((f) {
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: InputChip(
              avatar: const Icon(Icons.insert_drive_file, size: 16),
              label: Text(f.name, overflow: TextOverflow.ellipsis),
              visualDensity: VisualDensity.compact,
              onDeleted: () => setState(() => _pendingFiles.remove(f)),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _bubble(Map<String, dynamic> msg) {
    final isUser = msg['role'] == 'user';
    final actions = (msg['actions'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    final payload = (msg['payload'] as Map<String, dynamic>?) ?? {};
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.8),
        decoration: BoxDecoration(
          color: isUser ? Colors.teal.shade600 : Colors.grey.shade200,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(14),
            topRight: const Radius.circular(14),
            bottomLeft: Radius.circular(isUser ? 14 : 2),
            bottomRight: Radius.circular(isUser ? 2 : 14),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if ((msg['text']?.toString() ?? '').isNotEmpty)
              Text(
                msg['text']?.toString() ?? '',
                style: TextStyle(color: isUser ? Colors.white : Colors.black87, fontSize: 15),
              ),
            if (actions.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: actions.map((a) {
                  return ActionChip(
                    label: Text(a['label']?.toString() ?? '', style: const TextStyle(fontSize: 13)),
                    avatar: Icon(
                      (a['key']?.toString() ?? '').startsWith('cancel_task_')
                          ? Icons.cancel
                          : a['key'] == 'cancel_classes_confirm'
                              ? Icons.event_busy
                              : a['key'] == 'add_tasks'
                                  ? Icons.playlist_add
                                  : Icons.summarize,
                      size: 16),
                    onPressed: () => _runAction(a, payload),
                  );
                }).toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _inputBar() {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
        child: Row(
          children: [
            IconButton(
              icon: const Icon(Icons.attach_file),
              onPressed: _isSending ? null : _attachFile,
              tooltip: 'แนบไฟล์/รูป',
            ),
            Expanded(
              child: TextField(
                controller: _inputController,
                decoration: InputDecoration(
                  hintText: 'พิมพ์งาน แพลนวันนี้ ไปเที่ยว...',
                  isDense: true,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(24)),
                ),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _sendText(),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              icon: _isSending
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.send),
              onPressed: _isSending ? null : _sendText,
            ),
          ],
        ),
      ),
    );
  }
}
