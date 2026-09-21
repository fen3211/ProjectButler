'use strict';
/* Project Butler — галактика проектов. Стиль «Тёмная материя»: чистый чёрный,
   боке-звёзды, тонкая типографика, док. Canvas 2D + ручная 3D-проекция, без Three.js и CDN. */

const STACK_COLORS = {
  python: '#4fc3f7', node: '#a3e635', csharp: '#c084fc', go: '#22d3ee',
  docker: '#fb923c', js: '#fcd34d', git: '#fb923c', unknown: '#94a3b8'
};
const STATUS_COLORS = { alive: '#7ef0b2', abandoned: '#ffd479', broken: '#ff7a90', unknown: '#8a93ad' };
const STATUS_LABELS = { alive: 'живой', abandoned: 'заброшен', broken: 'сломан', unknown: 'пусто' };
const ACCENT = '#9d8cff';
const DUPE_COLOR = '#ff7a90';
const SPREAD = 150;
const CAM_DIST = 1500;
const FOV = 1250;
const HIT_RADIUS = 16;
const TOP_LABELS = 8;

const state = {
  feed: null, stars: [], hidden: new Set(), byName: {}, rank: new Map(),
  yaw: 0.6, pitch: -0.34, zoom: 1,
  hover: null, selected: null, width: 0, height: 0,
  bg: null, scanning: false,
};

const canvas = document.getElementById('sky');
const ctx = canvas.getContext('2d');
const ui = {
  root: document.getElementById('root'),
  stats: document.getElementById('stats'),
  legend: document.getElementById('legend'),
  dock: document.getElementById('dock'),
  detail: document.getElementById('detail'),
  tip: document.getElementById('tip'),
  status: document.getElementById('status'),
  error: document.getElementById('error'),
  rootInput: document.getElementById('rootInput'),
  rootList: document.getElementById('rootList'),
  rootApply: document.getElementById('rootApply'),
  browseBtn: document.getElementById('browseBtn'),
};

/* ---------- пикер папок ---------- */

const picker = {
  box: document.getElementById('picker'),
  pathEl: document.getElementById('pickPath'),
  drives: document.getElementById('pickDrives'),
  list: document.getElementById('pickList'),
  up: document.getElementById('pickUp'),
  scanBtn: document.getElementById('pickScan'),
  closeBtn: document.getElementById('pickClose'),
  current: '',
  parent: null,
};

function pickerOpen() { return picker.box.classList.contains('open'); }

function openPicker(start) {
  picker.box.classList.add('open');
  browse(start || (state.feed && state.feed.root) || '');
}

function closePicker() { picker.box.classList.remove('open'); }

function joinPath(base, name) {
  return base.endsWith('\\') ? base + name : base + '\\' + name;
}

function scanFrom(path) {
  closePicker();
  ui.rootInput.value = path;
  applyRoot();
}

async function browse(path) {
  picker.current = path;
  picker.parent = null;
  picker.pathEl.textContent = path || 'мой компьютер — выбери диск';
  picker.list.innerHTML = '<div class="pempty">читаю…</div>';
  try {
    const data = await api('/api/browse?path=' + encodeURIComponent(path));
    renderBrowse(data);
  } catch (err) {
    picker.drives.innerHTML = '';
    picker.list.innerHTML = '<div class="pempty">' + esc(err.message) + '</div>';
  }
}

function renderBrowse(data) {
  picker.parent = data.parent || null;
  picker.up.classList.toggle('disabled', !picker.parent);

  picker.drives.innerHTML = '';
  (data.drives || []).forEach((drive) => {
    const b = document.createElement('button');
    b.className = 'pdrive' +
      (String(picker.current).toUpperCase().startsWith(drive.toUpperCase()) ? ' on' : '');
    b.textContent = drive;
    b.onclick = () => browse(drive);
    picker.drives.append(b);
  });

  picker.list.innerHTML = '';
  if (!data.dirs.length) {
    const empty = document.createElement('div');
    empty.className = 'pempty';
    empty.textContent = 'подпапок не видно — можно сканировать эту или подняться выше';
    picker.list.append(empty);
  }
  data.dirs.forEach((name) => {
    const row = document.createElement('div');
    row.className = 'pitem';
    const ico = document.createElement('span');
    ico.className = 'ico';
    ico.textContent = '▸';
    const label = document.createElement('span');
    label.textContent = name;
    row.append(ico, label);
    const full = joinPath(picker.current, name);
    row.onclick = () => browse(full);
    row.ondblclick = () => scanFrom(full);
    picker.list.append(row);
  });
}

picker.closeBtn.addEventListener('click', closePicker);
picker.up.addEventListener('click', () => { if (picker.parent) browse(picker.parent); });
picker.scanBtn.addEventListener('click', () => { if (picker.current) scanFrom(picker.current); });
picker.box.addEventListener('click', (ev) => { if (ev.target === picker.box) closePicker(); });
ui.browseBtn.addEventListener('click', () => openPicker());

function say(text) { ui.status.textContent = text; }

function fail(text) {
  ui.error.style.display = 'block';
  ui.error.innerHTML = '';
  const p = document.createElement('div');
  p.textContent = text;
  const btn = document.createElement('div');
  btn.className = 'btn';
  btn.textContent = 'повторить';
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
  if (state.scanning) { say('скан уже идёт — дай ему доработать'); return; }
  say(rescan ? 'запускаю рескан…' : 'читаю фид…');
  try {
    if (rescan) {
      const res = await api('/api/scan', {});
      if (res.scanning) { waitScan(res.root); return; }
    }
    state.feed = await api('/galaxy.json');
  } catch (err) {
    fail('Не удалось получить данные: ' + err.message + '. Сервер поднят командой `python -m butler ui`.');
    return;
  }
  refreshUI();
  loadRoots();
  say('готово: ' + state.feed.projects.length + ' проектов, фид от ' + state.feed.generated_at_iso);
}

function refreshUI() {
  buildStars();
  renderTop();
  renderLegend();
  renderDock();
}

async function loadFeed() {
  state.feed = await api('/galaxy.json');
  refreshUI();
  loadRoots();
}

/* ---------- ожидание фонового скана ---------- */

let pollTimer = null;

function pollScan(onDone) {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    let st;
    try { st = await api('/api/scan-status'); }
    catch (e) { return; }                               // сеть моргнула — ждём дальше
    if (st.running) return;
    clearInterval(pollTimer);
    pollTimer = null;
    onDone(st);
  }, 1500);
}

function waitScan(root) {
  state.scanning = true;
  ui.rootApply.disabled = true;
  say('сканирую ' + root + ' — большим папкам нужно время, галактика обновится сама');
  pollScan((st) => {
    state.scanning = false;
    ui.rootApply.disabled = false;
    if (st.error) { fail(st.error); return; }
    loadFeed().then(() => {
      say('готово: ' + state.feed.projects.length + ' проектов, фид от ' + state.feed.generated_at_iso);
    }).catch((err) => fail('Не удалось обновить данные: ' + err.message));
  });
}

/* ---------- выбор папки сканирования ---------- */

async function loadRoots() {
  try {
    const data = await api('/api/roots');
    ui.rootList.innerHTML = '';
    const all = data.current && !data.roots.includes(data.current)
      ? [data.current, ...data.roots] : data.roots;
    all.forEach((root) => {
      const opt = document.createElement('option');
      opt.value = root;
      ui.rootList.append(opt);
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
  if (state.scanning) { say('скан уже идёт — дай ему доработать'); return; }
  ui.rootApply.disabled = true;
  let res;
  try {
    res = await api('/api/root', { root });
  } catch (err) {
    ui.rootApply.disabled = false;
    fail('Не переключил папку: ' + err.message);
    return;
  }
  select(null);
  state.hidden.clear();
  if (res.scanning) { waitScan(res.root); return; }
  ui.rootApply.disabled = false;
  try {
    await loadFeed();
    say('папка: ' + res.root + ' — проектов ' + res.totals.projects + ', TODO ' + res.totals.todos);
  } catch (err) {
    fail('Не обновил данные: ' + err.message);
  }
}

ui.rootApply.addEventListener('click', applyRoot);
ui.rootInput.addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter') applyRoot();
});

/* ---------- данные ---------- */

function buildStars() {
  const feed = state.feed;
  state.stars = feed.projects.map((p) => ({
    node: p,
    x: p.pos[0] * SPREAD,
    y: p.pos[1] * SPREAD,
    z: p.pos[2] * SPREAD,
    color: STACK_COLORS[p.stack] || STACK_COLORS.unknown,
    status: STATUS_COLORS[p.status] || STATUS_COLORS.unknown,
    size: 2.2 + (p.score / 100) * 4.6 + Math.min(3, p.todos / 8)
        + Math.min(2.6, Math.log10((p.junk_bytes || 0) + 1) * 0.5),
  })).map((s, i) => ({ ...s, index: i, screen: { x: 0, y: 0, r: 0, s: 0 } }));
  state.byName = {};
  state.stars.forEach((s) => { state.byName[s.node.name] = s; });
  const ranked = [...state.stars].sort((a, b) => b.node.score - a.node.score);
  state.rank = new Map(ranked.map((s, i) => [s.index, i]));
}

function humanBytes(num) {
  num = Number(num) || 0;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (num >= 1024 && i < units.length - 1) { num /= 1024; i++; }
  return (i === 0 ? Math.round(num) : num.toFixed(1)) + ' ' + units[i];
}

/* ---------- верхняя строка ---------- */

function metaStat(value, label, color) {
  const box = document.createElement('div');
  const b = document.createElement('b');
  b.textContent = value;
  if (color) b.style.color = color;
  const sm = document.createElement('small');
  sm.textContent = label;
  box.append(b, sm);
  return box;
}

function renderTop() {
  const totals = state.feed.totals;
  ui.root.textContent = state.feed.root;
  const junk = state.stars.reduce((acc, s) => acc + (s.node.junk_bytes || 0), 0);
  ui.stats.innerHTML = '';
  ui.stats.append(
    metaStat(String(totals.projects), 'проекта'),
    metaStat(String(totals.avg_score), 'avg score'),
    metaStat(String(totals.by_status.alive || 0), 'живых'),
    metaStat(String(totals.todos), 'todo'),
    metaStat(totals.dead.length ? String(totals.dead.length) : '0', 'на свалку',
      totals.dead.length ? '#ffd479' : null),
    metaStat(junk > 0 ? humanBytes(junk) : '0', 'мусора', junk > 0 ? '#ff7a90' : null),
  );
}

/* ---------- легенда + фильтры ---------- */

function renderLegend() {
  const totals = state.feed.totals;
  ui.legend.innerHTML = '';

  const stacks = document.createElement('div');
  stacks.className = 'grp';
  Object.keys(state.feed.clusters).forEach((stack) => {
    const count = totals.by_stack[stack] || 0;
    if (!count) return;
    const row = document.createElement('span');
    row.className = 'item';
    row.innerHTML = '<i style="background:' + (STACK_COLORS[stack] || '#888') + '"></i>' +
      esc(stack) + ' ' + count;
    stacks.append(row);
  });
  ui.legend.append(stacks);

  const sep = document.createElement('span');
  sep.className = 'sep';
  ui.legend.append(sep);

  const pills = document.createElement('div');
  pills.className = 'grp';
  ['alive', 'abandoned', 'broken', 'unknown'].forEach((status) => {
    const count = totals.by_status[status] || 0;
    if (!count) return;
    const pill = document.createElement('button');
    pill.className = 'pill';
    pill.setAttribute('aria-pressed', String(!state.hidden.has(status)));
    pill.innerHTML = '<i style="background:' + STATUS_COLORS[status] + '"></i>' +
      STATUS_LABELS[status] + ' · ' + count;
    pill.onclick = () => {
      if (state.hidden.has(status)) state.hidden.delete(status); else state.hidden.add(status);
      renderLegend();
      renderDock();
    };
    pills.append(pill);
  });

  const rescan = document.createElement('button');
  rescan.className = 'pill ghost';
  rescan.textContent = '↻ пересканировать';
  rescan.onclick = () => init(true);
  pills.append(rescan);

  const cosmosBtn = document.createElement('button');
  cosmosBtn.className = 'pill ghost';
  cosmosBtn.setAttribute('aria-pressed', String(!motionOff()));
  cosmosBtn.title = 'анимации космоса: дрейф, дыхание, параллакс от курсора';
  cosmosBtn.textContent = motionOff() ? '✦ космос: выкл' : '✦ космос: вкл';
  cosmosBtn.onclick = () => {
    if (motionOff()) localStorage.removeItem('cosmos-still');
    else localStorage.setItem('cosmos-still', '1');
    applyCosmosMotion();
    renderLegend();
  };
  pills.append(cosmosBtn);
  ui.legend.append(pills);
}

/* ---------- док проектов ---------- */

function dockStatus(node) {
  if (node.status === 'abandoned') return 'простой ' + node.idle_days + 'д';
  return STATUS_LABELS[node.status];
}

function renderDock() {
  ui.dock.innerHTML = '';
  const visibleStars = state.stars.filter(visible).sort((a, b) => b.node.score - a.node.score);
  if (!visibleStars.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'никого не видно — включи статусы в легенде выше или просканируй папку';
    ui.dock.append(empty);
    return;
  }
  visibleStars.forEach((star) => {
    const n = star.node;
    const item = document.createElement('div');
    item.className = 'item' + (star === state.selected ? ' active' : '');
    item.title = n.path;
    item.innerHTML =
      '<div class="nm"><i style="background:' + star.color + '"></i><span>' + esc(n.name) + '</span></div>' +
      '<div class="meta"><span class="sc">' + n.score + '</span>' +
      '<span class="st st-' + n.status + '">' + esc(dockStatus(n)) + '</span></div>' +
      '<div class="track"><i style="width:' + Math.max(2, n.score) + '%;background:' +
      star.status + '"></i></div>';
    item.onclick = () => select(star);
    item.ondblclick = () => openTarget(n.path, 'explorer');
    ui.dock.append(item);
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
  buildBg();
}

function mulberry32(a) {
  return function () {
    a |= 0; a = a + 0x6D2B79F5 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

/* фон (пыль + боке) prerender'ится один раз на resize */
function buildBg() {
  const dpr = window.devicePixelRatio || 1;
  const bg = document.createElement('canvas');
  bg.width = canvas.width; bg.height = canvas.height;
  const b = bg.getContext('2d');
  b.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W = state.width, H = state.height;
  const rnd = mulberry32(20260921);

  b.fillStyle = '#cfd8ff';
  for (let i = 0; i < 320; i++) {
    b.globalAlpha = rnd() * .35 + .05;
    b.beginPath();
    b.arc(rnd() * W, rnd() * H, rnd() * .9 + .2, 0, 7);
    b.fill();
  }
  b.globalAlpha = 1;

  function bokeh(x, y, r, rgb, a) {
    const g = b.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, 'rgba(' + rgb + ',' + a + ')');
    g.addColorStop(.55, 'rgba(' + rgb + ',' + a * .35 + ')');
    g.addColorStop(1, 'rgba(' + rgb + ',0)');
    b.fillStyle = g;
    b.beginPath(); b.arc(x, y, r, 0, 7); b.fill();
  }
  for (let i = 0; i < 26; i++) {
    bokeh(rnd() * W, rnd() * H, rnd() * 42 + 14, '157,140,255', rnd() * .12 + .04);
  }
  for (let i = 0; i < 18; i++) {
    bokeh(rnd() * W, rnd() * H, rnd() * 32 + 10, '110,231,255', rnd() * .10 + .03);
  }
  state.bg = bg;
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

function hexA(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + alpha + ')';
}

function drawLinks(order) {
  ctx.lineWidth = 1;
  for (const [stack, pos] of Object.entries(state.feed.clusters)) {
    const count = state.feed.totals.by_stack[stack] || 0;
    if (!count) continue;
    const center = project(pos[0] * SPREAD, pos[1] * SPREAD, pos[2] * SPREAD);
    ctx.strokeStyle = hexA(STACK_COLORS[stack] || STACK_COLORS.unknown, 0.12);
    for (const item of order) {
      if (item.star.node.stack !== stack) continue;
      ctx.beginPath();
      ctx.moveTo(center.x, center.y);
      ctx.lineTo(item.pr.x, item.pr.y);
      ctx.stroke();
    }
  }
}

function drawDupes() {
  const links = state.feed.links || [];
  if (!links.length) return;
  ctx.save();
  ctx.setLineDash([4, 5]);
  ctx.lineWidth = 1;
  for (const link of links) {
    const a = state.byName[link.a];
    const b = state.byName[link.b];
    if (!a || !b || !visible(a) || !visible(b)) continue;
    ctx.strokeStyle = hexA(DUPE_COLOR, 0.25 + link.score * 0.4);
    ctx.beginPath();
    ctx.moveTo(a.screen.x, a.screen.y);
    ctx.lineTo(b.screen.x, b.screen.y);
    ctx.stroke();
  }
  ctx.restore();
}

function drawStars(order) {
  order.forEach((item) => {
    const star = item.star, pr = item.pr;
    const r = Math.max(1.4, star.size * pr.s * 1.3);
    const alive = star.node.status === 'alive';
    star.screen = { x: pr.x, y: pr.y, r: r + 6, s: pr.s };

    const glowA = alive ? 0.5 : 0.3;
    const glow = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, r * 6.5);
    glow.addColorStop(0, hexA(star.color, glowA));
    glow.addColorStop(0.35, hexA(star.color, glowA * 0.35));
    glow.addColorStop(1, hexA(star.color, 0));
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, r * 6.5, 0, Math.PI * 2);
    ctx.fill();

    const core = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, r);
    core.addColorStop(0, '#ffffff');
    core.addColorStop(1, star.color);
    ctx.fillStyle = core;
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, r, 0, Math.PI * 2);
    ctx.fill();

    if (star.node.status === 'broken' || star.node.status === 'abandoned') {
      ctx.strokeStyle = hexA(star.status, 0.55);
      ctx.lineWidth = 1.1;
      if (star.node.status === 'broken') ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r + 4.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (star === state.selected) {
      ctx.strokeStyle = 'rgba(255,255,255,.85)';
      ctx.lineWidth = 1.1;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r + 7, 0, Math.PI * 2);
      ctx.stroke();
      ctx.save();
      ctx.shadowColor = 'rgba(200,210,255,.9)';
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.moveTo(pr.x - r * 5, pr.y); ctx.lineTo(pr.x + r * 5, pr.y);
      ctx.moveTo(pr.x, pr.y - r * 5); ctx.lineTo(pr.x, pr.y + r * 5);
      ctx.stroke();
      ctx.restore();
    }
    if (labelWorthy(star) && pr.s > 0.35) {
      const sel = star === state.selected || star === state.hover;
      ctx.font = (sel ? '450 ' : '300 ') + '11px "Segoe UI", sans-serif';
      ctx.fillStyle = sel ? 'rgba(242,244,255,.9)' : 'rgba(242,244,255,.55)';
      ctx.textAlign = 'center';
      ctx.fillText(star.node.name + ' · ' + star.node.score, pr.x, pr.y - r - 9);
    }
  });
}

function labelWorthy(star) {
  return star === state.hover || star === state.selected || state.rank.get(star.index) < TOP_LABELS;
}

let projected = [];
function draw() {
  if (!state.feed) return;
  ctx.clearRect(0, 0, state.width, state.height);
  if (state.bg) ctx.drawImage(state.bg, 0, 0, state.width, state.height);
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
  ui.tip.innerHTML = '<b>' + esc(n.name) + '</b> · ' + n.score +
    '<small>' + esc(n.stack) + ' · ' + STATUS_LABELS[n.status] + ' · ' +
    (n.why[0] ? esc(n.why[0]) : 'претензий нет') + '</small>';
  ui.tip.style.left = mx + 'px';
  ui.tip.style.top = my + 'px';
  ui.tip.style.opacity = '1';
}

function esc(text) {
  return String(text === undefined || text === null ? '' : text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ---------- карточка проекта ---------- */

function select(star) {
  state.selected = star;
  if (!star) { ui.detail.classList.remove('open'); renderDock(); return; }
  renderPanel(star);
  ui.detail.classList.add('open');
  renderDock();
}

function fact(label, value) {
  return '<div class="fact"><span>' + esc(label) + '</span><span>' + esc(value) + '</span></div>';
}

function sparkline(history) {
  if (!history || history.length < 2) return '';
  const pts = [...history].reverse();                 // старые слева
  const w = 280, h = 36;
  const step = w / (pts.length - 1);
  const poly = pts.map((p, i) =>
    (i * step).toFixed(1) + ',' + (h - (p.score / 100) * (h - 6) - 3).toFixed(1)).join(' ');
  return '<svg viewBox="0 0 ' + w + ' ' + h + '" class="spark">' +
    '<polyline points="' + poly + '" fill="none" stroke="#9d8cff" stroke-width="1.6"/>' +
    '</svg><div class="fact" style="border-bottom:0"><span>история score</span>' +
    '<span>последние ' + pts.length + ' сканов</span></div>';
}

async function loadHistory(star) {
  const box = document.getElementById('sparkBox');
  if (!box) return;
  try {
    const data = await api('/api/history?path=' + encodeURIComponent(star.node.path));
    box.innerHTML = sparkline(data.history) ||
      '<div class="fact" style="border-bottom:0"><span>история score</span>' +
      '<span>появится после второго скана</span></div>';
  } catch (err) {
    box.innerHTML = '<div class="warnbox">история недоступна: ' + esc(err.message) + '</div>';
  }
}

async function runDoctor(star, btn) {
  const out = document.getElementById('doctorOut');
  if (btn) btn.disabled = true;
  if (out) out.innerHTML = '<div class="fact" style="border-bottom:0"><span>диагностика</span><span>идёт…</span></div>';
  try {
    const data = await api('/api/doctor', { path: star.node.path });
    const rows = data.checks.map((c) =>
      '<div class="doctorrow"><span>' + (c.ok ? '✓' : '✗') + ' ' + esc(c.check) + '</span>' +
      '<span>' + esc(c.detail || '') + '</span></div>').join('');
    if (out) out.innerHTML = '<div class="kick" style="margin-top:14px">диагностика</div>' + rows;
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
    if (again) { select(again); renderPanel(again); }
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
    if (again) { select(again); renderPanel(again); }
  } catch (err) {
    fail('Не снеслось: ' + err.message);
    if (btn) btn.disabled = false;
  }
}

function renderPanel(star) {
  const n = star.node;
  const penalties = (n.penalties || []).map((p) => '<li>' + esc(p.why) + ' (' + p.points + ')</li>').join('');
  const bonuses = (n.bonuses || []).map((b) => '<li>+' + b.points + ' ' + esc(b.why) + '</li>').join('');

  const junk = n.junk_bytes || 0;
  const diskHtml = junk > 0
    ? '<div class="kick" style="margin-top:14px">мусор на диске · ' + esc(humanBytes(junk)) + '</div>' +
      (n.junk_parts || []).map((p) =>
        '<div class="junkrow"><span>' + esc(p.name) + '</span>' +
        '<span class="bytes">' + esc(humanBytes(p.bytes)) + '</span>' +
        '<button data-clean="' + esc(p.name) + '">снести</button></div>').join('')
    : '';
  const warns = [];
  if (n.secrets > 0) warns.push('найдено секретов: ' + n.secrets);
  if (n.env_leak_risk) warns.push('.env не в .gitignore');
  const warnHtml = warns.length
    ? '<div class="warnbox">⚠ ' + warns.map(esc).join(' · ') + '</div>' : '';

  ui.detail.innerHTML =
    '<button class="close" title="закрыть (Esc)">×</button>' +
    '<div class="kick">проект</div>' +
    '<h2>' + esc(n.name) + '</h2>' +
    '<div class="path">' + esc(n.path) + '</div>' +
    '<div class="scoreline"><span class="big">' + n.score + '</span>' +
    '<span class="of">/ 100</span>' +
    '<span class="badge st-' + n.status + '" style="border-color:' + star.status + '55;color:' + star.status + '">' +
    esc(STATUS_LABELS[n.status]) + '</span></div>' +
    '<div class="meter"><i style="width:' + Math.max(2, n.score) + '%;background:linear-gradient(90deg,' +
    ACCENT + ',' + star.status + ')"></i></div>' +
    '<div class="facts">' +
    fact('стек', n.stacks.join(', ') || '—') +
    fact('простой', n.idle_days + ' ' + pluralDays(n.idle_days)) +
    fact('ветка', n.branch || '—') +
    fact('зависимости', String(n.deps)) +
    fact('TODO', String(n.todos)) +
    fact('вес на диске', humanBytes(n.total_bytes)) +
    fact('README', n.has_readme ? 'есть' : 'нет') +
    '</div>' +
    warnHtml +
    (penalties ? '<ul class="why">' + penalties + '</ul>' : '') +
    (bonuses ? '<ul class="why bonus">' + bonuses + '</ul>' : '') +
    diskHtml +
    '<div id="sparkBox"></div>' +
    '<div class="acts">' +
    '<div class="abtn main" data-open="code">VS Code</div>' +
    '<div class="abtn" data-open="explorer">Папка</div>' +
    '<div class="abtn" data-open="terminal">Терминал</div>' +
    '<div class="abtn" id="doctorBtn">Диагностика</div>' +
    (n.has_git ? '' : '<div class="abtn" id="gitBtn">Создать git</div>') +
    '<div class="abtn" data-copy="path">Копировать путь</div>' +
    '</div>' +
    '<div id="doctorOut"></div>';

  ui.detail.querySelector('.close').onclick = () => select(null);
  ui.detail.querySelectorAll('[data-open]').forEach((btn) => {
    btn.onclick = () => openTarget(n.path, btn.dataset.open, btn);
  });
  ui.detail.querySelectorAll('[data-clean]').forEach((btn) => {
    btn.onclick = () => cleanJunk(star, btn.dataset.clean, btn);
  });
  ui.detail.querySelector('[data-copy]').onclick = () => {
    navigator.clipboard.writeText(n.path).then(() => say('путь скопирован: ' + n.path));
  };
  const doctorBtn = ui.detail.querySelector('#doctorBtn');
  if (doctorBtn) doctorBtn.onclick = () => runDoctor(star, doctorBtn);
  const gitBtn = ui.detail.querySelector('#gitBtn');
  if (gitBtn) gitBtn.onclick = () => gitInit(star, gitBtn);

  loadHistory(star);
}

function pluralDays(days) {
  const d = Math.abs(days) % 100;
  const d1 = d % 10;
  if (d > 10 && d < 20) return 'дней';
  if (d1 > 1 && d1 < 5) return 'дня';
  if (d1 === 1) return 'день';
  return 'дней';
}

async function openTarget(path, how, btn) {
  if (btn) btn.classList.add('disabled');
  try {
    const res = await api('/api/open', { path, with: how });
    say('открыто в ' + res.note + ': ' + path);
  } catch (err) {
    fail('Не удалось открыть: ' + err.message);
  } finally {
    if (btn) btn.classList.remove('disabled');
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
  if (ev.target === ui.rootInput) return;
  if (ev.key === 'Escape') {
    if (pickerOpen()) { closePicker(); return; }
    state.yaw = 0.6; state.pitch = -0.34; state.zoom = 1;
    select(null);
    return;
  }
  if ((ev.key === 'r' || ev.key === 'R') && !pickerOpen()) init(true);
});

window.addEventListener('resize', resize);

/* ---------- космос под курсором: параллакс + свечение ---------- */

const cosmosEl = document.getElementById('cosmos');
const cosmosGlow = document.getElementById('cosmosGlow');
const cosmosAim = { px: 0, py: 0, gx: window.innerWidth / 2, gy: window.innerHeight / 2 };
const cosmosCur = { px: 0, py: 0, gx: cosmosAim.gx, gy: cosmosAim.gy };

// Движение космоса гасится только вручную (тумблер в легенде): системный
// prefers-reduced-motion у части юзеров выключен на уровне Windows и
// превращал фон в натюрморт независимо от наших анимаций.
function motionOff() {
  try { return localStorage.getItem('cosmos-still') === '1'; } catch (e) { return false; }
}

function applyCosmosMotion() {
  if (!cosmosEl) return;
  cosmosEl.classList.toggle('still', motionOff());
}

window.addEventListener('mousemove', (ev) => {
  cosmosAim.px = (ev.clientX / window.innerWidth) * 2 - 1;   // −1..1
  cosmosAim.py = (ev.clientY / window.innerHeight) * 2 - 1;
  cosmosAim.gx = ev.clientX;
  cosmosAim.gy = ev.clientY;
});

function cosmosStep() {
  if (motionOff() || !cosmosEl) return;
  const dx = cosmosAim.px - cosmosCur.px;
  const dy = cosmosAim.py - cosmosCur.py;
  const dgx = cosmosAim.gx - cosmosCur.gx;
  const dgy = cosmosAim.gy - cosmosCur.gy;
  if (Math.abs(dx) < .002 && Math.abs(dy) < .002 &&
      Math.abs(dgx) < 1.5 && Math.abs(dgy) < 1.5) return;    // ничего не двигалось — DOM не трогаем
  cosmosCur.px += dx * .05; cosmosCur.py += dy * .05;        // параллакс — ленивый
  cosmosCur.gx += dgx * .14; cosmosCur.gy += dgy * .14;      // свечение — шустрее
  cosmosEl.style.setProperty('--px', cosmosCur.px.toFixed(4));
  cosmosEl.style.setProperty('--py', cosmosCur.py.toFixed(4));
  if (cosmosGlow) {
    cosmosGlow.style.setProperty('--gx', cosmosCur.gx.toFixed(1) + 'px');
    cosmosGlow.style.setProperty('--gy', cosmosCur.gy.toFixed(1) + 'px');
  }
}

applyCosmosMotion();

/* ---------- цикл ---------- */

function loop() {
  cosmosStep();
  draw();
  requestAnimationFrame(loop);
}

resize();
init(false);
requestAnimationFrame(loop);
