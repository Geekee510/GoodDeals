# 好价精选 · 国内优惠聚合站（类 Dealsea）

给朋友小圈子看的国内优惠信息聚合站。聚合「什么值得买」等平台的**公开 RSS 订阅**，
零抓取、零逆向、零登录，纯静态 + 定时自动更新。先期不盈利、不挂联盟链接，低风险。

> 参考：Dealsea（海外折扣聚合）、DealMoon 北美省钱快报。

---

## 特性

- 📡 **合法数据源**：仅使用平台主动开放的 RSS（SMZDM 官方源 + RSSHub 定制频道），不爬不逆向。
- 🤖 **全自动更新**：GitHub Actions 每 2 小时抓取一次，重新生成数据并部署，无需常驻服务器。
- 📱 **移动端优先**：卡片流 + 分类筛选 + 关键词搜索 + 深色模式，朋友手机微信里直接看。
- 🆓 **零成本**：GitHub Pages 托管免费；之后可平滑迁到国内已备案域名（见下文）。
- 🔒 **低风险合规**：标来源、不登录不收隐私、不盈利。

---

## 目录结构

```
deals-site/
├── index.html              # 前端页面（移动端优先）
├── config.json             # RSS 数据源配置（改这里增删频道）
├── requirements.txt        # Python 依赖
├── .nojekyll               # 关闭 GitHub Pages 的 Jekyll 处理
├── scripts/
│   └── fetch_deals.py      # 抓取 + 解析 + 去重 → data/deals.json
├── assets/
│   ├── css/style.css
│   └── js/app.js           # 渲染、筛选、搜索、主题
├── data/
│   └── deals.json          # 自动生成（已被 Actions 覆盖），也作为兜底样本
└── .github/workflows/
    └── build.yml           # 定时抓取 + 部署到 Pages
```

---

## 本地预览

需 Python 3.9+。注意：前端通过 `fetch` 读取 `data/deals.json`，**不能直接双击打开
`index.html`（file:// 会被浏览器拦截）**，要用本地静态服务器：

```bash
cd deals-site
pip install -r requirements.txt

# 1) 生成数据（可选，仓库已带一份样本）
python scripts/fetch_deals.py

# 2) 起本地服务
python -m http.server 8000
# 浏览器打开 http://127.0.0.1:8000/
```

---

## 部署到 GitHub Pages（阶段一）

1. 在 GitHub **新建仓库**（公开，名字随意，如 `deals`）。
2. 把本目录内容推到仓库的 `main` 分支：
   ```bash
   git init
   git add -A
   git commit -m "init 好价精选"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
3. 仓库 **Settings → Pages → Build and deployment → Source 选 "GitHub Actions"**。
4. 回到 **Actions** 页面，手动跑一次 `抓取并部署优惠站`（或等定时/推送自动触发）。
5. 部署完成后，站点地址为 `https://<用户名>.github.io/<仓库名>/`。

> ⚠️ **微信打开提示**：`*.github.io` 在微信内置浏览器里**可能被拦截红屏**（未备案海外域名）。
> 阶段一只建议小范围发给朋友实测，看能否打开。要彻底解决见阶段二。

---

## 自定义

- **增删数据源**：编辑 `config.json` 的 `sources`。
  - SMZDM 官方源用 `http://`（https 会被 403，脚本已自动降级重试）。
  - RSSHub 频道格式：`https://rsshub.app/smzdm/ranking/<rank_type>/<rank_id>/<hour>`
    - `rank_type`：`dianshang`(电商榜) / `pinlei`(品类榜) / `haitao`(海淘)
    - 电商 `rank_id`：京东 `23`、天猫 `25`、亚马逊中国 `26`…
    - 品类 `rank_id`：全部 `11`、食品生鲜 `12`、电脑数码 `13`、家用电器 `15`…
    - `hour`：`3` / `12` / `24`
  - 不想用的源把 `"enabled": false` 即可。
- **抓取频率**：改 `.github/workflows/build.yml` 里的 cron（默认每 2 小时 `0 */2 * * *`，UTC）。
- **站点标题/文案**：改 `config.json` 的 `site.title` / `site.subtitle`。
- **控制总量**：`site.max_items`（默认 300）。

---

## 阶段二：迁国内服务器 + 已备案域名（推荐给朋友长期使用）

等域名/服务器就绪后，只需替换"托管"一环，数据流不变：

1. 把仓库产物（`index.html` / `assets/` / `data/`）同步到国内静态托管：
   - 腾讯云 COS + CDN，或阿里云 OSS + CDN，或轻量云 + Nginx。
2. 域名（你已备案）解析到该托管，开启 HTTPS。
3. 小圈子几十~几百人流量，CDN 每月几十 GB 足够，整体年费约 **50~150 元**，微信秒开无拦截。
4. 同步方式任选：Actions 构建后加一步 `coscli` / `ossutil` / `rsync` 推到国内；或本地跑脚本后手动传。

> 不推荐 Cloudflare Pages：无中国大陆节点，国内访问慢、微信易红屏拦截。

---

## 合规声明

- 本项目仅使用平台**主动公开**的 RSS 订阅源，不做爬虫、不逆向、不登录。
- 数据版权归各来源平台所有，页面已标注来源；价格与优惠以来源页面实时为准。
- 先期不挂任何联盟/返利链接，不涉及盈利与 CPS 资质。
- 不收集任何个人信息，不做用户登录。
- 仅限朋友小圈子分享，不公开大规模传播。

---

## 已知坑

| 坑 | 说明 | 应对 |
|---|---|---|
| 微信打开 `*.github.io` 红屏 | 未备案海外域名易被拦 | 阶段一实测；阶段二迁国内备案域名 |
| 公共 RSSHub 偶发不稳 | 单源失败不影响整体 | 脚本已容错；多源冗余；后期可自托管 |
| SMZDM https 被 403 | 官方源仅 http 可用 | 脚本自动 https→http 重试 |
| 优惠时效性 | 过期折扣 | 按发布时间倒序，前端显示"X小时前" |
| GitHub 定时任务休眠 | 仓库 60 天无活动会暂停定时 | 偶尔手动触发一次即可恢复 |
