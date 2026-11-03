"""File text extraction — แยกข้อความจากไฟล์ที่ผู้ใช้อัปโหลด

รองรับ: txt/md/csv (text), pdf (pypdf), docx (python-docx), rtf (strip control words)
รูปภาพ (jpg/png/webp) จะไม่ extract ที่นี่ — ส่งเข้า AI vision แทน (ดู ai_service.analyze_image_file)

หลักการ (AGENTS.md §9): ไฟล์ที่อ่านไม่ได้/ไม่รู้จัก → คืนข้อผิดพลาดชัดเจน ไม่ crash
"""

import io
import re

TEXT_EXTS = {"txt", "md", "markdown", "csv", "log", "json"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "bmp"}
SUPPORTED_EXTS = TEXT_EXTS | IMAGE_EXTS | {"pdf", "docx", "rtf"}

# import แบบมี fallback — ถ้าลง library ไม่ครบ แอปยังเปิดได้ และไฟล์นั้น ๆ จะได้ error ชัดเจน
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None
try:
    from docx import Document
except ImportError:
    Document = None


def is_image_file(filename: str) -> bool:
    ext = _ext(filename)
    return ext in IMAGE_EXTS


def is_supported(filename: str) -> bool:
    return _ext(filename) in SUPPORTED_EXTS


def _ext(filename: str) -> str:
    return (filename or "").rsplit(".", 1)[-1].lower()


def _text_from_bytes(data: bytes) -> str:
    """ลอง decode utf-8 ก่อน แล้วค่อย fallback ตาม encoding ที่นิยมใน Windows"""
    for enc in ("utf-8", "cp874", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _strip_rtf(text: str) -> str:
    """เอา control words ของ RTF ออก (เช่น \\rtf1 \\ansi \\b \\par) แต่เก็บข้อความจริงไว้"""
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)   # control words + \uXXXX
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)    # hex byte → ช่องว่าง
    text = text.replace("{", " ").replace("}", " ")   # braces → ช่องว่าง
    return text


def extract_text_from_file(filename: str, data: bytes) -> str:
    """คืนข้อความในไฟล์ (ตัดบรรทัดว่าง/ws ซ้ำ). ไฟล์ที่ไม่รู้จัก → ValueError"""
    ext = _ext(filename)
    if ext in TEXT_EXTS:
        return _clean(_text_from_bytes(data))
    if ext == "pdf":
        if PdfReader is None:
            raise ValueError("ยังไม่ได้ติดตั้ง pypdf — รัน pip install pypdf ก่อน")
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue
        return _clean("\n".join(pages))
    if ext == "docx":
        if Document is None:
            raise ValueError("ยังไม่ได้ติดตั้ง python-docx — รัน pip install python-docx ก่อน")
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return _clean("\n".join(parts))
    if ext == "rtf":
        return _clean(_strip_rtf(_text_from_bytes(data)))
    if ext in IMAGE_EXTS:
        raise ValueError("รูปภาพต้องวิเคราะห์ผ่าน AI vision (ลอง upload เป็น jpg/png/webp ตรง ๆ)")
    raise ValueError(
        f"ไฟล์ .{ext} ยังอ่านไม่ได้ — ลองแปลงเป็น PDF/Word/ข้อความ หรือรูปภาพก่อน"
    )


def _clean(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines).strip()
