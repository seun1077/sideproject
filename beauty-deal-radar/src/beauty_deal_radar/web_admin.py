from __future__ import annotations

import html
import json
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .admin import (
    auto_publish_safe_deals,
    dashboard_metrics,
    deal_review_flags,
    decide_deal,
    decide_offer,
    is_safe_auto_publish_candidate,
    latest_deal_cards,
    review_queue,
)
from .db import apply_migrations, connect
from .paths import DB_PATH
from .pipeline import run_collection
from .repository import upsert_default_sources


APP_STATE = {"collecting": False, "last_message": ""}
DAILY_DEAL_REVIEW_LIMIT = 10
DAILY_MATCH_REVIEW_LIMIT = 10

PUBLICATION_LABELS = {
    "auto_approved": "자동 후보",
    "needs_review": "확인 필요",
    "approved": "공개 승인됨",
    "rejected": "노출 제외됨",
    "draft": "보류",
    "expired": "만료",
}

MATCH_LABELS = {
    "candidate": "같은 상품 후보",
    "approved": "같은 상품 확인",
    "rejected": "다른 상품",
    "excluded": "기준가 제외",
}

CONFIDENCE_LABELS = {
    "high": "근거 많음",
    "medium": "근거 보통",
    "low": "근거 적음",
}

DEAL_DECISION_LABELS = {
    "approve_deal": "공개 승인",
    "reject_deal": "노출 제외",
    "exclude_best_offer": "가격 불일치 제외",
    "hold": "보류",
}

OFFER_DECISION_LABELS = {
    "approve_match": "같은 상품 확인",
    "reject_match": "다른 상품 처리",
    "exclude": "기준가 제외",
}


def money(value: int | None) -> str:
    return "-" if value is None else f"{int(value):,}원"


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}%"


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def publication_label(status: str | None) -> str:
    return PUBLICATION_LABELS.get(status or "", status or "-")


def match_label(status: str | None) -> str:
    return MATCH_LABELS.get(status or "", status or "-")


def confidence_label(value: str | None) -> str:
    return CONFIDENCE_LABELS.get(value or "", value or "-")


def deal_evidence(row) -> tuple[str, str]:
    if row["discount_vs_30d_pct"] is not None:
        return (
            f"30일 중앙가 대비 {pct(row['discount_vs_30d_pct'])} 저렴",
            f"30일 중앙 {money(row['historical_median_30d_krw'])} · 시장 중앙 {money(row['market_median_price_krw'])}",
        )
    if row["discount_vs_market_pct"] is not None:
        return (
            f"오늘 수집가 중앙값 대비 {pct(row['discount_vs_market_pct'])} 저렴",
            f"시장 중앙 {money(row['market_median_price_krw'])} · 30일 데이터 누적 전 임시 기준",
        )
    return ("판정 근거 부족", "가격 표본이 더 필요합니다.")


def search_links(query: str) -> str:
    encoded = urllib.parse.quote(query)
    links = [
        ("네이버", f"https://search.shopping.naver.com/search/all?query={encoded}"),
        ("쿠팡", f"https://www.coupang.com/np/search?q={encoded}"),
        ("올리브영", f"https://www.oliveyoung.co.kr/store/search/getSearchMain.do?query={encoded}"),
        ("무신사", f"https://www.musinsa.com/search/goods?keyword={encoded}"),
    ]
    return " ".join(
        f'<a class="link" href="{url}" target="_blank" rel="noreferrer">{label}</a>'
        for label, url in links
    )


def layout(content: str, message: str = "") -> bytes:
    body = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Beauty Deal Radar Admin</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #111827;
      --muted: #657080;
      --accent: #0f766e;
      --danger: #b42318;
      --warn: #a16207;
      --ok: #166534;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      padding: 14px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    h1 {{ font-size: 18px; margin: 0; }}
    h2 {{ font-size: 16px; margin: 0 0 12px; }}
    main {{ max-width: 1440px; margin: 0 auto; padding: 18px 22px 48px; }}
    .grid {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }}
    .metric, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .metric {{ padding: 12px; }}
    .metric .label {{ color: var(--muted); font-size: 12px; }}
    .metric .value {{ font-weight: 700; font-size: 20px; margin-top: 4px; }}
    .panel {{ padding: 14px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-top: 1px solid var(--line); padding: 9px 8px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; font-weight: 600; }}
    tr:first-child th {{ border-top: 0; }}
    .title {{ font-weight: 650; }}
    .sub {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .explain {{ color: var(--text); font-size: 13px; font-weight: 650; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 2px 7px; font-size: 12px; border: 1px solid var(--line); }}
    .auto_approved, .approved {{ color: var(--ok); border-color: #86efac; background: #f0fdf4; }}
    .needs_review, .candidate {{ color: var(--warn); border-color: #fde68a; background: #fffbeb; }}
    .rejected, .excluded {{ color: var(--danger); border-color: #fecaca; background: #fef2f2; }}
    .draft {{ color: var(--muted); background: #f8fafc; }}
    .safe {{ color: var(--ok); }}
    .risk {{ color: var(--danger); }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    button, .button {{
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #ffffff;
      color: var(--text);
      padding: 7px 10px;
      font-weight: 650;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
    }}
    button.primary {{ background: var(--accent); border-color: var(--accent); color: #ffffff; }}
    button.danger {{ color: var(--danger); }}
    .link {{ color: #0f766e; text-decoration: none; margin-right: 8px; white-space: nowrap; }}
    .message {{ margin: 0 0 14px; border: 1px solid var(--line); background: #fff; border-radius: 8px; padding: 10px 12px; }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      table, tbody, tr, td {{ display: block; width: 100%; }}
      thead {{ display: none; }}
      tr {{ border-top: 1px solid var(--line); padding: 8px 0; }}
      td {{ border-top: 0; padding: 5px 0; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Beauty Deal Radar Admin</h1>
    <div class="actions">
      <form method="post" action="/auto-publish-safe">
        <button type="submit" title="가격 표본, 매칭 점수, 할인율이 안전 범위인 자동 후보만 공개합니다.">안전 후보 일괄 공개</button>
      </form>
      <form method="post" action="/collect">
        <button class="primary" type="submit">오늘 데이터 수집</button>
      </form>
    </div>
  </header>
  <main>
    {f'<div class="message">{esc(message)}</div>' if message else ''}
    {content}
  </main>
</body>
</html>"""
    return body.encode("utf-8")


def render_dashboard(db_path: Path, message: str = "") -> bytes:
    with connect(db_path) as conn:
        apply_migrations(conn)
        upsert_default_sources(conn)
        metrics = dashboard_metrics(conn)
        deal_backlog = [
            row
            for row in latest_deal_cards(conn, limit=200)
            if row["publication_status"] in {"auto_approved", "needs_review"}
        ]
        deals = deal_backlog[:DAILY_DEAL_REVIEW_LIMIT]
        queue = review_queue(conn, limit=DAILY_MATCH_REVIEW_LIMIT)

    latest_run = metrics["latest_run"] or {}
    safe_auto_count = sum(1 for row in deal_backlog if is_safe_auto_publish_candidate(row))
    metric_html = f"""
    <section class="grid">
      <div class="metric"><div class="label">상품</div><div class="value">{metrics['products']}</div></div>
      <div class="metric"><div class="label">오퍼</div><div class="value">{metrics['offers']}</div></div>
      <div class="metric"><div class="label">가격 스냅샷</div><div class="value">{metrics['price_snapshots']}</div></div>
      <div class="metric"><div class="label">오늘 가격 검증</div><div class="value">{len(deals)}/{metrics['deal_review_queue']}</div></div>
      <div class="metric"><div class="label">오늘 상품 매칭</div><div class="value">{len(queue)}/{metrics['review_queue']}</div></div>
      <div class="metric"><div class="label">안전 후보</div><div class="value">{safe_auto_count}</div></div>
    </section>
    <section class="panel">
      <h2>최근 실행</h2>
      <div class="sub">상태: {esc(latest_run.get('status', '-'))} · 시작: {esc(latest_run.get('started_at', '-'))} · 종료: {esc(latest_run.get('finished_at', '-'))} · 오퍼: {esc(latest_run.get('offer_count', '-'))}</div>
    </section>
    """

    deal_rows = []
    for row in deals:
        query = f"{row['brand']} {row['product']}"
        evidence, evidence_detail = deal_evidence(row)
        flags = deal_review_flags(row)
        if is_safe_auto_publish_candidate(row):
            review_hint = '<span class="safe">자동 공개 가능</span>'
        elif flags:
            review_hint = '<span class="risk">검수 필요: ' + esc(", ".join(flags[:3])) + "</span>"
        else:
            review_hint = "검수 완료 또는 보류"
        deal_rows.append(
            f"""
            <tr>
              <td>
                <div class="title">{esc(row['brand'])} {esc(row['product'])}</div>
                <div class="sub">{esc(row['best_title'])}</div>
                <div class="sub">{search_links(query)}</div>
              </td>
              <td>{money(row['current_min_price_krw'])}</td>
              <td><div class="explain">{esc(evidence)}</div><div class="sub">{esc(evidence_detail)}</div><div class="sub">{review_hint}</div></td>
              <td><strong>{row['deal_score']}</strong><div class="sub">{esc(confidence_label(row['confidence']))}</div></td>
              <td><span class="badge {esc(row['publication_status'])}">{esc(publication_label(row['publication_status']))}</span></td>
              <td>
                <div class="actions">
                  <a class="button" href="{esc(row['best_url'])}" target="_blank" rel="noreferrer">판매처 확인</a>
                  <form method="post" action="/deal-decision"><input type="hidden" name="id" value="{row['evaluation_id']}"><input type="hidden" name="decision" value="approve_deal"><button type="submit" title="사용자용 화면에 공개할 만한 특가로 승인합니다.">공개 승인</button></form>
                  <form method="post" action="/deal-decision"><input type="hidden" name="id" value="{row['evaluation_id']}"><input type="hidden" name="decision" value="exclude_best_offer"><button class="danger" type="submit" title="판매처에 들어갔을 때 실제 가격이 다르면 이 오퍼를 가격 기준에서 제외합니다.">가격 불일치 제외</button></form>
                  <form method="post" action="/deal-decision"><input type="hidden" name="id" value="{row['evaluation_id']}"><input type="hidden" name="decision" value="reject_deal"><button class="danger" type="submit" title="가격 근거가 약하거나 상품이 애매해서 사용자용 화면에서 제외합니다.">노출 제외</button></form>
                </div>
              </td>
            </tr>
            """
        )
    deal_html = f"""
    <section class="panel">
      <h2>오늘 가격 검증 10개</h2>
      <div class="sub">전체 후보를 다 보지 않고, 오늘은 상위 {DAILY_DEAL_REVIEW_LIMIT}개만 봅니다. 안전 후보는 상단 버튼으로 일괄 공개하고, 이상 징후가 있는 후보만 직접 확인하세요.</div>
      <table>
        <thead><tr><th>상품</th><th>현재가</th><th>왜 후보인가</th><th>점수/근거</th><th>공개 상태</th><th>검수</th></tr></thead>
        <tbody>{''.join(deal_rows) or '<tr><td colspan="6">아직 평가 데이터가 없습니다.</td></tr>'}</tbody>
      </table>
    </section>
    """

    queue_rows = []
    for row in queue:
        query = f"{row['brand'] or ''} {row['product'] or row['title']}"
        queue_rows.append(
            f"""
            <tr>
              <td>
                <div class="title">{esc(row['title'])}</div>
                <div class="sub">{esc(row['brand'])} {esc(row['product'])}</div>
                <div class="sub">{search_links(query)}</div>
              </td>
              <td>{money(row['normalized_price_krw'] or row['package_price_krw'])}<div class="sub">묶음 {esc(row['pack_count'])} · {esc(row['volume_value'])}{esc(row['volume_unit'])}</div></td>
              <td><span class="badge {esc(row['match_status'])}">{esc(match_label(row['match_status']))}</span><div class="sub">매칭 점수 {esc(row['match_score'])} {esc(row['exclusion_reason'] or '')}</div></td>
              <td>
                <div class="actions">
                  <a class="button" href="{esc(row['url'])}" target="_blank" rel="noreferrer">판매처 확인</a>
                  <form method="post" action="/offer-decision"><input type="hidden" name="id" value="{row['id']}"><input type="hidden" name="decision" value="approve_match"><button type="submit" title="이 판매처 상품이 왼쪽의 기준 상품과 같은 상품이면 선택합니다.">같은 상품 맞음</button></form>
                  <form method="post" action="/offer-decision"><input type="hidden" name="id" value="{row['id']}"><input type="hidden" name="decision" value="reject_match"><button type="submit" title="브랜드, 제품명, 용량, 옵션이 달라 같은 상품으로 보면 안 될 때 선택합니다.">다른 상품임</button></form>
                  <form method="post" action="/offer-decision"><input type="hidden" name="id" value="{row['id']}"><input type="hidden" name="decision" value="exclude"><button class="danger" type="submit" title="세트, 리필, 해외배송 등 가격 기준에 쓰면 안 되는 후보를 제외합니다.">가격기준 제외</button></form>
                </div>
              </td>
            </tr>
            """
        )
    queue_html = f"""
    <section class="panel">
      <h2>오늘 상품 매칭 검수 10개</h2>
      <div class="sub">자동 제외/반려된 후보는 오늘 업무에서 제외하고, 가격 기준에 들어갈 가능성이 있는 같은 상품 후보만 {DAILY_MATCH_REVIEW_LIMIT}개 보여줍니다.</div>
      <table>
        <thead><tr><th>수집된 판매처 상품</th><th>보정가</th><th>매칭 상태</th><th>검수</th></tr></thead>
        <tbody>{''.join(queue_rows) or '<tr><td colspan="4">검수할 후보가 없습니다.</td></tr>'}</tbody>
      </table>
    </section>
    """
    return layout(metric_html + deal_html + queue_html, message=message or APP_STATE.get("last_message", ""))


class AdminHandler(BaseHTTPRequestHandler):
    db_path = DB_PATH

    def do_GET(self) -> None:
        if urllib.parse.urlparse(self.path).path != "/":
            self.send_error(404)
            return
        self._send_html(render_dashboard(self.db_path))

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = urllib.parse.parse_qs(body)
        try:
            if parsed.path == "/collect":
                self._handle_collect()
            elif parsed.path == "/auto-publish-safe":
                self._handle_auto_publish_safe()
            elif parsed.path == "/offer-decision":
                self._handle_offer_decision(form)
            elif parsed.path == "/deal-decision":
                self._handle_deal_decision(form)
            else:
                self.send_error(404)
                return
        except Exception as exc:
            APP_STATE["last_message"] = f"오류: {exc}\n{traceback.format_exc(limit=3)}"
        self._redirect("/")

    def _handle_collect(self) -> None:
        if APP_STATE["collecting"]:
            APP_STATE["last_message"] = "이미 수집이 실행 중입니다."
            return
        APP_STATE["collecting"] = True
        try:
            summary = run_collection(db_path=self.db_path, write_csv_outputs=False, keep_raw=False)
            APP_STATE["last_message"] = "수집 완료: " + json.dumps(summary, ensure_ascii=False)
        finally:
            APP_STATE["collecting"] = False

    def _handle_auto_publish_safe(self) -> None:
        with connect(self.db_path) as conn:
            apply_migrations(conn)
            result = auto_publish_safe_deals(conn)
        APP_STATE["last_message"] = "안전 후보 일괄 공개 완료: " + json.dumps(result, ensure_ascii=False)

    def _handle_offer_decision(self, form: dict[str, list[str]]) -> None:
        offer_id = int(form.get("id", ["0"])[0])
        decision = form.get("decision", [""])[0]
        with connect(self.db_path) as conn:
            apply_migrations(conn)
            decide_offer(conn, offer_id, decision)
        APP_STATE["last_message"] = f"오퍼 #{offer_id} 처리 완료: {OFFER_DECISION_LABELS.get(decision, decision)}"

    def _handle_deal_decision(self, form: dict[str, list[str]]) -> None:
        evaluation_id = int(form.get("id", ["0"])[0])
        decision = form.get("decision", [""])[0]
        with connect(self.db_path) as conn:
            apply_migrations(conn)
            if decision == "exclude_best_offer":
                row = conn.execute(
                    "SELECT best_offer_id FROM deal_evaluations WHERE id = ?",
                    (evaluation_id,),
                ).fetchone()
                if row and row["best_offer_id"]:
                    decide_offer(conn, int(row["best_offer_id"]), "exclude", reason="landing_price_mismatch")
                decide_deal(conn, evaluation_id, "reject_deal", reason="landing_price_mismatch")
            elif decision == "approve_deal":
                row = conn.execute(
                    "SELECT best_offer_id FROM deal_evaluations WHERE id = ?",
                    (evaluation_id,),
                ).fetchone()
                if row and row["best_offer_id"]:
                    decide_offer(conn, int(row["best_offer_id"]), "approve_match", reason="deal_publication_approved")
                decide_deal(conn, evaluation_id, decision)
            else:
                decide_deal(conn, evaluation_id, decision)
        APP_STATE["last_message"] = f"딜 #{evaluation_id} 처리 완료: {DEAL_DECISION_LABELS.get(decision, decision)}"

    def _send_html(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        return


def run_admin_server(host: str = "127.0.0.1", port: int = 8765, db_path: Path = DB_PATH) -> None:
    handler = type("ConfiguredAdminHandler", (AdminHandler,), {"db_path": db_path})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Admin server running at http://{host}:{port}")
    server.serve_forever()


def run_admin_server_in_thread(host: str = "127.0.0.1", port: int = 8765, db_path: Path = DB_PATH) -> threading.Thread:
    thread = threading.Thread(target=run_admin_server, args=(host, port, db_path), daemon=True)
    thread.start()
    return thread
