import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'api_config.dart';

class OnboardingPage extends StatefulWidget {
  final VoidCallback onDone;
  const OnboardingPage({super.key, required this.onDone});

  @override
  State<OnboardingPage> createState() => _OnboardingPageState();
}

class _OnboardingPageState extends State<OnboardingPage> {
  bool _isSaving = false;
  bool _agreed = false;

  Future<void> _acceptAndContinue() async {
    setState(() => _isSaving = true);

    // auto-detect timezone offset จากเครื่องผู้ใช้ (นาทีที่ต่างจาก UTC, ค่าลบของ Dart)
    final offsetMinutes = -DateTime.now().timeZoneOffset.inMinutes;
    final offsetHours = offsetMinutes / 60.0;

    final tzUrl = Uri.parse('$apiBase/settings/timezone?offset_hours=$offsetHours');
    final onboardUrl = Uri.parse('$apiBase/onboarding/complete');
    try {
      await http.post(tzUrl);
      await http.post(onboardUrl);
    } catch (e) {
      // ไม่ต้อง block ผู้ใช้แม้บันทึกไม่สำเร็จ
    }
    widget.onDone();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Spacer(),
              const Text('ยินดีต้อนรับสู่',
                  style: TextStyle(fontSize: 16, color: Colors.grey)),
              const SizedBox(height: 4),
              const Text('Smart Task Manager',
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
              const SizedBox(height: 16),
              const Text(
                'แอปนี้ช่วยจัดการงานและพลังงานของคุณในแต่ละวัน โดยใช้ AI ช่วยวิเคราะห์งานที่คุณพิมพ์หรือพูดเข้ามา',
                style: TextStyle(fontSize: 15, height: 1.5),
              ),
              const SizedBox(height: 24),
              const Text(
                'ก่อนเริ่มใช้งาน',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                'ข้อความที่คุณพิมพ์ในหน้า Brain Dump จะถูกส่งไปให้ AI ภายนอกวิเคราะห์ เพื่อแปลงเป็นงานที่มีกำหนดเวลาและระยะเวลาโดยประมาณ',
                style: TextStyle(fontSize: 14, color: Colors.black87, height: 1.5),
              ),
              const SizedBox(height: 16),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                value: _agreed,
                onChanged: (value) => setState(() => _agreed = value ?? false),
                title: const Text('ฉันเข้าใจและยอมรับเงื่อนไขข้างต้น'),
              ),
              const Spacer(),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: (_agreed && !_isSaving) ? _acceptAndContinue : null,
                  child: _isSaving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('เริ่มใช้งาน'),
                ),
              ),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}