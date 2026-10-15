#!/usr/bin/env python3
"""
CLI Entrypoint for AI Relay Station Crawler & JSON Manager.
Supports:
- Initializing JSON database (`ai_relays_export.json`)
- Crawling & syncing from `panxunying/ai-coding-welfare`, GitHub Issues, Search Channels, and Live New-API endpoints
- Exporting JSON snapshot and self-contained interactive HTML dashboard (`ai_relay_dashboard.html`)
- Running RESTful API Server
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import HTTPServer
from typing import Any, Dict

from src.api import RelayAPIApplication, make_http_handler
from src.crawler import RelayCrawler
from src.db import DEFAULT_DB_PATH, RelayDatabase, utc_now_iso


def generate_dashboard_html(db: RelayDatabase, output_html_path: str) -> str:
    from src.json_store import public_data
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relay_dashboard_template_20261015.html")
    with open(template_path, encoding="utf-8") as f:
        template = f.read()
    data = db.snapshot()
    # HTML only contains visible entries; historical records stay in canonical JSON.
    data["stations"] = [s for s in data["stations"] if s.get("first_batch") or s.get("simple_signup_selected") or s.get("personal_link")]
    data.pop("crawl_logs", None)
    embedded = json.dumps(public_data(data), ensure_ascii=False).replace("<", "\\u003c")
    template = template.replace('let DATA = {"stations":[],"selection_notes":[]}; /* RELAY_DATA */', 'let DATA = '+embedded+'; /* RELAY_DATA */')
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(template)
    return output_html_path


def export_json_snapshot(db: RelayDatabase, output_json_path: str) -> str:
    # The store already is JSON: do not overwrite it with a truncated export.
    from src.json_store import public_data
    if os.path.abspath(output_json_path) != os.path.abspath(db.db_path):
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(public_data(db.snapshot()), f, ensure_ascii=False, indent=2)
    return output_json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 中转站多渠道爬虫与 JSON 数据库管理系统")
    parser.add_argument("--data", "--db", dest="db", default=DEFAULT_DB_PATH, help="JSON 数据库文件路径 (默认: ai_relays_export.json)")
    parser.add_argument("--sync", action="store_true", help="从 GitHub 福利站仓库同步中转站数据")
    parser.add_argument("--issues", action="store_true", help="从 GitHub Issues 爬取最新社区投稿中转站")
    parser.add_argument("--search", action="store_true", help="从 Google / Bing / DuckDuckGo 搜索渠道发现中转站")
    parser.add_argument("--probe", action="store_true", help="实时探测各站点 /api/status、跳转链接与最新公告")
    parser.add_argument("--probe-slug", type=str, default="", help="仅实时探测指定 slug 的站点 (如 docode)")
    parser.add_argument("--crawl-url", type=str, default="", help="直接爬取并收录指定的 AI 中转站 URL")
    parser.add_argument("--export-json", type=str, default="ai_relays_export.json", help="导出 JSON 数据文件名")
    parser.add_argument("--export-html", type=str, default="ai_relay_dashboard.html", help="导出可视化看板 HTML 文件名")
    parser.add_argument("--set-my-aff", nargs=2, metavar=("SLUG", "MY_CODE"), help="设置某站点的【我的专属邀请码】并自动生成我的推广链接 (例如: --set-my-aff agentrouter MY123)")
    parser.add_argument("--set-my-key", nargs=2, metavar=("SLUG", "MY_KEY"), help="设置某站点的【我的 API Key 令牌】保存到 JSON")
    parser.add_argument("--serve", type=int, default=0, help="启动 RESTful API 与看板 HTTP 服务的端口号 (例如 8080)")

    args = parser.parse_args()

    db = RelayDatabase(args.db)
    crawler = RelayCrawler(db, timeout=10.0)

    ran_any = False

    if args.sync:
        ran_any = True
        sync_res = crawler.sync_from_github_welfare_repo()
        print(f"[SYNC] 已从 {sync_res['source']} 同步 {sync_res['count']} 个 AI 中转站至 JSON ({args.db})")

    if args.issues:
        ran_any = True
        iss_res = crawler.crawl_github_issues_submissions()
        print(f"[ISSUES] 已从 GitHub Issues 社区投稿爬取并收录 {iss_res['discovered_count']} 个新站点")

    if args.search:
        ran_any = True
        s_res = crawler.crawl_search_channels()
        print(
            f"[SEARCH] 已执行 {s_res['queries_executed']} 组搜索引擎探测，记录 {s_res['logs_created']} 条搜索日志，"
            f"发现 {len(s_res['discovered_urls'])} 条推广链接"
        )

    if args.crawl_url:
        ran_any = True
        st = crawler.crawl_custom_url(args.crawl_url)
        print(f"[CRAWL-URL] 已抓取并入库站点: {st.get('name')} ({st.get('home_url')})")

    if args.set_my_aff:
        ran_any = True
        slug, my_code = args.set_my_aff
        updated = db.set_my_affiliate_info(slug, my_invite_code=my_code)
        if not updated:
            print(f"[ERROR] 未找到标识为 {slug} 的站点", file=sys.stderr)
            return 1
        print(
            f"[MY-AFF] 已更新站点 {updated['name']} ({updated['slug']}) 的个人邀请码:\n"
            f"  - 原上游邀请码: {updated['invite_code'] or '无'}\n"
            f"  - 我的专属邀请码: {updated['my_invite_code']}\n"
            f"  - 我的专属推广链接: {updated['my_invite_url']}"
        )

    if args.set_my_key:
        ran_any = True
        slug, my_key = args.set_my_key
        updated = db.set_my_affiliate_info(slug, my_api_key=my_key, replace_register_url=False)
        if not updated:
            print(f"[ERROR] 未找到标识为 {slug} 的站点", file=sys.stderr)
            return 1
        print(f"[MY-KEY] 已保存站点 {updated['name']} ({updated['slug']}) 的个人 API Key 令牌")

    if args.probe_slug:
        ran_any = True
        target = db.get_station(args.probe_slug)
        if not target:
            print(f"[ERROR] 未找到标识为 {args.probe_slug} 的站点", file=sys.stderr)
            return 1
        updated = crawler.probe_station_live(target)
        print(
            f"[PROBE] 站点 {updated['name']} ({updated['home_url']}) 探测完成: "
            f"online={updated['online_status']}, latency={updated['latency_ms']}ms, "
            f"redirect={updated['redirect_url']}, 充值比例={updated['recharge_ratio']}"
        )

    if args.probe:
        ran_any = True
        p_res = crawler.probe_all_stations()
        print(f"[PROBE-ALL] 已并发探测 {p_res['probed_count']} 个站点，在线 {p_res['online_count']} 个")

    if args.export_json:
        json_path = export_json_snapshot(db, args.export_json)
        print(f"[EXPORT-JSON] 已导出完整数据快照: {json_path}")

    if args.export_html:
        html_path = generate_dashboard_html(db, args.export_html)
        print(f"[EXPORT-HTML] 已生成可视化交互看板: {html_path}")

    stats = db.get_statistics()
    print(
        f"\n=== JSON 数据库统计 ({os.path.basename(args.db)}) ===\n"
        f"总收录站点: {stats['total_stations']} | 活跃站点: {stats['active_stations']} | "
        f"在线站点: {stats['online_stations']} | 历史归档: {stats['archived_stations']}\n"
        f"历史额度合计（非现金，不可跨站比较）: ${stats['total_usd_welfare']} | 活动/公告记录: {stats['total_activities']} 条 | "
        f"模型定价记录: {stats['total_models']} 条 | 爬虫日志: {stats['total_crawl_logs']} 条"
    )

    if args.serve > 0:
        app = RelayAPIApplication(db, crawler)
        handler_cls = make_http_handler(app, dashboard_path=args.export_html)
        server = HTTPServer(("127.0.0.1", args.serve), handler_cls)
        print(f"\n[SERVER] 已启动服务: http://127.0.0.1:{args.serve}")
        server.serve_forever()

    return 0


if __name__ == "__main__":
    sys.exit(main())
