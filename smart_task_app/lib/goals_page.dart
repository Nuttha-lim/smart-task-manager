import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'app_bar_actions.dart';
import 'points_notifier.dart';
import 'tasks_notifier.dart';
import 'spellcheck_helper.dart';
import 'api_config.dart';

class GoalsPage extends StatefulWidget {
  const GoalsPage({super.key});

  @override
  State<GoalsPage> createState() => _GoalsPageState();
}

class _GoalsPageState extends State<GoalsPage> {
  final TextEditingController _controller = TextEditingController();
  List<dynamic> _goals = [];
  bool _isLoading = true;
  bool _isCreating = false;
  DateTime? _targetDate;

  String _formatDate(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    _fetchGoals();
  }

  Future<void> _fetchGoals() async {
    setState(() => _isLoading = true);
    try {
      final response = await http.get(Uri.parse('$apiBase/goals'));
      if (response.statusCode == 200) {
        setState(() => _goals = jsonDecode(response.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    setState(() => _isLoading = false);
  }

  Future<void> _createGoal() async {
    final title = _controller.text.trim();
    if (title.isEmpty) return;

    setState(() => _isCreating = true);

    final spellResult = await resolveSpellcheck(title);
    final finalTitle = spellResult.finalText;
    if (finalTitle != title) {
      _controller.text = finalTitle;
    }
    if (mounted) showSpellcheckSnackBar(context, spellResult);

    try {
      // 1) แตกเป้าหมาย + ประเมินคุณภาพ (ยังไม่บันทึก) — ให้ผู้ใช้ตรวจก่อน
      final decomposeUrl = Uri.parse(
          '$apiBase/goals/decompose?title=${Uri.encodeComponent(finalTitle)}');
      final decomposeResp = await http.post(decomposeUrl);
      if (decomposeResp.statusCode != 200) {
        throw Exception('decompose failed: ${decomposeResp.statusCode}');
      }
      final data = jsonDecode(decomposeResp.body) as Map<String, dynamic>;
      final tasks = (data['tasks'] ?? []).map<Map<String, dynamic>>((t) {
        if (t is Map<String, dynamic>) return t;
        return {'title': t.toString()};
      }).toList();
      final assessment = (data['assessment'] ?? {}) as Map<String, dynamic>;

      if (!mounted) return;
      final confirmed = await showDialog<List<String>>(
        context: context,
        barrierDismissible: false,
        builder: (_) => GoalReviewDialog(
          goalTitle: finalTitle,
          tasks: tasks,
          issues: List<Map<String, dynamic>>.from(assessment['issues'] ?? []),
          warnings: List<String>.from(assessment['warnings'] ?? []),
          summary: assessment['summary']?.toString() ?? '',
        ),
      );
      if (confirmed == null) return; // ผู้ใช้ยกเลิก ไม่บันทึก

      // 2) บันทึกด้วยรายการที่ผู้ใช้ยืนยัน/แก้แล้ว
      final url = Uri.parse(
          '$apiBase/goals?title=${Uri.encodeComponent(finalTitle)}'
          '${_targetDate != null ? '&target_date=${_formatDate(_targetDate!)}' : ''}');
      final createResp = await http.post(
        url,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(confirmed),
      );
      if (createResp.statusCode != 200) {
        throw Exception('create failed: ${createResp.statusCode}');
      }
      _controller.clear();
      await _fetchGoals();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('สร้างเป้าหมายไม่สำเร็จ: $e')),
        );
      }
    }
    if (mounted) setState(() => _isCreating = false);
  }

  Future<void> _markSubtaskDone(String taskId) async {
    await http.patch(Uri.parse('$apiBase/tasks/$taskId'));
    PointsNotifier.instance.refresh();
    TasksNotifier.instance.changed();
    _fetchGoals();
  }

  Future<void> _pickTargetDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _targetDate ?? now,
      firstDate: now,
      lastDate: now.add(const Duration(days: 365 * 2)),
    );
    if (picked != null) setState(() => _targetDate = picked);
  }

  String _goalTargetLabel(dynamic goal) {
    final td = goal['target_date'];
    if (td == null) return '';
    try {
      final target = DateTime.parse(td);
      final daysLeft = target.difference(DateTime.now()).inDays;
      if (daysLeft < 0) return ' — เลยวันเป้าหมายมาแล้ว';
      if (daysLeft == 0) return ' — วันนี้คือวันเป้าหมาย';
      return ' — เหลือ $daysLeft วัน';
    } catch (e) {
      return '';
    }
  }

  Future<void> _showStudyPlan(dynamic goal) async {
    final goalId = goal['id'];
    try {
      final resp = await http.get(
          Uri.parse('$apiBase/goals/$goalId/study-plan'));
      if (resp.statusCode != 200) {
        final detail = (jsonDecode(resp.body) as Map<String, dynamic>)['detail']
                ?.toString() ??
            'เกิดข้อผิดพลาด';
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('จัดตารางไม่ได้: $detail')),
          );
        }
        return;
      }
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      if (!mounted) return;
      await showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        builder: (_) => FractionallySizedBox(
          heightFactor: 0.8,
          child: _StudyPlanSheet(
            goalTitle: goal['title']?.toString() ?? '',
            plan: data,
          ),
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('จัดตารางไม่สำเร็จ: $e')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('เป้าหมายระยะยาว'),
        actions: buildStandardAppBarActions(context),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: _controller,
                  decoration: const InputDecoration(
                    labelText: 'เป้าหมายที่อยากทำให้สำเร็จ',
                    hintText: 'เช่น เตรียมสอบวิชาสถิติ',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  icon: const Icon(Icons.event, size: 18),
                  label: Text(_targetDate == null
                      ? 'วันสอบ / วันเป้าหมาย (ไม่บังคับ)'
                      : 'เป้าหมายวันที่ ${_formatDate(_targetDate!)} — แตะเพื่อเปลี่ยน'),
                  onPressed: _isCreating ? null : _pickTargetDate,
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: _isCreating ? null : _createGoal,
                    child: _isCreating
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('ให้ AI ช่วยแตกเป็นงานย่อย'),
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _goals.isEmpty
                    ? const Center(child: Text('ยังไม่มีเป้าหมายเลย'))
                    : RefreshIndicator(
                        onRefresh: _fetchGoals,
                        child: ListView.builder(
                          padding: const EdgeInsets.all(12),
                          itemCount: _goals.length,
                          itemBuilder: (context, index) {
                            final goal = _goals[index];
                            final tasks = goal['tasks'] as List<dynamic>;
                            final doneCount = tasks.where((t) => t['status'] == 'DONE').length;

                            return Card(
                              margin: const EdgeInsets.only(bottom: 12),
                              child: Column(
                                children: [
                                  ExpansionTile(
                                    title: Text(goal['title'],
                                        style: const TextStyle(fontWeight: FontWeight.bold)),
                                    subtitle: Text(
                                        '$doneCount / ${tasks.length} เสร็จแล้ว'
                                        '${_goalTargetLabel(goal)}'),
                                    children: tasks.map<Widget>((t) {
                                      final isDone = t['status'] == 'DONE';
                                      return CheckboxListTile(
                                        value: isDone,
                                        onChanged: isDone
                                            ? null
                                            : (value) => _markSubtaskDone(t['id']),
                                        title: Text(
                                          t['title'],
                                          style: TextStyle(
                                            decoration: isDone ? TextDecoration.lineThrough : null,
                                            color: isDone ? Colors.grey : null,
                                          ),
                                        ),
                                      );
                                    }).toList(),
                                  ),
                                  if (goal['target_date'] != null)
                                    Padding(
                                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                                      child: Row(
                                        children: [
                                          TextButton.icon(
                                            icon: const Icon(Icons.calendar_month, size: 18),
                                            label: const Text('จัดตารางเตรียม'),
                                            onPressed: () => _showStudyPlan(goal),
                                          ),
                                        ],
                                      ),
                                    ),
                                ],
                              ),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}

/// Dialog ตรวจงานย่อยก่อนยืนยัน: แก้/ลบ/เพิ่มได้ (รวมเวลาโดยประมาณ) แล้วคืน
/// รายการสุดท้ายผ่าน Navigator.pop เป็น [{title, estimated_time}]
class GoalReviewDialog extends StatefulWidget {
  final String goalTitle;
  final List<Map<String, dynamic>> tasks;
  final List<Map<String, dynamic>> issues;
  final List<String> warnings;
  final String summary;

  const GoalReviewDialog({
    super.key,
    required this.goalTitle,
    required this.tasks,
    required this.issues,
    required this.warnings,
    required this.summary,
  });

  @override
  State<GoalReviewDialog> createState() => _GoalReviewDialogState();
}

class _GoalReviewDialogState extends State<GoalReviewDialog> {
  late final List<TextEditingController> _controllers;
  late final List<TextEditingController> _timeControllers;
  late final Map<int, String> _issueByIndex;

  @override
  void initState() {
    super.initState();
    _controllers = widget.tasks
        .map((t) => TextEditingController(text: t['title']?.toString() ?? ''))
        .toList();
    _timeControllers = widget.tasks
        .map((t) => TextEditingController(
            text: t['estimated_time'] != null ? t['estimated_time'].toString() : ''))
        .toList();
    _issueByIndex = {
      for (final issue in widget.issues)
        if (issue['index'] is int) issue['index'] as int: issue['message']?.toString() ?? '',
    };
  }

  @override
  void dispose() {
    for (final c in _controllers) {
      c.dispose();
    }
    for (final c in _timeControllers) {
      c.dispose();
    }
    super.dispose();
  }

  void _removeAt(int index) {
    setState(() {
      _controllers.removeAt(index).dispose();
      _timeControllers.removeAt(index).dispose();
    });
  }

  void _addEmpty() {
    setState(() {
      _controllers.add(TextEditingController());
      _timeControllers.add(TextEditingController());
    });
  }

  List<Map<String, dynamic>> _confirmedTasks() {
    final out = <Map<String, dynamic>>[];
    for (var i = 0; i < _controllers.length; i++) {
      final title = _controllers[i].text.trim();
      if (title.isEmpty) continue;
      final timeText = _timeControllers[i].text.trim();
      int? est;
      if (timeText.isNotEmpty) {
        est = int.tryParse(timeText);
        if (est == null || est <= 0) est = null;
      }
      out.add({'title': title, 'estimated_time': est});
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final hasWarnings = widget.warnings.isNotEmpty;
    return AlertDialog(
      title: const Text('ตรวจงานย่อยก่อนยืนยัน'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(widget.goalTitle,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(height: 4),
              if (widget.summary.isNotEmpty)
                Text(
                  widget.summary,
                  style: TextStyle(
                    fontSize: 13,
                    color: hasWarnings ? Colors.deepOrange : Colors.grey,
                  ),
                ),
              if (hasWarnings) ...[
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: Colors.orange.shade50,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.orange.shade200),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: widget.warnings
                        .map((w) => Padding(
                              padding: const EdgeInsets.only(bottom: 2),
                              child: Text('• $w',
                                  style: const TextStyle(color: Colors.deepOrange)),
                            ))
                        .toList(),
                  ),
                ),
              ],
              const SizedBox(height: 12),
              for (var i = 0; i < _controllers.length; i++) ...[
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _controllers[i],
                        decoration: InputDecoration(
                          isDense: true,
                          border: const OutlineInputBorder(),
                          labelText: 'งานย่อย ${i + 1}',
                          suffixIcon: _issueByIndex[i] == null
                              ? null
                              : Tooltip(
                                  message: _issueByIndex[i]!,
                                  child: const Padding(
                                    padding: EdgeInsets.all(8),
                                    child: Icon(Icons.warning_amber_rounded,
                                        color: Colors.orange, size: 20),
                                  ),
                                ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 110,
                      child: TextField(
                        controller: _timeControllers[i],
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          isDense: true,
                          border: OutlineInputBorder(),
                          labelText: 'นาที',
                          hintText: '30',
                        ),
                      ),
                    ),
                    IconButton(
                      tooltip: 'ลบข้อนี้',
                      icon: const Icon(Icons.remove_circle_outline),
                      onPressed: () => _removeAt(i),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
              ],
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: _addEmpty,
                  icon: const Icon(Icons.add),
                  label: const Text('เพิ่มงานย่อย'),
                ),
              ),
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
          onPressed: () => Navigator.of(context).pop(_confirmedTasks()),
          child: const Text('ยืนยันและบันทึก'),
        ),
      ],
    );
  }
}

/// แผนเตรียมสอบ/เป้าหมาย: แสดงตารางรายวันจาก GET /goals/{id}/study-plan
class _StudyPlanSheet extends StatelessWidget {
  final String goalTitle;
  final Map<String, dynamic> plan;

  const _StudyPlanSheet({required this.goalTitle, required this.plan});

  @override
  Widget build(BuildContext context) {
    final days = (plan['days'] as List<dynamic>? ?? []);
    final leftover = (plan['leftover'] as List<dynamic>? ?? []);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(goalTitle,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(height: 4),
              Text('วันเป้าหมาย ${plan['target_date']} — เหลือ ${plan['days_left']} วัน',
                  style: TextStyle(fontSize: 13, color: Colors.grey.shade700)),
              Text('กำลังต่อวัน: ${plan['per_day_minutes']} นาที (ระดับพลังงาน ${plan['energy_level']})',
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: days.isEmpty
              ? const Center(child: Text('ไม่มีงานย่อยให้จัด — ลองเพิ่มงานย่อยก่อน'))
              : ListView.builder(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                  itemCount: days.length,
                  itemBuilder: (context, i) {
                    final day = days[i] as Map<String, dynamic>;
                    final dayTasks = (day['tasks'] as List<dynamic>? ?? []);
                    return Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('${day['date']} — ${day['total_minutes']} นาที',
                                style: const TextStyle(fontWeight: FontWeight.bold)),
                            const SizedBox(height: 4),
                            ...dayTasks.map((t) => Padding(
                                  padding: const EdgeInsets.only(top: 2),
                                  child: Text('• ${t['title']}'),
                                )),
                            if (dayTasks.isEmpty)
                              const Text('พัก / ทำอย่างอื่น',
                                  style: TextStyle(color: Colors.grey)),
                          ],
                        ),
                      ),
                    );
                  },
                ),
        ),
        if (leftover.isNotEmpty)
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              'วางไม่พอ: ${leftover.map((t) => t['title']).join(', ')}',
              style: const TextStyle(color: Colors.deepOrange),
            ),
          ),
      ],
    );
  }
}