"""简历管理、Word/PDF 解析与 AI 审阅改写测试。"""
import io

import pytest
from docx import Document

from app.services import llm_client


def _make_docx_bytes() -> bytes:
    doc = Document()
    doc.add_paragraph("张三 - 后端开发工程师")
    doc.add_paragraph("5年 Python / FastAPI 微服务经验")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "技能"
    table.cell(0, 1).text = "FastAPI / SQLite / Docker"
    table.cell(1, 0).text = "意向"
    table.cell(1, 1).text = "北京 / AI 后端"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_minimal_pdf_bytes(text: str = "Resume PDF Sample") -> bytes:
    stream_data = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        ),
        f"4 0 obj << /Length {len(stream_data)} >> stream\n".encode("ascii")
        + stream_data
        + b"\nendstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def test_extract_json_object_variants():
    plain = '{"score": 88, "summary": "good"}'
    fenced = '```json\n{"score": 91, "summary": "great"}\n```'
    noisy = '分析结果如下：\n{"score": 76, "summary": "ok"}\n以上。'
    assert llm_client.extract_json_object(plain)["score"] == 88
    assert llm_client.extract_json_object(fenced)["score"] == 91
    assert llm_client.extract_json_object(noisy)["score"] == 76


@pytest.mark.asyncio
async def test_upload_docx_pdf_and_reject_invalid(auth):
    c = auth["client"]
    headers = {"X-CSRF-Token": auth["csrf"]}

    # 1. 上传 Word (.docx)，自动设为首个激活简历
    docx_bytes = _make_docx_bytes()
    r_docx = await c.post(
        "/api/resumes/upload",
        files={
            "file": (
                "my_resume.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"target_role": "Python 后端"},
        headers=headers,
    )
    assert r_docx.status_code == 200
    d1 = r_docx.json()["data"]
    assert d1["source_format"] == "docx"
    assert d1["is_active"] is True
    assert "FastAPI" in d1["raw_content"]
    assert "AI 后端" in d1["raw_content"]

    # 2. 上传 PDF (.pdf)
    pdf_bytes = _make_minimal_pdf_bytes("ZhangSan Python Backend")
    r_pdf = await c.post(
        "/api/resumes/upload",
        files={"file": ("cv.pdf", pdf_bytes, "application/pdf")},
        data={"title": "PDF 简历"},
        headers=headers,
    )
    assert r_pdf.status_code == 200
    d2 = r_pdf.json()["data"]
    assert d2["source_format"] == "pdf"
    assert d2["is_active"] is False
    assert "ZhangSan Python Backend" in d2["raw_content"]

    # 3. 不支持格式返回 422
    r_bad = await c.post(
        "/api/resumes/upload",
        files={"file": ("old.doc", b"binary", "application/msword")},
        headers=headers,
    )
    assert r_bad.status_code == 422


@pytest.mark.asyncio
async def test_resume_crud_activate_and_ai_review_rewrite(auth, monkeypatch):
    c = auth["client"]
    headers = {"X-CSRF-Token": auth["csrf"]}

    # 创建 AI Provider
    r_prov = await c.post(
        "/api/providers",
        json={
            "name": "ds-pro",
            "base_url": "https://api.example.com/v1",
            "api_format": "openai",
            "model": "deepseek-v4-pro",
            "api_key": "sk-test-key-1234",
        },
        headers=headers,
    )
    assert r_prov.status_code == 200

    # 手动创建简历
    r_create = await c.post(
        "/api/resumes",
        json={
            "title": "初始简历",
            "target_role": "后端工程师",
            "raw_content": "熟悉 Python 和 FastAPI，参与过后台接口开发。",
        },
        headers=headers,
    )
    assert r_create.status_code == 200
    r1_id = r_create.json()["data"]["id"]

    # Mock LLM 审阅响应
    async def fake_complete_json(*, provider, api_key, system_prompt, user_prompt, timeout_seconds=180.0):
        assert api_key == "sk-test-key-1234"
        if "打分" in system_prompt or "score" in system_prompt:
            return {
                "score": 82,
                "summary": "基础扎实，建议补充性能量化指标。",
                "strengths": ["具备 FastAPI 经验"],
                "issues": ["缺少 QPS/延迟数据"],
                "suggestions": ["补充具体业务成果指标"],
            }
        return {
            "title": "初始简历（AI 优化版）",
            "raw_content": "# 个人优势\n5年 Python/FastAPI 后端经验，主导高并发网关架构。",
            "structured_json": {"summary": "5年 Python/FastAPI 经验", "skills": ["Python", "FastAPI"]},
        }

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    # AI 审阅
    r_rev = await c.post(
        f"/api/resumes/{r1_id}/ai-review",
        json={"target_role": "高级 Python 开发"},
        headers=headers,
    )
    assert r_rev.status_code == 200
    rev_data = r_rev.json()["data"]
    assert rev_data["ai_review_json"]["score"] == 82
    assert rev_data["target_role"] == "高级 Python 开发"

    # AI 改写生成新版本
    r_rew = await c.post(
        f"/api/resumes/{r1_id}/ai-rewrite",
        json={"instruction": "突出架构经验"},
        headers=headers,
    )
    assert r_rew.status_code == 200
    rew_data = r_rew.json()["data"]
    r2_id = rew_data["id"]
    assert r2_id != r1_id
    assert rew_data["parent_id"] == r1_id
    assert rew_data["is_active"] is False
    assert "高并发网关" in rew_data["raw_content"]

    # 激活新版本并确认原版本取消激活
    r_act = await c.post(f"/api/resumes/{r2_id}/activate", headers=headers)
    assert r_act.status_code == 200
    assert r_act.json()["data"]["is_active"] is True

    r_old = await c.get(f"/api/resumes/{r1_id}")
    assert r_old.json()["data"]["is_active"] is False

    # 审计日志校验
    r_audit = await c.get("/api/audit-logs?action=resume.ai_rewrite")
    assert r_audit.status_code == 200
    assert r_audit.json()["data"]["total"] == 1

    # 导出 Word (.docx) 与 Markdown (.md)
    r_exp_docx = await c.get(f"/api/resumes/{r2_id}/export?format=docx")
    assert r_exp_docx.status_code == 200
    assert "wordprocessingml" in r_exp_docx.headers["content-type"]
    exported_doc = Document(io.BytesIO(r_exp_docx.content))
    exported_text = "\n".join(p.text for p in exported_doc.paragraphs)
    assert "初始简历（AI 优化版）" in exported_text
    assert "高并发网关架构" in exported_text

    r_exp_md = await c.get(f"/api/resumes/{r2_id}/export?format=md")
    assert r_exp_md.status_code == 200
    assert "text/markdown" in r_exp_md.headers["content-type"]
    assert "高并发网关架构" in r_exp_md.content.decode("utf-8")
