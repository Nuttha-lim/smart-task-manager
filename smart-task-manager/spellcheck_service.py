"""Smart typo correction service.

ตรวจสะกดคำไทยด้วย pythainlp และ "จำนิสัย" ผู้ใช้จาก 2 แหล่ง:
1. คำที่ผู้ใช้เคยพิมพ์จริงในงาน/เป้าหมาย (trusted words) — คำที่เคยใช้แล้วไม่ไปรบกวน
2. preference ที่ผู้ใช้ระบุชัดเจน (spell_prefs table) — override หรือขอคงคำเดิม

หลักการ conservative (ตาม AGENTS.md: "ช่วยไม่กดดัน / อย่าไปรบกวน"):
- ถ้า word อยู่ในพจนานุกรม pythainlp (thai_words()) => ถูกต้อง ไม่ยุ่ง (กัน false positive
  เช่น pythainlp spell แนะนำ "ทำงาน" -> "ทำงน" ซึ่งผิด)
- pythainlp spell() ใช้เป็นแหล่ง "ตัวเลือกคำแก้" เท่านั้น และจะ auto-correct เฉพาะเมื่อ
  ตัวเลือกนั้น (1) อยู่ในพจนานุกรม (2) ระยะทางแก้ไข (edit distance) <= 1
- คำประสม/คำไม่รู้จัก (เช่น "ส่งงาน", "ไปหาหมอ") จะไม่ถูกแก้ เพราะตัวแก้ไม่มีตัวเลือกที่เข้าเกณฑ์
- ถ้า pythainlp ใช้ไม่ได้ => fallback ไม่แก้คำ (คืนข้อความเดิม) ไม่ crash

หมายเหตุ: tokenizer ของ pythainlp จะ "แยก" คำที่สะกดผิดออกเป็นชิ้น ๆ (เช่น "เสรจ" -> เส/รจ)
ดังนั้นเราจึงแยกคำจากช่องว่าง/อักขระกำกับเอง (chunk) แทน ไม่พึ่ง word_tokenize ในการนับคำ
"""
import re

try:
    from pythainlp.spell import spell as _thai_spell
    from pythainlp.tokenize import word_tokenize as _word_tokenize
    _PYTHAINLP_OK = True
except Exception:
    _PYTHAINLP_OK = False
    _thai_spell = None
    _word_tokenize = None

# แยก chunk ของ "คำ" (ตัวอักษร/เลข) โดยเก็บ separator (ช่องว่าง/เครื่องหมาย) ไว้เป็น token เดิม
_CHUNK_RE = re.compile(r"[\u0E00-\u0E7FA-Za-z0-9]+")
_THAI_ONLY_RE = re.compile(r"^[\u0E00-\u0E7F]+$")
_MIN_WORD_LEN = 2

_THAI_DICT = None  # lazy-load thai_words()


def is_available():
    return _PYTHAINLP_OK


def _is_thai(word):
    return bool(_THAI_ONLY_RE.match(word))


def _thai_dict():
    """พจนานุกรมคำไทยของ pythainlp (โหลดครั้งเดียว)"""
    global _THAI_DICT
    if _THAI_DICT is None:
        try:
            from pythainlp.corpus.common import thai_words
            _THAI_DICT = set(thai_words())
        except Exception:
            _THAI_DICT = set()
    return _THAI_DICT


def _edit_distance(a, b):
    """Levenshtein distance (รองรับภาษาไทย: นับเป็นหน่วยรหัสอักษร)"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            ))
        prev = cur
    return prev[-1]


def tokenize_words(text):
    """แยก text เป็น (chunk, is_word) รักษาตำแหน่ง/ช่องว่าง/เครื่องหมายทุกตัว"""
    parts = []
    last = 0
    for m in _CHUNK_RE.finditer(text):
        if m.start() > last:
            parts.append((text[last:m.start()], False))
        parts.append((m.group(), True))
        last = m.end()
    if last < len(text):
        parts.append((text[last:], False))
    return parts


def clean_tokens(text):
    """คืนคำ (chunk) จากข้อความ ใช้สร้างคำศัพท์ของผู้ใช้"""
    return [tok for tok, is_word in tokenize_words(text) if is_word]


def spell_results(word):
    """คืน list ของคำที่ถูกต้องที่เป็นไปได้ (pythainlp 5.x คืน list[str])"""
    if not _PYTHAINLP_OK:
        return []
    try:
        results = _thai_spell(word)
        return list(results) if results else []
    except Exception:
        return []


def _safe_correction(word):
    """คืนคำแก้ที่ "เชื่อถือได้" เท่านั้น: อยู่ในพจนานุกรม + ระยะทางแก้ไข <= 1
    ถ้าไม่มั่นใจคืน None (เก็บคำเดิมไว้)"""
    if not _PYTHAINLP_OK or not _is_thai(word) or len(word) < _MIN_WORD_LEN:
        return None
    if word in _thai_dict():
        return None  # คำถูกต้องอยู่แล้ว
    for cand in spell_results(word):
        if (
            cand != word
            and cand in _thai_dict()
            and _edit_distance(word, cand) <= 1
        ):
            return cand
    return None


def _collect_suspect_runs(subtoks, dictionary):
    """จัดกลุ่ม sub-token ที่ไม่ใช่คำในพจนานุกรมเป็น run ที่ติดกัน
    คืน list ของ (start_index, run) — start_index ไว้ใช้ดึง token ข้างเคียง
    (คำที่สะกดผิดตัวแยกคำจะแยกเป็นชิ้น ๆ เช่น เส + รจ แต่ "เส" เป็นคำจริง จึงได้ run แค่ รจ)
    """
    runs = []
    cur = []
    start = None
    for idx, t in enumerate(subtoks):
        if not t:
            continue
        if _is_thai(t) and t not in dictionary:
            if start is None:
                start = idx
            cur.append(t)
        else:
            if cur:
                runs.append((start, cur))
                cur = []
                start = None
    if cur:
        runs.append((start, cur))
    return runs


def _correct_chunk(chunk, dictionary):
    """แก้คำสะกดภายใน chunk (ข้อความยาวที่เว้นวรรคหรือไม่ก็ได้)
    คืน (ข้อความที่แก้แล้ว, เปลี่ยนไปหรือไม่)"""
    # ทางลัด: ทั้ง chunk เป็นคำผิดคำเดียว (เช่น "เสรจ", "สวสดี")
    corr = _safe_correction(chunk)
    if corr:
        return corr, True

    if not _PYTHAINLP_OK:
        return chunk, False

    try:
        subtoks = [t for t in _word_tokenize(chunk, engine="newmm", keep_whitespace=False) if t and t.strip()]
    except Exception:
        return chunk, False

    if len(subtoks) <= 1:
        return chunk, False

    result = chunk
    changed = False
    for start, run in _collect_suspect_runs(subtoks, dictionary):
        if not any(len(t) >= _MIN_WORD_LEN for t in run):
            continue
        merged = "".join(run)
        # ลอง "เชื่อมกับคำข้างเคียง" ก่อน เพราะชิ้นที่แยกออกมาอาจเป็นส่วนหนึ่งของคำผิดคำเดียว
        # (เช่น รจ คือส่วนหางของ เสรจ ซึ่ง เส เป็นคำจริงในพจนานุกรม)
        candidates = []
        if start > 0:
            candidates.append(subtoks[start - 1] + merged)
        if start + len(run) < len(subtoks):
            candidates.append(merged + subtoks[start + len(run)])
        if start > 0 and start + len(run) < len(subtoks):
            candidates.append(subtoks[start - 1] + merged + subtoks[start + len(run)])

        best = None
        for cand in candidates:
            c = _safe_correction(cand)
            if c:
                best = (cand, c)
                break
        if best is None and len(merged) >= 3 and len(merged) <= 8:
            c = _safe_correction(merged)
            if c:
                best = (merged, c)
        if best:
            m, c = best
            result = result.replace(m, c, 1)
            changed = True
    return result, changed


def resolve_text(text, pref_map, trusted_words):
    """ตรวจ + แก้คำสะกดใน text.

    pref_map: dict {word: corrected} — ค่าว่าง/None หมายถึง "ให้คงคำเดิม"
    trusted_words: set ของคำที่ผู้ใช้เคยใช้จริง (จำนิสัย)
    """
    pref_map = pref_map or {}
    trusted_words = trusted_words or set()
    dictionary = _thai_dict()
    auto_corrected = []
    kept_original = []
    new_tokens = []

    for tok, is_word in tokenize_words(text):
        if not is_word:
            new_tokens.append(tok)
            continue
        w = tok
        # ตรวจเฉพาะคำภาษาไทยที่มีความยาวพอ
        if not _is_thai(w) or len(w) < _MIN_WORD_LEN:
            new_tokens.append(tok)
            continue

        # 1) preference ที่ผู้ใช้ตั้งไว้ชัดเจน (สำคัญสุด)
        if w in pref_map:
            target = pref_map[w]
            if target and target != w:
                new_tokens.append(tok.replace(w, target, 1))
                auto_corrected.append({"original": w, "corrected": target})
            else:
                new_tokens.append(tok)
                kept_original.append(w)
            continue

        # 2) คำที่ผู้ใช้เคยพิมพ์จริง -> ไม่ไปแก้ (จำนิสัย)
        if w in trusted_words:
            new_tokens.append(tok)
            kept_original.append(w)
            continue

        # 3) แก้สะกดแบบ conservative
        corrected, changed = _correct_chunk(w, dictionary)
        new_tokens.append(corrected)
        if changed:
            auto_corrected.append({"original": w, "corrected": corrected})
        elif w not in dictionary:
            kept_original.append(w)

    return {
        "final_text": "".join(new_tokens),
        "auto_corrected": auto_corrected,
        "kept_original": kept_original,
    }
