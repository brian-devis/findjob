"""AI Provider 统一调用客户端（支持 OpenAI 流式 SSE 与 Anthropic Messages）。"""
import json
import re
from typing import Any

import httpx

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.models.ai_provider import AIProvider

logger = get_logger("app.services.llm_client")

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型文本响应中提取 JSON 对象（自动剥离 Markdown 代码围栏）。"""
    cleaned = text.strip()
    match = _CODE_FENCE_RE.match(cleaned)
    if match:
        cleaned = match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise AppError("AI 返回内容不包含有效的 JSON 对象", status_code=502, code=1502) from None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AppError(f"AI 返回 JSON 解析失败：{exc}", status_code=502, code=1502) from exc

    if not isinstance(parsed, dict):
        raise AppError("AI 返回格式错误：顶层必须为 JSON 对象", status_code=502, code=1502)
    return parsed


async def _parse_openai_sse(response: httpx.Response) -> str:
    parts: list[str] = []
    async for line in response.aiter_lines():
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data:
            continue
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(chunk, dict) and chunk.get("error"):
            err = chunk["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise AppError(f"AI 上游流式返回错误：{msg}", status_code=502, code=1502)
        choices = chunk.get("choices") if isinstance(chunk, dict) else None
        if choices and isinstance(choices, list):
            delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    parts.append(content)
    out = "".join(parts).strip()
    if not out:
        raise AppError("AI 上游返回内容为空", status_code=502, code=1502)
    return out


async def _call_openai(
    *,
    base_url: str,
    api_key: str | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream, application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "stream": True,
    }

    async with (
        httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=15.0)) as client,
        client.stream("POST", url, headers=headers, json=payload) as resp,
    ):
        if resp.status_code >= 400:
            body = (await resp.aread()).decode("utf-8", errors="replace")[:300]
            raise AppError(
                f"AI 上游请求失败（HTTP {resp.status_code}）：{body}",
                status_code=502,
                code=1502,
            )
        content_type = resp.headers.get("content-type", "").lower()
        if "text/event-stream" in content_type:
            return await _parse_openai_sse(resp)
        raw = await resp.aread()
        data = json.loads(raw.decode("utf-8"))
        choices = data.get("choices") or []
        if not choices:
            raise AppError("AI 上游返回空 choices", status_code=502, code=1502)
        text = (choices[0].get("message") or {}).get("content", "")
        if not isinstance(text, str) or not text.strip():
            raise AppError("AI 上游返回内容为空", status_code=502, code=1502)
        return text.strip()


async def _call_anthropic(
    *,
    base_url: str,
    api_key: str | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float,
) -> str:
    url = base_url.rstrip("/") + "/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    if api_key:
        headers["x-api-key"] = api_key

    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=15.0)) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise AppError(
                f"AI 上游请求失败（HTTP {resp.status_code}）：{resp.text[:300]}",
                status_code=502,
                code=1502,
            )
        data = resp.json()
        blocks = data.get("content") or []
        texts = [
            b.get("text", "")
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        joined = "".join(texts).strip()
        if not joined:
            raise AppError("AI 上游返回内容为空", status_code=502, code=1502)
        return joined


async def complete_json(
    *,
    provider: AIProvider,
    api_key: str | None,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """调用指定 AIProvider 并解析返回的 JSON 对象。"""
    try:
        if provider.api_format == "anthropic":
            raw_text = await _call_anthropic(
                base_url=provider.base_url,
                api_key=api_key,
                model=provider.model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_seconds=timeout_seconds,
            )
        else:
            raw_text = await _call_openai(
                base_url=provider.base_url,
                api_key=api_key,
                model=provider.model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_seconds=timeout_seconds,
            )
    except AppError:
        raise
    except httpx.HTTPError as exc:
        logger.warning("调用 AI Provider(%s) 网络异常: %s", provider.name, exc)
        raise AppError(f"调用 AI 上游网络异常：{exc}", status_code=502, code=1502) from exc

    return extract_json_object(raw_text)
