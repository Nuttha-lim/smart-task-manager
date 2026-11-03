import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import 'app_bar_actions.dart';
import 'history_page.dart';
import 'travel_page.dart';
import 'goals_page.dart';
import 'push_service.dart';
import 'holiday_notifier.dart';
import 'api_config.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  double _offsetHours = 7.0;
  bool _isLoading = true;
  bool _isSaving = false;

  bool _nudgeEnabled = true;
  List<String> _nudgeTimes = [];
  bool _nudgeLoaded = false;

  bool _pushEnabled = false;

  bool _holidaysEnabled = true;

  final Map<double, String> _commonZones = {
    -8.0: 'Los Angeles (UTC-8)',
    -5.0: 'New York (UTC-5)',
    0.0: 'London (UTC+0)',
    1.0: 'Berlin (UTC+1)',
    7.0: 'Bangkok (UTC+7)',
    8.0: 'Singapore/China (UTC+8)',
    9.0: 'Tokyo/Korea (UTC+9)',
  };

  @override
  void initState() {
    super.initState();
    _fetchOffset();
    _loadNudge();
    _loadPush();
    _loadHolidays();
  }

  // ---------- วันหยุดในปฏิทิน (แต่ละประเทศไม่เหมือนกัน — เปิด/ปิดได้) ----------

  Future<void> _loadHolidays() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/settings/holidays'));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        setState(() => _holidaysEnabled = data['enabled'] == true);
      }
    } catch (e) {
      // เงียบไว้ก่อน — default เปิด
    }
  }

  Future<void> _toggleHolidays(bool value) async {
    setState(() => _holidaysEnabled = value);
    try {
      await http.post(Uri.parse('$apiBase/settings/holidays?enabled=$value'));
      HolidayNotifier.instance.changed(); // ให้ Calendar โหลดใหม่ตาม setting
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(value ? 'แสดงวันหยุดในปฏิทินแล้ว' : 'ซ่อนวันหยุดในปฏิทินแล้ว'),
          ),
        );
      }
    } catch (e) {
      setState(() => _holidaysEnabled = !value);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('บันทึกไม่สำเร็จ: $e')),
        );
      }
    }
  }

  // ---------- Push notification (Web Push / VAPID) ----------

  void _loadPush() {
    setState(() => _pushEnabled = PushService.isEnabled());
  }

  Future<void> _togglePush(bool value) async {
    if (value) {
      final ok = await PushService.requestSubscribe();
      if (!mounted) return;
      if (ok) {
        setState(() => _pushEnabled = true);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('เปิดการแจ้งเตือนแล้ว — งานด่วนจะส่งมาให้ถึงเบราว์เซอร์')),
        );
      } else {
        setState(() => _pushEnabled = false);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('เปิดไม่สำเร็จ — กรุณาอนุญาตการแจ้งเตือนในเบราว์เซอร์ก่อน')),
        );
      }
    } else {
      await PushService.unsubscribe();
      if (!mounted) return;
      setState(() => _pushEnabled = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('ปิดการแจ้งเตือนแล้ว')),
      );
    }
  }

  Future<void> _fetchOffset() async {
    setState(() => _isLoading = true);
    try {
      final response = await http.get(Uri.parse('$apiBase/settings/timezone'));
      final data = jsonDecode(response.body);
      setState(() => _offsetHours = (data['offset_hours'] as num).toDouble());
    } catch (e) {
      // เงียบไว้ก่อน
    }
    setState(() => _isLoading = false);
  }

  Future<void> _saveOffset(double offset) async {
    setState(() => _isSaving = true);
    try {
      await http.post(Uri.parse('$apiBase/settings/timezone?offset_hours=$offset'));
      setState(() => _offsetHours = offset);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('บันทึกเขตเวลาแล้ว')),
        );
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

  Future<void> _useDeviceTimezone() async {
    final offsetMinutes = -DateTime.now().timeZoneOffset.inMinutes;
    final offsetHours = offsetMinutes / 60.0;
    await _saveOffset(offsetHours);
  }

  // ---------- Nudge (ย้ายมาจากหน้า gamification) ----------

  Future<void> _loadNudge() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/settings/nudge'));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        setState(() {
          _nudgeEnabled = data['enabled'] == true;
          _nudgeTimes = (data['times'] as List<dynamic>? ?? []).cast<String>();
          _nudgeLoaded = true;
        });
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  Future<void> _saveNudge() async {
    try {
      final timesJson = jsonEncode(_nudgeTimes);
      await http.post(Uri.parse(
          '$apiBase/settings/nudge?enabled=$_nudgeEnabled&times=${Uri.encodeComponent(timesJson)}'));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('บันทึกการแจ้งเตือนกระตุ้นแล้ว')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('บันทึกไม่สำเร็จ: $e')),
        );
      }
    }
  }

  Future<void> _editNudgeTimes() async {
    final controller = TextEditingController(text: _nudgeTimes.join(', '));
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('เวลาที่อยากให้เตือนเบา ๆ'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('คั่นด้วยลูกน้ำ เช่น 09:00, 15:00, 20:00'),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              keyboardType: TextInputType.datetime,
              decoration: const InputDecoration(
                labelText: 'เวลา (HH:MM)',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('ยกเลิก'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('บันทึก'),
          ),
        ],
      ),
    );
    if (result == null) return;
    setState(() {
      _nudgeTimes = result
          .split(',')
          .map((t) => t.trim())
          .where((t) => RegExp(r'^\d{2}:\d{2}$').hasMatch(t))
          .toList()
        ..sort();
    });
    await _saveNudge();
  }

  void _push(Widget page) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => page));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('ตั้งค่า'),
        actions: buildStandardAppBarActions(context),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _sectionTitle('พื้นที่ของฉัน', Icons.folder_outlined),
                const SizedBox(height: 8),
                Card(
                  child: Column(
                    children: [
                      ListTile(
                        leading: const Icon(Icons.flag_outlined),
                        title: const Text('เป้าหมายระยะยาว'),
                        subtitle: const Text('แตกเป้าหมาย/เตรียมสอบ + จัดตารางเตรียมถึงวันเป้าหมาย'),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => _push(const GoalsPage()),
                      ),
                      ListTile(
                        leading: const Icon(Icons.history),
                        title: const Text('ประวัติงานทั้งหมด'),
                        subtitle: const Text('ดูงานที่ทำไปแล้ว + กดผิด/ยังไม่เสร็จได้'),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => _push(const HistoryPage()),
                      ),
                      ListTile(
                        leading: const Icon(Icons.flight_takeoff),
                        title: const Text('วางแผนทริป'),
                        subtitle: const Text('AI จัดตารางเที่ยววันต่อวัน + งานเตรียมตัว'),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => _push(const TravelPage()),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                _sectionTitle('ปฏิทิน', Icons.calendar_month),
                const SizedBox(height: 4),
                const Text('วันหยุดของแต่ละประเทศ/ปีไม่เหมือนกัน — ปิดได้ถ้าไม่อยากเห็น',
                    style: TextStyle(fontSize: 12, color: Colors.grey)),
                const SizedBox(height: 8),
                Card(
                  child: SwitchListTile(
                    title: const Text('แสดงวันหยุดในปฏิทิน'),
                    subtitle: const Text('เช่น วันแม่ 12 ส.ค., วันขึ้นปีใหม่ — พักผ่อน/ไม่กดดัน',
                        style: TextStyle(fontSize: 12)),
                    value: _holidaysEnabled,
                    onChanged: _toggleHolidays,
                  ),
                ),
                const SizedBox(height: 24),
                _sectionTitle('Push Notification', Icons.notifications),
                const SizedBox(height: 4),
                const Text('แจ้งเตือนไปถึงเบราว์เซอร์แม้ปิดแอป (งานด่วน/เลยกำหนด)',
                    style: TextStyle(fontSize: 12, color: Colors.grey)),
                const SizedBox(height: 8),
                Card(
                  child: SwitchListTile(
                    title: const Text('เปิดรับการแจ้งเตือน Push'),
                    subtitle: const Text('แอปจะขอสิทธิ์แจ้งเตือนจากเบราว์เซอร์ — ปิดได้ทุกเมื่อ'),
                    value: _pushEnabled,
                    onChanged: _togglePush,
                  ),
                ),
                const SizedBox(height: 24),
                _sectionTitle('การแจ้งเตือนกระตุ้น (Nudge)', Icons.notifications_active),
                const SizedBox(height: 4),
                const Text('เตือนเบา ๆ ให้เริ่มทำ ไม่บังคับ — ปิดวันไหนได้เอง',
                    style: TextStyle(fontSize: 12, color: Colors.grey)),
                const SizedBox(height: 8),
                if (!_nudgeLoaded)
                  const Card(child: Padding(padding: EdgeInsets.all(16), child: Center(child: Text('กำลังโหลด...'))))
                else
                  Card(
                    child: Column(
                      children: [
                        SwitchListTile(
                          title: const Text('เปิดใช้การแจ้งเตือนกระตุ้น'),
                          subtitle: const Text('เตือนเบา ๆ ให้เริ่มทำ ไม่บังคับ'),
                          value: _nudgeEnabled,
                          onChanged: (value) {
                            setState(() => _nudgeEnabled = value);
                            _saveNudge();
                          },
                        ),
                        ListTile(
                          leading: const Icon(Icons.schedule),
                          title: const Text('เวลาที่อยากให้เตือน'),
                          subtitle: Text(_nudgeTimes.isEmpty
                              ? 'ยังไม่ตั้งเวลา'
                              : _nudgeTimes.join(', ')),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: _nudgeEnabled ? _editNudgeTimes : null,
                        ),
                      ],
                    ),
                  ),
                const SizedBox(height: 24),
                _sectionTitle('เขตเวลา (Timezone)', Icons.schedule),
                const SizedBox(height: 4),
                Text('ปัจจุบัน: UTC${_offsetHours >= 0 ? '+' : ''}${_offsetHours.toStringAsFixed(1)}',
                    style: TextStyle(color: Colors.grey.shade700)),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.my_location),
                    label: const Text('ใช้เขตเวลาของอุปกรณ์นี้'),
                    onPressed: _isSaving ? null : _useDeviceTimezone,
                  ),
                ),
                const SizedBox(height: 20),
                const Text('หรือเลือกเขตเวลาที่ใช้บ่อย',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                ..._commonZones.entries.map((entry) => RadioListTile<double>(
                      value: entry.key,
                      groupValue: _offsetHours,
                      title: Text(entry.value,
                          style: const TextStyle(color: Colors.black87)),
                      activeColor: Colors.black87,
                      selectedTileColor: Colors.black12,
                      contentPadding:
                          const EdgeInsets.symmetric(horizontal: 0, vertical: 2),
                      onChanged: _isSaving
                          ? null
                          : (value) {
                              if (value != null) _saveOffset(value);
                            },
                    )),
                const SizedBox(height: 12),
              ],
            ),
    );
  }

  Widget _sectionTitle(String title, IconData icon) {
    return Row(
      children: [
        Icon(icon, size: 20, color: Colors.black87),
        const SizedBox(width: 8),
        Text(title,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
      ],
    );
  }
}
