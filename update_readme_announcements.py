#!/usr/bin/env python3
"""Refresh the README announcement snapshot from the project JSON store."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
START = '## 📢 站点公告快照'
END = '## 📋 推荐详情'
BEIJING = timezone(timedelta(hours=8))


def local_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(BEIJING).strftime('%Y-%m-%d %H:%M:%S')


def cell(value):
    return ' '.join(str(value or '').replace('|', '\\|').split())


def build_section(data):
    active = [s for s in data['stations'] if not s.get('is_archived') and not s.get('deleted_at')]
    online = sum(bool(s.get('online_status')) for s in active)
    checked = [s.get('last_checked_at') for s in active if s.get('last_checked_at')]
    probe_at = data.get('last_probe_at') or (max(checked) if checked else data.get('generated_at') or '')
    probe_display = local_time(probe_at) if probe_at else '无探测时间记录'
    slugs = data.get('first_batch_slugs') or []
    by_slug = {s['slug']: s for s in data['stations']}

    lines = [
        START + '（自动更新）',
        '',
        f'最近一次全站探测：`{probe_display}`（北京时间）。活跃站点 {len(active)} 个，探测器标记在线 {online} 个。以下区分本轮结构化公告与保留的公告快照；“在线”只代表探测器可达，不证明公告完整或活动仍有效。',
        '',
        '| 排名 | 站点 | 探测状态 | 公告来源/日期 | 公告与活动摘要 |',
        '| :---: | --- | :---: | --- | --- |',
    ]
    for rank, slug in enumerate(slugs, 1):
        station = by_slug.get(slug)
        if not station:
            continue
        checked_at = station.get('last_checked_at') or ''
        if not checked_at:
            status = '未探测'
        else:
            status = '在线' if station.get('online_status') else '离线'
        new_announcements = bool(checked_at and station.get('announcements_checked_at') == checked_at)
        source = '本轮接口公告' if new_announcements else '保存快照（本轮未返回结构化公告）'
        promos = station.get('live_promos') or []
        if promos:
            promo = promos[0]
            date = str(promo.get('date') or '日期未提供')
            summary = promo.get('text') or station.get('activities_summary') or '暂无公告摘要'
        else:
            date = '日期未提供'
            summary = station.get('activities_summary') or '暂无公告摘要'
        summary = cell(summary)
        if len(summary) > 260:
            summary = summary[:259] + '…'
        lines.append(f'| {rank} | {cell(station.get("name"))} | {status} | {source}；{cell(date)} | {summary} |')
    lines += ['', '公告日期和活动有效期以站点原文为准；探测成功不代表站点返回了新公告，旧快照可能过期。', '']
    return '\n'.join(lines)


def update(readme, data):
    text = readme.read_text(encoding='utf-8')
    start = text.index(START)
    end = text.index(END, start)
    text = text[:start] + build_section(data) + '\n' + text[end:]
    readme.write_text(text, encoding='utf-8', newline='\n')


def self_test():
    sample = {
        'last_probe_at': '2026-10-21T03:00:00Z',
        'stations': [
            {'slug': 'demo', 'name': 'Demo', 'last_checked_at': '2026-10-21T03:00:00Z',
             'online_status': True, 'announcements_checked_at': '2026-10-21T03:00:00Z',
             'live_promos': [{'date': '2026-10-20', 'text': '公告 | 已核验'}]},
        ],
        'first_batch_slugs': ['demo'],
    }
    result = build_section(sample)
    assert '2026-10-21 11:00:00' in result
    assert '本轮接口公告' in result and '公告 \\| 已核验' in result
    sample['stations'][0]['announcements_checked_at'] = '2026-10-20T00:00:00Z'
    assert '保存快照（本轮未返回结构化公告）' in build_section(sample)
    print('PASS: README timestamp, current announcement, stale-snapshot labeling, and Markdown escaping')


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        self_test()
    else:
        data = json.loads((ROOT / 'ai_relays_export.json').read_text(encoding='utf-8'))
        update(ROOT / 'README.md', data)
        print('Updated README.md announcement snapshot')
