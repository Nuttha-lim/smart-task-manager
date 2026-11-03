import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app_bar_actions.dart';
import 'api_config.dart';

/// Dynamic Break Generator — ให้ AI/backend แนะนำการพักตามพลังงานของวันนี้
/// แล้วมีตัวจับเวลาพักเบา ๆ (ยืดหยุ่น ไม่บังคับ — "พักเท่าไหร่ก็ได้")
class BreakPage extends StatefulWidget {
  const BreakPage({super.key});

  @override
  State<BreakPage> createState() => _BreakPageState();
}

class _BreakPageState extends State<BreakPage> {
  bool _isLoading = true;
  Map<String, dynamic>? _suggestion;

  int _secondsRemaining = 0;
  bool _isRunning = false;
  Timer? _timer;

  static const Map<int, String> _energyLabels = {
    1: 'พลังงานต่ำมาก',
    2: 'พลังงานต่ำ',
    3: 'พลังงานปกติ',
    4: 'พลังงานสูง',
    5: 'พลังงานเต็มเปี่ยม',
  };

  @override
  void initState() {
    super.initState();
    _loadSuggestion();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _loadSuggestion() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/break-suggestion'));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        setState(() {
          _suggestion = data;
          _secondsRemaining = ((data['break_minutes'] as num?) ?? 10).round() * 60;
        });
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
    if (mounted) setState(() => _isLoading = false);
  }

  /// ดึงไอเดียใหม่ (backend สุ่มใหม่ตามระดับพลังงาน) — ตัั้งเวลาพักค้างไว้เท่าเดิม
  Future<void> _anotherIdea() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/break-suggestion'));
      if (resp.statusCode == 200) {
        setState(() => _suggestion = jsonDecode(resp.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  void _toggleTimer() {
    if (_isRunning) {
      _timer?.cancel();
      setState(() => _isRunning = false);
      return;
    }
    if (_secondsRemaining <= 0) return;
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      setState(() => _secondsRemaining--);
      if (_secondsRemaining <= 0) {
        t.cancel();
        _isRunning = false;
        _showFinishedDialog();
      }
    });
    setState(() => _isRunning = true);
  }

  void _resetTimer() {
    _timer?.cancel();
    setState(() {
      _isRunning = false;
      _secondsRemaining = ((_suggestion?['break_minutes'] as num?) ?? 10).round() * 60;
    });
  }

  void _showFinishedDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('พักเสร็จแล้ว 🎈'),
        content: const Text('ไม่ต้องรีบ — พร้อมเมื่อไหร่ค่อยกลับไปทำก็ได้'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('โอเค'),
          ),
        ],
      ),
    );
  }

  String _formatTime(int seconds) {
    final m = (seconds ~/ 60).toString().padLeft(2, '0');
    final s = (seconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('อยากพักสักครู่'),
        actions: buildStandardAppBarActions(context),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (_suggestion != null) ...[
                  Card(
                    color: Colors.teal.shade50,
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.self_improvement, color: Colors.teal),
                              const SizedBox(width: 8),
                              Text(
                                _energyLabels[(_suggestion!['energy_level'] as num?)?.round()] ??
                                    'พลังงาน',
                                style: TextStyle(
                                    color: Colors.teal, fontWeight: FontWeight.bold),
                              ),
                              const Spacer(),
                              TextButton.icon(
                                icon: const Icon(Icons.refresh, size: 18),
                                label: const Text('ไอเดียอื่น'),
                                onPressed: _anotherIdea,
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          Text(
                            'พัก ${_suggestion!['break_minutes']} นาที — ${_suggestion!['activity']}',
                            style: const TextStyle(
                                fontSize: 20, fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'คำแนะนำนี้ดูตามพลังของวันนี้ ไม่ต้องทำตามเป๊ะ ๆ ก็ได้',
                            style: TextStyle(color: Colors.grey.shade700),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    _formatTime(_secondsRemaining),
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 56, fontWeight: FontWeight.w300),
                  ),
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: LinearProgressIndicator(
                      value: _secondsRemaining > 0
                          ? (_secondsRemaining /
                              (((_suggestion!['break_minutes'] as num?) ?? 10).round() * 60))
                          : 0,
                      minHeight: 8,
                      backgroundColor: Colors.black12,
                      color: Colors.teal,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      OutlinedButton.icon(
                        icon: Icon(_isRunning ? Icons.pause : Icons.play_arrow),
                        label: Text(_isRunning ? 'หยุดพักชั่วคราว' : 'เริ่มพัก'),
                        onPressed: _toggleTimer,
                      ),
                      const SizedBox(width: 8),
                      OutlinedButton.icon(
                        icon: const Icon(Icons.replay),
                        label: const Text('เริ่มใหม่'),
                        onPressed: _resetTimer,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'พักสั้นแค่ไหนก็ได้ — กลับไปทำงานต่อเมื่อพร้อม ไม่ต้องรอเวลาเป๊ะ',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                  ),
                ],
              ],
            ),
    );
  }
}
