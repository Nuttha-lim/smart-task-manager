import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:smart_task_app/notification_service.dart';

void main() {
  test('fetchNotifications returns parsed notifications and notifies stream listeners', () async {
    final mockClient = MockClient((request) async {
      expect(request.url.toString(), 'http://127.0.0.1:8000/notifications');
      final body = jsonEncode([
        {
          'id': 'note-1',
          'message': 'ทดสอบ',
          'urgency': 'high',
          'read': false,
          'created_at': '2026-08-06T00:00:00',
        }
      ]);
      return http.Response.bytes(
        utf8.encode(body),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });

    NotificationService.instance.setHttpClient(mockClient);

    final firstNotificationEvent = NotificationService.instance.stream.first;

    final notifications = await NotificationService.instance.fetchNotifications();
    final streamEvent = await firstNotificationEvent;

    expect(notifications, isA<List<dynamic>>());
    expect(notifications.length, 1);
    expect(notifications.first['id'], 'note-1');
    expect(streamEvent.length, 1);
    expect(streamEvent.first['message'], 'ทดสอบ');
  });
}
