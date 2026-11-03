import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app_bar_actions.dart';
import 'api_config.dart';

/// Daily Plan — จัดแพลนวันนี้ตามระดับพลังงาน + ตารางเรียน
///
/// Flow: ดู preview ว่าแต่ละระดับพลังงานทำงานอะไรได้บ้าง → เลือกระดับ → แอปจัด
/// ตารางจริง (งานลงช่วงว่างของตารางเรียน, ถ้างานแทรก/ตารางเปลี่ยน งานย้าย slot ให้เอง)
class DailyPlanPage extends StatefulWidget {
  final Map<String, dynamic>? initialPreview;
  final DateTime? initialDate;

  const DailyPlanPage({super.key, this.initialPreview, this.initialDate});

  @override
  State<DailyPlanPage> createState() => _DailyPlanPageState();
}

class _DailyPlanPageState extends State<DailyPlanPage> {
  Map<String, dynamic>? _preview;
  Map<String, dynamic>? _plan;
  int _selectedLevel = 3;
  bool _isLoading = true;
  bool _isBuilding = false;
  DateTime _date = DateTime.now();
  String _dateStr() =>
      '${_date.year}-${_date.month.toString().padLeft(2, '0')}-${_date.day.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    _date = widget.initialDate ?? DateTime.now();
    if (widget.initialPreview != null) {
      _preview = widget.initialPreview;
      _isLoading = false;
    } else {
      _loadPreview();
    }
  }

  Future<void> _loadPreview() async {
    setState(() => _isLoading = true);
    try {
      final resp = await http.get(Uri.parse('$apiBase/plan/preview?date=${_dateStr()}'));
      if (resp.statusCode == 200) {
        setState(() => _preview = jsonDecode(resp.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    setState(() => _isLoading = false);
  }

  Future<void> _buildPlan(int level) async {
    setState(() {
      _selectedLevel = level;
      _isBuilding = true;
    });
    try {
      final resp = await http.post(
          Uri.parse('$apiBase/plan/daily?date=${_dateStr()}&energy_level=$level'));
      if (resp.statusCode == 200) {
        setState(() => _plan = jsonDecode(resp.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    setState(() => _isBuilding = false);
  }

  Future<void> _changeDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime.now().subtract(const Duration(days: 30)),
      lastDate: DateTime.now().add(const Duration(days: 60)),
    );
    if (picked != null) {
      setState(() {
        _date = picked;
        _plan = null;
      });
      await _loadPreview();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('แพลนวันนี้'),
        actions: [
          IconButton(
            icon: const Icon(Icons.calendar_today),
            tooltip: 'เปลี่ยนวันที่',
            onPressed: _changeDate,
          ),
          ...buildStandardAppBarActions(context),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadPreview,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Text('${_date.year}-${_date.month.toString().padLeft(2, '0')}-${_date.day.toString().padLeft(2, '0')}',
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                  const SizedBox(height: 4),
                  if (_preview != null)
                    Text(
                      'เวลาว่างทั้งวัน ${_preview!['free_minutes']} นาที'
                      ' · มีคาบเรียน ${_preview!['class_count']} คาบ',
                      style: TextStyle(color: Colors.grey.shade700),
                    ),
                  const SizedBox(height: 16),
                  _sectionTitle('เลือกพลังวันนี้', Icons.bolt),
                  const SizedBox(height: 8),
                  if (_preview != null) _energyLevelSelector(),
                  const SizedBox(height: 16),
                  if (_plan != null) ...[
                    _sectionTitle('แพลนของคุณ', Icons.schedule),
                    const SizedBox(height: 8),
                    _planTimeline(),
                    const SizedBox(height: 16),
                  ],
                  const SizedBox(height: 16),
                  Text('ถ้าตารางเรียนเปลี่ยนหรือมีงานแทรก กลับมาเปิดหน้านี้อีกครั้ง '
                      'งานจะย้ายไปช่วงว่างให้อัตโนมัติ',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                ],
              ),
            ),
    );
  }

  Widget _sectionTitle(String title, IconData icon) {
    return Row(
      children: [
        Icon(icon, size: 20, color: Colors.black87),
        const SizedBox(width: 8),
        Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
      ],
    );
  }

  Widget _energyLevelSelector() {
    final levels = (_preview!['levels'] as List<dynamic>? ?? []);
    return Column(
      children: levels.map((lv) {
        final level = lv['energy_level'] as int;
        final tasks = (lv['tasks'] as List<dynamic>? ?? []);
        final totalEst = lv['total_est'] ?? 0;
        final selected = level == _selectedLevel;
        return Card(
          color: selected ? Colors.teal.shade50 : null,
          child: InkWell(
            onTap: () => _buildPlan(level),
            borderRadius: BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Row(
                children: [
                  Icon(selected ? Icons.bolt : Icons.bolt_outlined,
                      color: selected ? Colors.teal : Colors.grey),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('พลังระดับ $level — ได้งาน $totalEst นาที',
                            style: const TextStyle(fontWeight: FontWeight.bold)),
                        if (tasks.isEmpty)
                          Text('วันนี้ไม่มีงานพอสำหรับพลังระดับนี้',
                              style: TextStyle(fontSize: 12, color: Colors.grey.shade600))
                        else
                          Text(
                            tasks.map((t) => t['title']).take(3).join(' · '),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  if (_isBuilding && selected)
                    const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  else
                    const Icon(Icons.chevron_right),
                ],
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _planTimeline() {
    if (_plan == null) return const SizedBox.shrink();
    final schedules = (_plan!['schedules'] as List<dynamic>? ?? []);
    final taskSlots = (_plan!['task_slots'] as List<dynamic>? ?? []);
    final nextDay = (_plan!['next_day'] as Map<String, dynamic>? ?? {});
    final nextTasks = (nextDay['tasks'] as List<dynamic>? ?? []);

    final events = <Map<String, dynamic>>[
      ...schedules.map((s) => {
            'type': 'class',
            'start': s['start_time'] ?? '',
            'end': s['end_time'] ?? '',
            'label': '${s['subject'] ?? ''}${s['location'] != null ? ' (${s['location']})' : ''}',
          }),
      ...taskSlots.map((t) => {
            'type': 'task',
            'start': t['start_time'] ?? '',
            'end': t['end_time'] ?? '',
            'label': t['title'] ?? '',
          }),
    ]..sort((a, b) => (a['start'] as String).compareTo(b['start'] as String));

    if (events.isEmpty) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: Center(child: Text('วันนี้ไม่มีคาบเรียน และไม่มีงานที่จัดได้ — พักผ่อนได้เลย')),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ...events.map((e) {
          final isClass = e['type'] == 'class';
          return ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            leading: Icon(
              isClass ? Icons.school : Icons.check_circle_outline,
              color: isClass ? Colors.teal : Colors.deepPurple,
            ),
            title: Text(e['label'] ?? '',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: isClass ? Colors.teal.shade800 : Colors.black87,
                )),
            subtitle: Text('${e['start']} - ${e['end']}'),
          );
        }),
        if (nextTasks.isNotEmpty) ...[
          const SizedBox(height: 12),
          const Text('พรุ่งนี้แนะนำ', style: TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Text(
            nextTasks.map((t) => t['title']).join(' · '),
            style: TextStyle(color: Colors.grey.shade700),
          ),
        ],
      ],
    );
  }
}
