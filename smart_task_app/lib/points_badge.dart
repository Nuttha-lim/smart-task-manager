import 'package:flutter/material.dart';
import 'gamification_page.dart';
import 'points_notifier.dart';

class PointsBadge extends StatefulWidget {
  const PointsBadge({super.key});

  @override
  State<PointsBadge> createState() => PointsBadgeState();
}

class PointsBadgeState extends State<PointsBadge> {
  @override
  void initState() {
    super.initState();
    // ฟัง notifier กลาง — แต้มเปลี่ยนปุ๊บ badge อัปเดตปั๊บ ไม่ต้องกดเข้าไปดู
    PointsNotifier.instance.addListener(_onPointsChanged);
    PointsNotifier.instance.refresh();
  }

  void _onPointsChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    PointsNotifier.instance.removeListener(_onPointsChanged);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: Center(
        child: GestureDetector(
          onTap: () async {
            await Navigator.push(
              context,
              MaterialPageRoute(builder: (context) => const GamificationPage()),
            );
            PointsNotifier.instance.refresh(); // กลับจากหน้า gamification ให้ดึงแต้มล่าสุด
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.amber.shade50,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: Colors.amber.shade200),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.star, size: 16, color: Colors.amber),
                const SizedBox(width: 4),
                Text('${PointsNotifier.instance.points}',
                    style: const TextStyle(fontWeight: FontWeight.bold)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
