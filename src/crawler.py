"""
Multi-channel Crawler & Prober for AI Relay Stations.
Channels supported:
1. Reference Seed & GitHub Repository (`panxunying/ai-coding-welfare` sites.json & live.json)
2. GitHub Issues Community Submissions (`/repos/panxunying/ai-coding-welfare/issues`)
3. Search Engine Dorking (Google / Bing / DuckDuckGo HTML search for New-API / One-API relay stations)
4. Live New-API / One-API / Relay Station Prober (`/api/status`, `/api/pricing`, and redirect URL tracking)
"""

from __future__ import annotations

import html
import json
import logging
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.db import RelayDatabase, slugify, utc_now_iso, validate_url

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36 ai-relay-crawler/1.0"
)

RATIO_USD_PER_MTOK = 2.0

# Built-in curated baseline from panxunying/ai-coding-welfare + GitHub community issues
# Ensures offline/fallback resilience while supporting live probing and updates.
BUILTIN_SITES_SEED: List[Dict[str, Any]] = [
    {
        "id": "docode",
        "name": "DoCode",
        "subtitle": "New API 中转站 · 注册送 50 站内刀，注册时填邀请码 zIA2 再加 250，首日 300 刀，Claude 与 GPT 都在架上",
        "panel": "newapi",
        "signupUrl": "https://docode.cc/register?aff=zIA2",
        "homeUrl": "https://docode.cc",
        "statusApi": "https://docode.cc/api/status",
        "pricingApi": "https://docode.cc/api/pricing",
        "inviteCode": "zIA2",
        "credits": {"signup": 50, "invite": 250, "dailyCheckin": None, "unit": "site-usd"},
        "recharge_ratio": "price=0.02（活动1元=50站内刀，日常1:25；Stripe单价¥8）",
        "price_rate": 0.02,
        "stripe_unit_price": 8.0,
        "register": {
            "methods": ["邮箱 + 密码（需邮箱验证码 + Turnstile）"],
            "requirements": [
                "邀请码 = zIA2，从带 ?aff=zIA2 链接进入注册，立得 50 + 250 = 300 站内刀",
                "只能邮箱 + 密码建号，开启邮箱验证（email_verification=true）",
                "主域名打不开时可切换直连美国备用入口 https://api.docode.cc/register?aff=zIA2"
            ],
        },
        "endpoints": {"anthropic": "https://docode.cc", "openai": "https://docode.cc/v1"},
        "mirrors": [
            {"label": "直连美国", "homeUrl": "https://api.docode.cc", "signupUrl": "https://api.docode.cc/register?aff=zIA2"},
            {"label": "江浙沪专线", "homeUrl": "https://api.haogpt.net", "signupUrl": "https://api.haogpt.net/register?aff=zIA2"},
        ],
        "tags": ["New API", "免费额度", "Claude Code", "Codex", "Anthropic 兼容", "OpenAI 兼容"],
        "highlights": [
            "注册送 50 站内刀 + 邀请码 zIA2 赠送 250 站内刀，首日合计 300 站内刀",
            "Claude (sonnet-5 / opus4.6) 与 GPT (gpt-6.1-sol / pro) 同时在架，支持生图 img.docode.cc",
            "支持 Cherry Studio、CC Switch、DeepChat、Lobe Chat 一键导入"
        ],
        "activities_summary": "注册送50刀+邀请码zIA2送250刀；限时充值翻倍1元=50刀，充100送500刀、充200送1500刀、充500送6500刀；中秋VIP赠送1500~5000额度",
    },
    {
        "id": "agentrouter",
        "name": "AgentRouter",
        "subtitle": "AI Coding 公益站 · 注册即送 $100，邀请再送 $50，每日签到 $25",
        "panel": "newapi",
        "signupUrl": "https://agentrouter.org/register?aff=szt3",
        "homeUrl": "https://agentrouter.org",
        "docsUrl": "https://agentrouter.org/docs/index.html",
        "statusApi": "https://agentrouter.org/api/status",
        "pricingApi": "https://agentrouter.org/api/pricing",
        "inviteCode": "szt3",
        "credits": {"signup": 100, "invite": 50, "dailyCheckin": 25, "unit": "usd"},
        "recharge_ratio": "纯公益免费站（不支持充值，按注册+邀请+每日签到发放美元额度）",
        "register": {
            "methods": ["GitHub OAuth", "LinuxDO OAuth"],
            "requirements": [
                "务必从邀请链接 https://agentrouter.org/register?aff=szt3 进入注册，额外拿 $50",
                "注册成功后退出再重新登录一次，额度显示到账"
            ],
        },
        "endpoints": {"anthropic": "https://agentrouter.org", "openai": "https://agentrouter.org/v1"},
        "mirrors": [
            {"label": "大陆备用域名", "homeUrl": "https://ps.air-outer.com", "signupUrl": "https://ps.air-outer.com/register?aff=szt3"}
        ],
        "tags": ["公益站", "免费额度", "Claude Code", "Codex", "Anthropic 兼容"],
        "highlights": [
            "注册即送 $100 + 邀请链接 $50 + 每日签到 $25，首日合计 $175",
            "同时支持 Anthropic 与 OpenAI 兼容协议，直连 Claude Code / Codex / Cursor"
        ],
        "activities_summary": "注册送$100+邀请链接送$50+每日签到$25/天；绑定邮箱参与官方抽奖兑换码；每日10:00和19:00分批投放Claude/GPT额度",
    },
    {
        "id": "conduit",
        "name": "Conduit",
        "subtitle": "注册赠送 $500 额度 · 支持 GPT-6、Fable 5.1 等模型，Telegram 机器人注册",
        "panel": "relay",
        "signupUrl": "https://t.me/conduitoff_bot?start=ref_8111640723",
        "homeUrl": "https://t.me/conduitoff_bot",
        "statusApi": "https://t.me/conduitoff_bot",
        "inviteCode": "ref_8111640723",
        "credits": {"signup": 500, "invite": None, "dailyCheckin": None, "unit": "usd"},
        "recharge_ratio": "注册直接赠送 $500 体验额度（Telegram Bot 内核销）",
        "register": {
            "methods": ["Telegram 机器人 (@conduitoff_bot)"],
            "requirements": [
                "需要 Telegram 账号，通过完整邀请链接进入 @conduitoff_bot，保留 start=ref_8111640723",
                "点击 Start 后按机器人提示完成注册并查看 $500 余额"
            ],
        },
        "endpoints": {"anthropic": "", "openai": ""},
        "tags": ["免费额度", "注册 $500", "GPT-6", "Fable 5.1", "Telegram"],
        "highlights": ["注册即送 $500 额度", "支持 GPT-6、Fable 5.1 等前沿模型"],
        "activities_summary": "通过 Telegram 邀请链接启动机器人注册即赠 $500 API 额度",
    },
    {
        "id": "anyrouter",
        "name": "AnyRouter",
        "subtitle": "New API 中转站 · 注册送 $75，邀请再加 $50，每日签到 $25，首日 $150",
        "panel": "newapi",
        "signupUrl": "https://anyrouter.top/register?aff=Z24N",
        "homeUrl": "https://anyrouter.top",
        "statusApi": "https://anyrouter.top/api/status",
        "inviteCode": "Z24N",
        "credits": {"signup": 75, "invite": 50, "dailyCheckin": 25, "unit": "usd"},
        "recharge_ratio": "按 Token 计费（输入 $5/M、输出 $25/M），注册+邀请+签到免费领",
        "register": {
            "methods": ["GitHub OAuth (需满5年)", "LinuxDO OAuth (无年限门槛)"],
            "requirements": [
                "从邀请链接带 ?aff=Z24N 进入注册，额外获赠 $50",
                "GitHub 账号需满 5 年，不满 5 年请走 LinuxDO 授权登录"
            ],
        },
        "endpoints": {"anthropic": "https://anyrouter.top", "openai": "https://anyrouter.top/v1"},
        "tags": ["New API", "免费额度", "签到", "Claude Code", "Anthropic 兼容", "OpenAI 兼容"],
        "highlights": [
            "注册送 $75 + 邀请链接 $50 + 每日签到 $25，首日可得 $150",
            "Anthropic 与 OpenAI 双原生路由支持"
        ],
        "activities_summary": "新用户注册送$75+邀请码Z24N加送$50+每日签到$25（首日$150）；邀请好友注册享额外返利",
    },
    {
        "id": "kktoken",
        "name": "KKtoken AI",
        "subtitle": "New API 中转站 · 注册送 $75，邀请码再加 $25，每日签到 $20，输入输出 $1/M",
        "panel": "newapi",
        "signupUrl": "https://kktoken.cc/sign-up?aff=MzG9",
        "homeUrl": "https://kktoken.cc",
        "docsUrl": "https://kktoken.cc/dashboard/overview",
        "statusApi": "https://kktoken.cc/api/status",
        "inviteCode": "MzG9",
        "credits": {"signup": 75, "invite": 25, "dailyCheckin": 20, "unit": "usd"},
        "recharge_ratio": "¥7.3 ≈ $1（Stripe 通道 ¥8/$1；输入/输出各 $1 / 1M tokens）",
        "price_rate": 7.3,
        "stripe_unit_price": 8.0,
        "register": {
            "methods": ["GitHub OAuth (需满365天)"],
            "requirements": [
                "通过带 ?aff=MzG9 邀请链接注册立得 $75 + $25",
                "仅开放 GitHub 授权建号（账号需满 365 天），注册后可设置密码"
            ],
        },
        "endpoints": {"anthropic": "https://kktoken.cc", "openai": "https://kktoken.cc/v1"},
        "tags": ["New API", "免费额度", "签到", "按 token 计费", "Anthropic 兼容", "OpenAI 兼容"],
        "highlights": [
            "首日合计 $120（注册 $75 + 邀请 $25 + 首签 $20）",
            "按 token 计费，输入输出均为 $1 / 百万 tokens"
        ],
        "activities_summary": "注册送$75+邀请链接送$25+每日签到$20/天；长对话按token计费仅$1/M",
    },
    {
        "id": "justdowork",
        "name": "JustDoWork",
        "subtitle": "New API 中转站 · GitHub 一键登录，注册送 $70 + 每日签到 ≈$22",
        "panel": "newapi",
        "signupUrl": "https://api.justwoker.icu/register?aff=8lTQ",
        "homeUrl": "https://api.justwoker.icu",
        "docsUrl": "https://api.justwoker.icu/dashboard/overview",
        "statusApi": "https://api.justwoker.icu/api/status",
        "inviteCode": "8lTQ",
        "credits": {"signup": 70, "invite": None, "dailyCheckin": 22, "unit": "usd"},
        "recharge_ratio": "公益签到 + 在线兑换码（Quota单位 500000 = $1）",
        "register": {
            "methods": ["GitHub OAuth (需满365天)"],
            "requirements": [
                "已关闭邮箱密码注册，仅限注册满 365 天的 GitHub 账号登录",
                "从 ?aff=8lTQ 邀请链接进入注册"
            ],
        },
        "endpoints": {"anthropic": "https://api.justwoker.icu", "openai": "https://api.justwoker.icu/v1"},
        "tags": ["New API", "免费额度", "签到", "绘图", "OpenAI 兼容"],
        "highlights": ["注册即得 $70，每日签到约 $22，首日合计 ≈$92", "支持 Cherry Studio / DeepChat / CC Switch 一键导入"],
        "activities_summary": "注册送$70+每日签到领≈$22；官方公告不定期发放活动兑换码",
    },
    {
        "id": "cheapcodex",
        "name": "CheapCodex",
        "subtitle": "自研 AI 网关 · 邀请码送 $20，每日签到再 $20，OpenAI / Anthropic / Codex 三协议",
        "panel": "relay",
        "signupUrl": "https://api.cheapcodex.online/register?aff=U7SSQZSDB36S",
        "homeUrl": "https://api.cheapcodex.online",
        "statusApi": "https://api.cheapcodex.online/v1/models",
        "inviteCode": "U7SSQZSDB36S",
        "credits": {"signup": None, "invite": 20, "dailyCheckin": 20, "unit": "usd"},
        "recharge_ratio": "外置收单 pay.ldxp.cn 订阅制 + 免费签到 $20/天",
        "register": {
            "methods": ["邮箱注册"],
            "requirements": [
                "从带 ?aff=U7SSQZSDB36S 的邀请链接进入注册立得 $20",
                "仅需邮箱注册，无需第三方 OAuth 与 Turnstile 验证"
            ],
        },
        "endpoints": {"anthropic": "https://api.cheapcodex.online", "openai": "https://api.cheapcodex.online/v1"},
        "tags": ["免费额度", "签到", "Codex", "Claude Code", "OpenAI 兼容", "Anthropic 兼容"],
        "highlights": ["邀请链接注册送 $20 + 每日签到 $20，首日 $40", "支持 /v1/responses 原生 Codex CLI 协议"],
        "activities_summary": "邀请注册立送$20+每日签到领$20；开启邀请好友返佣活动",
    },
    {
        "id": "flushapi",
        "name": "FlushAPI",
        "subtitle": "New API 网关 · 注册送 $15，邀请进入共 $22.5，GitHub 一键建号，模型价格全公开",
        "panel": "newapi",
        "signupUrl": "https://flushapi.fun/sign-up?aff=WBF3",
        "homeUrl": "https://flushapi.fun",
        "docsUrl": "https://flushapi.fun/docs",
        "statusApi": "https://flushapi.fun/api/status",
        "pricingApi": "https://flushapi.fun/api/pricing",
        "inviteCode": "WBF3",
        "credits": {"signup": 15, "invite": 7.5, "dailyCheckin": None, "unit": "usd"},
        "recharge_ratio": "price=7.3（¥7.3 ≈ $1，DeepSeek低至$0.03/M，Claude系输入$5/输出$25）",
        "price_rate": 7.3,
        "register": {
            "methods": ["GitHub OAuth"],
            "requirements": [
                "从带 ?aff=WBF3 邀请链接进入注册得 $15 + $7.5 = $22.5",
                "仅支持 GitHub OAuth 一键建号，无需邮箱验证码与人机验证"
            ],
        },
        "endpoints": {"anthropic": "https://flushapi.fun", "openai": "https://flushapi.fun/v1"},
        "tags": ["New API", "签到", "Claude Code", "Codex", "免费额度", "Anthropic 兼容", "OpenAI 兼容"],
        "highlights": ["注册 $15 + 邀请 $7.5，首日 $22.5", "公开 16+ 模型定价，支持每日签到与邀请每单 +$7.5"],
        "activities_summary": "注册送$15+邀请码WBF3送$7.5；每邀请一位好友再得$7.5；开启后台每日签到",
    },
    {
        "id": "codex-relay",
        "name": "Codex Relay",
        "subtitle": "注册可获得 $10 API 额度 · 专为 AI Coding 打造",
        "panel": "relay",
        "signupUrl": "https://codex-relay.codes/register?aff=6jAq",
        "homeUrl": "https://codex-relay.codes",
        "statusApi": "https://codex-relay.codes",
        "inviteCode": "6jAq",
        "credits": {"signup": 10, "invite": None, "dailyCheckin": None, "unit": "usd"},
        "recharge_ratio": "新用户注册即送 $10 美元额度，充值比例见控制台",
        "register": {
            "methods": ["官网邮箱/账号注册"],
            "requirements": ["使用完整注册链接 https://codex-relay.codes/register?aff=6jAq 保留 aff=6jAq 完成注册"],
        },
        "endpoints": {"anthropic": "https://codex-relay.codes", "openai": "https://codex-relay.codes/v1"},
        "tags": ["免费额度", "注册 $10", "Codex"],
        "highlights": ["注册即送 $10 API 额度", "保留 aff=6jAq 邀请参数直达控制台"],
        "activities_summary": "新用户通过推广链接注册立享 $10 API 额度",
    },
    {
        "id": "matrix",
        "name": "Matrix",
        "subtitle": "统一 API 网关 + 开源应用商店 · 邀请注册送 600 积分，实名再送 2000 积分",
        "panel": "matrix",
        "signupUrl": "https://matrix.mzsjai.com/login?redirect=%2Fapp%2Fgrowth%3FinviteCode%3DMXMRFO52KD2_",
        "homeUrl": "https://matrix.mzsjai.com",
        "docsUrl": "https://matrix.mzsjai.com/docs/matrix/intro/",
        "statusApi": "https://matrix.mzsjai.com/api/health",
        "inviteCode": "MXMRFO52KD2_",
        "credits": {"signup": None, "invite": 600, "dailyCheckin": None, "unit": "point"},
        "recharge_ratio": "站内积分制（邀请送600积分，实名认证送2000积分，拉新双方各得600积分）",
        "register": {
            "methods": ["手机验证码", "邮箱 + 密码", "杭电统一身份认证"],
            "requirements": [
                "从带 inviteCode=MXMRFO52KD2_ 的链接注册即得 600 积分（无需先实名）",
                "个人实名认证后可在钱包页额外领取 2,000 积分"
            ],
        },
        "endpoints": {"anthropic": "", "openai": "https://matrix.mzsjai.com/v1"},
        "tags": ["积分制", "免费额度", "OpenAI 兼容", "开源应用商店", "Cursor"],
        "highlights": ["邀请注册即得 600 积分，实名再领 2000 积分", "一把 Key 调通 OpenAI / Anthropic / DeepSeek / Qwen 等模型"],
        "activities_summary": "邀请注册送600积分+实名认证领2000积分+邀请好友双方各得600积分+反馈建议赢兑换码（有效期至2026-12-31）",
    },
    {
        "id": "nofx",
        "name": "NOFX",
        "subtitle": "任务制积分站 · 做任务领 API 积分，签到 / Discord / 邀请 / 发推都给分",
        "panel": "relay",
        "signupUrl": "https://nofx.one/zh-CN/sign-in?ref=J369GHY4",
        "homeUrl": "https://nofx.one/zh-CN",
        "statusApi": "https://nofx.one/sitemap.xml",
        "inviteCode": "J369GHY4",
        "credits": {"signup": None, "invite": 10, "dailyCheckin": 5, "unit": "point"},
        "recharge_ratio": "任务积分制（免充值，约 5 积分 ≈ 7M tokens，支持 gpt-5.6-sol）",
        "register": {
            "methods": ["邮箱 Magic Link（免密登录）", "GitHub OAuth"],
            "requirements": [
                "从带 ?ref=J369GHY4 的邀请链接进入注册得 10 积分",
                "加入官方 Discord 使用 /verify 与 /checkin 领取每日签到积分"
            ],
        },
        "endpoints": {"anthropic": "", "openai": ""},
        "tags": ["积分制", "免费额度", "Discord 签到", "Codex", "OpenAI 兼容"],
        "highlights": ["邀请注册得 10 积分 + 每日签到 5 积分，首日 15 积分", "免密码 Magic Link 或 GitHub 一键登录"],
        "activities_summary": "邀请注册+10积分、Discord验证+5积分、每日签到+5积分、邀请好友+5积分/人、X发推截图过审+20积分",
    },
]


class RelayCrawler:
    """
    Multi-channel AI Relay Station Crawler & Prober.
    Supports:
    - Probing New-API / One-API endpoints (`/api/status`, `/api/pricing`)
    - Resolving registration & redirect links (`signupUrl` -> `redirect_url`)
    - Crawling GitHub repo (`panxunying/ai-coding-welfare`) and GitHub Issues
    - Crawling search engines (Google / Bing / DuckDuckGo) for AI relay stations
    """

    def __init__(
        self,
        db: RelayDatabase,
        timeout: float = 12.0,
        http_fetcher: Optional[Callable[[str, Dict[str, str], float], Tuple[int, str, str, int]]] = None,
    ) -> None:
        self.db = db
        self.timeout = timeout
        self._http_fetcher = http_fetcher or self._default_http_fetch

    @staticmethod
    def _default_http_fetch(
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 12.0,
    ) -> Tuple[int, str, str, int]:
        """
        Perform an HTTP GET request, following redirects, and return:
        (http_status, response_text, final_redirect_url, latency_ms)
        """
        req_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html, */*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if headers:
            req_headers.update(headers)

        started = time.perf_counter()
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                ms = int((time.perf_counter() - started) * 1000)
                status = int(getattr(resp, "status", 200))
                final_url = str(resp.geturl() or url)
                raw_bytes = resp.read(2 * 1024 * 1024)  # cap at 2MB
                charset = resp.headers.get_content_charset() or "utf-8"
                text = raw_bytes.decode(charset, errors="replace")
                return status, text, final_url, ms
        except urllib.error.HTTPError as err:
            ms = int((time.perf_counter() - started) * 1000)
            final_url = str(err.geturl() or url)
            try:
                body = err.read(65536).decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return int(err.code), body, final_url, ms
        except Exception as err:
            ms = int((time.perf_counter() - started) * 1000)
            raise RuntimeError(f"{type(err).__name__}: {err}") from err

    def fetch_url_safe(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Safe wrapper around HTTP fetch that never raises and returns structured metadata."""
        if not url:
            return {"ok": False, "status": 0, "text": "", "final_url": "", "ms": 0, "error": "empty url"}
        try:
            validated = validate_url(url, allow_empty=False)
        except ValueError as exc:
            return {"ok": False, "status": 0, "text": "", "final_url": url, "ms": 0, "error": str(exc)}

        try:
            status, text, final_url, ms = self._http_fetcher(validated, headers or {}, self.timeout)
            ok = 200 <= status < 400
            return {
                "ok": ok,
                "status": status,
                "text": text,
                "final_url": final_url,
                "ms": ms,
                "error": "" if ok else f"HTTP {status}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "status": 0,
                "text": "",
                "final_url": url,
                "ms": 0,
                "error": str(exc),
            }

    @staticmethod
    def parse_newapi_status(raw_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse New-API / One-API `/api/status` JSON payload into normalized station fields.
        """
        data = raw_json.get("data") if isinstance(raw_json.get("data"), dict) else raw_json
        if not isinstance(data, dict):
            return {}

        login_methods: List[str] = []
        if data.get("github_oauth"):
            age = data.get("github_minimum_account_age_days")
            login_methods.append(f"GitHub OAuth (需满{age}天)" if age else "GitHub OAuth")
        if data.get("linuxdo_oauth"):
            login_methods.append("LinuxDO OAuth")
        if data.get("discord_oauth"):
            login_methods.append("Discord OAuth")
        if data.get("telegram_oauth"):
            login_methods.append("Telegram OAuth")
        if data.get("wechat_login"):
            login_methods.append("微信登录")
        if data.get("oidc_enabled"):
            login_methods.append("OIDC")
        if data.get("passkey_login"):
            login_methods.append("Passkey")
        if data.get("password_login_enabled") or data.get("password_register_enabled"):
            if data.get("email_verification"):
                login_methods.append("邮箱 + 密码 (需邮箱验证码)")
            else:
                login_methods.append("账号密码")

        price_rate = None
        if data.get("price") is not None:
            try:
                price_rate = float(data["price"])
            except (ValueError, TypeError):
                price_rate = None

        stripe_price = None
        if data.get("stripe_unit_price") is not None:
            try:
                stripe_price = float(data["stripe_unit_price"])
            except (ValueError, TypeError):
                stripe_price = None

        quota_per_unit = None
        if data.get("quota_per_unit") is not None:
            try:
                quota_per_unit = float(data["quota_per_unit"])
            except (ValueError, TypeError):
                quota_per_unit = None

        recharge_ratio = ""
        if price_rate is not None and price_rate > 0:
            if price_rate < 1.0:
                per_rmb = round(1.0 / price_rate, 2)
                recharge_ratio = f"price={price_rate}（1元 = {per_rmb:g} 站内刀"
                if stripe_price:
                    recharge_ratio += f"，Stripe单价 ¥{stripe_price:g}"
                recharge_ratio += "）"
            else:
                recharge_ratio = f"price={price_rate}（¥{price_rate:g} ≈ $1"
                if stripe_price:
                    recharge_ratio += f"，Stripe通道 ¥{stripe_price:g}"
                recharge_ratio += "）"

        invitee_usd = None
        if quota_per_unit and data.get("quota_for_invitee"):
            try:
                invitee_usd = round(float(data["quota_for_invitee"]) / quota_per_unit, 2)
            except (ValueError, TypeError):
                pass

        signup_usd = None
        if quota_per_unit and data.get("quota_for_new_user"):
            try:
                signup_usd = round(float(data["quota_for_new_user"]) / quota_per_unit, 2)
            except (ValueError, TypeError):
                pass

        raw_announcements = data.get("announcements")
        announcements: List[Dict[str, Any]] = []
        if isinstance(raw_announcements, list):
            for item in raw_announcements[:15]:
                if not isinstance(item, dict):
                    continue
                content = str(item.get("content") or item.get("text") or "").strip()
                if not content:
                    continue
                clean_content = re.sub(r"\s+", " ", content)
                pub_date = str(item.get("publishDate") or item.get("date") or "")[:10]
                announcements.append(
                    {
                        "id": str(item.get("id") or ""),
                        "activity_type": str(item.get("type") or "announcement"),
                        "title": clean_content[:60],
                        "content": clean_content[:500],
                        "publish_date": pub_date,
                        "extra": str(item.get("extra") or ""),
                    }
                )

        api_info = data.get("api_info")
        mirrors: List[Dict[str, str]] = []
        if isinstance(api_info, list):
            for info in api_info:
                if isinstance(info, dict) and info.get("url"):
                    mirrors.append(
                        {
                            "label": str(info.get("route") or info.get("description") or "线路"),
                            "homeUrl": str(info.get("url")),
                        }
                    )

        return {
            "system_name": str(data.get("system_name") or "").strip(),
            "panel_version": str(data.get("version") or "").strip(),
            "register_open": data.get("register_enabled") if isinstance(data.get("register_enabled"), bool) else None,
            "password_register": (
                data.get("password_register_enabled")
                if isinstance(data.get("password_register_enabled"), bool)
                else None
            ),
            "checkin_enabled": data.get("checkin_enabled") if isinstance(data.get("checkin_enabled"), bool) else None,
            "email_verification": (
                data.get("email_verification") if isinstance(data.get("email_verification"), bool) else None
            ),
            "turnstile_check": data.get("turnstile_check") if isinstance(data.get("turnstile_check"), bool) else None,
            "github_min_age_days": data.get("github_minimum_account_age_days"),
            "registration_methods": login_methods,
            "price_rate": price_rate,
            "stripe_unit_price": stripe_price,
            "quota_per_unit": quota_per_unit,
            "recharge_ratio": recharge_ratio,
            "signup_bonus_api": signup_usd,
            "invite_bonus_api": invitee_usd,
            "announcements": announcements,
            "api_mirrors": mirrors,
            "server_address": str(data.get("server_address") or "").strip(),
        }

    @staticmethod
    def parse_newapi_pricing(raw_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse New-API `/api/pricing` JSON payload into normalized model list."""
        data = raw_json.get("data") if isinstance(raw_json, dict) else None
        if not isinstance(data, list):
            return []

        models: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict) or not item.get("model_name"):
                continue
            name = str(item["model_name"]).strip()
            try:
                ratio = float(item.get("model_ratio")) if item.get("model_ratio") is not None else None
            except (ValueError, TypeError):
                ratio = None
            try:
                compl = float(item.get("completion_ratio")) if item.get("completion_ratio") is not None else None
            except (ValueError, TypeError):
                compl = None
            try:
                fixed = float(item.get("model_price")) if item.get("model_price") else None
                if fixed is not None and fixed <= 0:
                    fixed = None
            except (ValueError, TypeError):
                fixed = None

            input_price = round(ratio * RATIO_USD_PER_MTOK, 3) if (fixed is None and ratio is not None) else None
            output_price = (
                round(ratio * compl * RATIO_USD_PER_MTOK, 3)
                if (fixed is None and ratio is not None and compl is not None)
                else None
            )

            groups = item.get("enable_groups") if isinstance(item.get("enable_groups"), list) else []
            protocols = (
                item.get("supported_endpoint_types")
                if isinstance(item.get("supported_endpoint_types"), list)
                else []
            )
            models.append(
                {
                    "name": name,
                    "ratio": ratio,
                    "completionRatio": compl,
                    "fixedPrice": fixed,
                    "inputPerMTok": input_price,
                    "outputPerMTok": output_price,
                    "groups": groups,
                    "protocols": protocols,
                }
            )
        return models

    @staticmethod
    def extract_info_from_html_or_text(text: str, base_url: str = "") -> Dict[str, Any]:
        """
        Extract relay station registration links, recharge ratios, bonuses, and activities
        from HTML or Markdown/Issue text using regex heuristics.
        """
        cleaned = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"<style\b[^>]*>.*?</style>", " ", cleaned, flags=re.DOTALL | re.IGNORECASE)
        plain = html.unescape(re.sub(r"<[^>]+>", " ", cleaned))
        plain = re.sub(r"\s+", " ", plain).strip()

        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.DOTALL | re.IGNORECASE)
        title = html.unescape(title_match.group(1)).strip() if title_match else ""

        # Find registration / affiliate link
        reg_link_match = re.search(
            r"(https?://[^\s\"'<>]+/(?:register|sign-up|signup|login|r|console)[^\s\"'<>]*)",
            text,
            flags=re.IGNORECASE,
        )
        register_url = reg_link_match.group(1) if reg_link_match else base_url

        invite_code = ""
        aff_match = re.search(r"(?:aff|ref|inviteCode|referral_code)=([A-Za-z0-9_-]+)", register_url)
        if aff_match:
            invite_code = aff_match.group(1)

        # Extract signup bonus and detect unit
        signup_bonus = None
        credit_unit = "usd"
        bonus_match = re.search(r"注册(?:即)?(?:送|赠送|可得|可获得|领)\s*([\$￥¥]?)\s*(\d+(?:\.\d+)?)", plain)
        if bonus_match:
            sym = bonus_match.group(1)
            if sym in ("￥", "¥"):
                credit_unit = "cny"
            try:
                signup_bonus = float(bonus_match.group(2))
            except ValueError:
                pass

        # Extract daily checkin bonus
        checkin_bonus = None
        checkin_match = re.search(r"(?:每日)?签到(?:再)?(?:送|领|可得|\+)?\s*[≈\$￥¥]?\s*(\d+(?:\.\d+)?)", plain)
        if checkin_match:
            try:
                checkin_bonus = float(checkin_match.group(1))
            except ValueError:
                pass

        # Extract recharge ratio
        recharge_ratio = ""
        ratio_match = re.search(
            r"(1\s*元\s*=\s*\d+\s*(?:美元|刀|站内刀|额度)|[￥¥]\s*\d+(?:\.\d+)?\s*[≈=]\s*\$\s*1|price\s*=\s*\d+(?:\.\d+)?)",
            plain,
            flags=re.IGNORECASE,
        )
        if ratio_match:
            recharge_ratio = ratio_match.group(1)

        # Extract registration methods
        methods: List[str] = []
        if re.search(r"GitHub", plain, re.IGNORECASE):
            methods.append("GitHub OAuth")
        if re.search(r"LinuxDO", plain, re.IGNORECASE):
            methods.append("LinuxDO OAuth")
        if re.search(r"Telegram", plain, re.IGNORECASE):
            methods.append("Telegram 机器人")
        if re.search(r"邮箱|Email", plain, re.IGNORECASE):
            methods.append("邮箱注册")
        if not methods:
            methods.append("官网注册")

        return {
            "title": title[:100],
            "register_url": register_url,
            "invite_code": invite_code,
            "signup_bonus": signup_bonus,
            "daily_checkin_bonus": checkin_bonus,
            "credit_unit": credit_unit,
            "recharge_ratio": recharge_ratio,
            "registration_methods": methods,
            "excerpt": plain[:300],
        }

    def normalize_reference_site(
        self,
        site: Dict[str, Any],
        live_snap: Optional[Dict[str, Any]] = None,
        source_channel: str = "github:ai-coding-welfare",
    ) -> Dict[str, Any]:
        """
        Convert an entry from `panxunying/ai-coding-welfare` (`sites.json` + `live.json`)
        into our unified SQLite station dictionary.
        """
        live = live_snap or {}
        credits = site.get("credits") or {}
        register_info = site.get("register") or {}
        endpoints = site.get("endpoints") or {}
        archived = site.get("archived")

        signup_url = str(site.get("signupUrl") or site.get("homeUrl") or "").strip()
        home_url = str(site.get("homeUrl") or signup_url).strip()

        invite_code = str(site.get("inviteCode") or "").strip()
        if not invite_code and signup_url:
            m = re.search(r"(?:aff|ref|inviteCode|start|i)=([A-Za-z0-9_-]+)", signup_url)
            if m:
                invite_code = m.group(1)

        reg_methods = list(register_info.get("methods") or [])
        for lm in live.get("loginMethods") or []:
            if lm not in reg_methods:
                reg_methods.append(lm)

        # Determine recharge ratio from site caveats/highlights or explicit field
        recharge_ratio = str(site.get("recharge_ratio") or "").strip()
        price_rate = site.get("price_rate")
        stripe_unit_price = site.get("stripe_unit_price")

        all_notes = " ".join(
            [
                *(site.get("highlights") or []),
                *(site.get("caveats") or []),
                str(site.get("modelsNote") or ""),
                str(credits.get("note") or ""),
            ]
        )
        if not recharge_ratio:
            if "price = 0.02" in all_notes or "1 元 = 50 站内刀" in all_notes:
                recharge_ratio = "price=0.02（活动1元=50站内刀，日常1:25；Stripe单价¥8）"
                price_rate = price_rate or 0.02
                stripe_unit_price = stripe_unit_price or 8.0
            elif "price=7.3" in all_notes or "$1 ≈ ¥7.3" in all_notes or "¥7.3 ≈ $1" in all_notes:
                recharge_ratio = "price=7.3（¥7.3 ≈ $1，Stripe通道 ¥8/$1）"
                price_rate = price_rate or 7.3
                stripe_unit_price = stripe_unit_price or 8.0
            elif "不支持充值" in all_notes or "公益站" in (site.get("tags") or []):
                recharge_ratio = "公益免费站（不支持充值，靠注册+邀请+签到获取额度）"
            elif credits.get("unit") == "point":
                recharge_ratio = "站内任务/活动积分制（无需充值，按积分调用模型）"
            else:
                recharge_ratio = "注册赠送免费额度（详见站点控制台定价说明）"

        # Summarize activities
        activities_list: List[Dict[str, Any]] = []
        for ann in live.get("announcements") or []:
            if isinstance(ann, dict) and (ann.get("text") or ann.get("content")):
                activities_list.append(
                    {
                        "id": str(ann.get("id") or ""),
                        "activity_type": "announcement",
                        "title": str(ann.get("text") or ann.get("content"))[:60],
                        "content": str(ann.get("text") or ann.get("content")),
                        "publish_date": str(ann.get("date") or ann.get("publishDate") or ""),
                    }
                )
        for em in site.get("earnMore") or []:
            activities_list.append(
                {
                    "activity_type": "welfare_rule",
                    "title": str(em)[:60],
                    "content": str(em),
                    "publish_date": "",
                }
            )

        activities_summary = str(site.get("activities_summary") or "").strip()
        if not activities_summary:
            summary_parts: List[str] = []
            if credits.get("signup"):
                summary_parts.append(f"注册送 {credits['signup']} ({credits.get('unit', 'usd')})")
            if credits.get("invite"):
                summary_parts.append(f"邀请链接送 {credits['invite']}")
            if credits.get("dailyCheckin"):
                summary_parts.append(f"每日签到送 {credits['dailyCheckin']}/天")
            if credits.get("dailyQuota"):
                summary_parts.append(f"每日重置额度池 {credits['dailyQuota']}/天")
            for em in (site.get("earnMore") or [])[:2]:
                summary_parts.append(str(em))
            if activities_list and activities_list[0].get("content"):
                summary_parts.append(f"最新公告：{activities_list[0]['content'][:80]}")
            activities_summary = "；".join(summary_parts)

        protocols: List[str] = []
        if endpoints.get("openai"):
            protocols.append("OpenAI 兼容")
        if endpoints.get("anthropic"):
            protocols.append("Anthropic 兼容")
        if not protocols:
            for t in site.get("tags") or []:
                if "兼容" in t:
                    protocols.append(t)

        signup_probe = live.get("signup") or {}
        redirect_url = str(signup_probe.get("url") or signup_url).strip()

        daily_val = credits.get("dailyCheckin") if credits.get("dailyCheckin") is not None else credits.get("dailyQuota")

        return {
            "slug": slugify(site.get("id") or site.get("name") or ""),
            "name": str(site.get("name") or "").strip(),
            "subtitle": str(site.get("subtitle") or "").strip(),
            "panel_type": str(site.get("panel") or "newapi").strip(),
            "home_url": home_url,
            "register_url": signup_url,
            "redirect_url": redirect_url,
            "status_api_url": str(site.get("statusApi") or "").strip(),
            "pricing_api_url": str(site.get("pricingApi") or "").strip(),
            "docs_url": str(site.get("docsUrl") or "").strip(),
            "invite_code": invite_code,
            "registration_methods": reg_methods,
            "registration_requirements": register_info.get("requirements") or [],
            "recharge_ratio": recharge_ratio,
            "price_rate": price_rate,
            "stripe_unit_price": stripe_unit_price,
            "quota_per_unit": live.get("quotaPerUnit"),
            "signup_bonus": credits.get("signup"),
            "invite_bonus": credits.get("invite"),
            "daily_checkin_bonus": daily_val,
            "credit_unit": str(credits.get("unit") or "usd"),
            "checkin_enabled": live.get("checkinEnabled"),
            "register_open": live.get("registerOpen"),
            "password_register": live.get("passwordRegister"),
            "github_min_age_days": live.get("githubMinAccountAgeDays"),
            "activities_summary": activities_summary,
            "supported_protocols": protocols,
            "openai_base_url": str(endpoints.get("openai") or ""),
            "anthropic_base_url": str(endpoints.get("anthropic") or ""),
            "mirrors": site.get("mirrors") or [],
            "tags": site.get("tags") or [],
            "highlights": site.get("highlights") or [],
            "caveats": site.get("caveats") or [],
            "source_channel": source_channel,
            "online_status": False if archived else bool(live.get("online", True)),
            "is_archived": bool(archived),
            "archived_reason": str(archived.get("reason") or "") if isinstance(archived, dict) else "",
            "latency_ms": live.get("latencyMs"),
            "system_name": str(live.get("systemName") or site.get("name") or ""),
            "panel_version": str(live.get("version") or ""),
            "last_checked_at": live.get("checkedAt") or utc_now_iso(),
            "activities": activities_list,
            "models": live.get("models") or [],
        }

    def sync_from_github_welfare_repo(self) -> Dict[str, Any]:
        """
        Fetch latest `data/sites.json` and `data/live.json` from `panxunying/ai-coding-welfare`,
        falling back to BUILTIN_SITES_SEED if GitHub raw is unreachable, and store in SQLite.
        """
        sites_url = "https://raw.githubusercontent.com/panxunying/ai-coding-welfare/main/data/sites.json"
        live_url = "https://raw.githubusercontent.com/panxunying/ai-coding-welfare/main/data/live.json"

        sites_res = self.fetch_url_safe(sites_url)
        live_res = self.fetch_url_safe(live_url)

        live_by_id: Dict[str, Dict[str, Any]] = {}
        if live_res["ok"]:
            try:
                live_data = json.loads(live_res["text"])
                for s in live_data.get("sites") or []:
                    if isinstance(s, dict) and s.get("id"):
                        live_by_id[str(s["id"])] = s
            except Exception as exc:
                logger.warning("Failed to parse live.json: %s", exc)

        raw_sites: List[Dict[str, Any]] = []
        source_channel = "github:ai-coding-welfare"
        if sites_res["ok"]:
            try:
                parsed = json.loads(sites_res["text"])
                raw_sites = parsed.get("sites") or []
                self.db.log_crawl(
                    channel="github_repo",
                    target_url=sites_url,
                    http_status=sites_res["status"],
                    latency_ms=sites_res["ms"],
                    is_success=True,
                    final_redirect_url=sites_res["final_url"],
                    raw_excerpt=f"Loaded {len(raw_sites)} sites from GitHub sites.json",
                )
            except Exception as exc:
                logger.warning("Failed to parse sites.json: %s", exc)

        if not raw_sites:
            raw_sites = BUILTIN_SITES_SEED
            source_channel = "seed:ai-coding-welfare"
            self.db.log_crawl(
                channel="seed_fallback",
                target_url=sites_url,
                http_status=sites_res.get("status", 0),
                latency_ms=sites_res.get("ms", 0),
                is_success=True,
                error_message=sites_res.get("error", ""),
                raw_excerpt=f"Used builtin seed with {len(raw_sites)} sites",
            )
        else:
            # Merge any enriched fields from BUILTIN_SITES_SEED (like DoCode recharge_ratio)
            seed_map = {s["id"]: s for s in BUILTIN_SITES_SEED}
            for s in raw_sites:
                sid = s.get("id")
                if sid in seed_map:
                    for k in ("recharge_ratio", "price_rate", "stripe_unit_price", "activities_summary"):
                        if not s.get(k) and seed_map[sid].get(k):
                            s[k] = seed_map[sid][k]

        upserted_ids: List[int] = []
        for site in raw_sites:
            sid = str(site.get("id") or "")
            norm = self.normalize_reference_site(site, live_by_id.get(sid), source_channel=source_channel)
            station_id = self.db.upsert_station(norm)
            upserted_ids.append(station_id)

        return {
            "source": source_channel,
            "count": len(upserted_ids),
            "station_ids": upserted_ids,
        }

    def crawl_github_issues_submissions(self) -> Dict[str, Any]:
        """
        Crawl community-submitted AI relay stations from
        `https://api.github.com/repos/panxunying/ai-coding-welfare/issues`
        and extract registration links, recharge ratios, and welfare activities.
        """
        issues_api = "https://api.github.com/repos/panxunying/ai-coding-welfare/issues?state=open&per_page=30"
        res = self.fetch_url_safe(issues_api, headers={"Accept": "application/vnd.github+json"})

        discovered: List[Dict[str, Any]] = []
        if res["ok"]:
            try:
                issues = json.loads(res["text"])
                if isinstance(issues, list):
                    for issue in issues:
                        if not isinstance(issue, dict) or "pull_request" in issue:
                            continue
                        title = str(issue.get("title") or "").strip()
                        body = str(issue.get("body") or "").strip()
                        if not body:
                            continue
                        parsed = self._parse_github_issue_submission(title, body, issue.get("html_url") or "")
                        if parsed:
                            station_id = self.db.upsert_station(parsed)
                            discovered.append({"id": station_id, "name": parsed["name"], "slug": parsed["slug"]})
                self.db.log_crawl(
                    channel="github_issues",
                    target_url=issues_api,
                    http_status=res["status"],
                    latency_ms=res["ms"],
                    is_success=True,
                    final_redirect_url=res["final_url"],
                    raw_excerpt=f"Discovered {len(discovered)} stations from GitHub Issues",
                )
            except Exception as exc:
                logger.warning("Error parsing GitHub issues: %s", exc)
        else:
            self.db.log_crawl(
                channel="github_issues",
                target_url=issues_api,
                http_status=res["status"],
                latency_ms=res["ms"],
                is_success=False,
                error_message=res["error"],
            )

        return {"discovered_count": len(discovered), "stations": discovered}

    def _parse_github_issue_submission(self, title: str, body: str, issue_url: str) -> Optional[Dict[str, Any]]:
        """Parse a GitHub Issue submission markdown body into a normalized station dict."""
        urls = re.findall(r"https?://[a-zA-Z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", body)
        valid_urls = [u.rstrip(").,;\"'`>") for u in urls if "github.com" not in u and "user-attachments" not in u]
        if not valid_urls:
            return None

        # Determine station name
        name = re.sub(r"^\[收录\]\s*|^提交站点[：:]\s*|^补充收录[：:]\s*", "", title).strip()
        name = re.split(r"[（(—\-]", name)[0].strip()
        name_sec = re.search(r"###\s*站点名称\s+([^\n#]+)", body)
        if name_sec:
            name = name_sec.group(1).strip()
        if not name:
            return None

        register_url = valid_urls[0]
        home_url = valid_urls[0]
        for u in valid_urls:
            if any(k in u.lower() for k in ("register", "sign-up", "signup", "login", "aff=", "ref=", "referral", "/r/")):
                register_url = u
                break

        parsed_reg = urllib.parse.urlparse(register_url)
        home_url = f"{parsed_reg.scheme}://{parsed_reg.netloc}"

        extracted = self.extract_info_from_html_or_text(body, base_url=register_url)
        panel_type = "newapi" if re.search(r"New\s*API", body, re.IGNORECASE) else "relay"

        status_api = f"{home_url}/api/status" if panel_type == "newapi" else home_url
        pricing_api = f"{home_url}/api/pricing" if panel_type == "newapi" else ""

        protocols: List[str] = []
        if re.search(r"\[[xX]\]\s*Anthropic|Anthropic\s*兼容", body):
            protocols.append("Anthropic 兼容")
        if re.search(r"\[[xX]\]\s*OpenAI|OpenAI\s*兼容", body):
            protocols.append("OpenAI 兼容")

        return {
            "slug": slugify(name, fallback_url=home_url),
            "name": name,
            "subtitle": f"社区投稿收录 · {title[:60]}",
            "panel_type": panel_type,
            "home_url": home_url,
            "register_url": register_url,
            "redirect_url": register_url,
            "status_api_url": status_api,
            "pricing_api_url": pricing_api,
            "docs_url": issue_url,
            "invite_code": extracted["invite_code"],
            "registration_methods": extracted["registration_methods"],
            "registration_requirements": [f"来源 GitHub Issue 投稿：{issue_url}"],
            "recharge_ratio": extracted["recharge_ratio"] or "见站内公示（社区投稿站点）",
            "signup_bonus": extracted["signup_bonus"],
            "daily_checkin_bonus": extracted["daily_checkin_bonus"],
            "credit_unit": extracted.get("credit_unit") or "usd",
            "activities_summary": extracted["excerpt"][:200],
            "supported_protocols": protocols or ["OpenAI 兼容"],
            "openai_base_url": f"{home_url}/v1",
            "anthropic_base_url": home_url if "Anthropic 兼容" in protocols else "",
            "tags": ["社区投稿", "AI中转站"],
            "highlights": [extracted["excerpt"][:160]],
            "source_channel": "github:issues",
            "online_status": True,
            "activities": [
                {
                    "activity_type": "community_submission",
                    "title": f"社区投稿：{name}",
                    "content": extracted["excerpt"][:400],
                    "publish_date": utc_now_iso()[:10],
                }
            ],
        }

    def crawl_search_channels(self, queries: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Search Google / Bing / DuckDuckGo for AI relay stations (New-API / One-API / Claude Code / Codex)
        and extract candidate URLs and metadata.
        """
        search_queries = queries or [
            '"new-api" "register?aff=" AI 中转站',
            '"api/status" "Claude Code" 中转站 注册送额度',
        ]
        discovered_urls: List[str] = []
        logs_created = 0

        for q in search_queries:
            encoded_q = urllib.parse.quote_plus(q)
            search_endpoints = [
                ("google_search", f"https://www.google.com/search?q={encoded_q}&num=10&hl=zh-CN"),
                ("bing_search", f"https://www.bing.com/search?q={encoded_q}&count=10"),
                ("duckduckgo_search", f"https://html.duckduckgo.com/html/?q={encoded_q}"),
            ]
            for channel_name, search_url in search_endpoints:
                res = self.fetch_url_safe(search_url)
                logs_created += 1
                if res["ok"] and res["text"]:
                    found = re.findall(
                        r"https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/(?:register|sign-up|signup)\?(?:aff|ref)=[A-Za-z0-9_-]+",
                        res["text"],
                    )
                    for u in found:
                        if u not in discovered_urls:
                            discovered_urls.append(u)
                    self.db.log_crawl(
                        channel=channel_name,
                        target_url=search_url,
                        http_status=res["status"],
                        latency_ms=res["ms"],
                        is_success=True,
                        final_redirect_url=res["final_url"],
                        raw_excerpt=f"Query='{q}' found {len(found)} relay signup links",
                    )
                else:
                    self.db.log_crawl(
                        channel=channel_name,
                        target_url=search_url,
                        http_status=res["status"],
                        latency_ms=res["ms"],
                        is_success=False,
                        error_message=res["error"] or "Search blocked or unreachable",
                    )

        return {
            "queries_executed": len(search_queries),
            "logs_created": logs_created,
            "discovered_urls": discovered_urls,
        }

    def probe_station_live(self, station: Dict[str, Any]) -> Dict[str, Any]:
        """
        Actively probe a single relay station's live `/api/status`, `/api/pricing`, and `register_url`
        (capturing final `redirect_url`, HTTP status, latency,recharge ratio, announcements, and models).
        """
        station_id = station.get("id")
        slug = station.get("slug") or slugify(station.get("name") or "")
        home_url = str(station.get("home_url") or "").rstrip("/")
        register_url = str(station.get("register_url") or home_url)
        status_api = str(station.get("status_api_url") or f"{home_url}/api/status")
        pricing_api = str(station.get("pricing_api_url") or "")

        # 1. Probe registration URL and track final redirect URL
        reg_res = self.fetch_url_safe(register_url)
        redirect_url = reg_res["final_url"] if reg_res["final_url"] else register_url
        self.db.log_crawl(
            station_id=station_id,
            channel="probe_register",
            target_url=register_url,
            final_redirect_url=redirect_url,
            http_status=reg_res["status"],
            latency_ms=reg_res["ms"],
            is_success=reg_res["ok"],
            error_message=reg_res["error"],
            raw_excerpt=reg_res["text"][:300] if reg_res["text"] else "",
        )

        # 2. Probe status API (especially for New-API / One-API stations like docode.cc)
        status_res = self.fetch_url_safe(status_api, headers={"Accept": "application/json"})
        parsed_status: Dict[str, Any] = {}
        status_json_ok = False
        if status_res["ok"] and status_res["text"]:
            try:
                raw_json = json.loads(status_res["text"])
                if isinstance(raw_json, dict):
                    parsed_status = self.parse_newapi_status(raw_json)
                    status_json_ok = True
            except Exception:
                pass

        self.db.log_crawl(
            station_id=station_id,
            channel="probe_status_api",
            target_url=status_api,
            final_redirect_url=status_res["final_url"],
            http_status=status_res["status"],
            latency_ms=status_res["ms"],
            is_success=status_res["ok"],
            error_message=status_res["error"],
            raw_excerpt=status_res["text"][:300] if status_res["text"] else "",
        )

        # 3. Probe pricing API if available
        models: List[Dict[str, Any]] = []
        if pricing_api:
            pr_res = self.fetch_url_safe(pricing_api, headers={"Accept": "application/json"})
            if pr_res["ok"] and pr_res["text"]:
                try:
                    pr_json = json.loads(pr_res["text"])
                    models = self.parse_newapi_pricing(pr_json)
                except Exception:
                    pass

        # Merge probed live fields into existing station data without overwriting valid manual fields with empty values
        updated = dict(station)
        updated["redirect_url"] = redirect_url
        updated["online_status"] = bool(
            reg_res["ok"] or status_res["ok"] or status_res["status"] in (401, 403, 429)
        )
        updated["latency_ms"] = status_res["ms"] or reg_res["ms"] or station.get("latency_ms")
        updated["last_checked_at"] = utc_now_iso()

        if status_json_ok and parsed_status:
            if parsed_status.get("system_name"):
                updated["system_name"] = parsed_status["system_name"]
            if parsed_status.get("panel_version"):
                updated["panel_version"] = parsed_status["panel_version"]
            if parsed_status.get("register_open") is not None:
                updated["register_open"] = parsed_status["register_open"]
            if parsed_status.get("password_register") is not None:
                updated["password_register"] = parsed_status["password_register"]
            if parsed_status.get("checkin_enabled") is not None:
                updated["checkin_enabled"] = parsed_status["checkin_enabled"]
            if parsed_status.get("email_verification") is not None:
                updated["email_verification"] = parsed_status["email_verification"]
            if parsed_status.get("turnstile_check") is not None:
                updated["turnstile_check"] = parsed_status["turnstile_check"]
            if parsed_status.get("github_min_age_days") is not None:
                updated["github_min_age_days"] = parsed_status["github_min_age_days"]
            if parsed_status.get("registration_methods"):
                existing_methods = list(updated.get("registration_methods") or [])
                for m in parsed_status["registration_methods"]:
                    if m not in existing_methods:
                        existing_methods.append(m)
                updated["registration_methods"] = existing_methods
            if parsed_status.get("price_rate") is not None:
                updated["price_rate"] = parsed_status["price_rate"]
            if parsed_status.get("stripe_unit_price") is not None:
                updated["stripe_unit_price"] = parsed_status["stripe_unit_price"]
            if parsed_status.get("quota_per_unit") is not None:
                updated["quota_per_unit"] = parsed_status["quota_per_unit"]
            if parsed_status.get("recharge_ratio") and not updated.get("recharge_ratio"):
                updated["recharge_ratio"] = parsed_status["recharge_ratio"]
            if parsed_status.get("announcements"):
                updated["activities"] = parsed_status["announcements"]
                updated["live_promos"] = [
                    {"date": a["publish_date"], "tag": "站内公告", "text": a["content"]}
                    for a in sorted(parsed_status["announcements"], key=lambda a: a["publish_date"], reverse=True)[:2]
                ]
                latest_text = parsed_status["announcements"][0]["content"][:90]
                if latest_text and latest_text not in (updated.get("activities_summary") or ""):
                    base_sum = updated.get("activities_summary") or ""
                    updated["activities_summary"] = (
                        f"{base_sum} | 最新公告：{latest_text}".strip(" |")
                    )

        if models:
            updated["models"] = models

        self.db.upsert_station(updated)
        return self.db.get_station(slug) or updated

    def probe_all_stations(self, max_workers: int = 6, online_only: bool = False) -> Dict[str, Any]:
        """Concurrently probe active relay stations in SQLite and update their live status."""
        listing = self.db.list_stations(online_only=online_only, include_archived=False, limit=100)
        stations = listing["items"]
        results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            future_map = {pool.submit(self.probe_station_live, st): st["slug"] for st in stations}
            for fut in as_completed(future_map):
                slug = future_map[fut]
                try:
                    res = fut.result()
                    results.append(
                        {
                            "slug": slug,
                            "online": res.get("online_status"),
                            "latency_ms": res.get("latency_ms"),
                            "redirect_url": res.get("redirect_url"),
                        }
                    )
                except Exception as exc:
                    logger.error("Failed probing station %s: %s", slug, exc)
                    results.append({"slug": slug, "online": False, "error": str(exc)})

        return {
            "probed_count": len(results),
            "online_count": sum(1 for r in results if r.get("online")),
            "results": results,
        }

    def crawl_custom_url(self, url: str, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Crawl any user-supplied AI relay station URL (e.g., https://docode.cc),
        automatically probing `/api/status`, `/api/pricing`, and HTML metadata,
        then saving to SQLite3.
        """
        cleaned_url = validate_url(url, allow_empty=False)
        parsed = urllib.parse.urlparse(cleaned_url)
        home_url = f"{parsed.scheme}://{parsed.netloc}"

        page_res = self.fetch_url_safe(cleaned_url)
        html_info = self.extract_info_from_html_or_text(page_res["text"], base_url=cleaned_url)

        status_api = f"{home_url}/api/status"
        pricing_api = f"{home_url}/api/pricing"

        station_name = (
            name
            or html_info["title"]
            or parsed.netloc.split(":")[0].replace("www.", "").replace("api.", "")
        )
        slug = slugify(station_name)

        draft: Dict[str, Any] = {
            "slug": slug,
            "name": station_name,
            "subtitle": f"自动探测收录站点 ({home_url})",
            "panel_type": "newapi",
            "home_url": home_url,
            "register_url": html_info["register_url"] or cleaned_url,
            "redirect_url": page_res["final_url"] or cleaned_url,
            "status_api_url": status_api,
            "pricing_api_url": pricing_api,
            "invite_code": html_info["invite_code"],
            "registration_methods": html_info["registration_methods"],
            "recharge_ratio": html_info["recharge_ratio"],
            "signup_bonus": html_info["signup_bonus"],
            "daily_checkin_bonus": html_info["daily_checkin_bonus"],
            "activities_summary": html_info["excerpt"][:200],
            "supported_protocols": ["OpenAI 兼容", "Anthropic 兼容"],
            "openai_base_url": f"{home_url}/v1",
            "anthropic_base_url": home_url,
            "source_channel": "custom_crawl",
            "online_status": page_res["ok"],
            "latency_ms": page_res["ms"],
        }

        station_id = self.db.upsert_station(draft)
        saved = self.db.get_station(station_id)
        if saved:
            return self.probe_station_live(saved)
        return draft
