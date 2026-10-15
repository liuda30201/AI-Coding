"""
RESTful HTTP API Server & Export Utilities for AI Relay Station Crawler.
Follows RESTful API design standards:
- Unified JSON response structure: {"code": 0, "message": "success", "data": ...}
- Input validation and JSON schema validation
- Endpoints:
  - GET  /api/v1/health
  - GET  /api/v1/stats
  - GET  /api/v1/stations
  - GET  /api/v1/stations/<slug_or_id>
  - POST /api/v1/stations
  - DELETE /api/v1/stations/<slug_or_id>
  - POST /api/v1/crawl
"""

from __future__ import annotations

import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple

from src.crawler import RelayCrawler
from src.db import RelayDatabase, utc_now_iso
from src.json_store import public_data


class RelayAPIApplication:
    """Core WSGI-like / framework-agnostic API router for easy unit testing and HTTP serving."""

    def __init__(self, db: RelayDatabase, crawler: Optional[RelayCrawler] = None) -> None:
        self.db = db
        self.crawler = crawler or RelayCrawler(db)

    @staticmethod
    def _ok(data: Any, status: int = 200) -> Tuple[int, Dict[str, Any]]:
        return status, {"code": 0, "message": "success", "data": public_data(data)}

    @staticmethod
    def _err(status: int, code: int, message: str, field: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
        payload: Dict[str, Any] = {"code": code, "message": message}
        if field:
            payload["field"] = field
        return status, payload

    def handle_request(
        self,
        method: str,
        path: str,
        query_params: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        """Route and process an API request, returning (http_status, response_dict)."""
        method = method.upper()
        q = query_params or {}
        clean_path = path.split("?")[0].rstrip("/") or "/"

        try:
            if method == "GET" and clean_path == "/api/v1/health":
                return self._ok({"status": "healthy", "timestamp": utc_now_iso()})

            if method == "GET" and clean_path == "/api/v1/stats":
                return self._ok(self.db.get_statistics())

            if method == "GET" and clean_path == "/api/v1/stations":
                try:
                    page = int(q.get("page", "1") or "1")
                    limit = int(q.get("limit", "20") or "20")
                except (ValueError, TypeError):
                    return self._err(400, 1004, "Query parameters 'page' and 'limit' must be valid integers", field="page")
                keyword = q.get("keyword")
                channel = q.get("channel")
                panel_type = q.get("panel_type")
                online_only = q.get("online_only", "").lower() in ("1", "true", "yes")
                include_archived = q.get("include_archived", "").lower() in ("1", "true", "yes")
                checkin_only = q.get("checkin_only", "").lower() in ("1", "true", "yes")

                result = self.db.list_stations(
                    keyword=keyword,
                    channel=channel,
                    panel_type=panel_type,
                    online_only=online_only,
                    include_archived=include_archived,
                    checkin_only=checkin_only,
                    page=page,
                    limit=limit,
                )
                return self._ok(result)

            if method == "GET" and clean_path.startswith("/api/v1/stations/"):
                identifier = clean_path.split("/api/v1/stations/", 1)[1]
                station = self.db.get_station(identifier)
                if not station:
                    return self._err(404, 4040, f"Station '{identifier}' not found")
                return self._ok(station)

            if method == "POST" and clean_path == "/api/v1/stations":
                if not isinstance(body, dict):
                    return self._err(400, 1001, "Request body must be a JSON object")
                station_id = self.db.upsert_station(body)
                created = self.db.get_station(station_id)
                return self._ok(created, status=201)

            if method == "DELETE" and clean_path.startswith("/api/v1/stations/"):
                identifier = clean_path.split("/api/v1/stations/", 1)[1]
                deleted = self.db.delete_station(identifier)
                if not deleted:
                    return self._err(404, 4040, f"Station '{identifier}' not found")
                return self._ok({"deleted": identifier})

            if method == "POST" and clean_path == "/api/v1/crawl":
                payload = body or {}
                mode = str(payload.get("mode") or "sync").strip().lower()
                if mode == "sync":
                    res = self.crawler.sync_from_github_welfare_repo()
                    return self._ok(res)
                if mode == "issues":
                    res = self.crawler.crawl_github_issues_submissions()
                    return self._ok(res)
                if mode == "search":
                    queries = payload.get("queries")
                    res = self.crawler.crawl_search_channels(queries if isinstance(queries, list) else None)
                    return self._ok(res)
                if mode == "probe":
                    slug = payload.get("slug")
                    if slug:
                        st = self.db.get_station(slug)
                        if not st:
                            return self._err(404, 4040, f"Station '{slug}' not found")
                        return self._ok(self.crawler.probe_station_live(st))
                    return self._ok(self.crawler.probe_all_stations())
                if mode == "url":
                    target_url = str(payload.get("url") or "").strip()
                    if not target_url:
                        return self._err(400, 1002, "Field 'url' is required for mode='url'", field="url")
                    res = self.crawler.crawl_custom_url(target_url, name=payload.get("name"))
                    return self._ok(res, status=201)

                return self._err(400, 1003, f"Unsupported crawl mode: {mode}", field="mode")

            return self._err(404, 4044, f"Endpoint '{method} {clean_path}' not found")

        except ValueError as exc:
            return self._err(400, 1000, str(exc))
        except Exception as exc:
            return self._err(500, 5000, f"Internal server error: {exc}")


def make_http_handler(app: RelayAPIApplication, dashboard_path: Optional[str] = None):
    """Create a BaseHTTPRequestHandler bound to RelayAPIApplication."""

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, data: Dict[str, Any]) -> None:
            raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in ("/", "/index.html") and dashboard_path and os.path.exists(dashboard_path):
                with open(dashboard_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            if parsed.path == "/ai_relays_export.json":
                data = app.db.snapshot()
                data.pop("crawl_logs", None)
                self._send_json(200, public_data(data))
                return

            q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
            status, payload = app.handle_request("GET", parsed.path, query_params=q)
            self._send_json(status, payload)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0") or "0")
            body_obj = None
            if length > 0:
                raw_body = self.rfile.read(min(length, 1024 * 1024))
                try:
                    body_obj = json.loads(raw_body.decode("utf-8"))
                except Exception:
                    self._send_json(400, {"code": 1001, "message": "Invalid JSON body"})
                    return
            status, payload = app.handle_request("POST", parsed.path, body=body_obj)
            self._send_json(status, payload)

        def do_DELETE(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            status, payload = app.handle_request("DELETE", parsed.path)
            self._send_json(status, payload)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return Handler
