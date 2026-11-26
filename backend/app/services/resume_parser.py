"""简历文件解析器：支持 PDF（.pdf）、Word（.docx）与 Markdown/纯文本。"""
import io
from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.exceptions import ValidationError

MAX_RESUME_UPLOAD_BYTES = 5 * 1024 * 1024


def _normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned: list[str] = []
    blank_streak = 0
    for line in lines:
        if not line.strip():
            blank_streak += 1
            if blank_streak <= 1 and cleaned:
                cleaned.append("")
        else:
            blank_streak = 0
            cleaned.append(line)
    return "\n".join(cleaned).strip()


def _extract_pdf(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
    except (PdfReadError, ValueError, OSError) as exc:
        raise ValidationError(f"PDF 文件解析失败：{exc}") from exc

    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except (PdfReadError, ValueError, KeyError, TypeError):
            text = ""
        if text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)


def _extract_docx(content: bytes) -> str:
    try:
        doc = Document(io.BytesIO(content))
    except (PackageNotFoundError, ValueError, OSError, KeyError) as exc:
        raise ValidationError(f"Word (.docx) 文件解析失败：{exc}") from exc

    parts: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())

    for table in doc.tables:
        for row in table.rows:
            cells: list[str] = []
            for cell in row.cells:
                val = " ".join(cell.text.split())
                if val and (not cells or cells[-1] != val):
                    cells.append(val)
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return content.decode("gb18030")
        except UnicodeDecodeError as exc:
            raise ValidationError("文本文件编码无法识别，请使用 UTF-8 或 GB18030") from exc


def parse_resume_upload(filename: str, content: bytes) -> tuple[str, str]:
    """解析上传的简历文件，返回 `(source_format, extracted_text)`。"""
    if not content:
        raise ValidationError("上传文件为空")
    if len(content) > MAX_RESUME_UPLOAD_BYTES:
        raise ValidationError("文件大小不能超过 5MB")

    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        fmt = "pdf"
        raw = _extract_pdf(content)
    elif ext == ".docx":
        fmt = "docx"
        raw = _extract_docx(content)
    elif ext in {".md", ".markdown"}:
        fmt = "markdown"
        raw = _extract_text(content)
    elif ext == ".txt":
        fmt = "text"
        raw = _extract_text(content)
    elif ext == ".doc":
        raise ValidationError("暂不支持旧版 .doc 二进制格式，请在 Word/WPS 中另存为 .docx 或 .pdf 后上传")
    else:
        raise ValidationError("不支持的文件格式，仅支持 .pdf、.docx、.md、.txt")

    normalized = _normalize_text(raw)
    if not normalized:
        raise ValidationError("未能从文件中提取到有效简历文本")
    return fmt, normalized
