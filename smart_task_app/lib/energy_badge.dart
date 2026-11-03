import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import 'energy_notifier.dart';
import 'api_config.dart';

class EnergyBadge extends StatefulWidget {
  const EnergyBadge({super.key});

  @override
  State<EnergyBadge> createState() => _EnergyBadgeState();
}

class _EnergyBadgeState extends State<EnergyBadge> {
  int? _level;

  final Map<int, String> _emojis = {
    1: '😴',
    2: '😪',
    3: '🙂',
    4: '😃',
    5: '🔥',
  };

  final Map<int, String> _labels = {
    1: 'ร่างกายต้องการเตียง',
    2: 'เหนื่อยๆ ทำได้นิดหน่อย',
    3: 'ปกติ พอไหว',
    4: 'สดใส ทำงานได้ดี',
    5: 'ไฟลุกพร้อมลุย',
  };

  @override
  void initState() {
    super.initState();
    _fetchLevel();
  }

  Future<void> _fetchLevel() async {
    final url = Uri.parse('$apiBase/energy-log/today');
    try {
      final response = await http.get(url);
      final data = jsonDecode(response.body);
      if (mounted) {
        setState(() => _level = data['energy_level']);
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  Future<void> _updateLevel(int level) async {
    Navigator.pop(context); // ปิด sheet ก่อนเลย ไม่ต้องรอ network
    final url = Uri.parse('$apiBase/energy-log?level=$level');
    try {
      await http.post(url);
    } catch (e) {
      // เงียบไว้ก่อน
    }
    EnergyNotifier.instance.changed(); // บอก Dashboard ให้คำนวณแพลนวันนี้ใหม่ตามพลังงาน
    await _fetchLevel(); // ดึงค่าล่าสุดจาก backend มายืนยันอีกที
  }

  void _openPicker() {
    showModalBottomSheet(
      context: context,
      builder: (context) => Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('อัปเดตพลังงานตอนนี้',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const SizedBox(height: 16),
            ..._labels.entries.map((entry) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: SizedBox(
                    width: double.infinity,
                    child: OutlinedButton(
                      style: OutlinedButton.styleFrom(
                        backgroundColor: _level == entry.key
                            ? Colors.black12
                            : Colors.white,
                        side: const BorderSide(color: Colors.black38),
                        foregroundColor: Colors.black87,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                      onPressed: () => _updateLevel(entry.key),
                      child: Text(
                        '${entry.key} ${_emojis[entry.key]}  ${entry.value}',
                        style: const TextStyle(color: Colors.black87),
                      ),
                    ),
                  ),
                )),

          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 12),
      child: Center(
        child: GestureDetector(
          onTap: _openPicker,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.deepPurple.shade50,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: Colors.deepPurple.shade100),
            ),
            child: Text(
              _level != null ? '$_level ${_emojis[_level]}' : '⚡',
              style: const TextStyle(fontSize: 15),
            ),
          ),
        ),
      ),
    );
  }
}