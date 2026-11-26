"""简历导出服务（Word .docx 与 Markdown）。"""
from __future__ import annotations

import io
import re
from urllib.parse import quote

from docx import Document


def build_content_disposition(title: str, ext: str) -> str:
    """构造同时兼容 ASCII 与 UTF-8 文件名的 Content-Disposition 头。"""
    clean_title = re.sub(r'[\\/:*?"<>|\r\n]+', "_", (title or "resume")).strip() or "resume"
    full_name = f"{clean_title}.{ext}"
    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", clean_title).strip("_") or "resume"
    encoded = quote(full_name)
    return f'attachment; filename="{ascii_fallback}.{ext}"; filename*=UTF-8\'\'{encoded}'


def build_resume_markdown(*, title: str, target_role: str | None, raw_content: str) -> bytes:
    """导出为带元信息头部的 Markdown 文件字节。"""
    lines = [f"# {title.strip() or '个人简历'}"]
    if target_role and target_role.strip():
        lines.append(f"\n> 目标岗位：{target_role.strip()}")
    lines.append("")
    lines.append((raw_content or "").strip())
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def build_resume_docx(*, title: str, target_role: str | None, raw_content: str) -> bytes:
    """将简历标题、目标岗位与正文渲染为 Word (.docx) 字节流。"""
    doc = Document()
    doc.add_heading(title.strip() or "个人简历", level=1)
    if target_role and target_role.strip():
        doc.add_paragraph(f"目标岗位：{target_role.strip()}")

    for raw_line in (raw_content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=3)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=2)
        elif line.startswith(("- ", "* ", "• ")):
            doc.add_paragraph(line[2:].strip(), style="List Bullet")
        else:
            doc.add_paragraph(line)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
