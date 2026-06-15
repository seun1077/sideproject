from __future__ import annotations

import html
import json
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .db import apply_migrations, connect
from .paths import DB_PATH
from .public_api import categories, list_deals, list_products, price_history, service_summary
from .repository import upsert_default_sources


INDEX_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Beauty Deal Radar</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --surface: #ffffff;
      --line: #d9dee7;
      --text: #14171f;
      --muted: #697386;
      --teal: #0f766e;
      --teal-soft: #e6f5f2;
      --red: #b42318;
      --red-soft: #fff0ed;
      --yellow: #a16207;
      --yellow-soft: #fff8dd;
      --blue: #2563eb;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      padding: 18px 24px;
    }
    .header-inner {
      max-width: 1280px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: 1fr auto;
      align-items: center;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 22px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .meta {
      color: var(--muted);
      font-size: 12px;
      margin-top: 5px;
    }
    .metrics {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .metric {
      min-width: 88px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: #fbfcfd;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 11px;
    }
    .metric strong {
      display: block;
      margin-top: 2px;
      font-size: 16px;
    }
    main {
      max-width: 1280px;
      margin: 0 auto;
      padding: 18px 24px 48px;
    }
    .toolbar {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) auto auto;
      gap: 10px;
      align-items: center;
      margin-bottom: 14px;
    }
    input, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--surface);
      padding: 9px 10px;
      color: var(--text);
      font: inherit;
    }
    .segmented {
      display: inline-flex;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: var(--surface);
    }
    .segmented button {
      border: 0;
      border-right: 1px solid var(--line);
      background: transparent;
      padding: 9px 12px;
      color: var(--muted);
      font-weight: 650;
      cursor: pointer;
    }
    .segmented button:last-child { border-right: 0; }
    .segmented button.active {
      color: var(--teal);
      background: var(--teal-soft);
    }
    .content {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      gap: 14px;
      align-items: start;
    }
    .section-title {
      margin: 18px 0 10px;
      font-size: 15px;
      letter-spacing: 0;
    }
    .deal-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .deal-card, .side-panel, .product-row, .empty {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .deal-card {
      padding: 12px;
      display: grid;
      grid-template-columns: 44px minmax(0, 1fr);
      gap: 10px;
      cursor: pointer;
    }
    .deal-card.selected {
      border-color: var(--teal);
      box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.12);
    }
    .thumb {
      width: 44px;
      height: 44px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      color: #ffffff;
      font-weight: 800;
      background:
        linear-gradient(135deg, rgba(15, 118, 110, 0.96), rgba(37, 99, 235, 0.88));
    }
    .deal-title {
      font-weight: 750;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .deal-sub {
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .price-line {
      margin-top: 9px;
      display: flex;
      align-items: baseline;
      gap: 8px;
      flex-wrap: wrap;
    }
    .price {
      font-size: 20px;
      font-weight: 800;
    }
    .price-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }
    .compare-list {
      margin-top: 9px;
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
    }
    .compare-row {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      border-top: 1px solid #eef1f5;
      padding-top: 5px;
    }
    .compare-row strong {
      color: var(--text);
      white-space: nowrap;
    }
    .discount {
      color: var(--red);
      background: var(--red-soft);
      border: 1px solid #ffd1c9;
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 12px;
      font-weight: 750;
    }
    .actions {
      margin-top: 10px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    a.button {
      display: inline-block;
      color: var(--teal);
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 6px 9px;
      text-decoration: none;
      font-weight: 700;
      background: #ffffff;
    }
    .side-panel {
      padding: 14px;
      position: sticky;
      top: 14px;
    }
    .chart {
      margin-top: 12px;
      width: 100%;
      height: 160px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }
    .product-list {
      display: grid;
      gap: 8px;
    }
    .product-row {
      padding: 10px 12px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
      cursor: pointer;
    }
    .product-row strong {
      display: block;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .empty {
      padding: 28px 18px;
      text-align: center;
      color: var(--muted);
    }
    .empty strong {
      display: block;
      color: var(--text);
      font-size: 16px;
      margin-bottom: 4px;
    }
    @media (max-width: 960px) {
      .header-inner, .toolbar, .content { grid-template-columns: 1fr; }
      .metrics { justify-content: flex-start; }
      .deal-grid { grid-template-columns: 1fr; }
      .side-panel { position: static; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div>
        <h1>Beauty Deal Radar</h1>
        <div class="meta" id="runMeta">데이터 상태 확인 중</div>
      </div>
      <div class="metrics">
        <div class="metric"><span>상품</span><strong id="metricProducts">0</strong></div>
        <div class="metric"><span>오퍼</span><strong id="metricOffers">0</strong></div>
        <div class="metric"><span>스냅샷</span><strong id="metricSnapshots">0</strong></div>
        <div class="metric"><span>딜 후보</span><strong id="metricDeals">0</strong></div>
      </div>
    </div>
  </header>
  <main>
    <div class="toolbar">
      <input id="searchInput" type="search" placeholder="브랜드 또는 상품명">
      <select id="categorySelect"><option value="">전체 카테고리</option></select>
      <div class="segmented" aria-label="할인율 필터">
        <button class="active" data-min-discount="0" type="button">전체</button>
        <button data-min-discount="20" type="button">20% 이상</button>
        <button data-min-discount="40" type="button">40% 이상</button>
      </div>
    </div>
    <div class="content">
      <section>
        <h2 class="section-title">오늘의 가격 신호</h2>
        <div id="dealGrid" class="deal-grid"></div>
        <h2 class="section-title">추적 상품</h2>
        <div id="productList" class="product-list"></div>
      </section>
      <aside class="side-panel">
        <h2 class="section-title" style="margin-top:0">가격 히스토리</h2>
        <div id="selectedMeta" class="meta">상품을 선택하면 일별 가격 흐름이 표시됩니다.</div>
        <div id="chart" class="chart"></div>
        <div id="historyStats" class="meta"></div>
      </aside>
    </div>
  </main>
  <script>
    const state = {
      deals: [],
      products: [],
      categories: [],
      selectedProductId: null,
      minDiscount: 0,
      query: "",
      category: "",
    };

    const won = (value) => value == null ? "-" : `${Number(value).toLocaleString("ko-KR")}원`;
    const pct = (value) => value == null ? "-" : `${Number(value).toFixed(1)}%`;
    const initial = (brand) => (brand || "?").trim().slice(0, 1);
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[char]));

    async function getJson(url) {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    }

    async function load() {
      const [summary, deals, products, categories] = await Promise.all([
        getJson("/api/summary"),
        getJson("/api/deals?visibility=all&limit=60"),
        getJson("/api/products?limit=200"),
        getJson("/api/categories"),
      ]);
      state.deals = deals.items || [];
      state.products = products.items || [];
      state.categories = categories.items || [];
      renderSummary(summary);
      renderCategories();
      renderDeals();
      renderProducts();
      const first = state.deals[0]?.product_id || state.products[0]?.id;
      if (first) selectProduct(first);
    }

    function renderSummary(summary) {
      document.getElementById("metricProducts").textContent = summary.products ?? 0;
      document.getElementById("metricOffers").textContent = summary.offers ?? 0;
      document.getElementById("metricSnapshots").textContent = summary.price_snapshots ?? 0;
      document.getElementById("metricDeals").textContent = summary.deal_candidates ?? 0;
      const latest = summary.latest_success?.finished_at || summary.latest_run?.finished_at;
      document.getElementById("runMeta").textContent = latest
        ? `최근 수집 ${latest}`
        : "아직 성공한 수집 실행이 없습니다.";
    }

    function renderCategories() {
      const select = document.getElementById("categorySelect");
      select.innerHTML = '<option value="">전체 카테고리</option>' +
        state.categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join("");
    }

    function filteredDeals() {
      const query = state.query.toLowerCase();
      return state.deals.filter((deal) => {
        if ((deal.discount_pct || 0) < state.minDiscount) return false;
        if (state.category && deal.category !== state.category) return false;
        if (query && !`${deal.brand} ${deal.product} ${deal.title}`.toLowerCase().includes(query)) return false;
        return true;
      });
    }

    function optionLabel(option) {
      const count = option.pack_count && option.pack_count > 1 ? `${option.pack_count}개 묶음` : "단품/옵션";
      return `${count} ${won(option.package_price_krw)} · 개당 ${won(option.unit_price_krw)}`;
    }

    function renderOptions(deal) {
      const options = deal.other_options || [];
      if (!options.length) return "";
      const cheaper = deal.cheaper_options || [];
      const heading = cheaper.length
        ? "더 싼 묶음 옵션이 수집됨"
        : "비교된 다른 옵션";
      const rows = options.slice(0, 2).map((option) => `
        <div class="compare-row">
          <span>${escapeHtml(optionLabel(option))}</span>
          ${option.url ? `<a href="${escapeHtml(option.url)}" target="_blank" rel="noreferrer">확인</a>` : ""}
        </div>
      `).join("");
      return `<div class="compare-list"><div><strong>${heading}</strong></div>${rows}</div>`;
    }

    function renderDeals() {
      const grid = document.getElementById("dealGrid");
      const deals = filteredDeals();
      if (!deals.length) {
        grid.innerHTML = `<div class="empty" style="grid-column: 1 / -1"><strong>표시할 딜 후보가 없습니다.</strong><span>관리자 페이지에서 수집을 실행하면 이 영역에 실제 후보가 채워집니다.</span></div>`;
        return;
      }
      grid.innerHTML = deals.map((deal) => `
        <article class="deal-card ${state.selectedProductId === deal.product_id ? "selected" : ""}" data-product-id="${deal.product_id}">
          <div class="thumb">${escapeHtml(initial(deal.brand))}</div>
          <div>
            <div class="deal-title">${escapeHtml(deal.brand)} ${escapeHtml(deal.product)}</div>
            <div class="deal-sub">${escapeHtml(deal.title || "")}</div>
            <div class="price-line">
              <span class="price-label">후보가</span>
              <span class="price">${won(deal.current_price_krw)}</span>
              <span class="discount">${won(deal.price_gap_krw)} 저렴 · ${pct(deal.discount_pct)}</span>
            </div>
            <div class="meta">현재 수집 시중가 ${won(deal.reference_price_krw)} · ${deal.discount_basis === "30d" ? "30일 중앙가 기준" : "오늘 수집 중앙가 기준"} · ${escapeHtml(deal.source || "-")}</div>
            ${renderOptions(deal)}
            <div class="actions">
              ${deal.url ? `<a class="button" href="${escapeHtml(deal.url)}" target="_blank" rel="noreferrer">판매처</a>` : ""}
            </div>
          </div>
        </article>
      `).join("");
      grid.querySelectorAll(".deal-card").forEach((card) => {
        card.addEventListener("click", (event) => {
          if (event.target.closest("a")) return;
          selectProduct(Number(card.dataset.productId));
        });
      });
    }

    function filteredProducts() {
      const query = state.query.toLowerCase();
      return state.products.filter((product) => {
        if (state.category && product.category !== state.category) return false;
        if (query && !`${product.brand} ${product.product}`.toLowerCase().includes(query)) return false;
        return true;
      });
    }

    function renderProducts() {
      const list = document.getElementById("productList");
      const products = filteredProducts();
      if (!products.length) {
        list.innerHTML = `<div class="empty"><strong>추적 상품이 없습니다.</strong><span>seed 상품이 DB에 들어오면 이 목록이 채워집니다.</span></div>`;
        return;
      }
      list.innerHTML = products.map((product) => `
        <div class="product-row" data-product-id="${product.id}">
          <div>
            <strong>${escapeHtml(product.brand)} ${escapeHtml(product.product)}</strong>
            <div class="meta">${escapeHtml(product.category)} · ${escapeHtml(product.volume || "-")} · ${product.snapshot_count} snapshots</div>
          </div>
          <div>
            <div style="font-weight:800;text-align:right">${won(product.current_price_krw)}</div>
            <div class="meta" style="text-align:right">시중 ${won(product.market_median_price_krw)}</div>
          </div>
        </div>
      `).join("");
      list.querySelectorAll(".product-row").forEach((row) => {
        row.addEventListener("click", () => selectProduct(Number(row.dataset.productId)));
      });
    }

    async function selectProduct(productId) {
      state.selectedProductId = productId;
      renderDeals();
      const product = state.products.find((item) => item.id === productId);
      document.getElementById("selectedMeta").textContent = product
        ? `${product.brand} ${product.product}`
        : "선택한 상품";
      const history = await getJson(`/api/products/${productId}/price-history?days=90`);
      renderChart(history.items || []);
    }

    function renderChart(rows) {
      const target = document.getElementById("chart");
      const stats = document.getElementById("historyStats");
      if (!rows.length) {
        target.innerHTML = `<div class="empty" style="height:100%;border:0">아직 일별 가격 통계가 없습니다.</div>`;
        stats.textContent = "";
        return;
      }
      const values = rows.map((row) => row.median_price_krw).filter((value) => value != null);
      const min = Math.min(...values);
      const max = Math.max(...values);
      const width = 320;
      const height = 150;
      const pad = 18;
      const span = Math.max(1, max - min);
      const points = rows.map((row, index) => {
        const x = pad + (index / Math.max(1, rows.length - 1)) * (width - pad * 2);
        const y = height - pad - ((row.median_price_krw - min) / span) * (height - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(" ");
      target.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" width="100%" height="100%" role="img" aria-label="가격 차트">
          <line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" stroke="#d9dee7"/>
          <polyline points="${points}" fill="none" stroke="#0f766e" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
          <circle cx="${points.split(" ").at(-1).split(",")[0]}" cy="${points.split(" ").at(-1).split(",")[1]}" r="4" fill="#b42318"/>
        </svg>`;
      stats.textContent = `${rows[0].date} ~ ${rows.at(-1).date} · 중앙가 범위 ${won(min)} ~ ${won(max)}`;
    }

    document.getElementById("searchInput").addEventListener("input", (event) => {
      state.query = event.target.value;
      renderDeals();
      renderProducts();
    });
    document.getElementById("categorySelect").addEventListener("change", (event) => {
      state.category = event.target.value;
      renderDeals();
      renderProducts();
    });
    document.querySelectorAll("[data-min-discount]").forEach((button) => {
      button.addEventListener("click", () => {
        state.minDiscount = Number(button.dataset.minDiscount || 0);
        document.querySelectorAll("[data-min-discount]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        renderDeals();
      });
    });

    load().catch((error) => {
      document.getElementById("dealGrid").innerHTML = `<div class="empty" style="grid-column:1/-1"><strong>데이터를 불러오지 못했습니다.</strong><span>${escapeHtml(error.message)}</span></div>`;
    });
  </script>
</body>
</html>
"""


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _query_value(query: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    values = query.get(key)
    return values[0] if values else default


def _int_query(query: dict[str, list[str]], key: str, default: int) -> int:
    value = _query_value(query, key)
    if value is None:
        return default
    try:
        return max(1, min(int(value), 500))
    except ValueError:
        return default


def _float_query(query: dict[str, list[str]], key: str) -> float | None:
    value = _query_value(query, key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


class PublicHandler(BaseHTTPRequestHandler):
    db_path = DB_PATH

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/":
                self._send_html(INDEX_HTML.encode("utf-8"))
            elif path == "/api/summary":
                with self._conn() as conn:
                    self._send_json(service_summary(conn))
            elif path == "/api/categories":
                with self._conn() as conn:
                    self._send_json({"items": categories(conn)})
            elif path == "/api/deals":
                with self._conn() as conn:
                    self._send_json(
                        {
                            "items": list_deals(
                                conn,
                                limit=_int_query(query, "limit", 30),
                                category=_query_value(query, "category"),
                                min_discount=_float_query(query, "min_discount"),
                                visibility=_query_value(query, "visibility", "all") or "all",
                            )
                        }
                    )
            elif path == "/api/products":
                with self._conn() as conn:
                    self._send_json({"items": list_products(conn, limit=_int_query(query, "limit", 100))})
            else:
                match = re.fullmatch(r"/api/products/(\d+)/price-history", path)
                if not match:
                    self.send_error(404)
                    return
                with self._conn() as conn:
                    self._send_json(
                        {
                            "items": price_history(
                                conn,
                                int(match.group(1)),
                                days=_int_query(query, "days", 90),
                            )
                        }
                    )
        except Exception as exc:
            self._send_json({"error": html.escape(str(exc))}, status=500)

    def _conn(self):
        conn = connect(self.db_path)
        apply_migrations(conn)
        upsert_default_sources(conn)
        return conn

    def _send_html(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def run_public_server(host: str = "127.0.0.1", port: int = 8766, db_path: Path = DB_PATH) -> None:
    handler = type("ConfiguredPublicHandler", (PublicHandler,), {"db_path": db_path})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Public MVP running at http://{host}:{port}")
    server.serve_forever()
