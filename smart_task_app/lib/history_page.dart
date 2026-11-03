import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'app_bar_actions.dart';
import 'points_notifier.dart';
import 'task_detail_page.dart';
import 'tasks_notifier.dart';
import 'api_config.dart';

class HistoryPage extends StatefulWidget {
  const HistoryPage({super.key});

  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  List<dynamic> _tasks = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _fetchTasks();
  }

  Future<void> _fetchTasks() async {
    setState(() => _isLoading = true);
    try {
      final response = await http.get(Uri.parse('$apiBase/tasks'));
      if (response.statusCode == 200) {
        final tasks = jsonDecode(response.body) as List<dynamic>;
        tasks.sort((a, b) => (b['created_at'] ?? '').compareTo(a['created_at'] ?? ''));
        setState(() => _tasks = tasks);
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    setState(() => _isLoading = false);
  }

  Future<void> _openDetail(Map<String, dynamic> task) async {
    final result = await Navigator.push(
      context,
      MaterialPageRoute(builder: (context) => TaskDetailPage(task: task)),
    );
    if (result != null) _fetchTasks();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('ประวัติงานทั้งหมด'),
        actions: buildStandardAppBarActions(context),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _fetchTasks,
              child: _tasks.isEmpty
                  ? const Center(child: Text('ยังไม่มีงานเลย'))
                  : ListView.builder(
                      padding: const EdgeInsets.all(12),
                      itemCount: _tasks.length,
                      itemBuilder: (context, index) {
                        final t = _tasks[index];
                        final isDone = t['status'] == 'DONE';
                        return Card(
                          child: ListTile(
                            leading: Icon(
                              isDone ? Icons.check_circle : Icons.radio_button_unchecked,
                              color: isDone ? Colors.green : Colors.grey,
                            ),
                            title: Text(
                              t['title'] ?? '',
                              style: TextStyle(
                                decoration: isDone ? TextDecoration.lineThrough : null,
                                color: isDone ? Colors.grey : null,
                              ),
                            ),
                            subtitle: Text(t['deadline'] != null
                                ? 'กำหนดส่ง: ${t['deadline']} ${t['deadline_time'] ?? ''}'
                                : 'ไม่มีกำหนดส่ง'),
                            onTap: () => _openDetail(t),
                            trailing: isDone
                                ? IconButton(
                                    icon: const Icon(Icons.undo, color: Colors.grey),
                                    tooltip: 'กดผิด / ยังไม่เสร็จจริง',
                                    onPressed: () => _undoDone(t),
                                  )
                                : null,
                          ),
                        );
                      },
                    ),
            ),
    );
  }

  Future<void> _undoDone(dynamic task) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('กลับเป็นยังไม่เสร็จ?'),
        content: Text('งาน "${task['title']}" จะกลับเป็นยังไม่เสร็จ'
            'และแต้มที่ได้ (${task['points_awarded'] ?? 0} แต้ม) จะถูกหักคืน'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('ไม่ ปล่อยไว้'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('ยกเลิกว่าทำเสร็จ'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    String message;
    try {
      final resp = await http.post(
          Uri.parse('$apiBase/tasks/${task['id']}/undo'));
      final data = jsonDecode(resp.body);
      message = data['status'] == 'TODO'
          ? 'กลับเป็นยังไม่เสร็จแล้ว — ทำต่อได้ไม่กดดัน'
          : (data['error'] ?? 'ยกเลิกไม่สำเร็จ');
    } catch (e) {
      message = 'ยกเลิกไม่สำเร็จ: $e';
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    PointsNotifier.instance.refresh();
    TasksNotifier.instance.changed(); // ให้ Dashboard อัปเดตทั้ง list + สรุปวันนี้
    await _fetchTasks();
  }
}