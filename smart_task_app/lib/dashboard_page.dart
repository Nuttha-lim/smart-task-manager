import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:async';
import 'dart:convert';
import 'notification_service.dart';
import 'notifications_page.dart';
import 'task_detail_page.dart';
import 'app_bar_actions.dart';
import 'settings_page.dart';
import 'break_page.dart';
import 'points_notifier.dart';
import 'tasks_notifier.dart';
import 'energy_notifier.dart';
import 'api_config.dart';

enum EscalationLevel { safe, upcoming, startNow, overdue }

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  List<dynamic> _tasks = [];
  Map<String, dynamic> _escalations = {}; // id -> {urgency, seconds_to_latest_start, ...} จาก /tasks/escalations
  bool _isLoading = true;
  int _unreadNotifications = 0;
  int _previousUnreadNotifications = 0;
  bool _hasLoadedNotifications = false;

  StreamSubscription<List<dynamic>>? _notificationsSubscription;
  Timer? _recheckTimer;
  bool _isAskingDeadline = false;
  bool _showNudgeBanner = false;
  String _nudgeMessage = '';

  // สรุปวันนี้ (ทำไปแล้ว + ควรทำอะไรต่อตามพลังงาน) — จาก GET /dashboard/today
  bool _todayLoaded = false;
  int? _todayEnergy;
  List<dynamic> _doneToday = [];
  List<dynamic> _todoToday = [];
  Map<String, dynamic>? _todayPlan;

  @override
  void initState() {
    super.initState();
    _fetchTasks();
    _fetchToday();
    // โหลดงานใหม่เมื่อหน้าอื่นสร้างงานเพิ่ม (File Upload / Travel) — IndexedStack ไม่ rerun initState
    TasksNotifier.instance.addListener(_onTasksChanged);
    // โหลดแพลนวันนี้ใหม่เมื่อผู้ใช้เปลี่ยนพลังงาน (จาก badge ใน app bar)
    EnergyNotifier.instance.addListener(_onEnergyChanged);
    _checkPendingDeadlines();
    _checkNudge();
    // Re-check-in ทุก 30 นาทีระหว่างที่ยังอยู่หน้า dashboard
    // (backend ตัดสินใจเองว่างานไหนครบ 7 วันแล้ว งานที่เพิ่งถามไปจะไม่เด้งซ้ำ)
    _recheckTimer = Timer.periodic(const Duration(minutes: 30), (_) {
      if (!mounted || _isAskingDeadline) return;
      _checkPendingDeadlines();
    });
    _fetchNotifications();
    _notificationsSubscription = NotificationService.instance.stream.listen((list) {
      if (!mounted) return;
      final unread = list.where((n) => n['read'] == false).length;
      if (_hasLoadedNotifications && unread > _previousUnreadNotifications) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('มีการแจ้งเตือนใหม่!')), 
        );
      }
      setState(() {
        _unreadNotifications = unread;
        _previousUnreadNotifications = unread;
        _hasLoadedNotifications = true;
      });
    });
  }

  @override
  void dispose() {
    _recheckTimer?.cancel();
    _notificationsSubscription?.cancel();
    TasksNotifier.instance.removeListener(_onTasksChanged);
    EnergyNotifier.instance.removeListener(_onEnergyChanged);
    super.dispose();
  }

  void _onTasksChanged() {
    if (!mounted) return;
    _fetchTasks();
    _fetchToday();
  }

  void _onEnergyChanged() {
    if (!mounted) return;
    _fetchToday();
  }

  Future<void> _fetchToday() async {
    try {
      final response = await http.get(Uri.parse('$apiBase/dashboard/today'));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (!mounted) return;
        setState(() {
          _todayLoaded = true;
          _todayEnergy = data['energy_level'];
          _doneToday = (data['done_today'] as List<dynamic>? ?? []);
          _todoToday = (data['todo_today'] as List<dynamic>? ?? []);
          _todayPlan = data['plan'] as Map<String, dynamic>?;
        });
      }
    } catch (e) {
      // เงียบไว้ก่อน ไม่ให้หน้าแรกเด้ง error
    }
  }

  Future<void> _fetchNotifications() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/notifications'));
      if (resp.statusCode == 200) {
        final list = jsonDecode(resp.body) as List<dynamic>;
        setState(() {
          _unreadNotifications = list.where((n) => n['read'] == false).length;
        });
      }
    } catch (e) {
      // ignore
    }
  }

  Future<void> _checkPendingDeadlines() async {
    try {
      final response = await http.get(
        Uri.parse('$apiBase/tasks/needs-deadline-check'),
      );
      if (response.statusCode == 200) {
        final tasks = jsonDecode(response.body) as List<dynamic>;
        if (tasks.isNotEmpty && mounted) {
          // รอให้ frame แรก build เสร็จก่อนค่อยเด้ง dialog
          WidgetsBinding.instance.addPostFrameCallback((_) {
            _showDeadlineCheckDialog(tasks);
          });
        }
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  Future<void> _showDeadlineCheckDialog(List<dynamic> tasks) async {
    if (_isAskingDeadline) return;
    _isAskingDeadline = true;
    try {
      for (var i = 0; i < tasks.length; i++) {
        if (!mounted) return;
        final task = tasks[i];
        DateTime? pickedDeadline;

        await showDialog(
          context: context,
          barrierDismissible: false,
          builder: (dialogContext) => StatefulBuilder(
            builder: (dialogContext, setDialogState) => AlertDialog(
              title: const Text('ทบทวนงานที่ยังไม่มีกำหนดส่ง'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (tasks.length > 1) ...[
                    Text('งานที่ ${i + 1} จาก ${tasks.length}',
                        style: TextStyle(color: Colors.grey.shade600)),
                    const SizedBox(height: 8),
                  ],
                  Text(task['title'],
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  const Text('งานนี้จริงๆ ต้องเสร็จภายในวันไหน?'),
                  const SizedBox(height: 12),
                  if (pickedDeadline != null)
                    Text(
                      'เลือกไว้: ${pickedDeadline!.year}-${pickedDeadline!.month.toString().padLeft(2, '0')}-${pickedDeadline!.day.toString().padLeft(2, '0')}',
                      style: const TextStyle(color: Colors.green),
                    ),
                  TextButton.icon(
                    icon: const Icon(Icons.calendar_today, size: 16),
                    label: const Text('เลือกวันที่'),
                    onPressed: () async {
                      final picked = await showDatePicker(
                        context: dialogContext,
                        initialDate: DateTime.now(),
                        firstDate: DateTime.now(),
                        lastDate:
                            DateTime.now().add(const Duration(days: 365)),
                      );
                      if (picked != null) {
                        setDialogState(() => pickedDeadline = picked);
                      }
                    },
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () async {
                    await http.post(Uri.parse(
                        '$apiBase/tasks/${task['id']}/deadline-check?skip=true'));
                    if (dialogContext.mounted) Navigator.pop(dialogContext);
                  },
                  child: const Text('ยังไม่ทราบตอนนี้'),
                ),
                ElevatedButton(
                  onPressed: pickedDeadline == null
                      ? null
                      : () async {
                          final d = pickedDeadline!;
                          final deadlineStr =
                              "${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}";
                          await http.post(Uri.parse(
                              '$apiBase/tasks/${task['id']}/deadline-check?deadline=$deadlineStr'));
                          if (dialogContext.mounted) Navigator.pop(dialogContext);
                        },
                  child: const Text('ยืนยัน'),
                ),
              ],
            ),
          ),
        );
      }
    } finally {
      _isAskingDeadline = false;
    }
    _fetchTasks();
  }

  Future<void> _fetchTasks() async {
    setState(() => _isLoading = true);
    final url = Uri.parse('$apiBase/tasks');
    try {
      final response = await http.get(url);
      if (response.statusCode == 200) {
        setState(() {
          _tasks = jsonDecode(response.body);
        });
      }
    } catch (e) {
      // เงียบไว้ก่อน ไม่ต้อง crash แอป
    }
    await _fetchEscalations();
    setState(() => _isLoading = false);
  }

  /// ระดับความเร่งด่วนจาก backend (จุดเดียวกับ worker/celery — กัน threshold ต่างกัน)
  Future<void> _fetchEscalations() async {
    try {
      final response = await http
          .get(Uri.parse('$apiBase/tasks/escalations'));
      if (response.statusCode == 200) {
        final list = jsonDecode(response.body) as List<dynamic>;
        final map = <String, dynamic>{};
        for (final e in list) {
          if (e is Map<String, dynamic>) map[e['id']] = e;
        }
        if (mounted) setState(() => _escalations = map);
      }
    } catch (e) {
      // backend ไม่ตอบ → ใช้การคำนวณในเครื่องแทน (fallback ข้างล่าง)
    }
  }

  Future<void> _checkNudge() async {
    try {
      final response = await http.get(Uri.parse('$apiBase/nudge'));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (mounted && data['should_show'] == true) {
          setState(() {
            _showNudgeBanner = true;
            _nudgeMessage = data['message'] ?? '';
          });
        }
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  Future<void> _dismissNudge() async {
    try {
      await http.post(Uri.parse('$apiBase/nudge/dismiss'));
    } catch (e) {
      // เงียบไว้ก่อน
    }
    if (mounted) setState(() => _showNudgeBanner = false);
  }

  Future<void> _markDone(String taskId, dynamic task) async {
    final url = Uri.parse('$apiBase/tasks/$taskId');
    Map<String, dynamic>? result;
    try {
      final response = await http.patch(url);
      result = jsonDecode(response.body);
    } catch (e) {
      // เงียบไว้ก่อน
    }
    _fetchTasks();
    _fetchToday();
    PointsNotifier.instance.refresh(); // อัปเดตแต้มทันที ไม่ต้องรอสลับหน้า
    _checkNudge();

    final estimatedTime = task['estimated_time'] as int?;
    Map<String, dynamic>? breakInfo;
    try {
      final breakUrl = Uri.parse('$apiBase/break-suggestion'
          '${estimatedTime != null ? '?estimated_time=$estimatedTime' : ''}');
      final breakResponse = await http.get(breakUrl);
      breakInfo = jsonDecode(breakResponse.body);
    } catch (e) {
      // เงียบไว้ก่อน
    }

    if (mounted) {
      final unlocked = (result?['unlocked_achievements'] as List<dynamic>? ?? []);
      final streakCurrent = (result?['streak'] as Map<String, dynamic>?)?['current'] ?? 0;
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('เยี่ยมมาก! 🎉'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (result?['points_earned'] != null)
                Text('ได้รับ ${result!['points_earned']} แต้ม',
                    style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.amber)),
              if ((streakCurrent as num) > 1) ...[
                const SizedBox(height: 8),
                Text('ติดต่อกัน $streakCurrent วัน 🔥',
                    style: const TextStyle(fontWeight: FontWeight.bold)),
              ],
              if (unlocked.isNotEmpty) ...[
                const SizedBox(height: 12),
                const Text('ปลดล็อกความสำเร็จใหม่!',
                    style: TextStyle(fontWeight: FontWeight.bold, color: Colors.deepPurple)),
                const SizedBox(height: 4),
                ...unlocked.map((a) => Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text('${a['icon'] ?? ''} ${a['title'] ?? ''} (+${a['points'] ?? 0} แต้ม)'),
                    )),
              ],
              const SizedBox(height: 12),
              if (breakInfo != null) ...[
                const Text('ลองพักสักครู่ก่อนไปต่อไหม?',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                Text('พัก ${breakInfo['break_minutes']} นาที: ${breakInfo['activity']}'),
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    icon: const Icon(Icons.self_improvement, size: 18),
                    label: const Text('เปิดตัวจับเวลาพัก'),
                    onPressed: () {
                      Navigator.pop(context);
                      _openBreakPage();
                    },
                  ),
                ),
              ],
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('โอเค'),
            ),
          ],
        ),
      );
    }
  }

  Future<void> _openDetail(Map<String, dynamic> task) async {
    final result = await Navigator.push(
      context,
      MaterialPageRoute(builder: (context) => TaskDetailPage(task: task)),
    );
    if (result != null) _fetchTasks();
  }

  Future<void> _openBreakPage() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (context) => const BreakPage()),
    );
  }

  /// รวม deadline (YYYY-MM-DD) + deadline_time (HH:MM) เป็น DateTime เดียว
  DateTime? _deadlineDateTime(dynamic task) {
    final deadline = task['deadline'];
    if (deadline == null) return null;
    final timeStr = (task['deadline_time'] ?? '23:59').toString();
    final parts = timeStr.split(':');
    final hour = int.tryParse(parts[0]) ?? 23;
    final minute = parts.length > 1 ? (int.tryParse(parts[1]) ?? 59) : 59;
    try {
      final datePart = DateTime.parse(deadline.toString());
      return DateTime(datePart.year, datePart.month, datePart.day, hour, minute);
    } catch (e) {
      return null;
    }
  }

  /// คำนวณ Latest Start Time = Deadline - (Estimated Time + Buffer)
  EscalationLevel _getEscalationLevel(dynamic task) {
    // ใช้ระดับจาก backend /tasks/escalations ก่อน (จุดเดียวกับ worker/celery — กัน threshold ต่างกัน)
    final backend = _escalations[task['id']];
    if (backend is Map<String, dynamic>) {
      switch (backend['urgency']) {
        case 'overdue':
          return EscalationLevel.overdue;
        case 'critical':
        case 'high':
          return EscalationLevel.startNow;
        case 'medium':
          return EscalationLevel.upcoming;
        case 'low':
          return EscalationLevel.safe;
      }
    }
    // fallback: คำนวณในเครื่อง (เดิม) เผื่อ backend ไม่ตอบหรืองานเพิ่งสร้าง
    final deadlineDt = _deadlineDateTime(task);
    if (deadlineDt == null) return EscalationLevel.safe;

    final now = DateTime.now();
    if (now.isAfter(deadlineDt)) return EscalationLevel.overdue;

    final estimatedMinutes = task['estimated_time'] as int?;
    late int bufferMinutes;
    late int totalMinutesNeeded;

    if (estimatedMinutes != null && estimatedMinutes > 0) {
      bufferMinutes = (estimatedMinutes * 0.2).round().clamp(15, 999999);
      totalMinutesNeeded = estimatedMinutes + bufferMinutes;
    } else {
      // ไม่รู้ estimated_time ใช้ buffer default 2 ชั่วโมงแทน
      totalMinutesNeeded = 120;
    }

    final latestStart = deadlineDt.subtract(Duration(minutes: totalMinutesNeeded));

    if (now.isAfter(latestStart) || now.isAtSameMomentAs(latestStart)) {
      return EscalationLevel.startNow;
    }

    // ใกล้ถึงเวลาที่ควรเริ่ม ถ้าเหลือเวลาก่อนถึง latestStart น้อยกว่า 24 ชม.
    if (latestStart.difference(now).inHours < 24) {
      return EscalationLevel.upcoming;
    }

    return EscalationLevel.safe;
  }

  int _levelPriority(EscalationLevel level) {
    switch (level) {
      case EscalationLevel.overdue:
        return 0;
      case EscalationLevel.startNow:
        return 1;
      case EscalationLevel.upcoming:
        return 2;
      case EscalationLevel.safe:
        return 3;
    }
  }

  int _urgencyCompare(dynamic a, dynamic b) {
    final levelA = _levelPriority(_getEscalationLevel(a));
    final levelB = _levelPriority(_getEscalationLevel(b));
    if (levelA != levelB) return levelA.compareTo(levelB);

    // ระดับเดียวกัน ให้เรียงตาม deadline ใกล้สุดก่อน
    final dtA = _deadlineDateTime(a);
    final dtB = _deadlineDateTime(b);
    if (dtA == null && dtB == null) return 0;
    if (dtA == null) return 1; // ไม่มี deadline ไปท้ายสุด
    if (dtB == null) return -1;
    return dtA.compareTo(dtB);
  }

  String _fmt(dynamic task) {
    final d = task['deadline'];
    final t = task['deadline_time'] ?? '23:59';
    return '$d $t';
  }

  @override
  Widget build(BuildContext context) {
    final todoTasks = _tasks.where((t) => t['status'] == 'TODO').toList();
    todoTasks.sort((a, b) => _urgencyCompare(a, b));
    final focusTask = todoTasks.isNotEmpty ? todoTasks.first : null;
    final restTasks = todoTasks.length > 1 ? todoTasks.sublist(1) : [];

    final overdueTasks = todoTasks
        .where((t) => _getEscalationLevel(t) == EscalationLevel.overdue)
        .toList();
    final startNowTasks = todoTasks
        .where((t) => _getEscalationLevel(t) == EscalationLevel.startNow)
        .toList();
    final upcomingTasks = todoTasks
        .where((t) => _getEscalationLevel(t) == EscalationLevel.upcoming)
        .toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Zen Dashboard'),
        actions: [
          ...buildStandardAppBarActions(context, onNotificationsPressed: () {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (context) => const NotificationsPage()),
            );
          }, onSettingsPressed: () {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (context) => const SettingsPage()),
            );
          }),
          Stack(
            alignment: Alignment.center,
            children: [
              const SizedBox(width: 48, height: 48),
              if (_unreadNotifications > 0)
                Positioned(
                  right: 8,
                  top: 8,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(color: Colors.red, shape: BoxShape.circle),
                    child: Text('$_unreadNotifications', style: const TextStyle(color: Colors.white, fontSize: 12)),
                  ),
                ),
            ],
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _fetchTasks,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (_showNudgeBanner)
                    _nudgeBanner(),
                  if (_todayLoaded) _todaySection(),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.self_improvement, size: 18),
                      label: const Text('อยากพักสักครู่'),
                      onPressed: _openBreakPage,
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (overdueTasks.isNotEmpty)
                    _escalationBanner(
                      color: Colors.red,
                      icon: Icons.error,
                      title: 'เลยกำหนดแล้ว!',
                      tasks: overdueTasks,
                    ),
                  if (startNowTasks.isNotEmpty)
                    _escalationBanner(
                      color: Colors.deepOrange,
                      icon: Icons.notifications_active,
                      title: 'ถึงเวลาต้องเริ่มแล้ว!',
                      tasks: startNowTasks,
                    ),
                  if (upcomingTasks.isNotEmpty)
                    _escalationBanner(
                      color: Colors.orange,
                      icon: Icons.notifications_none,
                      title: 'ใกล้ถึงเวลาที่ควรเริ่มแล้ว',
                      tasks: upcomingTasks,
                    ),
                  const Text('สิ่งที่ต้องทำตอนนี้',
                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                  const SizedBox(height: 8),
                  if (focusTask == null)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(24),
                        child: Center(child: Text('ไม่มีงานค้างแล้ว 🎉')),
                      ),
                    )
                  else
                    Card(
                      color: Colors.deepPurple.shade50,
                      child: InkWell(
                        onTap: () => _openDetail(focusTask),
                        child: Padding(
                          padding: const EdgeInsets.all(20),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(focusTask['title'],
                                  style: const TextStyle(
                                      fontSize: 22, fontWeight: FontWeight.bold)),
                              if ((focusTask['description'] ?? '').toString().isNotEmpty) ...[
                                const SizedBox(height: 6),
                                Text(focusTask['description'],
                                    style: TextStyle(color: Colors.grey.shade800)),
                              ],
                              if (focusTask['deadline'] != null) ...[
                                const SizedBox(height: 4),
                                Text('กำหนดส่ง: ${_fmt(focusTask)}',
                                    style: TextStyle(color: Colors.grey.shade700)),
                              ],
                              const SizedBox(height: 16),
                              ElevatedButton(
                                onPressed: () => _markDone(focusTask['id'], focusTask),
                                child: const Text('เสร็จแล้ว ✓'),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  const SizedBox(height: 24),
                  if (restTasks.isNotEmpty) ...[
                    const Text('งานอื่นที่รออยู่',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                    const SizedBox(height: 8),
                    ...restTasks.map((t) => Card(
                          child: ListTile(
                            title: Text(t['title']),
                            subtitle: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if ((t['description'] ?? '').toString().isNotEmpty)
                                  Text(t['description']),
                                if (t['deadline'] != null) Text('กำหนดส่ง: ${_fmt(t)}'),
                              ],
                            ),
                            trailing: IconButton(
                              icon: const Icon(Icons.check_circle_outline),
                              onPressed: () => _markDone(t['id'], t),
                            ),
                            onTap: () => _openDetail(t),
                          ),
                        )),
                  ],
                ],
              ),
            ),
    );
  }


  Widget _todaySection() {
    final planSlots = (_todayPlan?['task_slots'] as List<dynamic>? ?? []);
    final energy = _todayEnergy;

    // "สิ่งที่ควรทำวันนี้" = แพลนตามพลังงาน (ถ้ามี) หรือไม่งั้นก็งานที่ครบกำหนดวันนี้
    final List<dynamic> shouldDo = planSlots.isNotEmpty
        ? planSlots
        : _todoToday;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.today, size: 20, color: Colors.black87),
            const SizedBox(width: 8),
            const Text('วันนี้',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const Spacer(),
            if (energy != null)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.teal.shade50,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.teal.shade200),
                ),
                child: Text('พลังงาน $energy/5',
                    style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.teal)),
              ),
          ],
        ),
        const SizedBox(height: 8),
        Card(
          color: Colors.green.shade50,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('ทำไปแล้ววันนี้',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                if (_doneToday.isEmpty)
                  Text('ยังไม่เสร็จอะไรเลยวันนี้ — ไม่เป็นไร เริ่มจากงานเล็ก ๆ ก่อนก็ได้',
                      style: TextStyle(color: Colors.grey.shade700))
                else
                  ..._doneToday.map((t) => Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.check_circle, size: 16, color: Colors.green),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(t['title'] ?? '',
                                  style: const TextStyle(decoration: TextDecoration.lineThrough, color: Colors.grey)),
                            ),
                          ],
                        ),
                      )),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        Card(
          color: Colors.teal.shade50,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  energy != null
                      ? 'สิ่งที่ควรทำวันนี้ (ตามพลังงาน $energy/5)'
                      : 'สิ่งที่ควรทำวันนี้',
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                if (shouldDo.isEmpty)
                  Text('ไม่มีอะไรค้างวันนี้ — พักผ่อนได้เต็มที่ 🎉',
                      style: TextStyle(color: Colors.grey.shade700))
                else
                  ...shouldDo.map((t) {
                    final title = t['title'] ?? '';
                    // plan slot มี start_time/end_time; task ปกติมี deadline
                    final timeText = t['start_time'] != null
                        ? '${t['start_time']}–${t['end_time']}'
                        : (t['deadline'] != null
                            ? 'กำหนดส่ง ${t['deadline']}'
                            : '');
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.play_circle_outline, size: 16, color: Colors.teal),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              timeText.isEmpty ? '$title' : '$title  ($timeText)',
                              style: const TextStyle(fontWeight: FontWeight.w500),
                            ),
                          ),
                        ],
                      ),
                    );
                  }),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
      ],
    );
  }

  Widget _nudgeBanner() {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.teal.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.teal),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.spa, color: Colors.teal),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(_nudgeMessage.isNotEmpty
                    ? _nudgeMessage
                    : 'มีงานค้างอยู่ ถ้าอยากทำก็เริ่มจากอันง่ายสุดก่อนได้เลย',
                    style: const TextStyle(color: Colors.teal, fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text('นี่เป็นแค่การเตือนใจเบา ๆ ไม่ต้องทำก็ได้',
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.close, size: 18),
            onPressed: _dismissNudge,
            tooltip: 'ปิดวันนี้',
          ),
        ],
      ),
    );
  }

  Widget _escalationBanner({
    required Color color,
    required IconData icon,
    required String title,
    required List<dynamic> tasks,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color),
              const SizedBox(width: 8),
              Text(title, style: TextStyle(fontWeight: FontWeight.bold, color: color)),
            ],
          ),
          const SizedBox(height: 8),
          ...tasks.map((t) => Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('• ${t['title']} (${_fmt(t)})'),
              )),
        ],
      ),
    );
  }
}