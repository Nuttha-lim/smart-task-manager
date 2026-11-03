import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import 'app_bar_actions.dart';
import 'tasks_notifier.dart';
import 'api_config.dart';

class TaskDetailPage extends StatefulWidget {
  final Map<String, dynamic> task;
  const TaskDetailPage({super.key, required this.task});

  @override
  State<TaskDetailPage> createState() => _TaskDetailPageState();
}

class _TaskDetailPageState extends State<TaskDetailPage> {
  bool _isEditing = false;
  bool _isSaving = false;
  late TextEditingController _titleController;
  late TextEditingController _descController;
  late TextEditingController _timeController;
  DateTime? _deadline;

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController(text: widget.task['title'] ?? '');
    _descController = TextEditingController(text: widget.task['description'] ?? '');
    _timeController = TextEditingController(text: widget.task['deadline_time'] ?? '23:59');
    if (widget.task['deadline'] != null) {
      try {
        _deadline = DateTime.parse(widget.task['deadline']);
      } catch (e) {
        _deadline = null;
      }
    }
  }

  Future<void> _pickDeadline() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _deadline ?? DateTime.now(),
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) setState(() => _deadline = picked);
  }

  Future<void> _save() async {
    setState(() => _isSaving = true);
    final id = widget.task['id'];
    var urlString = '$apiBase/tasks/$id'
        '?title=${Uri.encodeComponent(_titleController.text)}'
        '&description=${Uri.encodeComponent(_descController.text)}'
        '&deadline_time=${Uri.encodeComponent(_timeController.text)}';
    if (_deadline != null) {
      final d = "${_deadline!.year}-${_deadline!.month.toString().padLeft(2, '0')}-${_deadline!.day.toString().padLeft(2, '0')}";
      urlString += '&deadline=$d';
    }
    try {
      final response = await http.put(Uri.parse(urlString));
      if (response.statusCode == 200 && mounted) {
        TasksNotifier.instance.changed(); // Dashboard/History โหลดใหม่
        Navigator.pop(context, jsonDecode(response.body));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('บันทึกไม่สำเร็จ: $e')),
        );
      }
    }
    setState(() => _isSaving = false);
  }

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('ลบงานนี้?'),
        content: Text('ต้องการลบ "${widget.task['title']}" ใช่ไหม'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('ยกเลิก')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('ลบ', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    final id = widget.task['id'];
    try {
      await http.delete(Uri.parse('$apiBase/tasks/$id'));
      TasksNotifier.instance.changed(); // Dashboard/History โหลดใหม่
      if (mounted) Navigator.pop(context, {'deleted': true});
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('ลบไม่สำเร็จ: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final deadlineStr = _deadline != null
        ? "${_deadline!.year}-${_deadline!.month.toString().padLeft(2, '0')}-${_deadline!.day.toString().padLeft(2, '0')}"
        : null;

    return Scaffold(
      appBar: AppBar(
        title: Text(_isEditing ? 'แก้ไขงาน' : 'รายละเอียดงาน'),
        actions: [
          ...buildStandardAppBarActions(context),
          IconButton(
            icon: const Icon(Icons.delete_outline, color: Colors.red),
            onPressed: _delete,
          ),
          IconButton(
            icon: Icon(_isEditing ? Icons.close : Icons.edit),
            onPressed: () => setState(() => _isEditing = !_isEditing),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: _isEditing
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextField(
                    controller: _titleController,
                    decoration: const InputDecoration(labelText: 'ชื่องาน', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _descController,
                    maxLines: 3,
                    decoration: const InputDecoration(labelText: 'รายละเอียดเพิ่มเติม (ถ้ามี)', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 12),
                  InkWell(
                    onTap: _pickDeadline,
                    child: InputDecorator(
                      decoration: const InputDecoration(labelText: 'กำหนดส่ง', border: OutlineInputBorder()),
                      child: Text(deadlineStr ?? 'ไม่ระบุ (แตะเพื่อเลือก)'),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _timeController,
                    decoration: const InputDecoration(labelText: 'เวลาส่ง (HH:MM)', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton(
                    onPressed: _isSaving ? null : _save,
                    style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                    child: _isSaving
                        ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('บันทึกการแก้ไข'),
                  ),
                ],
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(widget.task['title'] ?? '', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  Chip(label: Text(widget.task['status'] ?? 'TODO')),
                  const SizedBox(height: 16),
                  if ((widget.task['description'] ?? '').isNotEmpty) ...[
                    const Text('รายละเอียด', style: TextStyle(fontWeight: FontWeight.bold)),
                    const SizedBox(height: 4),
                    Text(widget.task['description']),
                    const SizedBox(height: 16),
                  ],
                  const Text('กำหนดส่ง', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text(deadlineStr != null
                      ? '$deadlineStr ${widget.task['deadline_time'] ?? '23:59'}'
                      : 'ไม่ระบุ'),
                  const SizedBox(height: 16),
                  const Text('สร้างเมื่อ', style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text(widget.task['created_at'] ?? '-'),
                ],
              ),
      ),
    );
  }
}