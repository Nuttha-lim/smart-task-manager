import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dashboard_page.dart';
import 'energy_checkin_page.dart';
import 'notification_service.dart';
import 'onboarding_page.dart';
import 'calendar_page.dart';
import 'chat_page.dart';
import 'push_service.dart';
import 'api_config.dart';
void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Smart Task Manager',
      debugShowCheckedModeBanner: false,
      home: const HomeShell(),
    );
  }
}

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _currentIndex = 0;
  bool? _onboardingDone;
  bool? _hasCheckedInToday;

  final List<Widget> _pages = const [
    ChatPage(),
    DashboardPage(),
    CalendarPage(),
  ];

  @override
  void initState() {
    super.initState();
    NotificationService.instance.startPolling();
    PushService.init().catchError((_) {});
    _checkOnboarding();
  }

  @override
  void dispose() {
    NotificationService.instance.stopPolling();
    super.dispose();
  }

  Future<void> _checkOnboarding() async {
    final url = Uri.parse('$apiBase/onboarding/status');
    try {
      final response = await http.get(url);
      final data = jsonDecode(response.body);
      setState(() {
        _onboardingDone = data['done'] == true;
      });
      if (_onboardingDone == true) {
        _checkTodayEnergy();
      }
    } catch (e) {
      setState(() => _onboardingDone = true);
      _checkTodayEnergy();
    }
  }

  Future<void> _checkTodayEnergy() async {
    final url = Uri.parse('$apiBase/energy-log/today');
    try {
      final response = await http.get(url);
      final data = jsonDecode(response.body);
      setState(() {
        _hasCheckedInToday = data['energy_level'] != null;
      });
    } catch (e) {
      setState(() => _hasCheckedInToday = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_onboardingDone == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (_onboardingDone == false) {
      return OnboardingPage(
        onDone: () {
          setState(() => _onboardingDone = true);
          _checkTodayEnergy();
        },
      );
    }

    if (_hasCheckedInToday == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (_hasCheckedInToday == false) {
      return EnergyCheckinPage(
        onDone: () => setState(() => _hasCheckedInToday = true),
      );
    }

    return PopScope(
      // ปุ่มกลับ (เบราว์เซอร์/แอนดรอยด์) จะสลับแท็บแทนการออกจากแอป —
      // ป้องกันกดกลับแล้วแอป "ตาย" เงียบ ๆ บนเว็บ
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        if (_currentIndex > 0) {
          setState(() => _currentIndex = _currentIndex - 1);
        }
      },
      child: Scaffold(
        body: _pages[_currentIndex],
        bottomNavigationBar: BottomNavigationBar(
          currentIndex: _currentIndex,
          selectedItemColor: Colors.black87,
          unselectedItemColor: Colors.black54,
          backgroundColor: Colors.white,
          type: BottomNavigationBarType.fixed,
          onTap: (index) => setState(() => _currentIndex = index),
          items: const [
            BottomNavigationBarItem(icon: Icon(Icons.chat_bubble), label: 'แชท'),
            BottomNavigationBarItem(icon: Icon(Icons.dashboard), label: 'Dashboard'),
            BottomNavigationBarItem(icon: Icon(Icons.calendar_month), label: 'Calendar'),
          ],
        ),
      ),
    );
  }
}