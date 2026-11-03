import 'package:flutter/material.dart';

import 'energy_badge.dart';
import 'notifications_page.dart';
import 'points_badge.dart';
import 'settings_page.dart';

List<Widget> buildStandardAppBarActions(
  BuildContext context, {
  VoidCallback? onNotificationsPressed,
  VoidCallback? onSettingsPressed,
}) {
  return [
    IconButton(
      icon: const Icon(Icons.notifications),
      onPressed: onNotificationsPressed ?? () {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (context) => const NotificationsPage()),
        );
      },
    ),
    IconButton(
      icon: const Icon(Icons.settings),
      onPressed: onSettingsPressed ?? () {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (context) => const SettingsPage()),
        );
      },
    ),
    const PointsBadge(),
    const EnergyBadge(),
  ];
}
