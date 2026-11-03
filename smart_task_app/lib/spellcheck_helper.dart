import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'api_config.dart';

const _baseUrl = apiBase;

class SpellcheckResult {
  final String finalText;
  final List<Map<String, dynamic>> autoCorrected;
  final List<String> keptOriginal;

  const SpellcheckResult({
    required this.finalText,
    required this.autoCorrected,
    required this.keptOriginal,
  });
}

/// ใส่เฉพาะคำที่เลือกให้แก้ (ใช้ใน unit test + logic ฝั่ง client)
String applySpellcheckChanges(
  String original,
  List<dynamic> changes,
  Set<int> useCorrected,
) {
  var result = original;
  for (var i = 0; i < changes.length; i++) {
    if (!useCorrected.contains(i)) continue;
    final change = changes[i] as Map<String, dynamic>;
    final from = change['original']?.toString() ?? '';
    final to = change['corrected']?.toString() ?? '';
    if (from.isNotEmpty && to.isNotEmpty) {
      result = result.replaceFirst(from, to);
    }
  }
  return result;
}

String buildSpellcheckPreview({
  required String originalText,
  required String correctedText,
  required List<dynamic> changes,
  required Set<int> useCorrected,
}) {
  if (useCorrected.length == changes.length) return correctedText;
  if (useCorrected.isEmpty) return originalText;
  return applySpellcheckChanges(originalText, changes, useCorrected);
}

/// ตรวจสะกดแล้วแก้อัตโนมัติเฉพาะคำที่ไม่เคยใช้ในประวัติ
Future<SpellcheckResult> resolveSpellcheck(String text) async {
  final trimmed = text.trim();
  if (trimmed.isEmpty) {
    return const SpellcheckResult(
      finalText: '',
      autoCorrected: [],
      keptOriginal: [],
    );
  }

  final url = Uri.parse(
    '$_baseUrl/spellcheck/auto-resolve?text=${Uri.encodeComponent(trimmed)}',
  );
  try {
    final response = await http.post(url);
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return SpellcheckResult(
        finalText: data['final_text']?.toString() ?? trimmed,
        autoCorrected: List<Map<String, dynamic>>.from(data['auto_corrected'] ?? []),
        keptOriginal: List<String>.from(data['kept_original'] ?? []),
      );
    }
  } catch (_) {}

  return SpellcheckResult(
    finalText: trimmed,
    autoCorrected: [],
    keptOriginal: [],
  );
}

void showSpellcheckSnackBar(BuildContext context, SpellcheckResult result) {
  if (result.autoCorrected.isEmpty || !context.mounted) return;
  final parts = result.autoCorrected
      .map((c) => '${c['original']} → ${c['corrected']}')
      .join(', ');
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text('แก้คำสะกดให้แล้ว: $parts')),
  );
}
