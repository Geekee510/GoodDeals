/* 好价精选 · 前端逻辑
 * 读取同目录 data/deals.json（由 GitHub Actions 定时生成），渲染优惠卡片流，
 * 支持分类筛选 + 关键词搜索 + 深色模式。纯静态，无后端、无追踪。
 */
(function () {
  "use strict";

  var DATA_URL = "./data/deals.json";
  var state = { deals: [], cat: "全部", q: "" };

  // ---- 工具 ----
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function timeAgo(iso) {
    if (!iso) return "";
    var t = new Date(iso).getTime();
    if (isNaN(t)) return "";
    var diff = Date.now() - t;
    var m = 60000, h = 3600000, d = 86400000;
    if (diff < 0) return "";
    if (diff < m) return "刚刚";
    if (diff < h) return Math.floor(diff / m) + "分钟前";
    if (diff < d) return Math.floor(diff / h) + "小时前";
    if (diff < 30 * d) return Math.floor(diff / d) + "天前";
    var dt = new Date(t);
    var p = function (n) { return String(n).padStart(2, "0"); };
    return dt.getFullYear() + "-" + p(dt.getMonth() + 1) + "-" + p(dt.getDate());
  }

  // ---- 渲染 ----
  // 来源标签配色：同一来源颜色稳定（字符串 hash → 10 色调色板，见 style.css .src-c*）
  function srcColorClass(name) {
    var s = String(name || ""), h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return "src-c" + (h % 10);
  }

  function cardHTML(d) {
    var price = d.price != null
      ? '<span class="price">¥' + d.price + "</span>"
      : "";
    var img = d.image
      ? '<img class="thumb" src="' + esc(d.image) + '" loading="lazy" referrerpolicy="no-referrer" alt="" />'
      : '<div class="thumb thumb-ph">🏷️</div>';
    var cat = d.category || "优惠";
    return (
      '<a class="card" href="' + esc(d.link) + '" target="_blank" rel="noopener">' +
      img +
      '<div class="card-body">' +
      '<div class="card-title">' + esc(d.title) + "</div>" +
      '<div class="card-meta">' +
      price +
      '<span class="tag">' + esc(cat) + "</span>" +
      '<span class="src ' + srcColorClass(d.source) + '">' + esc(d.source) + "</span>" +
      '<span class="time">' + timeAgo(d.published) + "</span>" +
      "</div></div></a>"
    );
  }

  function restoreScroll() {
    try {
      var sp = parseInt(sessionStorage.getItem("gd_scroll") || "0", 10);
      if (sp > 0) { window.scrollTo(0, sp); sessionStorage.removeItem("gd_scroll"); }
    } catch (e) {}
  }

  function render() {
    var q = state.q.trim().toLowerCase();
    var list = state.deals.filter(function (d) {
      var okCat = state.cat === "全部" || (d.category || "优惠") === state.cat;
      var okQ = !q || (d.title || "").toLowerCase().indexOf(q) !== -1;
      return okCat && okQ;
    });

    var box = document.getElementById("list");
    box.innerHTML = list.map(cardHTML).join("");

    var empty = document.getElementById("empty");
    empty.hidden = list.length !== 0;
  }

  function buildCats() {
    var cats = {};
    state.deals.forEach(function (d) {
      var c = d.category || "优惠";
      cats[c] = (cats[c] || 0) + 1;
    });
    var names = ["全部"].concat(Object.keys(cats));
    // 把「其他」分类移到筛选栏最后（它不是真实品类，放末尾更整洁）
    var other = names.filter(function (n) { return n === "其他"; });
    var rest = names.filter(function (n) { return n !== "其他"; });
    names = rest.concat(other);
    var box = document.getElementById("catFilter");
    box.innerHTML = names
      .map(function (n) {
        var label = n === "全部" ? "全部" : n;
        return (
          '<button class="chip' +
          (n === state.cat ? " active" : "") +
          '" data-cat="' + esc(n) + '">' + esc(label) + "</button>"
        );
      })
      .join("");

    box.querySelectorAll(".chip").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.cat = btn.getAttribute("data-cat");
        box.querySelectorAll(".chip").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        render();
      });
    });
  }

  function setMeta(payload) {
    var site = payload.site || {};
    if (site.title) document.getElementById("siteTitle").textContent = site.title;
    if (site.subtitle) document.getElementById("siteSubtitle").textContent = site.subtitle;
    var up = document.getElementById("updated");
    var when = timeAgo(payload.updated_at);
    up.textContent =
      "更新于 " + (when || payload.updated_at || "") + " · 共 " + (payload.count || 0) + " 条";
  }

  // ---- 主题 ----
  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem("theme"); } catch (e) {}
    var dark = saved
      ? saved === "dark"
      : window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (dark) document.documentElement.setAttribute("data-theme", "dark");
    document.getElementById("themeToggle").addEventListener("click", function () {
      var isDark = document.documentElement.getAttribute("data-theme") === "dark";
      if (isDark) {
        document.documentElement.removeAttribute("data-theme");
        try { localStorage.setItem("theme", "light"); } catch (e) {}
      } else {
        document.documentElement.setAttribute("data-theme", "dark");
        try { localStorage.setItem("theme", "dark"); } catch (e) {}
      }
    });
  }

  // ---- 启动 ----
  function init() {
    initTheme();

    var search = document.getElementById("search");
    search.addEventListener("input", function () {
      state.q = search.value || "";
      render();
    });

    // 点击卡片跳转外链前，记录当前滚动位置；返回时由 restoreScroll() 恢复
    // （微信内置浏览器右滑返回后页面重载，浏览器原生 scrollRestoration 不可靠）
    document.getElementById("list").addEventListener("click", function (e) {
      var a = e.target && e.target.closest ? e.target.closest("a.card") : null;
      if (a) {
        try { sessionStorage.setItem("gd_scroll", String(window.scrollY)); } catch (err) {}
      }
    });

    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (payload) {
        state.deals = payload.deals || [];
        setMeta(payload);
        buildCats();
        render();
        restoreScroll();
      })
      .catch(function () {
        document.getElementById("loaderr").hidden = false;
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
