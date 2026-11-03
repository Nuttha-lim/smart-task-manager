import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app_bar_actions.dart';
import 'api_config.dart';

class EnergyCheckinPage extends StatefulWidget {
  final VoidCallback onDone;
  const EnergyCheckinPage({super.key, required this.onDone});

  @override
  State<EnergyCheckinPage> createState() => _EnergyCheckinPageState();
}

class _EnergyCheckinPageState extends State<EnergyCheckinPage> {
  bool _isSaving = false;

  final Map<int, String> _levels = {
    1: 'ร่างกายต้องการเตียง 😴',
    2: 'เหนื่อยๆ ทำได้นิดหน่อย',
    3: 'ปกติ พอไหว',
    4: 'สดใส ทำงานได้ดี',
    5: 'ไฟลุกพร้อมลุย 🔥',
  };

  Future<void> _selectLevel(int level) async {
    setState(() => _isSaving = true);
    final url = Uri.parse('$apiBase/energy-log?level=$level');
    try {
      await http.post(url);
    } catch (e) {
      // ไม่ต้อง block ผู้ใช้แม้บันทึกไม่สำเร็จ
    }
    widget.onDone();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('อัปเดตพลังงาน'),
        actions: buildStandardAppBarActions(context),
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text('วันนี้พลังงานเป็นยังไงบ้าง?',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 32),
              if (_isSaving)
                const CircularProgressIndicator()
              else
                ..._levels.entries.map((entry) => Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: SizedBox(
                        width: double.infinity,
                        child: OutlinedButton(
                          onPressed: () => _selectLevel(entry.key),
                          child: Text('${entry.key} - ${entry.value}'),
                        ),
                      ),
                    )),
            ],
          ),
        ),
      ),
    );
  }
}