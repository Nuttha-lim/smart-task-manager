import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app_bar_actions.dart';
import 'routines_page.dart';
import 'api_config.dart';

/// Day Timeline — ไทม์ไลน์ของวันหนึ่ง ๆ: กิจวัตร + ตารางเรียน + งาน + วันหยุด
/// แตะวันในปฏิทินแล้วเปิดมาหน้านี้ (แทน bottom sheet เดิมที่อ่านยาก)
class DayTimelinePage extends StatefulWidget {
  const DayTimelinePage({super.key, required this.day, this.initialData});

  final DateTime day;
  final Map<String, dynamic>? initialData;

  @override
  State<DayTimelinePage> createState() => _DayTimelinePageState();
}

class _DayTimelinePageState extends State<DayTimelinePage> {
  static const Map<int, String> _dayNames = {
    1: 'จันทร์', 2: 'อังคาร', 3: 'พุธ', 4: 'พฤหัสบดี',
    5: 'ศุกร์', 6: 'เสาร์', 7: 'อาทิตย์',
  };
  static const Map<int, String> _energyEmoji = {
    1: '😴', 2: '😪', 3: '🙂', 4: '😃', 5: '🔥',
  };

  Map<String, dynamic>? _data;
  bool _isLoading = false;

  String get _dateStr => '${widget.day.year}-'
      '${widget.day.month.toString().padLeft(2, '0')}-'
      '${widget.day.day.toString().padLeft(2, '0')}';

  String get _monthStr => '${widget.day.year}-'
      '${widget.day.month.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    _data = widget.initialData;
    if (_data == null) _fetch();
  }

  Future<void> _fetch() async {
    setState(() => _isLoading = true);
    try {
      final resp = await http.get(
          Uri.parse('$apiBase/calendar?month=$_monthStr'));
      if (resp.statusCode == 200 && mounted) {
        setState(() => _data = jsonDecode(resp.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    if (mounted) setState(() => _isLoading = false);
  }

  Future<void> _openRoutines() async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => const RoutinesPage()),
    );
    if (changed == true && mounted) {
      _fetch(); // กิจวัตรเปลี่ยน → โหลดใหม่ให้ timeline ตรง
    }
  }

  // ---------- ข้อมูลของวัน ----------

  List<dynamic> _holidays() => (_data?['holidays'] as List<dynamic>? ?? [])
      .where((h) => h['date'] == _dateStr)
      .toList();

  List<dynamic> _tasks() => (_data?['tasks'] as List<dynamic>? ?? [])
      .where((t) => t['date'] == _dateStr)
      .toList();

  List<dynamic> _schedules() {
    final cancels = _cancellations();
    final list = (_data?['schedules'] as List<dynamic>? ?? [])
        .where((s) => s is Map && s['day_of_week'] == widget.day.weekday)
        .cast<Map<String, dynamic>>();
    return list.map((s) {
      final cancelled = cancels.any((c) => _overlaps(
            s['start_time']?.toString() ?? '',
            s['end_time']?.toString() ?? '',
            c['start_time']?.toString() ?? '00:00',
            c['end_time']?.toString() ?? '23:59',
          ));
      return {...s, 'cancelled': cancelled};
    }).toList();
  }

  List<dynamic> _cancellations() =>
      (_data?['cancellations'] as List<dynamic>? ?? [])
          .where((c) => c['date'] == _dateStr)
          .toList();

  static bool _overlaps(String sStart, String sEnd, String cStart, String cEnd) {
    int toMin(String t) {
      final parts = t.split(':');
      if (parts.length != 2) return 0;
      return (int.tryParse(parts[0]) ?? 0) * 60 + (int.tryParse(parts[1]) ?? 0);
    }

    final a = toMin(sStart), b = toMin(sEnd), c = toMin(cStart), d = toMin(cEnd);
    return a < d && c < b;
  }

  List<dynamic> _routines() => (_data?['routines'] as List<dynamic>? ?? [])
      .where((r) => r['enabled'] == true)
      .toList();

  int? get _energy {
    for (final e in _data?['energy_logs'] as List<dynamic>? ?? []) {
      if (e['date'] == _dateStr) return e['energy_level'] as int?;
    }
    return null;
  }

  bool get _isEmpty =>
      _holidays().isEmpty &&
      _tasks().isEmpty &&
      _schedules().isEmpty &&
      _routines().isEmpty &&
      _energy == null;

  // ---------- build ----------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('${_dayNames[widget.day.weekday]}  $_dateStr'),
        actions: [
          IconButton(
            icon: const Icon(Icons.alarm),
            tooltip: 'จัดการกิจวัตร',
            onPressed: _openRoutines,
          ),
          ...buildStandardAppBarActions(context),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _fetch,
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  _header(),
                  const SizedBox(height: 8),
                  if (_isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(
                        child: Text('วันนี้ไม่มีอะไรเลย — พักผ่อนได้เต็มที่',
                            style: TextStyle(color: Colors.grey)),
                      ),
                    )
                  else
                    ..._timelineItems(),
                  const SizedBox(height: 12),
                ],
              ),
            ),
    );
  }

  Widget _header() {
    final energy = _energy;
    final holidays = _holidays();
    return Card(
      elevation: 0,
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(_dateStr,
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                if (energy != null)
                  Text('${_energyEmoji[energy]} พลังงาน $_energy',
                      style: const TextStyle(fontSize: 14)),
              ],
            ),
            if (holidays.isNotEmpty)
              ...holidays.map((h) => Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text('🏖 ${h['name']}',
                        style: const TextStyle(
                            color: Colors.red, fontWeight: FontWeight.w600)),
                  )),
          ],
        ),
      ),
    );
  }

  List<Widget> _timelineItems() {
    final items = <_TimelineItem>[];

    // กิจวัตร (ทุกวัน)
    for (final r in _routines()) {
      items.add(_TimelineItem(
        time: r['time']?.toString() ?? '',
        title: r['title']?.toString() ?? '',
        subtitle: r['description']?.toString() ?? 'กิจวัตร',
        icon: Icons.alarm_on,
        color: Colors.indigo,
      ));
    }
    // ตารางเรียน (ตามวัน) — คาบที่ยกเลิกเฉพาะวันแสดงเป็นสีเทา/ขีดฆ่า
    for (final s in _schedules()) {
      final cancelled = s['cancelled'] == true;
      items.add(_TimelineItem(
        time: s['start_time']?.toString() ?? '',
        title: s['subject']?.toString() ?? '',
        subtitle: cancelled
            ? 'ยกเลิกคาบนี้ (${s['start_time']} – ${s['end_time']})'
            : '${s['start_time']} – ${s['end_time']}'
                '${s['location'] != null ? ' · ${s['location']}' : ''}',
        icon: cancelled ? Icons.event_busy : Icons.school,
        color: cancelled ? Colors.grey : Colors.teal,
        cancelled: cancelled,
      ));
    }
    // งาน (ตามวัน)
    for (final t in _tasks()) {
      items.add(_TimelineItem(
        time: t['deadline_time']?.toString() ?? '',
        title: t['title']?.toString() ?? '',
        subtitle: t['status'] == 'DONE'
            ? 'เสร็จแล้ว ✓'
            : 'กำหนดส่ง ${t['deadline_time'] ?? ''}',
        icon: Icons.task_alt,
        color: Colors.deepPurple,
        done: t['status'] == 'DONE',
      ));
    }

    // เรียงตามเวลา (เร็วก่อน); รายการไร้เวลาไปท้ายสุด
    items.sort((a, b) {
      if (a.time.isEmpty) return 1;
      if (b.time.isEmpty) return -1;
      return a.time.compareTo(b.time);
    });

    return items.map((item) => _timelineRow(item)).toList();
  }

  Widget _timelineRow(_TimelineItem item) {
    final color = item.done ? Colors.green : (item.cancelled ? Colors.grey : item.color);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // เวลา
        SizedBox(
          width: 54,
          child: Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
              item.time.isEmpty ? '' : item.time,
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ),
        ),
        // เส้น timeline + จุด
        SizedBox(
          width: 24,
          child: Column(
            children: [
              Container(
                margin: const EdgeInsets.only(top: 12),
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: color,
                  shape: BoxShape.circle,
                ),
              ),
              Container(width: 2, height: 46, color: color.withValues(alpha: 0.25)),
            ],
          ),
        ),
        // การ์ด
        Expanded(
          child: Card(
            elevation: 0,
            margin: const EdgeInsets.only(bottom: 10),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
              side: BorderSide(color: color.withValues(alpha: 0.3)),
            ),
            child: ListTile(
              dense: true,
              leading: Icon(item.icon, color: color),
              title: Text(
                item.title,
                style: (item.done || item.cancelled)
                    ? const TextStyle(
                        decoration: TextDecoration.lineThrough,
                        color: Colors.grey)
                    : null,
              ),
              subtitle: Text(item.subtitle,
                  style: const TextStyle(fontSize: 12)),
            ),
          ),
        ),
      ],
    );
  }
}

class _TimelineItem {
  _TimelineItem({
    required this.time,
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.color,
    this.done = false,
    this.cancelled = false,
  });
  final String time;
  final String title;
  final String subtitle;
  final IconData icon;
  final Color color;
  final bool done;
  final bool cancelled;
}
