import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app_bar_actions.dart';
import 'task_review_dialog.dart';
import 'tasks_notifier.dart';
import 'api_config.dart';

/// Travel Planning — ให้ AI วางแผนทริป (ตารางวันต่อวัน + งานเตรียมตัว)
/// ผู้ใช้ตรวจแผนก่อน → ยืนยัน → สร้างงานเตรียมตัวจริง + เก็บแผนไว้ดู
class TravelPage extends StatefulWidget {
  const TravelPage({super.key});

  @override
  State<TravelPage> createState() => _TravelPageState();
}

class _TravelPageState extends State<TravelPage> {
  final TextEditingController _destinationController = TextEditingController();
  final TextEditingController _notesController = TextEditingController();

  DateTime? _startDate;
  DateTime? _endDate;

  bool _isPlanning = false;
  bool _isSaving = false;
  Map<String, dynamic>? _plan;

  List<dynamic> _savedPlans = [];
  bool _isLoadingPlans = true;

  @override
  void initState() {
    super.initState();
    _fetchSavedPlans();
  }

  @override
  void dispose() {
    _destinationController.dispose();
    _notesController.dispose();
    super.dispose();
  }

  String _fmtDate(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> _pickStart() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _startDate ?? now,
      firstDate: now.subtract(const Duration(days: 30)),
      lastDate: now.add(const Duration(days: 730)),
    );
    if (picked != null) {
      setState(() {
        _startDate = picked;
        if (_endDate == null || _endDate!.isBefore(picked)) {
          _endDate = picked;
        }
      });
    }
  }

  Future<void> _pickEnd() async {
    final now = DateTime.now();
    final first = _startDate ?? now;
    final picked = await showDatePicker(
      context: context,
      initialDate: (_endDate != null && !_endDate!.isBefore(first)) ? _endDate! : first,
      firstDate: first,
      lastDate: first.add(const Duration(days: 730)),
    );
    if (picked != null) setState(() => _endDate = picked);
  }

  Future<void> _planTrip() async {
    final destination = _destinationController.text.trim();
    if (destination.isEmpty) {
      _showSnack('กรอกปลายทางก่อน');
      return;
    }
    if (_startDate == null || _endDate == null) {
      _showSnack('เลือกวันเดินทางก่อน');
      return;
    }

    setState(() {
      _isPlanning = true;
      _plan = null;
    });

    final notes = _notesController.text.trim();
    final url = Uri.parse(
        '$apiBase/travel/plan?destination=${Uri.encodeComponent(destination)}'
        '&start_date=${_fmtDate(_startDate!)}&end_date=${_fmtDate(_endDate!)}'
        '&notes=${Uri.encodeComponent(notes)}');
    try {
      final resp = await http.post(url);
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        setState(() => _plan = data);
        if (data['error'] != null) _showSnack(data['error'].toString());
      }
    } catch (e) {
      _showSnack('เชื่อมต่อ backend ไม่ได้ — $e');
    }
    if (mounted) setState(() => _isPlanning = false);
  }

  Future<void> _confirmAndSave() async {
    final plan = _plan;
    if (plan == null) return;

    final prepTasks = (plan['prep_tasks'] as List<dynamic>? ?? [])
        .map((t) => (t as Map).cast<String, dynamic>())
        .toList();

    setState(() => _isSaving = true);
    final confirmed = await showDialog<List<Map<String, dynamic>>>(
      context: context,
      barrierDismissible: false,
      builder: (_) => TaskReviewDialog(
        title: 'ตรวจงานเตรียมตัวก่อนยืนยัน',
        subtitle: 'ทริป ${plan['destination']} (${plan['start_date']} → ${plan['end_date']})',
        summary: 'งานเตรียมตัวเหล่านี้จะถูกสร้างเป็นงานจริงพร้อมกำหนดส่ง',
        tasks: prepTasks,
      ),
    );
    if (confirmed == null || !mounted) {
      if (mounted) setState(() => _isSaving = false);
      return;
    }

    try {
      final resp = await http.post(
        Uri.parse(
            '$apiBase/travel?destination=${Uri.encodeComponent(plan['destination'] ?? '')}'
            '&start_date=${plan['start_date']}&end_date=${plan['end_date']}'
            '&notes=${Uri.encodeComponent((plan['notes'] ?? '').toString())}'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'days': plan['days'] ?? [],
          'prep_tasks': confirmed,
        }),
      );
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        final created = (data['created_tasks'] as List<dynamic>? ?? []).length;
        _showSnack('บันทึกแผนทริปแล้ว + สร้างงานเตรียมตัว $created รายการ');
        TasksNotifier.instance.changed();
        setState(() {
          _plan = null;
          _destinationController.clear();
          _notesController.clear();
          _startDate = null;
          _endDate = null;
        });
        await _fetchSavedPlans();
      }
    } catch (e) {
      _showSnack('บันทึกไม่สำเร็จ: $e');
    }
    if (mounted) setState(() => _isSaving = false);
  }

  Future<void> _fetchSavedPlans() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/travel'));
      if (resp.statusCode == 200) {
        setState(() => _savedPlans = jsonDecode(resp.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    if (mounted) setState(() => _isLoadingPlans = false);
  }

  Future<void> _deletePlan(String id) async {
    try {
      await http.delete(Uri.parse('$apiBase/travel/$id'));
      await _fetchSavedPlans();
    } catch (e) {
      _showSnack('ลบไม่สำเร็จ: $e');
    }
  }

  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('วางแผนทริป'),
        actions: buildStandardAppBarActions(context),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'บอกปลายทาง + วันเดินทาง แล้วให้ AI วางแผนทริปเป็นวันต่อวัน '
            'พร้อมงานเตรียมตัว (จองตั๋ว เตรียมของ) ให้อัตโนมัติ',
            style: TextStyle(color: Colors.grey.shade700),
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  TextField(
                    controller: _destinationController,
                    decoration: const InputDecoration(
                      labelText: 'ปลายทาง',
                      hintText: 'เช่น เชียงใหม่, โตเกียว',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: _dateField('วันแรก', _startDate, _pickStart),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _dateField('วันสุดท้าย', _endDate, _pickEnd),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _notesController,
                    decoration: const InputDecoration(
                      labelText: 'รายละเอียดเพิ่มเติม (ไม่บังคับ)',
                      hintText: 'เช่น เที่ยวพักผ่อน เน้นธรรมชาติ',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      icon: _isPlanning
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.auto_awesome),
                      label: Text(_isPlanning ? 'กำลังวางแผน...' : 'ให้ AI วางแผนทริป'),
                      onPressed: _isPlanning ? null : _planTrip,
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (_plan != null) ...[
            const SizedBox(height: 16),
            if (_plan!['error'] != null)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(_plan!['error'].toString(),
                      style: const TextStyle(color: Colors.red)),
                ),
              )
            else ...[
              Text('แผนทริป ${_plan!['destination']} '
                  '(${(_plan!['days'] as List).length} วัน)',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(height: 8),
              ...(_plan!['days'] as List<dynamic>).map((d) => Card(
                    margin: const EdgeInsets.only(bottom: 6),
                    child: ExpansionTile(
                      leading: const Icon(Icons.calendar_today, color: Colors.teal),
                      title: Text('${d['date']} — ${d['title'] ?? ''}'),
                      children: (d['items'] as List<dynamic>? ?? [])
                          .map<Widget>((item) => ListTile(
                                dense: true,
                                contentPadding: const EdgeInsets.symmetric(horizontal: 20),
                                leading: const Icon(Icons.check_circle_outline,
                                    size: 16, color: Colors.teal),
                                title: Text(item.toString()),
                              ))
                          .toList(),
                    ),
                  )),
              const SizedBox(height: 12),
              Text('งานเตรียมตัว ${(_plan!['prep_tasks'] as List).length} อย่าง',
                  style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 4),
              ...(_plan!['prep_tasks'] as List<dynamic>).map((t) => ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.task_alt, color: Colors.deepPurple),
                    title: Text(t['title']?.toString() ?? ''),
                    subtitle: Text([
                      if (t['deadline'] != null) 'ทำก่อน ${t['deadline']}',
                      if (t['estimated_time'] != null) '~${t['estimated_time']} นาที',
                    ].join(' · ')),
                  )),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  icon: _isSaving
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.check),
                  label: Text(_isSaving ? 'กำลังบันทึก...' : 'ตรวจและยืนยันแผนทริป'),
                  onPressed: _isSaving ? null : _confirmAndSave,
                ),
              ),
            ],
          ],
          const SizedBox(height: 24),
          const Divider(),
          const Text('แผนทริปที่บันทึกไว้',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          const SizedBox(height: 8),
          if (_isLoadingPlans)
            const Center(child: CircularProgressIndicator())
          else if (_savedPlans.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Center(child: Text('ยังไม่มีแผนทริปที่บันทึกไว้')),
              ),
            )
          else
            ..._savedPlans.map((p) => Card(
                  margin: const EdgeInsets.only(bottom: 8),
                  child: ExpansionTile(
                    leading: const Icon(Icons.flight_takeoff, color: Colors.teal),
                    title: Text(p['destination']?.toString() ?? ''),
                    subtitle: Text(
                        '${p['start_date'] ?? '?'} → ${p['end_date'] ?? '?'}'
                        ' · งานเตรียมตัว ${(p['prep_tasks'] as List).length} อย่าง'),
                    trailing: IconButton(
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () => _deletePlan(p['id']),
                      tooltip: 'ลบแผนนี้',
                    ),
                    children: [
                      ...(p['days'] as List<dynamic>).map((d) => ListTile(
                            dense: true,
                            contentPadding: const EdgeInsets.symmetric(horizontal: 20),
                            title: Text(
                                '${d['date']} — ${d['title'] ?? ''}',
                                style: const TextStyle(fontWeight: FontWeight.w600)),
                            subtitle: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: (d['items'] as List<dynamic>? ?? [])
                                  .map<Widget>((item) => Text('• $item'))
                                  .toList(),
                            ),
                          )),
                    ],
                  ),
                )),
        ],
      ),
    );
  }

  Widget _dateField(String label, DateTime? value, VoidCallback onTap) {
    return InkWell(
      onTap: onTap,
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
          isDense: true,
        ),
        child: Row(
          children: [
            const Icon(Icons.event, size: 18),
            const SizedBox(width: 8),
            Text(value == null ? 'เลือกวันที่' : _fmtDate(value)),
          ],
        ),
      ),
    );
  }
}
