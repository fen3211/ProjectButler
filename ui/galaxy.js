'use strict';
/* Project Butler — галактика проектов. Canvas 2D + ручная 3D-проекция: без Three.js и CDN. */

const STACK_COLORS = {
  python: '#4fc3f7', node: '#a3e635', csharp: '#c084fc', go: '#22d3ee',
  docker: '#60a5fa', js: '#fcd34d', git: '#fb923c', unknown: '#94a3b8'
};
const STATUS_COLORS = { alive: '#4ade80', abandoned: '#fbbf24', broken: '#f87171', unknown: '#6b7a99' };
const STATUS_LABELS = { alive: 'живой', abandoned: 'заброшен', broken: 'сломан', unknown: 'пусто' };
const SPREAD = 150;         // мировые единицы на единицу раскладки фида
const CAM_DIST = 1500;      // «камера» по z
const FOV = 1250;
const HIT_RADIUS = 16;
const TOP_LABELS = 8;

const state = {
  feed: null, stars: [], hidden: new Set(), byName: {},
  yaw: 0.6, pitch: -0.34, zoom: 1,
  hover: null, selected: null, width: 0, height: 0,
};

const canvas = document.getElementById('sky');
const ctx = canvas.getContext('2d');
const ui = {
  root: document.getElementById('root'),
  stats: document.getElementById('stats'),
  chips: document.getElementById('chips'),
  legend: document.getElementById('legend'),
  panel: document.getElementById('panel'),
  tip: document.getElementById('tip'),
  status: document.getElementById('status'),
  error: document.getElementById('error'),
  rootSelect: document.getElementById('rootSelect'),
  rootInput: document.getElementById('rootInput'),
  rootApply: document.getElementById('rootApply'),
};

function say(text) { ui.status.textContent = text; }

function fail(text) {
  ui.error.style.display = 'block';
  ui.error.innerHTML = '';
  const p = document.createElement('div');
  p.textContent = text;
  const btn = document.createElement('button');
  btn.textContent = 'повторить';
  btn.style.marginTop = '12px';
  btn.onclick = () => { ui.error.style.display = 'none'; init(false); };
  ui.error.append(p, btn);
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) throw new Error((data && data.error) || ('HTTP ' + res.status));
  return data;
}

async function init(rescan) {
  say(rescan ? 'сканирую папку… (это может занять пару минут)' : 'читаю фид…');
  try {
    if (rescan) await api('/api/scan', {});
    state.feed = await api('/galaxy.json');
  } catch (err) {
    fail('Не удалось получить данные: ' + err.message + '. Сервер поднят командой `python -m butler ui`.');
    return;
  }
  buildStars();
  renderHud();
  loadRoots();
  say('готово: ' + state.feed.projects.length + ' проектов, фид от ' + state.feed.generated_at_iso);
}

/* ---------- выбор папки сканирования ---------- */

async function loadRoots() {
  try {
    const data = await api('/api/roots');
    ui.rootSelect.innerHTML = '';
    const all = data.current && !data.roots.includes(data.current)
      ? [data.current, ...data.roots] : data.roots;
    all.forEach((root) => {
      const opt = document.createElement('option');
      opt.value = root;
      opt.textContent = root;
      if (root === data.current) opt.selected = true;
      ui.rootSelect.append(opt);
    });
    if (document.activeElement !== ui.rootInput) {
      ui.rootInput.value = data.current || '';
    }
  } catch (err) {
    say('не удалось получить список папок: ' + err.message);
  }
}

async function applyRoot() {
  const root = (ui.rootInput.value || '').trim();
  if (!root) { say('укажи папку, гений'); return; }
  ui.rootApply.disabled = true;
  say('сканирую ' + root + ' …');
  try {
    const res = await api('/api/root', { root });
    state.selected = null;
    ui.panel.classList.remove('open');
    state.hidden.clear();
    state.feed = await api('/galaxy.json');
    buildStars();
    renderHud();
    loadRoots();
    say('папка: ' + res.root + ' — проектов ' + res.totals.projects + ', TODO ' + res.totals.todos);
  } catch (err) {
    fail('Не переключил папку: ' + err.message);
  } finally {
    ui.rootApply.disabled = false;
  }
}

ui.rootSelect.addEventListener('change', () => {
  if (ui.rootSelect.value) ui.rootInput.value = ui.rootSelect.value;
});
ui.rootApply.addEventListener('click', applyRoot);
ui.rootInput.addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter') applyRoot();
});

function buildStars() {
  const feed = state.feed;
  state.stars = feed.projects.map((p) => ({
    node: p,
    x: p.pos[0] * SPREAD,
    y: p.pos[1] * SPREAD,
    z: p.pos[2] * SPREAD,
    color: STACK_COLORS[p.stack] || STACK_COLORS.unknown,
    status: STATUS_COLORS[p.status] || STATUS_COLORS.unknown,
    size: 2.2 + (p.score / 100) * 5.2 + Math.min(3.4, p.todos / 6)
        + Math.min(3, Math.log10((p.junk_bytes || 0) + 1) * 0.55),
  })).map((s, i) => ({ ...s, index: i, screen: { x: 0, y: 0, r: 0, s: 0 } }));
  state.byName = {};
  state.stars.forEach((s) => { state.byName[s.node.name] = s; });
}

function statBox(value, label) {
  const box = document.createElement('div');
  box.className = 'stat';
  const b = document.createElement('b');
  b.textContent = value;
  const sm = document.createElement('small');
  sm.textContent = label;
  box.append(b, sm);
  return box;
}

function renderHud() {
  const totals = state.feed.totals;
  ui.root.textContent = state.feed.root;
  ui.stats.innerHTML = '';
  ui.stats.append(
    statBox(String(totals.projects), 'проектов'),
    statBox(String(totals.avg_score), 'средний score'),
    statBox(String(totals.by_status.alive || 0), 'живых'),
    statBox(String(totals.dead.length), 'на свалку'),
    statBox(String(totals.todos), 'TODO'),
  );

  ui.chips.innerHTML = '';
  ['alive', 'abandoned', 'broken', 'unknown'].forEach((status) => {
    const count = totals.by_status[status] || 0;
    if (!count) return;
    const chip = document.createElement('button');
    chip.className = 'chip';
    chip.setAttribute('aria-pressed', String(!state.hidden.has(status)));
    chip.innerHTML = '<i class="dot" style="color:' + STATUS_COLORS[status] + '"></i>' +
      STATUS_LABELS[status] + ' · ' + count;
    chip.onclick = () => {
      if (state.hidden.has(status)) state.hidden.delete(status); else state.hidden.add(status);
      renderHud();
    };
    ui.chips.append(chip);
  });

  const chip = document.createElement('button');
  chip.className = 'chip';
  chip.textContent = '↻ пересканировать';
  chip.onclick = () => init(true);
  ui.chips.append(chip);

  ui.legend.innerHTML = '';
  const stacks = Object.keys(state.feed.clusters);
  stacks.forEach((stack) => {
    const count = totals.by_stack[stack] || 0;
    if (!count) return;
    const row = document.createElement('div');
    row.innerHTML = '<i style="background:' + (STACK_COLORS[stack] || '#888') + '"></i>' +
      stack + ' · ' + count;
    ui.legend.append(row);
  });
}

/* ---------- проекция и отрисовка ---------- */

function resize() {
  const dpr = window.devicePixelRatio || 1;
  state.width = window.innerWidth;
  state.height = window.innerHeight;
  canvas.width = Math.floor(state.width * dpr);
  canvas.height = Math.floor(state.height * dpr);
  canvas.style.width = state.width + 'px';
  canvas.style.height = state.height + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function project(x, y, z) {
  const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw);
  const cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
  const x1 = x * cy - z * sy;
  const z1 = x * sy + z * cy;
  const y1 = y * cp - z1 * sp;
  const z2 = y * sp + z1 * cp;
  const s = (FOV / (CAM_DIST + z2)) * state.zoom;
  return { x: state.width / 2 + x1 * s, y: state.height / 2 + y1 * s, z: z2, s };
}

function visible(star) { return !state.hidden.has(star.node.status); }

function drawNebulae() {
  for (const [stack, pos] of Object.entries(state.feed.clusters)) {
    if (!(state.feed.totals.by_stack[stack] || 0)) continue;
    const pr = project(pos[0] * SPREAD, pos[1] * SPREAD, pos[2] * SPREAD);
    const radius = 200 * pr.s;
    if (radius < 8) continue;
    const grad = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, radius);
    const color = STACK_COLORS[stack] || STACK_COLORS.unknown;
    grad.addColorStop(0, hexA(color, 0.16));
    grad.addColorStop(0.5, hexA(color, 0.05));
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, radius, 0, Math.PI * 2);
    ctx.fill();
  }
}

function hexA(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + alpha + ')';
}

function drawLinks(order) {
  ctx.lineWidth = 1;
  for (const [stack, pos] of Object.entries(state.feed.clusters)) {
    const center = project(pos[0] * SPREAD, pos[1] * SPREAD, pos[2] * SPREAD);
    ctx.strokeStyle = hexA(STACK_COLORS[stack] || STACK_COLORS.unknown, 0.08);
    for (const item of order) {
      if (item.star.node.stack !== stack) continue;
      ctx.beginPath();
      ctx.moveTo(center.x, center.y);
      ctx.lineTo(item.pr.x, item.pr.y);
      ctx.stroke();
    }
  }
}

function labelWorthy(star, rank) {
  return star === state.hover || star === state.selected || rank < TOP_LABELS;
}

function drawStars(order) {
  const ranked = [...order].sort((a, b) => b.star.node.score - a.star.node.score);
  order.forEach((item) => {
    const star = item.star, pr = item.pr;
    const r = Math.max(1.2, star.size * pr.s * 1.35);
    const rank = ranked.indexOf(item);
    star.screen = { x: pr.x, y: pr.y, r: r + 6, s: pr.s };

    const glow = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, r * 4.5);
    glow.addColorStop(0, hexA(star.color, star.node.status === 'alive' ? 0.55 : 0.3));
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, r * 4.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.beginPath();
    ctx.fillStyle = star.node.status === 'alive' ? star.color : hexA(star.color, 0.75);
    ctx.arc(pr.x, pr.y, r, 0, Math.PI * 2);
    ctx.fill();

    if (star.node.status === 'broken' || star.node.status === 'abandoned') {
      ctx.strokeStyle = hexA(star.status, 0.9);
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r + 3, 0, Math.PI * 2);
      ctx.stroke();
    }
    if (star === state.selected) {
      ctx.strokeStyle = '#e8eefc';
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r + 7, 0, Math.PI * 2);
      ctx.stroke();
    }
    if (labelWorthy(star, rank) && pr.s > 0.35) {
      ctx.font = (rank < 3 ? '600 ' : '') + Math.max(10, Math.min(14, 11 * pr.s * 1.4)) + 'px "Segoe UI", sans-serif';
      ctx.fillStyle = rank < 3 ? 'rgba(232,238,252,.92)' : 'rgba(232,238,252,.62)';
      ctx.textAlign = 'center';
      ctx.fillText(star.node.name, pr.x, pr.y - r - 7);
    }
  });
}

function drawDupes() {
  const links = state.feed.links || [];
  if (!links.length) return;
  ctx.save();
  ctx.setLineDash([5, 5]);
  ctx.lineWidth = 1.2;
  for (const link of links) {
    const a = state.byName[link.a];
    const b = state.byName[link.b];
    if (!a || !b || !visible(a) || !visible(b)) continue;
    ctx.strokeStyle = hexA('#f472b6', 0.3 + link.score * 0.45);
    ctx.beginPath();
    ctx.moveTo(a.screen.x, a.screen.y);
    ctx.lineTo(b.screen.x, b.screen.y);
    ctx.stroke();
  }
  ctx.restore();
}

let projected = [];
function draw() {
  if (!state.feed) return;
  ctx.clearRect(0, 0, state.width, state.height);
  drawNebulae();
  projected = state.stars.filter(visible).map((star) => {
    const pr = project(star.x, star.y, star.z);
    star.screen = { x: pr.x, y: pr.y, r: 8, s: pr.s };
    return { star, pr };
  }).sort((a, b) => b.pr.z - a.pr.z);
  drawLinks(projected);
  drawDupes();
  drawStars(projected);
}

function pick(mx, my) {
  let best = null, bestDist = Infinity;
  for (const star of state.stars) {
    if (!visible(star)) continue;
    const sc = star.screen;
    const dist = Math.hypot(sc.x - mx, sc.y - my);
    const limit = Math.max(HIT_RADIUS, sc.r);
    if (dist < limit && dist < bestDist) { best = star; bestDist = dist; }
  }
  return best;
}

function showTip(star, mx, my) {
  if (!star) { ui.tip.style.opacity = '0'; return; }
  const n = star.node;
  ui.tip.innerHTML = '<b>' + esc(n.name) + '</b><br>' +
    n.stack + ' · score ' + n.score + ' · ' + STATUS_LABELS[n.status] +
    '<small>' + (n.why[0] ? esc(n.why[0]) : 'претензий нет') + '</small>';
  ui.tip.style.left = mx + 'px';
  ui.tip.style.top = my + 'px';
  ui.tip.style.opacity = '1';
}

function esc(text) {
  return String(text === undefined || text === null ? '' : text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ---------- панель проекта ---------- */

function select(star) {
  state.selected = star;
  if (!star) { ui.panel.classList.remove('open'); return; }
  renderPanel(star);
  ui.panel.classList.add('open');
}

function row(label, value) {
  return '<div class="row"><span>' + esc(label) + '</span><span>' + esc(value) + '</span></div>';
}

function humanBytes(num) {
  num = Number(num) || 0;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (num >= 1024 && i < units.length - 1) { num /= 1024; i++; }
  return (i === 0 ? Math.round(num) : num.toFixed(1)) + ' ' + units[i];
}

function sparkline(history) {
  if (!history || history.length < 2) return '';
  const pts = [...history].reverse();                 // старые слева
  const w = 280, h = 36;
  const step = w / (pts.length - 1);
  const poly = pts.map((p, i) =>
    (i * step).toFixed(1) + ',' + (h - (p.score / 100) * (h - 6) - 3).toFixed(1)).join(' ');
  return '<svg viewBox="0 0 ' + w + ' ' + h + '" class="spark">' +
    '<polyline points="' + poly + '" fill="none" stroke="#7dd3fc" stroke-width="2"/>' +
    '</svg><div class="muted small">история score (последние ' + pts.length + ' сканов)</div>';
}

async function loadHistory(star) {
  const box = document.getElementById('sparkBox');
  if (!box) return;
  try {
    const data = await api('/api/history?path=' + encodeURIComponent(star.node.path));
    box.innerHTML = sparkline(data.history) ||
      '<span class="muted small">история появится после второго скана</span>';
  } catch (err) {
    box.innerHTML = '<span class="muted small">история недоступна: ' + esc(err.message) + '</span>';
  }
}

async function runDoctor(star, btn) {
  const out = document.getElementById('doctorOut');
  if (btn) btn.disabled = true;
  if (out) out.innerHTML = '<div class="muted small">диагностирую…</div>';
  try {
    const data = await api('/api/doctor', { path: star.node.path });
    const rows = data.checks.map((c) =>
      '<div class="row"><span>' + (c.ok ? '✓' : '✗') + ' ' + esc(c.check) + '</span>' +
      '<span>' + esc(c.detail || '') + '</span></div>').join('');
    if (out) out.innerHTML = '<div class="section">Диагностика</div>' + rows;
  } catch (err) {
    if (out) out.innerHTML = '<div class="warnbox">' + esc(err.message) + '</div>';
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function gitInit(star, btn) {
  if (!window.confirm('Создать git-репозиторий, .gitignore и первый коммит в «' +
      star.node.name + '»?')) return;
  if (btn) btn.disabled = true;
  try {
    await api('/api/gitinit', { path: star.node.path, confirm: true });
    say('git создан: ' + star.node.name);
    await init(true);
    const again = state.byName[star.node.name];
    if (again) renderPanel(again);
  } catch (err) {
    fail('git не создался: ' + err.message);
    if (btn) btn.disabled = false;
  }
}

async function cleanJunk(star, part, btn) {
  if (!window.confirm('Снести «' + part + '» в ' + star.node.name + '?\n' +
      'Его можно пересоздать (npm install / python -m venv), но это займёт время.')) return;
  if (btn) btn.disabled = true;
  try {
    const res = await api('/api/clean', { path: star.node.path, part: part, confirm: true });
    say('снесено ' + res.removed + ', освобождено ' + humanBytes(res.freed_bytes));
    await init(true);
    const again = state.byName[star.node.name];
    if (again) renderPanel(again);
  } catch (err) {
    fail('Не снеслось: ' + err.message);
    if (btn) btn.disabled = false;
  }
}
function renderPanel(star) {
  const n = star.node;
  const meter = Math.max(3, n.score);
  const penalties = (n.penalties || []).map((p) => '<li>' + esc(p.why) + ' (' + p.points + ')</li>').join('');
  const bonuses = (n.bonuses || []).map((b) => '<li>+' + b.points + ' ' + esc(b.why) + '</li>').join('');

  const junk = n.junk_bytes || 0;
  const diskHtml = junk > 0
    ? '<div class="section">Мусор на диске: <b>' + humanBytes(junk) + '</b></div>' +
      (n.junk_parts || []).map((p) =>
        '<div class="junkrow"><span>' + esc(p.name) + '</span>' +
        '<span class="muted">' + humanBytes(p.bytes) + '</span>' +
        '<button data-clean="' + esc(p.name) + '">снести</button></div>').join('')
    : '';
  const warns = [];
  if (n.secrets > 0) warns.push('найдено секретов: ' + n.secrets);
  if (n.env_leak_risk) warns.push('.env не в .gitignore');
  const warnHtml = warns.length
    ? '<div class="warnbox">⚠ ' + warns.map(esc).join(' · ') + '</div>' : '';

  ui.panel.innerHTML =
    '<h2>' + esc(n.name) + '</h2>' +
    '<div class="tagline">' + esc(n.tagline || n.rel) + '</div>' +
    '<div class="meter"><i style="width:' + meter + '%;background:' + star.status + '"></i></div>' +
    row('health', n.score + ' / 100 — ' + STATUS_LABELS[n.status]) +
    row('стек', n.stacks.join(', ') || '—') +
    row('простой', n.idle_days + ' дней') +
    row('ветка', n.branch) +
    row('точка входа', n.entry || '—') +
    row('зависимости', n.deps) +
    row('TODO внутри', n.todos) +
    row('вес на диске', humanBytes(n.total_bytes)) +
    row('README', n.has_readme ? 'есть' : 'нет') +
    warnHtml +
    (penalties ? '<ul class="why">' + penalties + '</ul>' : '') +
    (bonuses ? '<ul class="why bonus">' + bonuses + '</ul>' : '') +
    diskHtml +
    '<div id="sparkBox" class="muted small">история загружается…</div>' +
    '<div class="sub" style="margin-top:12px">' + esc(n.path) + '</div>' +
    '<div class="actions">' +
    '<button data-open="explorer">Проводник</button>' +
    '<button data-open="code">VS Code</button>' +
    '<button data-open="terminal">Терминал</button>' +
    '<button id="doctorBtn">Диагностика</button>' +
    (n.has_git ? '' : '<button id="gitBtn">Создать git</button>') +
    '<button data-copy="path">Копировать путь</button>' +
    '</div>' +
    '<div id="doctorOut"></div>';

  ui.panel.querySelectorAll('button[data-open]').forEach((btn) => {
    btn.onclick = () => openTarget(n.path, btn.dataset.open, btn);
  });
  ui.panel.querySelectorAll('button[data-clean]').forEach((btn) => {
    btn.onclick = () => cleanJunk(star, btn.dataset.clean, btn);
  });
  ui.panel.querySelector('button[data-copy]').onclick = () => {
    navigator.clipboard.writeText(n.path).then(() => say('путь скопирован: ' + n.path));
  };
  const doctorBtn = ui.panel.querySelector('#doctorBtn');
  if (doctorBtn) doctorBtn.onclick = () => runDoctor(star, doctorBtn);
  const gitBtn = ui.panel.querySelector('#gitBtn');
  if (gitBtn) gitBtn.onclick = () => gitInit(star, gitBtn);

  loadHistory(star);
}

async function openTarget(path, how, btn) {
  if (btn) btn.disabled = true;
  try {
    const res = await api('/api/open', { path, with: how });
    say('открыто в ' + res.note + ': ' + path);
  } catch (err) {
    fail('Не удалось открыть: ' + err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ---------- ввод ---------- */

let drag = null;

canvas.addEventListener('pointerdown', (ev) => {
  drag = { x: ev.clientX, y: ev.clientY, moved: false };
  canvas.classList.add('dragging');
  canvas.setPointerCapture(ev.pointerId);
});

canvas.addEventListener('pointermove', (ev) => {
  if (drag) {
    const dx = ev.clientX - drag.x;
    const dy = ev.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    state.yaw += dx * 0.006;
    state.pitch = Math.max(-1.25, Math.min(1.25, state.pitch + dy * 0.006));
    drag.x = ev.clientX;
    drag.y = ev.clientY;
    showTip(null);
    return;
  }
  const star = pick(ev.clientX, ev.clientY);
  state.hover = star;
  showTip(star, ev.clientX, ev.clientY);
});

canvas.addEventListener('pointerup', (ev) => {
  canvas.classList.remove('dragging');
  if (drag && !drag.moved) {
    const star = pick(ev.clientX, ev.clientY);
    select(star || null);
    if (star) say(star.node.name + ' — ' + star.node.path);
  }
  drag = null;
});

canvas.addEventListener('dblclick', (ev) => {
  const star = pick(ev.clientX, ev.clientY);
  if (star) openTarget(star.node.path, 'explorer');
});

canvas.addEventListener('wheel', (ev) => {
  ev.preventDefault();
  state.zoom = Math.max(0.35, Math.min(3.5, state.zoom * Math.exp(-ev.deltaY * 0.0012)));
}, { passive: false });

window.addEventListener('keydown', (ev) => {
  if (ev.key === 'r' || ev.key === 'R') init(true);
  if (ev.key === 'Escape') {
    state.yaw = 0.6; state.pitch = -0.34; state.zoom = 1;
    select(null);
  }
});

window.addEventListener('resize', resize);

/* ---------- цикл ---------- */

function loop() {
  draw();
  requestAnimationFrame(loop);
}

resize();
init(false);
requestAnimationFrame(loop);
