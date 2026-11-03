import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'app_bar_actions.dart';
import 'points_notifier.dart';
import 'api_config.dart';

class GamificationPage extends StatefulWidget {
  const GamificationPage({super.key});

  @override
  State<GamificationPage> createState() => _GamificationPageState();
}

class _GamificationPageState extends State<GamificationPage> {
  bool _isLoading = true;
  Map<String, dynamic>? _status;
  List<dynamic> _rewards = [];

  final TextEditingController _rewardTitleController = TextEditingController();
  List<dynamic> _rewardIdeas = [];

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  Future<void> _loadAll() async {
    await Future.wait([_loadStatus(), _loadRewards(), _loadRewardIdeas()]);
    if (mounted) setState(() => _isLoading = false);
  }

  Future<void> _loadStatus() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/gamification'));
      if (resp.statusCode == 200) {
        setState(() => _status = jsonDecode(resp.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  Future<void> _loadRewards() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/rewards'));
      if (resp.statusCode == 200) {
        setState(() => _rewards = jsonDecode(resp.body));
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  Future<void> _loadRewardIdeas() async {
    try {
      final resp = await http.get(Uri.parse('$apiBase/rewards/ideas?n=5'));
      if (resp.statusCode == 200) {
        setState(() {
          _rewardIdeas = (jsonDecode(resp.body)['ideas'] as List<dynamic>? ?? []);
        });
      }
    } catch (e) {
      // เงียบไว้ก่อน
    }
  }

  Future<void> _addReward() async {
    final title = _rewardTitleController.text.trim();
    if (title.isEmpty) {
      _showSnack('กรอกชื่อรางวัลก่อน — แต้มให้ AI คิดให้เอง');
      return;
    }
    try {
      final resp = await http.post(Uri.parse(
          '$apiBase/rewards?title=${Uri.encodeComponent(title)}'));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        _rewardTitleController.clear();
        _showSnack('เพิ่มรางวัลแล้ว — AI ให้ ${data['point_cost']} แต้ม');
        await _loadRewards();
      } else {
        _showSnack('เพิ่มรางวัลไม่สำเร็จ');
      }
    } catch (e) {
      _showSnack('เพิ่มรางวัลไม่สำเร็จ: $e');
    }
  }

  Future<void> _addRewardFromIdea(dynamic idea) async {
    try {
      final resp = await http.post(Uri.parse(
          '$apiBase/rewards/ideas?title=${Uri.encodeComponent(idea['title'] as String)}'));
      if (resp.statusCode == 200) {
        _showSnack('เพิ่มไอเดีย "${idea['title']}" แล้ว');
        await _loadAll();
      }
    } catch (e) {
      _showSnack('เพิ่มไม่สำเร็จ: $e');
    }
  }

  Future<void> _redeem(dynamic reward) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('แลกรางวัล "${reward['title']}"?'),
        content: Text('ใช้ ${reward['point_cost']} แต้มเพื่อแลก',
            style: const TextStyle(fontSize: 16)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('ยกเลิก'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('แลกเลย'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      final resp = await http.post(
          Uri.parse('$apiBase/rewards/${reward['id']}/redeem'));
      final data = jsonDecode(resp.body);
      if (data['redeemed'] == true) {
        _showSnack('แลกแล้ว! เหลือ ${data['remaining_points']} แต้ม 🎉');
      } else {
        _showSnack(data['error'] ?? 'แลกไม่สำเร็จ');
      }
      PointsNotifier.instance.refresh(); // badge แต้มทุกหน้าเด้งตามทันที
      await _loadAll();
    } catch (e) {
      _showSnack('แลกไม่สำเร็จ: $e');
    }
  }

  Future<void> _deleteReward(String id) async {
    try {
      await http.delete(Uri.parse('$apiBase/rewards/$id'));
      await _loadRewards();
    } catch (e) {
      _showSnack('ลบไม่สำเร็จ: $e');
    }
  }

  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('เกมมิฟิเคชัน'),
        actions: buildStandardAppBarActions(context),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadAll,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (_status != null) _levelCard(_status!),
                  const SizedBox(height: 24),
                  _sectionTitle('ความสำเร็จ', Icons.emoji_events),
                  const SizedBox(height: 8),
                  if (_status != null) _achievementsGrid(_status!),
                  const SizedBox(height: 24),
                  _sectionTitle('รางวัลของฉัน', Icons.card_giftcard),
                  const SizedBox(height: 8),
                  _addRewardForm(),
                  const SizedBox(height: 8),
                  if (_rewards.isEmpty)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(20),
                        child: Center(child: Text('ยังไม่มีรางวัล — เพิ่มรางวัลที่อยากได้เองได้เลย')),
                      ),
                    )
                  else
                    ..._rewards.map((r) => _rewardCard(r)),
                  const SizedBox(height: 24),
                  _sectionTitle('ไอเดียรางวัลจาก AI', Icons.auto_awesome),
                  const SizedBox(height: 4),
                  Text('AI คิดแต้มและจำกัดสิทธิ์ให้เอง — แตะเพื่อเพิ่มเป็นรางวัลของคุณ',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
                  const SizedBox(height: 8),
                  if (_rewardIdeas.isEmpty)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(20),
                        child: Center(child: Text('กำลังคิดไอเดีย...')),
                      ),
                    )
                  else
                    ..._rewardIdeas.map((i) => _ideaCard(i)),
                ],
              ),
            ),
    );
  }

  Widget _sectionTitle(String title, IconData icon) {
    return Row(
      children: [
        Icon(icon, size: 20, color: Colors.black87),
        const SizedBox(width: 8),
        Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
      ],
    );
  }

  Widget _levelCard(Map<String, dynamic> status) {
    final level = (status['level'] as Map<String, dynamic>? ?? {}).cast<String, dynamic>();
    final streak = (status['streak'] as Map<String, dynamic>? ?? {}).cast<String, dynamic>();
    final levelNum = level['level'] ?? 1;
    final into = (level['into'] as num?)?.toDouble() ?? 0;
    final forNext = (level['for_next'] as num?)?.toDouble() ?? 100;
    final total = into + forNext;
    final progress = total > 0 ? (into / total).clamp(0.0, 1.0) : 0.0;

    return Card(
      color: Colors.amber.shade50,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('ระดับ $levelNum',
                    style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                const Icon(Icons.stars, color: Colors.amber, size: 28),
              ],
            ),
            const SizedBox(height: 4),
            Text('แต้มสะสมทั้งหมด ${status['lifetime_points'] ?? 0}',
                style: TextStyle(color: Colors.grey.shade700)),
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: progress,
                minHeight: 10,
                backgroundColor: Colors.black12,
                color: Colors.amber,
              ),
            ),
            const SizedBox(height: 6),
            Text('อีก ${forNext.round()} แต้มถึงระดับถัดไป',
                style: TextStyle(color: Colors.grey.shade700, fontSize: 13)),
            const SizedBox(height: 16),
            Row(
              children: [
                _statPill(Icons.star, '${status['points'] ?? 0}', 'แต้มใช้แลกได้'),
                const SizedBox(width: 8),
                _statPill(Icons.local_fire_department, '${streak['current'] ?? 0}',
                    'ติดต่อกัน'),
                const SizedBox(width: 8),
                _statPill(Icons.emoji_events, '${streak['best'] ?? 0}', 'สถิติสูงสุด'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _statPill(IconData icon, String value, String label) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: Colors.black12),
        ),
        child: Column(
          children: [
            Icon(icon, size: 18, color: Colors.black54),
            const SizedBox(height: 4),
            Text(value, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade600)),
          ],
        ),
      ),
    );
  }

  Widget _achievementsGrid(Map<String, dynamic> status) {
    final achievements = (status['achievements'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: achievements.map((a) {
        final unlocked = a['unlocked'] == true;
        return GestureDetector(
          onTap: () => _showAchievementDetail(a),
          child: Container(
            width: 160,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: unlocked ? Colors.deepPurple.shade50 : Colors.grey.shade100,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: unlocked ? Colors.deepPurple.shade200 : Colors.black12,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(a['icon'] ?? '🎖️', style: const TextStyle(fontSize: 22)),
                    if (unlocked)
                      const Icon(Icons.check_circle, color: Colors.green, size: 16)
                    else
                      const Icon(Icons.lock, size: 16, color: Colors.grey),
                  ],
                ),
                const SizedBox(height: 8),
                Text(a['title'] ?? '',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: unlocked ? Colors.black87 : Colors.grey.shade600,
                    )),
                const SizedBox(height: 2),
                Text(
                  a['description'] ?? '',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  void _showAchievementDetail(Map<String, dynamic> a) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('${a['icon'] ?? ''}  ${a['title'] ?? ''}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(a['description'] ?? ''),
            const SizedBox(height: 12),
            Text('โบนัส ${a['points'] ?? 0} แต้ม',
                style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.amber)),
            const SizedBox(height: 8),
            Text(
              a['unlocked'] == true ? 'ปลดล็อกแล้ว 🎉' : 'ยังไม่ปลดล็อก — ทำต่อได้ไม่กดดัน',
              style: TextStyle(
                color: a['unlocked'] == true ? Colors.green : Colors.grey.shade600,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('ปิด'),
          ),
        ],
      ),
    );
  }

  Widget _addRewardForm() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _rewardTitleController,
                decoration: const InputDecoration(
                  labelText: 'รางวัลที่อยากได้ (เช่น ดูหนัง 1 เรื่อง)',
                  helperText: 'แต้มให้ AI คิดให้ตามความเหมาะสม',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              icon: const Icon(Icons.add),
              onPressed: _addReward,
              tooltip: 'เพิ่มรางวัล',
            ),
          ],
        ),
      ),
    );
  }

  Widget _ideaCard(dynamic idea) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: const Icon(Icons.auto_awesome, color: Colors.deepPurple),
        title: Text(idea['title'] ?? ''),
        subtitle: Text('${idea['point_cost']} แต้ม · '
            'วันละ ${idea['max_per_day']} ครั้ง · '
            'เดือนละ ${idea['max_per_month']} ครั้ง · '
            'ปีละ ${idea['max_per_year']} ครั้ง'),
        trailing: IconButton(
          icon: const Icon(Icons.add_circle_outline, color: Colors.deepPurple),
          onPressed: () => _addRewardFromIdea(idea),
          tooltip: 'เพิ่มเป็นรางวัล',
        ),
      ),
    );
  }

  Widget _rewardCard(dynamic reward) {
    final canAfford = (_status?['points'] ?? 0) >= (reward['point_cost'] ?? 0);
    final available = reward['available'] != false;
    final usage = (reward['usage'] as Map<String, dynamic>? ?? {}).cast<String, dynamic>();
    final usageText = usage.isEmpty
        ? ''
        : 'วันนี้ใช้ ${usage['day'] ?? 0}/${reward['max_per_day'] ?? '∞'}'
            ' · เดือน ${usage['month'] ?? 0}/${reward['max_per_month'] ?? '∞'}'
            ' · ปี ${usage['year'] ?? 0}/${reward['max_per_year'] ?? '∞'}';
    final limitText = (reward['max_per_day'] ?? reward['max_per_month'] ?? reward['max_per_year']) == null
        ? ''
        : 'จำกัด วันละ ${reward['max_per_day'] ?? '∞'} · เดือนละ ${reward['max_per_month'] ?? '∞'} · ปีละ ${reward['max_per_year'] ?? '∞'}';
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(Icons.card_giftcard,
            color: available ? Colors.deepOrange : Colors.grey),
        title: Text(reward['title']),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${reward['point_cost']} แต้ม'),
            if (limitText.isNotEmpty)
              Text(limitText, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
            if (usageText.isNotEmpty)
              Text(usageText, style: TextStyle(fontSize: 12, color: Colors.grey.shade600)),
            if (!available)
              Text(reward['unavailable_reason'] ?? 'ใช้ไม่ได้ช่วงนี้',
                  style: const TextStyle(fontSize: 12, color: Colors.red)),
          ],
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: () => _deleteReward(reward['id']),
              tooltip: 'ลบรางวัล',
            ),
            ElevatedButton(
              onPressed: (canAfford && available) ? () => _redeem(reward) : null,
              child: const Text('แลก'),
            ),
          ],
        ),
      ),
    );
  }
}
