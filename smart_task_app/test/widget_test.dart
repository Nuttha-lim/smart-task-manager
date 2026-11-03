import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smart_task_app/chat_page.dart';
import 'package:smart_task_app/main.dart';

void main() {
  testWidgets('HomeShell opens chat when startup requests are unavailable',
      (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();

    expect(find.byType(ChatPage), findsOneWidget);
    expect(find.text('แชท'), findsWidgets);
    expect(find.text('Dashboard'), findsWidgets);
    expect(find.text('Calendar'), findsWidgets);
    final navigation = tester.widget<BottomNavigationBar>(
      find.byType(BottomNavigationBar),
    );
    expect(navigation.currentIndex, 0);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();
  });
}
