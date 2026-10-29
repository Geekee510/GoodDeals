#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_deals.py
==============
抓取「什么值得买（SMZDM）」官方 RSS 与 RSSHub 定制频道，解析、去重后输出
`data/deals.json`，供静态前端渲染。

设计原则（对应项目方案）：
- 仅使用平台 **主动公开的 RSS 订阅源**，不爬取、不逆向、不登录，零合规风险。
- 数据版权归来源平台所有，前端会标注来源，仅供学习研究 / 小圈子分享。
- 单源失败不影响整体（容错），字段缺失有兜底。

依赖：feedparser, requests
用法：python scripts/fetch_deals.py
"""
import json
import os
import re
import html
from datetime import datetime, timezone

import feedparser
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
OUTPUT_PATH = os.path.join(ROOT, "data", "deals.json")

# 价格：匹配 ¥ / ￥ 以及国内常见的「到手价199 / 68.7元 / ￥1,299.00」写法
PRICE_SYMBOL_RE = re.compile(
    r"[¥￥]\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)"
)
PRICE_YUAN_RE = re.compile(r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\s*元")
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_image(text: str):
    if not text:
        return None
    m = IMG_RE.search(text)
    return m.group(1) if m else None


def extract_price(text: str):
    if not text:
        return None
    # 优先 ¥/￥ 符号价，其次「数字+元」写法（SMZDM 常见）
    for rx in (PRICE_SYMBOL_RE, PRICE_YUAN_RE):
        m = rx.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def fetch_feed(source: dict, timeout: int, ua: str):
    headers = {
        "User-Agent": ua,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Referer": "https://www.smzdm.com/",
    }
    try:
        resp = requests.get(source["url"], timeout=timeout, headers=headers)
        # 什么值得买官方 feed 仅 http 可用，https 会 403；此处自动降级重试
        if resp.status_code == 403 and source["url"].startswith("https://"):
            http_url = "http://" + source["url"][len("https://"):]
            log(f"  ↩ https 被拒，改用 http 重试 {http_url}")
            resp = requests.get(http_url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            log(f"  ⚠ 解析异常 {source['name']}: {parsed.bozo_exception}")
            return []
        return parsed.entries
    except Exception as e:
        log(f"  ✗ 抓取失败 {source['name']} ({source['url']}): {e}")
        return []


def parse_entry(entry: dict, source: dict):
    link = (entry.get("link") or "").strip()
    if not link:
        return None
    title = (entry.get("title") or "").strip()
    summary = entry.get("summary") or entry.get("description") or ""

    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if published:
        dt = datetime(*published[:6], tzinfo=timezone.utc)
        published_iso = dt.isoformat()
        published_ts = dt.timestamp()
    else:
        published_iso = ""
        published_ts = 0.0

    price = extract_price(title) or extract_price(summary)
    # 封面图优先级：SMZDM focus_pic 字段 > 描述内 <img> > media_content
    image = entry.get("focus_pic") or extract_image(summary)
    if not image and entry.get("media_content"):
        for m in entry["media_content"]:
            if m.get("url"):
                image = m["url"]
                break

    category = source.get("category") or entry.get("category", "")
    return {
        "title": title,
        "link": link,
        "price": price,
        "image": image,
        "category": category,
        "source": source["name"],
        "summary": strip_html(summary)[:200],
        "published": published_iso,
        "published_ts": published_ts,
    }


def main() -> None:
    config = load_config()
    site = config.get("site", {})
    timeout = site.get("fetch_timeout", 15)
    ua = site.get("user_agent", "Mozilla/5.0")
    max_items = site.get("max_items", 300)

    log(f"开始抓取，启用源 {sum(1 for s in config['sources'] if s.get('enabled', True))} 个")
    deals = {}
    for source in config["sources"]:
        if not source.get("enabled", True):
            continue
        log(f"→ {source['name']} ({source['url']})")
        entries = fetch_feed(source, timeout, ua)
        log(f"  获取到 {len(entries)} 条")
        for entry in entries:
            item = parse_entry(entry, source)
            if not item:
                continue
            if item["link"] in deals:  # 按链接去重
                continue
            deals[item["link"]] = item

    items = list(deals.values())
    items.sort(key=lambda x: x["published_ts"], reverse=True)
    items = items[:max_items]

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "site": {
            "title": site.get("title", "好价精选"),
            "subtitle": site.get("subtitle", ""),
        },
        "deals": items,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log(f"✓ 完成，输出 {len(items)} 条 → {os.path.relpath(OUTPUT_PATH, ROOT)}")


if __name__ == "__main__":
    main()
