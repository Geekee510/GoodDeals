#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_deals.py
==============
抓取「什么值得买（SMZDM）」官方 RSS 与官方榜单接口（/top/json_more），解析、去重后输出
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

# 价格：匹配 ¥ / ￥ 以及国内常见的「到手价199 / 68.7元 / ￥1,299.00」写法。
# 数字部分支持 1~6 位（4099元）或千分位（1,299元）——
# 勿用 \d{1,3}：对「4099元」会从第二位匹配出「099」→ 99 的严重错价！
PRICE_SYMBOL_RE = re.compile(
    r"[¥￥]\s?((?:\d{1,3}(?:,\d{3})+|\d{1,6})(?:\.\d{1,2})?)"
)
PRICE_YUAN_RE = re.compile(r"((?:\d{1,3}(?:,\d{3})+|\d{1,6})(?:\.\d{1,2})?)\s*元")
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")

# 关键词自动分类（针对 SMZDM 综合好价源与线报酷，两者均不提供统一品类）。
# 算法：classify(title, desc) 两级判定——标题命中直接定类（标题最能代表商品，
# 避免正文促销文案干扰）；标题无命中才用正文；同文本内按「命中词数」评分取最高，
# 平分时靠前的类优先。词表按子串匹配，勿用歧义单字（如"酒/包"）。
CATEGORY_KEYWORDS = {
    # 酒水置顶（最高优先级）：酒类一旦命中即归入此类，避免被后面的美妆/食品词误截。
    # 注意不用单字「酒」，否则「酒家」「酒店」类标题会误入
    "酒水": ["白酒", "红酒", "啤酒", "葡萄酒", "茅台", "五粮液", "洋河", "泸州",
             "郎酒", "汾酒", "黄酒", "洋酒", "香槟", "鸡尾酒", "威士忌", "白兰地",
             "伏特加", "果酒", "米酒", "清酒", "名酒", "泡酒", "药酒", "贡酒",
             "纯粮", "酒精度", "原浆"],
    "数码": ["手机", "电脑", "笔记本", "平板", "键盘", "鼠标", "耳机", "显卡", "显示器",
             "充电", "数据线", "路由器", "相机", "镜头", "主板", "cpu", "内存", "硬盘",
             "固态", "充电宝", "蓝牙", "音箱", "智能手表", "手表", "ipad", "iphone",
             "安卓", "摄像头", "无人机", "数码", "游戏机", "switch", "主机", "麦克风",
             "移动电源", "手环", "投影", "存储卡", "电脑椅", "键鼠",
             # 苹果电子产品消歧：标题含「苹果」时靠这些产品词压过食品的「苹果」
             "airpods", "mac", "macbook", "imac", "ios", "苹果手机", "苹果电脑",
             "苹果平板", "苹果耳机", "苹果手表", "苹果笔电",
             "电源", "充电器", "适配器", "type-c", "lightning", "毫安", "智能门锁"],
    "家用电器": ["冰箱", "洗衣机", "空调", "电视", "热水器", "微波炉", "电饭煲", "扫地",
             "净化器", "加湿", "电风扇", "风扇", "油烟机", "洗碗机", "净水", "吹风机",
             "电动牙刷", "家电", "吸尘器", "料理机", "空气炸锅", "取暖", "电水壶",
             "电火锅", "电蒸锅", "电磁炉", "豆浆机", "榨汁机", "体脂秤", "挂烫机",
             "破壁机", "电压力锅", "灯具"],
    "美妆个护": ["美妆", "面膜", "口红", "护肤", "化妆品", "洗面奶", "精华", "防晒",
             "香水", "洗发", "沐浴", "牙膏", "卫生巾", "卸妆", "粉底", "眼影",
             "彩妆", "身体乳", "护手", "剃须", "润肤", "面霜", "乳液", "湿巾",
             "玻尿酸", "胶原蛋白", "洁面", "爽肤"],
    "服饰鞋包": ["服饰", "衣服", "男装", "女装", "外套", "裤", "裙", "内衣", "t恤",
             "运动鞋", "靴", "帽子", "围巾", "背包", "挎包", "钱包", "手提包",
             "双肩包", "书包", "箱包", "卡包", "鞋", "羽绒", "卫衣", "衬衫",
             "冲锋衣", "夹克", "牛仔裤", "休闲裤", "袜", "马甲", "棉服", "皮衣",
             "西服", "家居服", "睡衣", "秋衣", "秋裤", "短袖", "长袖", "连衣裙",
             "半身裙", "上衣", "工装", "布料", "面料"],
    "运动户外": ["运动", "户外", "健身", "瑜伽", "跑步", "球", "帐篷", "睡袋", "登山",
             "自行车", "哑铃", "跑步机", "泳衣", "骑行", "徒步", "越野", "钓",
             "渔具", "羽毛球", "篮球", "足球", "乒乓球", "摩托车", "电动车",
             "滑板", "护膝", "护腕", "轮滑", "旱冰"],
    "日用百货": ["日用", "百货", "收纳", "清洁", "洗衣液", "垃圾", "保鲜", "雨伞",
             "雨具", "电池", "灯泡", "挂钩", "家居", "厨具", "杯", "碗", "锅",
             "床品", "毛巾", "拖把", "抽纸", "卷纸", "湿厕纸", "纸", "洗洁精",
             "菜板", "餐具", "筷子", "香薰", "花瓶", "维达", "清风", "心相印",
             "皂", "刷", "梳子", "衣架", "砧板", "水壶", "保温壶", "密封罐"],
    "食品生鲜": ["食品", "零食", "牛奶", "生鲜", "水果", "咖啡", "茶", "饮料",
             "坚果", "饼干", "巧克力", "大米", "面粉", "食用油", "肉", "海鲜",
             "蔬菜", "速食", "方便面", "酸奶", "糖", "调味品", "面包", "薯片",
             "燕麦", "苹果", "橙", "香蕉", "榴莲", "牛排", "鸡翅", "鸡爪",
             "牛肉", "猪肉", "羊肉", "鱼", "虾", "蟹", "蛋", "豆浆", "糕点",
             "辣条", "可乐", "果汁", "矿泉水", "包子", "饺子", "汤圆", "米线",
             "粉丝", "醋", "酱油", "料酒", "火腿", "香肠", "卤味",
             # 水果细分（注意：勿用「果」单字，否则「苹果手机」等会双计误导数码）
             "芒果", "百香果", "火龙果", "猕猴桃", "草莓", "蓝莓", "西梅", "椰子",
             "柚", "橙子", "雪梨", "水蜜桃", "黄桃", "荔枝", "龙眼", "枇杷",
             "车厘子", "山竹", "甘蔗", "哈密瓜", "西瓜", "葡萄"],
}


def _match_cat(low: str):
    """对单段文本评分：命中最多的类获胜，平分时按词表顺序（前面的类优先）。"""
    if not low:
        return None
    best_cat, best_n = None, 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        n = sum(1 for kw in kws if kw in low)
        if n > best_n:
            best_cat, best_n = cat, n
    return best_cat


def classify(title: str = "", desc: str = "") -> str:
    """两级判定：标题优先（最能代表商品，不受正文促销文案干扰），
    标题无命中再用正文兜底；都无命中归「其他」。"""
    cat = _match_cat((title or "").lower())
    if cat:
        return cat
    cat = _match_cat((desc or "").lower())
    return cat or "其他"


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
        category = classify(title, summary)
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


def fetch_ranking(source: dict, timeout: int, ua: str):
    """直接调用 SMZDM 官方榜单接口 /top/json_more。

    RSSHub 的 smzdm/ranking 路由本质也是转发这个接口，但 rsshub.app 公共
    实例封锁了云机房 IP；直连 smzdm.com 自己的接口则云端可用、无需登录、
    无签名，低风险。返回 JSON 的 data.list 为嵌套数组 [[item,item],...]。
    """
    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://www.smzdm.com/top",
        "X-Requested-With": "XMLHttpRequest",
    }
    params = {
        "rank_type": source.get("rank_type", "pinlei"),
        "rank_id": source.get("rank_id", "11"),
        "hour": source.get("hour", "24"),
    }
    url = "https://www.smzdm.com/top/json_more"
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
        j = resp.json()
        if j.get("error_code") != 0:
            log(f"  ⚠ 接口返回错误 {source['name']}: {j.get('error_msg')}")
            return []
        rows = (j.get("data") or {}).get("list", [])
        items = []
        for row in rows:
            if not isinstance(row, list):
                row = [row]
            for it in row:
                if isinstance(it, dict) and it.get("article_title"):
                    items.append(it)
        return items
    except Exception as e:
        log(f"  ✗ 抓取失败 {source['name']} ({url}): {e}")
        return []


def parse_ranking_item(item: dict, source: dict):
    link = (item.get("article_url") or "").strip()
    if not link:
        return None
    title = (item.get("article_title") or "").strip()
    price_raw = item.get("article_price") or ""
    price = extract_price(price_raw)
    image = item.get("article_pic") or None
    # 分类以内容为准（classify 识别不出「其他」时才用榜单名兜底）——
    # 实测 SMZDM 榜单会混入杂项条目，直接贴榜单名会造成系统性错分
    cat = classify(title, strip_html(price_raw))
    category = cat if cat != "其他" else (source.get("category") or "好价")
    now = datetime.now(timezone.utc)
    return {
        "title": title,
        "link": link,
        "price": price,
        "image": image,
        "category": category,
        "source": source["name"],
        "summary": strip_html(price_raw)[:200],
        "published": now.isoformat(),
        "published_ts": now.timestamp(),
    }


def fetch_xianbao(source: dict, timeout: int, ua: str):
    """线报酷开放 API（无需密钥、无需登录）。

    文档：https://new.xianbao.fun/docs/api.html
    端点 GET /api/v1/feed?cate=<频道>&limit=<n>&with_html=1
    返回 data.items，字段：title/url/price/content/category/published_at。
    - 列表本身无封面图，但 with_html=1 后 content 为 HTML，可从中抠首图
      （线报酷已对图片做防盗链处理，可直接嵌入）。
    - published_at 为 Unix 秒时间戳。
    - 限流 60 次/IP/分钟（每次运行仅几个请求，安全）。
    """
    headers = {
        "User-Agent": ua,
        "Accept": "application/json",
    }
    params = {
        "cate": source.get("cate", "weibo"),
        "limit": source.get("limit", 30),
        "with_html": 1,
    }
    url = "https://new.xianbao.fun/api/v1/feed"
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
        j = resp.json()
        if j.get("code") not in (0, None):
            log(f"  ⚠ 接口返回异常 {source['name']}: {j.get('msg')}")
            return []
        return (j.get("data") or {}).get("items", [])
    except Exception as e:
        log(f"  ✗ 抓取失败 {source['name']} ({url}): {e}")
        return []


def parse_xianbao_item(item: dict, source: dict):
    link = (item.get("url") or "").strip()
    if not link:
        return None
    title = (item.get("title") or "").strip()
    content = item.get("content") or ""

    price = item.get("price")
    if price is not None:
        try:
            price = float(price)
        except (ValueError, TypeError):
            price = None

    # 封面图：从 content 的 HTML 中抠首图（线报酷已做防盗链处理）；无线报则占位
    image = extract_image(content) or None

    # 时间：published_at 为 Unix 秒
    pa = item.get("published_at")
    if isinstance(pa, (int, float)):
        dt = datetime.fromtimestamp(pa, tz=timezone.utc)
        published_iso = dt.isoformat()
        published_ts = dt.timestamp()
    else:
        now = datetime.now(timezone.utc)
        published_iso = now.isoformat()
        published_ts = now.timestamp()

    # 用统一关键词分类，与 SMZDM 主源视角一致
    category = classify(title, content)
    return {
        "title": title,
        "link": link,
        "price": price,
        "image": image,
        "category": category,
        "source": source["name"],
        "summary": strip_html(content)[:200],
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
        if source.get("type") == "smzdm_ranking":
            log(f"→ {source['name']} (SMZDM榜单 {source.get('rank_type')}/{source.get('rank_id')})")
            raw = fetch_ranking(source, timeout, ua)
            items_raw = [parse_ranking_item(it, source) for it in raw]
        elif source.get("type") == "xianbao_feed":
            log(f"→ {source['name']} (线报酷 feed/{source.get('cate')})")
            raw = fetch_xianbao(source, timeout, ua)
            items_raw = [parse_xianbao_item(it, source) for it in raw]
        else:
            log(f"→ {source['name']} ({source['url']})")
            entries = fetch_feed(source, timeout, ua)
            items_raw = [parse_entry(e, source) for e in entries]
        items_raw = [x for x in items_raw if x]
        log(f"  获取到 {len(items_raw)} 条")
        for item in items_raw:
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
