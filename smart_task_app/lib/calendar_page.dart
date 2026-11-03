import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app_bar_actions.dart';
import 'day_timeline_page.dart';
import 'timetable_page.dart';
import 'holiday_notifier.dart';
import 'api_config.dart';

/// Calendar Overview — ปฏิทินรายเดือนรวม: งาน + พลังงาน + วันหยุด + ตารางเรียน
class CalendarPage extends StatefulWidget {
  const CalendarPage({super.key});

  @override
  State<CalendarPage> createState() => _CalendarPageState();
}

class _CalendarPageState extends State<CalendarPage> {
  static const List<String> _weekdayHeaders = ['จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา'];
  static const Map<int, String> _energyEmoji = {
    1: '😴', 2: '😪', 3: '🙂', 4: '😃', 5: '🔥',
  };

  late DateTime _current;
  bool _isLoading = true;
  Map<String, dynamic>? _data;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _current = DateTime(now.year, now.month);
    HolidayNotifier.instance.addListener(_onHolidaySettingChanged);
    _fetch();
  }

  @override
  void dispose() {
    HolidayNotifier.instance.removeListener(_onHolidaySettingChanged);
    super.dispose();
  }

  void _onHolidaySettingChanged() {
    if (mounted) _fetch();
  }

  Future<void> _fetch() async {
    setState(() => _isLoading = true);
    final monthStr =
        '${_current.year}-${_current.month.toString().padLeft(2, '0')}';
    try {
      final resp = await http.get(Uri.parse('$apiBase/calendar?month=$monthStr'));
      if (resp.statusCode == 200) {
        setState(() => _data = jsonDecode(resp.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    if (mounted) setState(() => _isLoading = false);
  }

  void _changeMonth(int delta) {
    setState(() {
      _current = DateTime(_current.year, _current.month + delta, 1);
    });
    _fetch();
  }

  Future<void> _openTimetable() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (context) => const TimetablePage()),
    );
    _fetch(); // กลับมาแล้วดึงตารางเรียนล่าสุด
  }

  // ---------- ข้อมูลของวันหนึ่ง ๆ ----------

  List<dynamic> _tasksOn(String dateStr) =>
      (_data?['tasks'] as List<dynamic>? ?? [])
          .where((t) => t['date'] == dateStr)
          .toList();

  List<dynamic> _holidaysOn(String dateStr) =>
      (_data?['holidays'] as List<dynamic>? ?? [])
          .where((h) => h['date'] == dateStr)
          .toList();

  int? _energyOn(String dateStr) {
    for (final e in _data?['energy_logs'] as List<dynamic>? ?? []) {
      if (e['date'] == dateStr) return e['energy_level'] as int?;
    }
    return null;
  }

  List<dynamic> _schedulesOnDay(DateTime date) {
    final dateStr = '${date.year}-${date.month.toString().padLeft(2, '0')}-'
        '${date.day.toString().padLeft(2, '0')}';
    final cancels = (_data?['cancellations'] as List<dynamic>? ?? [])
        .where((c) => c['date'] == dateStr)
        .toList();
    return (_data?['schedules'] as List<dynamic>? ?? [])
        .where((s) {
      if (s['day_of_week'] != date.weekday) return false;
      final sStart = s['start_time']?.toString() ?? '';
      final sEnd = s['end_time']?.toString() ?? '';
      // คาบที่โดนยกเลิกเฉพาะวันนั้น ไม่นับขึ้นในกริด
      return !cancels.any((c) => _overlaps(
            sStart,
            sEnd,
            c['start_time']?.toString() ?? '00:00',
            c['end_time']?.toString() ?? '23:59',
          ));
    }).toList();
  }

  static bool _overlaps(String sStart, String sEnd, String cStart, String cEnd) {
    int toMin(String t) {
      final parts = t.split(':');
      if (parts.length != 2) return 0;
      return (int.tryParse(parts[0]) ?? 0) * 60 + (int.tryParse(parts[1]) ?? 0);
    }

    final a = toMin(sStart), b = toMin(sEnd), c = toMin(cStart), d = toMin(cEnd);
    return a < d && c < b;
  }

  int get _activeRoutineCount =>
      (_data?['routines'] as List<dynamic>? ?? [])
          .where((r) => r['enabled'] == true)
          .length;

  // ---------- build ----------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('ปฏิทิน'),
        actions: [
          IconButton(
            icon: const Icon(Icons.schedule),
            tooltip: 'ตารางเรียน',
            onPressed: _openTimetable,
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
                  Row(
                    children: [
                      IconButton(
                        icon: const Icon(Icons.chevron_left),
                        onPressed: () => _changeMonth(-1),
                      ),
                      Expanded(
                        child: Text(
                          _monthLabel(),
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.bold),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.chevron_right),
                        onPressed: () => _changeMonth(1),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: _weekdayHeaders
                        .map((d) => Expanded(
                              child: Text(d,
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      color: Colors.grey.shade700)),
                            ))
                        .toList(),
                  ),
                  const SizedBox(height: 4),
                  _buildGrid(),
                  const SizedBox(height: 8),
                  _legend(),
                ],
              ),
            ),
    );
  }

  String _monthLabel() {
    const thaiMonths = [
      'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
      'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
    ];
    return '${thaiMonths[_current.month - 1]} ${_current.year + 543}';
  }

  Widget _buildGrid() {
    final first = DateTime(_current.year, _current.month, 1);
    final daysInMonth = DateTime(_current.year, _current.month + 1, 0).day;
    final leading = first.weekday - 1; // จันทร์=1 → 0 ช่องว่าง
    final cells = <Widget>[];

    for (var i = 0; i < leading; i++) {
      cells.add(const SizedBox(height: 64));
    }
    for (var day = 1; day <= daysInMonth; day++) {
      cells.add(_dayCell(DateTime(_current.year, _current.month, day)));
    }
    return Column(
      children: [
        for (var row = 0; row < cells.length / 7; row++)
          Row(
            children: [
              for (var col = 0; col < 7; col++)
                Expanded(
                  child: (row * 7 + col) < cells.length
                      ? cells[row * 7 + col]
                      : const SizedBox(height: 64),
                ),
            ],
          ),
      ],
    );
  }

  Widget _dayCell(DateTime date) {
    final dateStr = '${date.year}-${date.month.toString().padLeft(2, '0')}-'
        '${date.day.toString().padLeft(2, '0')}';
    final holidays = _holidaysOn(dateStr);
    final isHoliday = holidays.isNotEmpty;
    final tasks = _tasksOn(dateStr);
    final schedules = _schedulesOnDay(date);
    final energy = _energyOn(dateStr);
    final isToday = dateStr == _todayStr();

    return GestureDetector(
      onTap: () => _openDayTimeline(date),
      child: Container(
        margin: const EdgeInsets.all(2),
        height: 60,
        decoration: BoxDecoration(
          color: isToday ? Colors.amber.shade100 : Colors.grey.shade50,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(
            color: isToday ? Colors.amber : Colors.black12,
            width: isToday ? 1.5 : 1,
          ),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(left: 4, top: 2),
              child: Text(
                '${date.day}${isHoliday ? ' 🏖' : ''}',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: isHoliday ? FontWeight.bold : FontWeight.normal,
                  color: isHoliday ? Colors.red : Colors.black87,
                ),
              ),
            ),
            if (energy != null)
              Padding(
                padding: const EdgeInsets.only(left: 4),
                child: Text(_energyEmoji[energy] ?? '', style: const TextStyle(fontSize: 10)),
              ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  if (tasks.isNotEmpty)
                    _dot(Colors.deepPurple, tasks.length),
                  if (schedules.isNotEmpty)
                    _dot(Colors.teal, schedules.length),
                  if (_activeRoutineCount > 0)
                    _dot(Colors.indigo, _activeRoutineCount),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _dot(Color color, int count) {
    return Padding(
      padding: const EdgeInsets.only(left: 2),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(8)),
        child: Text('$count',
            style: const TextStyle(color: Colors.white, fontSize: 9)),
      ),
    );
  }

  Widget _legend() {
    return Wrap(
      spacing: 16,
      runSpacing: 4,
      children: const [
        _LegendItem(Icons.circle, Colors.deepPurple, 'งาน'),
        _LegendItem(Icons.circle, Colors.teal, 'ตารางเรียน'),
        _LegendItem(Icons.alarm_on, Colors.indigo, 'กิจวัตร'),
        _LegendItem(Icons.spa, Colors.red, 'วันหยุด'),
      ],
    );
  }

  String _todayStr() {
    final n = DateTime.now();
    return '${n.year}-${n.month.toString().padLeft(2, '0')}-'
        '${n.day.toString().padLeft(2, '0')}';
  }

  void _openDayTimeline(DateTime date) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => DayTimelinePage(day: date, initialData: _data),
      ),
    );
    _fetch(); // กลับมาจาก timeline → โหลดใหม่ (กิจวัตรอาจเปลี่ยน)
  }
}

class _LegendItem extends StatelessWidget {
  const _LegendItem(this.icon, this.color, this.label);
  final IconData icon;
  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: color, size: 10),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 12)),
      ],
    );
  }
}
