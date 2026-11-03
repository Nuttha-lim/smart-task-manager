import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'notification_service.dart';

import 'app_bar_actions.dart';
import 'api_config.dart';

class NotificationsPage extends StatefulWidget {
  const NotificationsPage({super.key});

  @override
  State<NotificationsPage> createState() => _NotificationsPageState();
}

class _NotificationsPageState extends State<NotificationsPage> {
  List<dynamic> _notifications = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    NotificationService.instance.startPolling();
    _fetchNotifications();
  }

  Future<void> _fetchNotifications() async {
    setState(() => _isLoading = true);
    final list = await NotificationService.instance.fetchNotifications();
    if (mounted) {
      setState(() {
        _notifications = list;
        _isLoading = false;
      });
    }
  }

  Future<void> _ackNotification(String id) async {
    try {
      final uri = Uri.parse('$apiBase/notifications/$id/ack');
      final resp = await http.post(uri);
      if (resp.statusCode == 200) {
        _fetchNotifications();
      }
    } catch (_) {
      // ignore network errors
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('การแจ้งเตือน'),
        actions: buildStandardAppBarActions(context),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _fetchNotifications,
              child: _notifications.isEmpty
                  ? ListView(
                      children: [
                        const SizedBox(height: 200),
                        const Center(child: Text('ยังไม่มีการแจ้งเตือนใหม่')), 
                      ],
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.all(12),
                      itemCount: _notifications.length,
                      itemBuilder: (context, index) {
                        final note = _notifications[index];
                        final read = note['read'] == true;
                        return Card(
                          margin: const EdgeInsets.only(bottom: 12),
                          child: ListTile(
                            title: Text(note['message'] ?? ''),
                            subtitle: Text('${note['urgency']} • ${note['created_at']}'),
                            trailing: read
                                ? const Icon(Icons.check, color: Colors.green)
                                : TextButton(
                                    onPressed: () => _ackNotification(note['id']),
                                    child: const Text('ทำเครื่องหมายว่าอ่านแล้ว'),
                                  ),
                          ),
                        );
                      },
                    ),
            ),
    );
  }
}
