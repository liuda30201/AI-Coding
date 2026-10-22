"""Single JSON store. RelayDatabase is retained as a compatibility name.
Writes are atomic and serialized across instances/threads in one process.
Run one writer process per file (the bundled HTTP server is single-process).
"""
from __future__ import annotations
import copy
import json
import math
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ai_relays_export.json')
SLUG_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_-]{1,62}$')
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def utc_now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def validate_url(url, allow_empty=True):
    if url is None or not str(url).strip():
        if allow_empty:
            return None
        raise ValueError('URL cannot be empty')
    cleaned = str(url).strip()
    p = urlparse(cleaned)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Invalid HTTP/HTTPS URL: ' + cleaned)
    return cleaned


def slugify(value, fallback_url=''):
    raw = re.sub(r'[^a-z0-9_-]+', '-', str(value or '').strip().lower())
    raw = re.sub(r'-{2,}', '-', raw).strip('-_')
    if len(raw) < 2 and fallback_url:
        host = urlparse(fallback_url).hostname or ''
        for prefix in ('www.', 'api.', 'new.', 'free.'):
            if host.startswith(prefix):
                host = host[len(prefix):]
        raw = re.sub(r'[^a-z0-9_-]+', '-', host.split('.')[0]).strip('-_')
    return (raw if len(raw) >= 2 else 'site-' + (raw or 'unknown'))[:63]


def public_data(value):
    """Never copy private credentials into HTML/API/export responses."""
    if isinstance(value, dict):
        return {k: public_data(v) for k, v in value.items() if k not in ('my_api_key', 'api_key', 'access_token', 'secret')}
    if isinstance(value, list):
        return [public_data(v) for v in value]
    return value


class RelayDatabase:
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = os.path.abspath(db_path)
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(self.db_path, threading.RLock())
        with self._lock:
            if not os.path.exists(self.db_path):
                self._save({'schema_version': 2, 'stations': [], 'crawl_logs': [], 'selection_notes': []})
            self._read()

    def _read(self):
        with open(self.db_path, encoding='utf-8') as f:
            d = json.load(f)
        if not isinstance(d, dict) or not isinstance(d.get('stations'), list) or not isinstance(d.get('crawl_logs', []), list):
            raise ValueError('Invalid JSON store schema; original file was not overwritten')
        d.setdefault('crawl_logs', [])
        return d

    def _save(self, data):
        parent = os.path.dirname(self.db_path)
        os.makedirs(parent, exist_ok=True)
        raw = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
        fd, path = tempfile.mkstemp(prefix='.relay-', suffix='.tmp', dir=parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(path, self.db_path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._read())

    def mark_generated(self, at=None):
        generated_at = at or utc_now_iso()
        with self._lock:
            root = self._read()
            root['generated_at'] = generated_at
            root['last_probe_at'] = generated_at
            self._save(root)
            return generated_at

    def _find(self, data, identifier):
        return next((s for s in data['stations'] if (str(s.get('id')) == str(identifier) if str(identifier).isdigit() else s['slug'] == str(identifier).strip().lower())), None)

    def upsert_station(self, data):
        if not isinstance(data, dict) or not str(data.get('name') or '').strip():
            raise ValueError("Station 'name' is required")
        home = validate_url(data.get('home_url'), False)
        slug = slugify(data.get('slug') or data['name'], home)
        incoming = copy.deepcopy(data)
        incoming.update(name=str(data['name']).strip(), home_url=home, slug=slug)
        for field in ('register_url', 'redirect_url', 'status_api_url', 'pricing_api_url', 'docs_url', 'my_invite_url'):
            if incoming.get(field):
                incoming[field] = validate_url(incoming[field])
        with self._lock:
            root = self._read()
            old = self._find(root, slug)
            s = copy.deepcopy(old) if old else {'id': max((x['id'] for x in root['stations']), default=0) + 1, 'created_at': utc_now_iso(), 'activities': [], 'models': [], 'panel_type': 'newapi', 'credit_unit': 'usd', 'source_channel': 'manual', 'online_status': False, 'is_archived': False}
            sid = s['id']
            created = s['created_at']
            # Preserve existing personal overrides and curated evidence on remote sync.
            protected = {k: s[k] for k in ('my_invite_code', 'my_invite_url', 'my_api_key') if s.get(k)}
            acts, models = incoming.pop('activities', None), incoming.pop('models', None)
            s.update(incoming)
            s.update(protected)
            s.update(id=sid, created_at=created, updated_at=utc_now_iso(), deleted_at=None)
            for field in ('signup_bonus', 'invite_bonus', 'daily_checkin_bonus', 'first_day_total'):
                val = s.get(field)
                if val not in (None, ''):
                    val = float(val)
                    if not math.isfinite(val) or val < 0:
                        raise ValueError('Invalid nonnegative amount: ' + field)
                    s[field] = val
            if data.get('first_day_total') is None:
                parts = [s.get(k) for k in ('signup_bonus', 'invite_bonus', 'daily_checkin_bonus') if s.get(k) is not None]
                s['first_day_total'] = sum(parts) if parts else None
            for key in ('registration_methods', 'registration_requirements', 'supported_protocols', 'mirrors', 'tags', 'highlights', 'caveats'):
                s.setdefault(key, [])
            for key in ('invite_code', 'my_invite_code', 'my_invite_url', 'my_api_key', 'recharge_ratio', 'activities_summary', 'subtitle'):
                s.setdefault(key, '')
            s.setdefault('register_url', home)
            s.setdefault('redirect_url', s['register_url'])
            if s.get('my_invite_url'):
                s['register_url'] = s['redirect_url'] = s['my_invite_url']
                s['invite_code'] = s['my_invite_code']
            if acts is not None:
                for act in acts:
                    a = {'content': act, 'title': act[:60]} if isinstance(act, str) else copy.deepcopy(act)
                    if a.get('content') and not any(x.get('content') == a['content'] for x in s['activities']):
                        s['activities'].append(a)
            if models is not None:
                by_name = {m['name']: m for m in s['models']}
                for model in models:
                    m = copy.deepcopy(model)
                    name = m.get('name') or m.get('model_name')
                    if name:
                        m['name'] = name
                        by_name[name] = m
                s['models'] = list(by_name.values())
            s['model_count'] = len(s['models'])
            if old:
                root['stations'][root['stations'].index(old)] = s
            else:
                root['stations'].append(s)
            self._save(root)
            return sid

    def get_station(self, identifier):
        with self._lock:
            root = self._read()
            s = self._find(root, identifier)
            if not s or s.get('deleted_at'):
                return None
            s['recent_logs'] = [x for x in root['crawl_logs'] if x.get('station_id') == s['id']][-10:][::-1]
            return copy.deepcopy(s)

    def list_stations(self, keyword=None, channel=None, panel_type=None, online_only=False, include_archived=False, checkin_only=False, page=1, limit=20):
        page, limit = max(1, int(page)), max(1, min(100, int(limit)))
        with self._lock:
            items = self._read()['stations']
        items = [s for s in items if not s.get('deleted_at') and (include_archived or not s.get('is_archived')) and (not online_only or s.get('online_status')) and (not checkin_only or s.get('checkin_enabled') or (s.get('daily_checkin_bonus') or 0) > 0) and (not channel or s.get('source_channel') == channel) and (not panel_type or s.get('panel_type') == panel_type) and (not keyword or keyword.strip().lower() in json.dumps(public_data(s), ensure_ascii=False).lower())]
        items.sort(key=lambda s: (bool(s.get('is_archived')), not bool(s.get('online_status')), -(s.get('first_day_total') or 0), s['id']))
        total = len(items)
        return {'items': items[(page-1)*limit:page*limit], 'pagination': {'page': page, 'limit': limit, 'total': total, 'pages': (total+limit-1)//limit}}

    def set_my_affiliate_info(self, identifier, my_invite_code=None, my_api_key=None, replace_register_url=True):
        with self._lock:
            root = self._read()
            s = self._find(root, identifier)
            if not s or s.get('deleted_at'):
                return None
            if my_invite_code is not None:
                code = str(my_invite_code).strip()
                s['my_invite_code'] = code
                p = urlparse(s.get('register_url') or s['home_url'])
                pairs = parse_qsl(p.query, keep_blank_values=True)
                keys = {'aff', 'ref', 'inviteCode', 'referral_code', 'start', 'i'}
                if '/r/' in p.path:
                    p = p._replace(path=re.sub(r'(/r/)[^/]+', lambda m: m[1]+code, p.path))
                else:
                    pairs = [(k, code if k in keys else v) for k, v in pairs]
                    if not any(k in keys for k, v in pairs):
                        pairs.append(('aff', code))
                    p = p._replace(query=urlencode(pairs))
                s['my_invite_url'] = urlunparse(p)
                if replace_register_url:
                    s['register_url'] = s['redirect_url'] = s['my_invite_url']
                    s['invite_code'] = code
            if my_api_key is not None:
                s['my_api_key'] = str(my_api_key)
            self._save(root)
            return self.get_station(identifier)

    def delete_station(self, identifier, hard=False):
        with self._lock:
            root = self._read()
            s = self._find(root, identifier)
            if not s or (s.get('deleted_at') and not hard):
                return False
            if hard:
                root['stations'].remove(s)
                for log in root['crawl_logs']:
                    if log.get('station_id') == s['id']:
                        log['station_id'] = None
            else:
                s['deleted_at'] = utc_now_iso()
            self._save(root)
            return True

    def log_crawl(self, channel, target_url, http_status=0, latency_ms=0, is_success=False, final_redirect_url='', error_message='', raw_excerpt='', station_id=None):
        with self._lock:
            root = self._read()
            log = dict(id=max((x['id'] for x in root['crawl_logs']), default=0)+1, channel=channel, target_url=target_url, http_status=int(http_status), latency_ms=int(latency_ms), is_success=bool(is_success), final_redirect_url=final_redirect_url, error_message=str(error_message)[:500], raw_excerpt=str(raw_excerpt)[:1000], station_id=station_id, checked_at=utc_now_iso())
            root['crawl_logs'].append(log)
            self._save(root)
            return log['id']

    def get_statistics(self):
        root = self.snapshot()
        items = [s for s in root['stations'] if not s.get('deleted_at')]
        active = [s for s in items if not s.get('is_archived')]
        amounts = [s.get('first_day_total') or 0 for s in active if s.get('credit_unit') == 'usd']
        return dict(total_stations=len(items), active_stations=len(active), online_stations=sum(bool(s.get('online_status')) for s in active), archived_stations=len(items)-len(active), total_usd_welfare=round(sum(amounts), 2), max_first_day_usd=max(amounts, default=0), checkin_stations=sum(bool(s.get('checkin_enabled') or (s.get('daily_checkin_bonus') or 0)>0) for s in active), total_activities=sum(len(s.get('activities', [])) for s in items), total_models=sum(len(s.get('models', [])) for s in items), total_crawl_logs=len(root['crawl_logs']), by_channel={k:sum(s.get('source_channel')==k for s in items) for k in {s.get('source_channel', 'manual') for s in items}})
