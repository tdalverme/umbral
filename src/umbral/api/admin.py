"""Internal admin routes."""

from __future__ import annotations

import json
from secrets import compare_digest

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from umbral.admin import AdminLearningDashboard
from umbral.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(request: Request) -> None:
    expected = get_settings().admin_api_key
    if not expected:
        return
    provided = request.headers.get("x-admin-key") or request.query_params.get("key")
    if not provided or not compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin key required",
        )


@router.get("/learning.json")
def learning_json(
    _: None = Depends(require_admin),
    window_days: int = Query(14, ge=1, le=90),
) -> dict:
    return AdminLearningDashboard().build(window_days=window_days)


@router.get("/learning", response_class=HTMLResponse)
def learning_page(
    request: Request,
    _: None = Depends(require_admin),
    window_days: int = Query(14, ge=1, le=90),
) -> HTMLResponse:
    key = request.query_params.get("key", "")
    return HTMLResponse(_render_learning_page(window_days=window_days, key=key))


def _render_learning_page(*, window_days: int, key: str) -> str:
    bootstrap = json.dumps({"windowDays": window_days, "adminKey": key})
    return _LEARNING_PAGE.replace("__BOOTSTRAP__", bootstrap)


_LEARNING_PAGE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Umbral Admin</title>
  <style>
    :root {
      --ink: #171717;
      --muted: #62615d;
      --line: #d8d4ca;
      --paper: #f7f4ec;
      --panel: #fffdf8;
      --good: #1d7c55;
      --bad: #b84a3a;
      --accent: #245c73;
      --accent-2: #8f3f54;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--paper);
      font-family: "Aptos", "Segoe UI", sans-serif;
    }
    header {
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    .wrap { width: min(1180px, calc(100vw - 32px)); margin: 0 auto; }
    .topbar {
      min-height: 84px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 { margin: 0; font-size: 24px; line-height: 1.1; letter-spacing: 0; }
    .sub { color: var(--muted); margin-top: 6px; font-size: 14px; }
    .controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    select, button {
      min-height: 36px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
    }
    button { background: var(--ink); color: #fff; cursor: pointer; }
    main { padding: 22px 0 42px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .metric, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .metric { padding: 14px; min-height: 108px; }
    .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
    .value { font-size: 30px; line-height: 1.15; margin-top: 10px; font-weight: 700; }
    .hint { color: var(--muted); font-size: 13px; margin-top: 6px; }
    .sections {
      display: grid;
      grid-template-columns: 1.1fr .9fr;
      gap: 14px;
      margin-top: 14px;
      align-items: start;
    }
    .panel { overflow: hidden; }
    .panel h2 {
      margin: 0;
      padding: 13px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 15px;
      background: #fbf8f0;
    }
    .panel-body { padding: 12px 14px 14px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; border-bottom: 1px solid #e7e2d8; padding: 9px 7px; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; font-size: 12px; }
    tr:last-child td { border-bottom: 0; }
    a { color: var(--accent); }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 0 7px;
      border-radius: 999px;
      font-size: 12px;
      border: 1px solid var(--line);
      background: #fff;
      white-space: nowrap;
    }
    .like { color: var(--good); border-color: #9ed0b9; }
    .dislike { color: var(--bad); border-color: #e1aea6; }
    .bar { height: 8px; border-radius: 999px; overflow: hidden; background: #e6e0d4; margin-top: 8px; }
    .fill { height: 100%; background: var(--accent); }
    .question {
      border-left: 3px solid var(--accent-2);
      padding: 10px 0 10px 10px;
      margin: 0 0 8px;
    }
    .question strong { display: block; font-size: 14px; }
    .question span { color: var(--muted); font-size: 13px; }
    .muted { color: var(--muted); }
    .error { color: var(--bad); padding: 16px; }
    @media (max-width: 920px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .sections { grid-template-columns: 1fr; }
      .topbar { align-items: flex-start; flex-direction: column; padding: 16px 0; }
    }
    @media (max-width: 560px) {
      .grid { grid-template-columns: 1fr; }
      table { font-size: 12px; }
      th, td { padding: 8px 5px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <div>
        <h1>Umbral Admin</h1>
        <div class="sub" id="subtitle">Radar de aprendizaje del MVP</div>
      </div>
      <div class="controls">
        <select id="window">
          <option value="7">7 dias</option>
          <option value="14">14 dias</option>
          <option value="30">30 dias</option>
          <option value="90">90 dias</option>
        </select>
        <button id="refresh">Actualizar</button>
      </div>
    </div>
  </header>
  <main class="wrap">
    <section class="grid" id="metrics"></section>
    <section class="sections">
      <div class="panel"><h2>Usuarios</h2><div class="panel-body" id="users"></div></div>
      <div class="panel"><h2>Preguntas de aprendizaje</h2><div class="panel-body" id="questions"></div></div>
    </section>
    <section class="sections">
      <div class="panel"><h2>Motivos de feedback</h2><div class="panel-body" id="reasons"></div></div>
      <div class="panel"><h2>Calidad de fuentes</h2><div class="panel-body" id="sources"></div></div>
    </section>
    <section class="sections">
      <div class="panel"><h2>Feedback reciente</h2><div class="panel-body" id="recent"></div></div>
      <div class="panel"><h2>Calidad de matches</h2><div class="panel-body" id="matches"></div></div>
    </section>
  </main>
  <script>
    const BOOTSTRAP = __BOOTSTRAP__;
    const $ = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[char]));
    const fmt = (value, suffix = "") => value === null || value === undefined ? "-" : `${value}${suffix}`;
    const compactDate = (value) => value ? new Date(value).toLocaleDateString("es-AR", { month: "short", day: "2-digit" }) : "-";
    const table = (headers, rows) => `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("") || `<tr><td colspan="${headers.length}" class="muted">Sin datos</td></tr>`}</tbody></table>`;

    $("window").value = String(BOOTSTRAP.windowDays);
    $("refresh").addEventListener("click", load);
    $("window").addEventListener("change", load);

    async function load() {
      const days = $("window").value;
      const headers = BOOTSTRAP.adminKey ? { "x-admin-key": BOOTSTRAP.adminKey } : {};
      const response = await fetch(`/admin/learning.json?window_days=${days}`, { headers });
      if (!response.ok) {
        document.querySelector("main").innerHTML = `<div class="panel error">No se pudo cargar el admin: ${response.status}</div>`;
        return;
      }
      render(await response.json());
    }

    function render(data) {
      const s = data.summary;
      $("subtitle").textContent = `Ventana: ${data.window_days} dias. Generado: ${new Date(data.generated_at).toLocaleString("es-AR")}`;
      $("metrics").innerHTML = [
        metric("Usuarios onboarded", s.users_onboarded, `${s.onboarding_rate_pct}% del total`),
        metric("Envios", s.notifications_sent_window, `${s.feedback_response_rate_pct}% respuesta`),
        metric("Likes", s.likes_window, `${s.notification_to_like_rate_pct}% envio -> like`),
        metric("Ingestion", s.ingestion_accepted_window, `${s.ingestion_acceptance_rate_pct}% aceptados`),
        metric("Listings activos", s.active_listings_total, `${s.analysis_coverage_pct}% raw analizado`),
        metric("Matches cacheados", s.matches_cached_window, `score medio ${s.avg_match_score_window}`),
        metric("Dislikes", s.dislikes_window, `${s.like_rate_pct}% feedback positivo`),
        metric("Errores pipeline", s.ingestion_errors_window, "en la ventana"),
      ].join("");
      renderUsers(data.users);
      renderQuestions(data.learning_questions);
      renderReasons(data.feedback_reasons);
      renderSources(data.source_quality);
      renderRecent(data.recent_feedback);
      renderMatches(data.match_quality);
    }

    function metric(label, value, hint) {
      return `<article class="metric"><div class="label">${label}</div><div class="value">${value}</div><div class="hint">${hint}</div></article>`;
    }

    function renderUsers(users) {
      $("users").innerHTML = table(["Usuario", "Estado", "Envios", "Resp.", "Busca"], users.slice(0, 12).map((user) => {
        const name = user.telegram_username ? `@${escapeHtml(user.telegram_username)}` : escapeHtml(user.telegram_id);
        const neighborhoods = (user.neighborhoods || []).slice(0, 3).join(", ");
        return `<tr>
          <td><strong>${name}</strong><div class="muted">${compactDate(user.created_at)}</div></td>
          <td><span class="pill">${user.onboarding_completed ? "onboarded" : `paso ${user.onboarding_step}`}</span></td>
          <td>${user.notifications_sent}</td>
          <td>${user.response_rate_pct}%</td>
          <td>${escapeHtml(neighborhoods || user.operation_type || "-")}<div class="muted">${fmt(user.max_price_usd, " USD")}</div></td>
        </tr>`;
      }));
    }

    function renderQuestions(items) {
      $("questions").innerHTML = items.map((item) => `<p class="question"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.why)}</span></p>`).join("");
    }

    function renderReasons(reasons) {
      $("reasons").innerHTML = table(["Motivo", "Total", "Likes", "Dislikes"], reasons.map((reason) => `<tr>
        <td>${escapeHtml(reason.label)}<div class="bar"><div class="fill" style="width:${Math.min(reason.count * 12, 100)}%"></div></div></td>
        <td>${reason.count}</td>
        <td>${reason.likes}</td>
        <td>${reason.dislikes}</td>
      </tr>`));
    }

    function renderSources(sources) {
      $("sources").innerHTML = table(["Fuente", "Total", "Acept.", "Errores"], sources.map((source) => `<tr>
        <td>${escapeHtml(source.source)}<div class="muted">${source.acceptance_rate_pct}% aceptacion</div></td>
        <td>${source.total}</td>
        <td>${source.accepted}</td>
        <td>${source.errors}</td>
      </tr>`));
    }

    function renderRecent(items) {
      $("recent").innerHTML = table(["Fecha", "Tipo", "Motivo", "Listing"], items.map((item) => `<tr>
        <td>${compactDate(item.created_at)}</td>
        <td><span class="pill ${item.feedback_type}">${item.feedback_type}</span></td>
        <td>${escapeHtml(item.reason_label)}</td>
        <td>${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(item.title || item.neighborhood || item.listing_id)}</a>` : escapeHtml(item.title || item.neighborhood || item.listing_id)}</td>
      </tr>`));
    }

    function renderMatches(matchQuality) {
      const bands = matchQuality.by_band.map((item) => `<tr><td>${escapeHtml(item.band)}</td><td>${item.count}</td></tr>`);
      const gaps = matchQuality.top_gaps.map((item) => `<tr><td>${escapeHtml(item.gap)}</td><td>${item.count}</td></tr>`);
      $("matches").innerHTML = `<div class="label">Bandas</div>${table(["Banda", "Cant."], bands)}<div class="label" style="margin-top:14px">Gaps</div>${table(["Gap", "Cant."], gaps)}`;
    }

    load();
  </script>
</body>
</html>"""
