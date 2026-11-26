"""Windows Local Agent 持久化浏览器管理与 BOSS 页面状态检测。

设计原则：
1. 使用真实可见桌面 Chrome/Edge + Persistent Profile 复用人工登录态；
2. 延迟导入 playwright，确保未安装浏览器二进制的无头测试环境也可导入运行；
3. 严禁任何验证码/滑块/反爬绕过逻辑，遇到登录页或风控页立即返回 needs_human_action=True。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

from agent.config import AgentSettings

logger = logging.getLogger("agent.browser")

_VERIFY_URL_TOKENS = ("verify", "captcha", "slider", "geetest")
_VERIFY_TEXT_TOKENS = ("安全验证", "人机验证", "拖动滑块", "完成验证", "点击按钮进行验证")
_LOGIN_URL_TOKENS = ("/web/user", "login")
_LOGIN_TEXT_TOKENS = ("扫码登录", "验证码登录", "app扫码", "密码登录", "立即登录")


class BossBrowserAdapter(Protocol):
    """BOSS 浏览器适配器协议（便于单元测试注入 mock）。"""

    async def check_boss_login(self) -> dict[str, Any]: ...

    async def sync_boss_resume(
        self,
        *,
        title: str,
        target_role: str | None,
        advantage_text: str,
        skills: list[str],
        raw_content: str,
        structured_json: dict[str, Any],
        dry_run: bool,
    ) -> dict[str, Any]: ...

    async def scan_boss_jobs(
        self,
        *,
        keywords: list[str],
        city: str | None,
        max_jobs: int,
        dry_run: bool,
    ) -> dict[str, Any]: ...

    async def apply_boss_job(
        self,
        *,
        boss_job_id: str,
        title: str,
        company: str,
        job_url: str | None,
        greeting: str,
        dry_run: bool,
    ) -> dict[str, Any]: ...

    async def close(self) -> None: ...


def detect_boss_page_state(url: str, page_text: str) -> dict[str, Any]:
    """根据页面 URL 与可见文本判定 BOSS 直聘登录与风控状态。"""
    lower_url = (url or "").lower()
    text = page_text or ""
    lower_text = text.lower()

    if any(tok in lower_url for tok in _VERIFY_URL_TOKENS) or any(
        tok in text for tok in _VERIFY_TEXT_TOKENS
    ):
        return {
            "logged_in": False,
            "needs_human_action": True,
            "reason": "verification_required",
            "message": "检测到 BOSS 直聘安全/人机验证，请在本地浏览器窗口手动完成后重试",
            "current_url": url,
        }

    if any(tok in lower_url for tok in _LOGIN_URL_TOKENS) or any(
        tok in lower_text for tok in _LOGIN_TEXT_TOKENS
    ):
        return {
            "logged_in": False,
            "needs_human_action": True,
            "reason": "login_required",
            "message": "BOSS 直聘尚未登录或登录已过期，请在本地浏览器窗口手动扫码登录",
            "current_url": url,
        }

    if "/web/geek/" in lower_url or (
        "/job_detail/" in lower_url
        and ("立即沟通" in text or "继续沟通" in text)
        and "登录/注册" not in text
    ):
        return {
            "logged_in": True,
            "needs_human_action": False,
            "reason": "ok",
            "message": "BOSS 直聘登录状态有效",
            "current_url": url,
        }

    return {
        "logged_in": False,
        "needs_human_action": True,
        "reason": "login_required",
        "message": "未能确认 BOSS 直聘登录状态，请在本地浏览器窗口确认登录情况",
        "current_url": url,
    }


class PersistentBrowserManager:
    """管理单个可见桌面持久化 Playwright 浏览器上下文。"""

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._playwright: Any = None
        self._context: Any = None

    def _channel_candidates(self) -> list[str | None]:
        candidates: list[str | None] = []
        for ch in (self._settings.browser_channel, "chrome", "msedge", None):
            normalized = ch.strip() if isinstance(ch, str) and ch.strip() else None
            if normalized not in candidates:
                candidates.append(normalized)
        return candidates

    async def _ensure_context(self) -> Any:
        if self._context is not None:
            return self._context

        from playwright.async_api import async_playwright

        profile_dir = Path(os.path.expandvars(self._settings.browser_profile_dir)).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)

        pw = await async_playwright().start()
        last_exc: Exception | None = None
        for channel in self._channel_candidates():
            launch_kwargs: dict[str, Any] = {
                "user_data_dir": str(profile_dir),
                "headless": self._settings.browser_headless,
                "viewport": {"width": 1366, "height": 900},
            }
            if channel is not None:
                launch_kwargs["channel"] = channel
            try:
                ctx = await pw.chromium.launch_persistent_context(**launch_kwargs)
                self._playwright = pw
                self._context = ctx
                logger.info(
                    "已启动持久化浏览器（channel=%s, profile=%s）",
                    channel or "chromium",
                    profile_dir,
                )
                return ctx
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("尝试启动浏览器 channel=%s 失败: %s", channel or "chromium", exc)

        await pw.stop()
        raise RuntimeError(f"无法启动持久化浏览器，请确认已安装 Chrome/Edge/Playwright: {last_exc}")

    async def _get_page(self) -> Any:
        ctx = await self._ensure_context()
        pages = getattr(ctx, "pages", None) or []
        for page in pages:
            if not page.is_closed():
                return page
        return await ctx.new_page()

    async def _goto_and_inspect(self, url: str) -> tuple[Any, dict[str, Any]]:
        page = await self._get_page()
        timeout = self._settings.browser_action_timeout_ms
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        try:
            await page.wait_for_load_state("networkidle", timeout=min(timeout, 5000))
        except Exception as exc:  # noqa: BLE001
            logger.debug("等待页面 networkidle 超时或提前返回，继续检查状态: %s", exc)

        body_text = ""
        try:
            body_text = await page.locator("body").inner_text(timeout=3000)
        except Exception:  # noqa: BLE001
            body_text = ""

        state = detect_boss_page_state(page.url, body_text)
        return page, state

    async def check_boss_login(self) -> dict[str, Any]:
        async with self._lock:
            _, state = await self._goto_and_inspect(self._settings.boss_resume_url)
            return state

    async def sync_boss_resume(
        self,
        *,
        title: str,
        target_role: str | None,
        advantage_text: str,
        skills: list[str],
        raw_content: str,
        structured_json: dict[str, Any],
        dry_run: bool,
    ) -> dict[str, Any]:
        preview = {
            "title": title,
            "target_role": target_role,
            "advantage_text": advantage_text,
            "skills": skills,
        }
        async with self._lock:
            page, state = await self._goto_and_inspect(self._settings.boss_resume_url)
            if state["needs_human_action"]:
                return {
                    "synced": False,
                    "dry_run": dry_run,
                    "logged_in": False,
                    "needs_human_action": True,
                    "reason": state["reason"],
                    "message": state["message"],
                    "current_url": state["current_url"],
                    "preview": preview,
                }

            if dry_run:
                return {
                    "synced": False,
                    "dry_run": True,
                    "logged_in": True,
                    "needs_human_action": False,
                    "reason": "dry_run_preview",
                    "message": "预演模式通过：BOSS 登录态有效，已生成同步预览（未改动线上简历）",
                    "current_url": state["current_url"],
                    "preview": preview,
                }

            updated = await self._try_fill_advantage(page, advantage_text)
            if not updated:
                return {
                    "synced": False,
                    "dry_run": False,
                    "logged_in": True,
                    "needs_human_action": True,
                    "reason": "manual_paste_required",
                    "message": "未能自动定位 BOSS 在线简历「个人优势」编辑框，请在本地浏览器中核对并粘贴预览内容后保存",
                    "current_url": page.url,
                    "preview": preview,
                }

            return {
                "synced": True,
                "dry_run": False,
                "logged_in": True,
                "needs_human_action": False,
                "reason": "ok",
                "message": "已将「个人优势」同步更新至 BOSS 在线简历",
                "current_url": page.url,
                "preview": preview,
            }

    async def _try_fill_advantage(self, page: Any, advantage_text: str) -> bool:
        """尝试定位并更新 BOSS 在线简历的「个人优势」字段，未命中时返回 False 由人工接管。"""
        timeout = min(self._settings.browser_action_timeout_ms, 5000)
        section_selectors = [
            "xpath=//*[contains(@class,'resume-item') or self::section][.//*[contains(text(),'个人优势')]]",
            "xpath=//*[contains(text(),'个人优势')]/ancestor::*[contains(@class,'item') or self::div][1]",
        ]
        try:
            container = None
            for sel in section_selectors:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    container = loc
                    break
            if container is None:
                return False

            edit_btn = container.locator(
                "a:has-text('编辑'), button:has-text('编辑'), [class*='edit']"
            ).first
            if await edit_btn.count() > 0:
                await edit_btn.click(timeout=timeout)

            textarea = page.locator("textarea:visible").first
            if await textarea.count() == 0:
                return False
            await textarea.fill(advantage_text, timeout=timeout)

            save_btn = page.locator(
                "button:has-text('保存'):visible, a:has-text('保存'):visible"
            ).first
            if await save_btn.count() == 0:
                return False
            await save_btn.click(timeout=timeout)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("自动写入 BOSS 在线简历个人优势失败，转为人工核对: %s", exc)
            return False

    async def scan_boss_jobs(
        self,
        *,
        keywords: list[str],
        city: str | None,
        max_jobs: int,
        dry_run: bool,
    ) -> dict[str, Any]:
        query = " ".join(k.strip() for k in keywords if k.strip())
        params: dict[str, str] = {}
        if query:
            params["query"] = query
        if city and city.strip():
            params["cityName"] = city.strip()
        base = self._settings.boss_jobs_url.rstrip("?")
        target_url = f"{base}?{urlencode(params)}" if params else base

        async with self._lock:
            page, state = await self._goto_and_inspect(target_url)
            if state["needs_human_action"]:
                return {
                    "jobs": [],
                    "dry_run": dry_run,
                    "logged_in": False,
                    "needs_human_action": True,
                    "reason": state["reason"],
                    "message": state["message"],
                    "current_url": state["current_url"],
                }

            if dry_run:
                return {
                    "jobs": [],
                    "dry_run": True,
                    "logged_in": True,
                    "needs_human_action": False,
                    "reason": "dry_run_preview",
                    "message": "预演模式：搜索页与登录态校验通过（未抓取列表）",
                    "current_url": page.url,
                }

            raw_cards = await page.evaluate(
                """(limit) => {
                  const cards = Array.from(document.querySelectorAll('.job-card-wrapper, li.job-card-box, [data-jobid]'));
                  return cards.slice(0, limit).map((el, idx) => {
                    const link = el.querySelector('a[href*="job_detail"], a.job-card-left');
                    const href = link ? (link.getAttribute('href') || '') : '';
                    const titleEl = el.querySelector('.job-name, .job-title, h3');
                    const companyEl = el.querySelector('.company-name, .company-text a');
                    const salaryEl = el.querySelector('.salary, .red');
                    const cityEl = el.querySelector('.job-area, .job-area-wrapper');
                    const tagEls = Array.from(el.querySelectorAll('.tag-list li, .job-tag'));
                    return {
                      job_id_attr: el.getAttribute('data-jobid') || '',
                      href,
                      title: titleEl ? titleEl.textContent.trim() : '',
                      company: companyEl ? companyEl.textContent.trim() : '',
                      salary: salaryEl ? salaryEl.textContent.trim() : '',
                      city: cityEl ? cityEl.textContent.trim() : '',
                      tags: tagEls.map(t => (t.textContent || '').trim()).filter(Boolean),
                      idx,
                    };
                  });
                }""",
                max_jobs,
            )

            jobs: list[dict[str, Any]] = []
            for item in raw_cards or []:
                title = str(item.get("title") or "").strip()
                company = str(item.get("company") or "").strip()
                if not title or not company:
                    continue
                href = str(item.get("href") or "").strip()
                attr_id = str(item.get("job_id_attr") or "").strip()
                matched = re.search(r"job_detail/([^./?]+)", href)
                boss_job_id = attr_id or (matched.group(1) if matched else f"boss-{len(jobs)+1}")
                full_url = (
                    href
                    if href.startswith("http")
                    else (f"{self._settings.boss_base_url.rstrip('/')}{href}" if href else None)
                )
                jobs.append(
                    {
                        "boss_job_id": boss_job_id,
                        "title": title,
                        "company": company,
                        "salary": str(item.get("salary") or "").strip() or None,
                        "city": str(item.get("city") or "").strip() or None,
                        "job_url": full_url,
                        "tags": item.get("tags") or [],
                    }
                )

            return {
                "jobs": jobs,
                "scanned_count": len(jobs),
                "dry_run": False,
                "logged_in": True,
                "needs_human_action": False,
                "reason": "ok",
                "message": f"已扫描获取 {len(jobs)} 个 BOSS 岗位",
                "current_url": page.url,
            }

    async def apply_boss_job(
        self,
        *,
        boss_job_id: str,
        title: str,
        company: str,
        job_url: str | None,
        greeting: str,
        dry_run: bool,
    ) -> dict[str, Any]:
        target_url = (
            job_url.strip()
            if job_url and job_url.strip()
            else f"{self._settings.boss_base_url.rstrip('/')}/job_detail/{boss_job_id}.html"
        )
        async with self._lock:
            page, state = await self._goto_and_inspect(target_url)
            if state["needs_human_action"]:
                return {
                    "applied": False,
                    "dry_run": dry_run,
                    "logged_in": False,
                    "needs_human_action": True,
                    "reason": state["reason"],
                    "message": state["message"],
                    "current_url": state["current_url"],
                }

            continue_btn = page.locator(
                "a:has-text('继续沟通'):visible, button:has-text('继续沟通'):visible"
            ).first
            if await continue_btn.count() > 0:
                return {
                    "applied": True,
                    "already_applied": True,
                    "dry_run": dry_run,
                    "logged_in": True,
                    "needs_human_action": False,
                    "reason": "already_applied",
                    "message": f"此前已与「{company} - {title}」沟通过，已自动去重",
                    "current_url": page.url,
                }

            if dry_run:
                return {
                    "applied": False,
                    "dry_run": True,
                    "logged_in": True,
                    "needs_human_action": False,
                    "reason": "dry_run_preview",
                    "message": f"预演检查通过：可在桌面浏览器向「{title}」发送打招呼",
                    "greeting": greeting,
                    "current_url": page.url,
                }

            timeout = min(self._settings.browser_action_timeout_ms, 5000)
            try:
                chat_btn = page.locator(
                    "a.btn-startchat:visible, a:has-text('立即沟通'):visible, button:has-text('立即沟通'):visible"
                ).first
                if await chat_btn.count() == 0:
                    return {
                        "applied": False,
                        "dry_run": False,
                        "logged_in": True,
                        "needs_human_action": True,
                        "reason": "manual_apply_required",
                        "message": "未定位到「立即沟通」按钮，请在本地浏览器手动核对并投递",
                        "current_url": page.url,
                    }
                await chat_btn.click(timeout=timeout)
                input_box = page.locator(
                    "textarea:visible, .chat-input [contenteditable='true']:visible"
                ).first
                if await input_box.count() > 0:
                    await input_box.fill(greeting, timeout=timeout)
                    send_btn = page.locator("button:has-text('发送'):visible").first
                    if await send_btn.count() > 0:
                        await send_btn.click(timeout=timeout)
                return {
                    "applied": True,
                    "dry_run": False,
                    "logged_in": True,
                    "needs_human_action": False,
                    "reason": "ok",
                    "message": f"已向「{company} - {title}」发送沟通",
                    "current_url": page.url,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("自动点击立即沟通失败，转为人工处理: %s", exc)
                return {
                    "applied": False,
                    "dry_run": False,
                    "logged_in": True,
                    "needs_human_action": True,
                    "reason": "manual_apply_required",
                    "message": f"自动投递受阻，请在本地浏览器手动完成沟通：{exc}",
                    "current_url": page.url,
                }

    async def close(self) -> None:
        async with self._lock:
            if self._context is not None:
                try:
                    await self._context.close()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("关闭持久化浏览器上下文时忽略异常: %s", exc)
                self._context = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("停止 Playwright 实例时忽略异常: %s", exc)
                self._playwright = None
