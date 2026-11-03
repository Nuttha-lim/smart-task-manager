import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'api_config.dart';

class NotificationService {
  NotificationService._();
  static final NotificationService instance = NotificationService._();

  static const String _baseUrl = apiBase;
  final StreamController<List<dynamic>> _controller = StreamController<List<dynamic>>.broadcast(sync: true);
  Timer? _pollTimer;
  http.Client _httpClient = http.Client();

  Stream<List<dynamic>> get stream => _controller.stream;

  void setHttpClient(http.Client client) {
    _httpClient = client;
  }

  Future<List<dynamic>> fetchNotifications() async {
    final uri = Uri.parse('$_baseUrl/notifications');
    try {
      print('[NotificationService] using client: ${_httpClient.runtimeType}');
      print('[NotificationService] GET $uri');
      final response = await _httpClient.get(uri);
      print('[NotificationService] status=${response.statusCode} body=${response.body}');
      if (response.statusCode == 200) {
        final list = jsonDecode(response.body) as List<dynamic>;
        _controller.add(list);
        return list;
      }
      // If non-200, emit empty list so listeners don't wait indefinitely.
      print('[NotificationService] non-200 response, emitting empty list');
      _controller.add([]);
    } catch (e, st) {
      print('[NotificationService] fetch error: $e');
      print(st);
      // On error, emit empty list so listeners don't wait indefinitely.
      try {
        _controller.add([]);
      } catch (_) {}
    }
    return [];
  }

  void startPolling({Duration interval = const Duration(seconds: 60)}) {
    if (_pollTimer != null) {
      return;
    }
    _pollTimer = Timer.periodic(interval, (_) => fetchNotifications());
    fetchNotifications();
  }

  void stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }
}
