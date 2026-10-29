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

# 关键词自动分类（针对 SMZDM 综合好价源，该源不提供逐条分类）。
# 顺序即优先级：靠前命中即归类。未命中归为「其他」。
CATEGORY_KEYWORDS = {
    "数码": ["手机", "电脑", "笔记本", "平板", "键盘", "鼠标", "耳机", "显卡", "显示器",
             "充电", "数据线", "路由器", "相机", "主板", "cpu", "内存", "硬盘", "固态",
             "充电宝", "蓝牙", "音箱", "智能手表", "ipad", "iphone", "安卓", "摄像头",
             "无人机", "数码", "游戏机", "switch", "主机", "显示器", "麦克风", "固态硬盘"],
    "家用电器": ["冰箱", "洗衣机", "空调", "电视", "热水器", "微波炉", "电饭煲", "扫地",
             "净化器", "加湿器", "电风扇", "油烟机", "洗碗机", "净水器", "吹风机",
             "电动牙刷", "家电", "吸尘器", "料理机", "空气炸锅", "取暖", "电水壶"],
    "美妆个护": ["美妆", "面膜", "口红", "护肤", "化妆品", "洗面奶", "精华", "防晒",
             "香水", "洗发", "沐浴", "牙膏", "纸巾", "卫生巾", "卸妆", "粉底", "眼影",
             "彩妆", "身体乳", "护手", "剃须"],
    "服饰鞋包": ["服饰", "衣服", "男装", "女装", "外套", "裤", "裙", "内衣", "t恤",
             "运动鞋", "靴", "帽子", "围巾", "包", "鞋", "羽绒", "卫衣", "衬衫"],
    "运动户外": ["运动", "户外", "健身", "瑜伽", "跑步", "球", "帐篷", "睡袋", "登山",
             "自行车", "哑铃", "跑步机", "泳衣", "骑行"],
    "日用百货": ["日用", "百货", "收纳", "清洁", "洗衣液", "垃圾袋", "保鲜", "雨伞",
             "电池", "灯泡", "挂钩", "家居", "厨具", "杯", "碗", "锅", "床品", "毛巾",
             "拖把", "垃圾桶"],
    "食品生鲜": ["食品", "零食", "牛奶", "生鲜", "水果", "咖啡", "茶", "饮料", "酒",
             "坚果", "饼干", "巧克力", "大米", "油", "面", "肉", "海鲜", "蔬菜",
             "速食", "方便面", "酸奶", "水", "糖", "调味品", "面包"],
}


def classify(text: str) -> str:
    if not text:
        return "其他"
    low = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in low:
                return cat
    return "其他"


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

    # 分类：来源显式指定优先；若开启 auto_category 则用关键词自动归类（SMZDM 综合源无逐条分类）
    if source.get("auto_category"):
        category = classify((title + " " + summary).lower())
    else:
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
