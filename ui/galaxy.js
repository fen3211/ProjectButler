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
  bg: null, scanning: false, bornAt: 0,
  spin: null, lastAction: 0, cosmosStill: false,
  query: '', prev: {}, fx: [], warpT0: 0,
  meta: {}, contentHits: new Set(), tagFilter: new Set(), feedMtime: 0,
  settings: { theme: 'darkmatter', lang: 'ru', custom: {} }, palette: null,
};

/* палитры тем для канваса: пыль, туманности, акценты */
const CANVAS_THEMES = {
  darkmatter:  { dust: '#cfd8ff', warm: '157,140,255', cool: '110,231,255', accent: '#9d8cff', accent2: '#6ee7ff' },
  deepspace:   { dust: '#bfd4ff', warm: '90,150,255',  cool: '70,225,205',  accent: '#6ea8ff', accent2: '#4de3d0' },
  mars:        { dust: '#ffe0c8', warm: '255,150,90',  cool: '255,205,120', accent: '#ffab6e', accent2: '#ffd479' },
  observatory: { dust: '#5a6480', warm: '120,100,220', cool: '20,140,165',  accent: '#6d4fd4', accent2: '#0e8fa8' },
};

function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
  if (!m) return '';
  const n = parseInt(m[1], 16);
  return (n >> 16) + ',' + ((n >> 8) & 255) + ',' + (n & 255);
}

function accentColor() {
  return (state.palette && state.palette.accent) || ACCENT;
}

/* ---------- i18n: ru / en для видимых поверхностей UI ---------- */

const I18N = {
  ru: {
    digest_btn: 'дайджест', browse_btn: 'обзор', scan_btn: 'скан',
    search_ph: '⌕  поиск — /',
    keys_html: 'мышь — вращать · колесо — зум · клик — карточка · двойной клик — папка · <kbd>/</kbd> — поиск · <kbd>R</kbd> — рескан · <kbd>Esc</kbd> — сброс',
    st_alive: 'живой', st_abandoned: 'заброшен', st_broken: 'сломан', st_unknown: 'пусто',
    idle_word: 'простой',
    kick: 'проект', f_stack: 'стек', f_idle: 'простой', f_branch: 'ветка',
    f_deps: 'зависимости', f_todos: 'TODO', f_weight: 'вес на диске', f_readme: 'README',
    yes: 'есть', no: 'нет',
    b_folder: 'Папка', b_terminal: 'Терминал', b_run: 'Запустить', b_stop: 'Остановить',
    b_res: 'Воскресить', b_doctor: 'Диагностика', b_readme: 'Сгенерировать README',
    b_copy: 'Копировать путь', b_git: 'Создать git', clean_btn: 'снести',
    tag_ph: '+ тег',
    note_ph: 'заметка: что это, почему забросил, что доделать…',
    p_title: 'папка сканирования', p_mycomp: 'мой компьютер — выбери диск',
    p_reading: 'читаю…', p_none: 'подпапок не видно — можно сканировать эту или подняться выше',
    p_up: '↑ выше', p_scan: 'сканировать эту папку',
    d_title: 'дайджест · что изменилось',
    d_nothing: 'тишь да гладь — ничего не изменилось',
    d_born: 'родились', d_left: 'ушли',
    d_need2: 'нужен второй скан — сравнивать пока не с чем',
    d_projects: 'проектов', d_junk: 'мусора', d_secrets: 'секретов',
    rescan_pill: '↻ пересканировать', cosmos_on: '✦ космос: вкл', cosmos_off: '✦ космос: выкл',
    busy_scan: 'скан уже идёт — дай ему доработать', rescan_start: 'запускаю рескан…',
    feed_reading: 'читаю фид…', ready: 'готово: ', feed_from: 'фид от',
    fail_data: 'Не удалось получить данные: ', fail_server_hint: 'Сервер поднят командой `python -m butler ui`.',
    settings: 'настройки',
    set_theme: 'тема', th_darkmatter: 'Тёмная материя', th_deepspace: 'Глубокий космос',
    th_mars: 'Закат на Марсе', th_observatory: 'Обсерватория', th_custom: 'Свой стиль',
    set_lang: 'язык / language', set_colors: 'свой стиль: акцент, второй, фон, пыль',
    save_custom: 'сохранить свой стиль', set_gh: 'github',
    gh_token_ph: 'Personal Access Token с правами repo',
    gh_login: 'войти', gh_logout: 'выйти',
    gh_howto: 'Токен создаётся на github.com/settings/tokens (права repo). Хранится только у тебя.',
    gh_publish: 'Опубликовать на GitHub', gh_private: 'приватный',
    gh_settings: 'настройки репозитория', gh_release: 'Создать релиз',
    gh_tag_ph: 'тег, напр. v1.0.0', gh_name_ph: 'название релиза (опционально)',
    gh_body_ph: 'что в релизе', gh_desc_ph: 'описание репозитория', gh_save: 'сохранить',
    gh_open: 'открыть на GitHub', gh_no_git: 'нет git — сначала «Создать git»',
    gh_no_auth: 'вход через GitHub — в настройках (⚙)',
    runlog_run: 'лог запуска · ', runlog_done: 'процесс завершён (код ', runlog_quiet: 'пока тихо…',
    res_kick: 'воскрешение · ', kick_diag: 'диагностика', junk_kick: 'мусор на диске · ',
    hist: 'история score', hist_last: 'последние', hist_scans: 'сканов',
    hist_none: 'появится после второго скана', runlog_head_idle: 'диагностика',
  },
  en: {
    digest_btn: 'digest', browse_btn: 'browse', scan_btn: 'scan',
    search_ph: '⌕  search — /',
    keys_html: 'drag — orbit · wheel — zoom · click — card · double click — folder · <kbd>/</kbd> — search · <kbd>R</kbd> — rescan · <kbd>Esc</kbd> — reset',
    st_alive: 'alive', st_abandoned: 'abandoned', st_broken: 'broken', st_unknown: 'empty',
    idle_word: 'idle',
    kick: 'project', f_stack: 'stack', f_idle: 'idle', f_branch: 'branch',
    f_deps: 'deps', f_todos: 'TODOs', f_weight: 'disk weight', f_readme: 'README',
    yes: 'yes', no: 'none',
    b_folder: 'Folder', b_terminal: 'Terminal', b_run: 'Run', b_stop: 'Stop',
    b_res: 'Resurrect', b_doctor: 'Diagnose', b_readme: 'Generate README',
    b_copy: 'Copy path', b_git: 'Create git', clean_btn: 'purge',
    tag_ph: '+ tag',
    note_ph: 'note: what is this, why abandoned, what to finish…',
    p_title: 'scan folder', p_mycomp: 'my computer — pick a drive',
    p_reading: 'reading…', p_none: 'no subfolders visible — scan this one or go up',
    p_up: '↑ up', p_scan: 'scan this folder',
    d_title: 'digest · what changed',
    d_nothing: 'all quiet — nothing changed',
    d_born: 'born', d_left: 'gone',
    d_need2: 'need a second scan to compare',
    d_projects: 'projects', d_junk: 'junk', d_secrets: 'secrets',
    rescan_pill: '↻ rescan', cosmos_on: '✦ cosmos: on', cosmos_off: '✦ cosmos: off',
    busy_scan: 'scan already running — let it finish', rescan_start: 'starting rescan…',
    feed_reading: 'reading feed…', ready: 'ready: ', feed_from: 'feed from',
    fail_data: 'Failed to fetch data: ', fail_server_hint: 'server is started by `python -m butler ui`.',
    settings: 'settings',
    set_theme: 'theme', th_darkmatter: 'Dark matter', th_deepspace: 'Deep space',
    th_mars: 'Mars sunset', th_observatory: 'Observatory', th_custom: 'Custom',
    set_lang: 'язык / language', set_colors: 'custom: accent, secondary, background, dust',
    save_custom: 'save custom style', set_gh: 'github',
    gh_token_ph: 'Personal Access Token with repo scope',
    gh_login: 'sign in', gh_logout: 'sign out',
    gh_howto: 'Create a token at github.com/settings/tokens (repo scope). Stored locally only.',
    gh_publish: 'Publish to GitHub', gh_private: 'private',
    gh_settings: 'repo settings', gh_release: 'Create release',
    gh_tag_ph: 'tag, e.g. v1.0.0', gh_name_ph: 'release title (optional)',
    gh_body_ph: 'release notes', gh_desc_ph: 'repo description', gh_save: 'save',
    gh_open: 'open on GitHub', gh_no_git: 'no git — use «Create git» first',
    gh_no_auth: 'GitHub sign-in — in settings (⚙)',
    runlog_run: 'run log · ', runlog_done: 'process finished (code ', runlog_quiet: 'quiet so far…',
    res_kick: 'resurrect · ', kick_diag: 'diagnostics', junk_kick: 'junk on disk · ',
    hist: 'score history', hist_last: 'last', hist_scans: 'scans',
    hist_none: 'appears after second scan', runlog_head_idle: 'diagnostics',
  },
};

function t(key) {
  const d = I18N[state.lang] || I18N.ru;
  return d[key] !== undefined ? d[key] : (I18N.ru[key] !== undefined ? I18N.ru[key] : key);
}

function statusLabel(status) {
  return t('st_' + status);
}

function applyLang() {
  const pairs = [[ui.digestBtn, 'digest_btn'], [ui.browseBtn, 'browse_btn'],
                 [ui.rootApply, 'scan_btn']];
  pairs.forEach(([el, key]) => { if (el) el.textContent = t(key); });
  if (ui.search) ui.search.placeholder = t('search_ph');
  const keys = document.querySelector('.keys');
  if (keys) keys.innerHTML = t('keys_html');
  if (ui.setKick) ui.setKick.textContent = t('settings');
  const pk = document.getElementById('pickKick');
  if (pk) pk.textContent = t('p_title');
  const up = document.getElementById('pickUp');
  if (up) up.textContent = t('p_up');
  const ps = document.getElementById('pickScan');
  if (ps) ps.textContent = t('p_scan');
  const dk = document.querySelector('#digest .pkick');
  if (dk) dk.textContent = t('d_title');
}

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
  search: document.getElementById('searchInput'),
  digest: document.getElementById('digest'),
  digestMeta: document.getElementById('digestMeta'),
  digestBody: document.getElementById('digestBody'),
  digestClose: document.getElementById('digestClose'),
  digestBtn: document.getElementById('digestBtn'),
  settingsBtn: document.getElementById('settingsBtn'),
  settingsPanel: document.getElementById('settingsPanel'),
  settingsBody: document.getElementById('settingsBody'),
  setClose: document.getElementById('setClose'),
  setKick: document.getElementById('setKick'),
  setGhLine: document.getElementById('setGhLine'),
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
  picker.pathEl.textContent = path || t('p_mycomp');
  picker.list.innerHTML = '<div class="pempty">' + t('p_reading') + '</div>';
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
    empty.textContent = t('p_none');
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

/* ---------- поиск-затмение ---------- */

let searchDebounce = null;

ui.search.addEventListener('input', () => {
  state.query = ui.search.value.trim().toLowerCase();
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(contentSearch, 350);   // содержимое ищем с задержкой
  renderDock();
});
ui.search.addEventListener('keydown', (ev) => {
  ev.stopPropagation();                            // R и прочие хоткеи не стреляют в поиске
  if (ev.key === 'Escape') {
    ui.search.value = '';
    state.query = '';
    state.contentHits = new Set();
    renderDock();
    ui.search.blur();
  }
});

/* серверный поиск по зависимостям и README — то, чего не видно из фида */
async function contentSearch() {
  if (state.query.length < 3) { state.contentHits = new Set(); renderDock(); return; }
  try {
    const data = await api('/api/search?q=' + encodeURIComponent(state.query));
    state.contentHits = new Set((data.results || []).map((r) => r.path));
    const names = (data.results || []).map((r) => r.name);
    if (names.length) {
      say('по содержимому нашлось: ' + names.slice(0, 4).join(', ') +
          (names.length > 4 ? ' и ещё ' + (names.length - 4) : ''));
    }
    renderDock();
  } catch (err) { /* содержимое — бонус, молча живём без него */ }
}

/* ---------- дайджест изменений ---------- */

function digestOpen() { return ui.digest.classList.contains('open'); }

function openDigest() {
  ui.digest.classList.add('open');
  ui.digestBody.innerHTML = '<div class="pempty">читаю диф…</div>';
  api('/api/digest').then(renderDigest).catch((err) => {
    ui.digestBody.innerHTML = '<div class="pempty">' + esc(err.message) + '</div>';
  });
}

function closeDigest() { ui.digest.classList.remove('open'); }

function digestChips(names, cls) {
  if (!names || !names.length) return '';
  return '<div class="tagrow">' + names.map((n) =>
    '<span class="tagchip" style="border-color:' + cls + '55;background:' + cls + '14">' +
    esc(n) + '</span>').join('') + '</div>';
}

function renderDigest(data) {
  const d = data.diff || {};
  const human = humanBytes(data.junk_bytes || 0);
  ui.digestMeta.textContent = data.root + ' · ' + data.projects + ' ' + t('d_projects') + ' · ' +
    human + ' ' + t('d_junk') + ' · ' + data.secrets + ' ' + t('d_secrets') + ' · ' + data.todos + ' TODO';
  const rows = [];
  if (d.scans < 2) {
    rows.push('<div class="pempty">' + t('d_need2') + '</div>');
  } else {
    if (d.added && d.added.length) {
      rows.push('<div class="kick" style="margin-top:6px">' + t('d_born') + ' (' + d.added.length + ')</div>');
      rows.push(digestChips(d.added, '#7ef0b2'));
    }
    if (d.removed && d.removed.length) {
      rows.push('<div class="kick" style="margin-top:10px">' + t('d_left') + ' (' + d.removed.length + ')</div>');
      rows.push(digestChips(d.removed, '#ff7a90'));
    }
    (d.improved || []).forEach((it) => {
      rows.push('<div class="fact"><span>▲ ' + esc(it.name) + '</span><span style="color:var(--good)">' +
        it.from + ' → ' + it.to + ' (+' + it.delta + ')</span></div>');
    });
    (d.worsened || []).forEach((it) => {
      rows.push('<div class="fact"><span>▼ ' + esc(it.name) + '</span><span style="color:var(--bad)">' +
        it.from + ' → ' + it.to + ' (' + it.delta + ')</span></div>');
    });
    // пустые массивы в JS truthy — проверяем длины явно, иначе «тишь да гладь» никогда не покажется
    if (!((d.added && d.added.length) || (d.removed && d.removed.length) ||
          (d.improved && d.improved.length) || (d.worsened && d.worsened.length))) {
      rows.push('<div class="pempty">' + t('d_nothing') + '</div>');
    }
  }
  ui.digestBody.innerHTML = rows.join('');
}

ui.digestClose.addEventListener('click', closeDigest);
ui.digest.addEventListener('click', (ev) => { if (ev.target === ui.digest) closeDigest(); });
ui.digestBtn.addEventListener('click', openDigest);

/* ---------- панель настроек: темы, язык, свой стиль, GitHub ---------- */

const THEME_SWATCHES = {
  darkmatter: ['#010104', '#9d8cff', '#6ee7ff'],
  deepspace: ['#01030a', '#6ea8ff', '#4de3d0'],
  mars: ['#0a0402', '#ffab6e', '#ffd479'],
  observatory: ['#f4f2ec', '#6d4fd4', '#0e8fa8'],
  custom: ['#000000', '#ffffff', '#888888'],
};

function settingsOpen() { return ui.settingsPanel.classList.contains('open'); }

function openSettings() {
  ui.settingsPanel.classList.add('open');
  renderSettings();
}

function closeSettings() { ui.settingsPanel.classList.remove('open'); }

async function saveSettings(patch) {
  const next = Object.assign({}, state.settings, patch);
  try {
    state.settings = await api('/api/settings', next);
    applySettings(state.settings);
    return true;
  } catch (err) {
    fail('settings: ' + err.message);
    return false;
  }
}

function renderSettings() {
  const body = ui.settingsBody;
  body.innerHTML = '';
  const cur = state.settings.theme || 'darkmatter';
  const custom = state.settings.custom || {};

  const themeKick = document.createElement('div');
  themeKick.className = 'secKick';
  themeKick.style.borderTop = 'none';
  themeKick.style.paddingTop = '0';
  themeKick.textContent = t('set_theme');
  body.append(themeKick);

  const grid = document.createElement('div');
  grid.className = 'themeGrid';
  ['darkmatter', 'deepspace', 'mars', 'observatory', 'custom'].forEach((id) => {
    const card = document.createElement('div');
    card.className = 'themeCard' + (cur === id ? ' on' : '');
    const sw = THEME_SWATCHES[id];
    card.innerHTML = '<div class="swatch" style="background:linear-gradient(120deg,' +
      sw[0] + ' 38%,' + sw[1] + ' 39%,' + sw[1] + ' 62%,' + sw[2] + ' 63%)"></div>' +
      t('th_' + id);
    card.onclick = () => saveSettings({ theme: id }).then(() => renderSettings());
    grid.append(card);
  });
  body.append(grid);

  if (cur === 'custom') {
    const row = document.createElement('div');
    row.className = 'setrow';
    const label = document.createElement('label');
    label.textContent = t('set_colors');
    row.append(label);
    const defs = [['accent', custom.accent || '#9d8cff'], ['accent2', custom.accent2 || '#6ee7ff'],
                  ['bg', custom.bg || '#010104'], ['dust', custom.dust || '#cfd8ff']];
    const inputs = {};
    defs.forEach(([key, val]) => {
      const inp = document.createElement('input');
      inp.type = 'color';
      inp.className = 'colorInp';
      inp.value = val;
      inputs[key] = inp;
      row.append(inp);
    });
    const save = document.createElement('button');
    save.className = 'langBtn';
    save.textContent = t('save_custom');
    save.onclick = () => {
      const cc = {};
      Object.entries(inputs).forEach(([k, el]) => { cc[k] = el.value; });
      saveSettings({ custom: cc }).then(() => { renderSettings(); say('✓ ' + t('save_custom')); });
    };
    row.append(save);
    body.append(row);
  }

  const langKick = document.createElement('div');
  langKick.className = 'secKick';
  langKick.textContent = t('set_lang');
  body.append(langKick);
  const langRow = document.createElement('div');
  langRow.className = 'setrow';
  [['ru', 'Русский'], ['en', 'English']].forEach(([code, title]) => {
    const b = document.createElement('button');
    b.className = 'langBtn' + ((state.lang || 'ru') === code ? ' on' : '');
    b.textContent = title;
    b.onclick = () => saveSettings({ lang: code }).then(() => {
      renderLegend();
      renderDock();
      if (state.selected) renderPanel(state.selected);
      renderSettings();
    });
    langRow.append(b);
  });
  body.append(langRow);

  const ghKick = document.createElement('div');
  ghKick.className = 'secKick';
  ghKick.textContent = t('set_gh');
  body.append(ghKick);
  const ghBox = document.createElement('div');
  ghBox.id = 'ghAuthBox';
  body.append(ghBox);
  renderGhAuth(ghBox);
}

async function renderGhAuth(box) {
  box.innerHTML = '<div class="pempty">' + t('p_reading') + '</div>';
  let st = { authed: false };
  try { st = await api('/api/gh/status'); } catch (e) { /* нет сети — рисуем как есть */ }
  box.innerHTML = '';
  if (st.authed) {
    const line = document.createElement('div');
    line.className = 'ghline';
    if (st.avatar) {
      const img = document.createElement('img');
      img.src = st.avatar;
      img.alt = '';
      line.append(img);
    }
    const who = document.createElement('span');
    who.textContent = (st.name || st.login) + ' · @' + st.login;
    line.append(who);
    const out = document.createElement('button');
    out.className = 'langBtn';
    out.style.marginLeft = 'auto';
    out.textContent = t('gh_logout');
    out.onclick = async () => {
      await api('/api/gh/logout', {});
      renderGhAuth(box);
      say('GitHub: ' + t('gh_logout'));
    };
    line.append(out);
    box.append(line);
    return;
  }
  if (st.stale) {
    const warn = document.createElement('div');
    warn.className = 'pempty';
    warn.textContent = '⚠ ' + (st.error || '');
    box.append(warn);
  }
  const row = document.createElement('div');
  row.className = 'setrow';
  const inp = document.createElement('input');
  inp.className = 'searchbox';
  inp.style.width = '300px';
  inp.type = 'password';
  inp.placeholder = t('gh_token_ph');
  row.append(inp);
  const btn = document.createElement('button');
  btn.className = 'langBtn';
  btn.textContent = t('gh_login');
  btn.onclick = async () => {
    if (!inp.value.trim()) return;
    btn.disabled = true;
    try {
      const res = await api('/api/gh/login', { token: inp.value.trim() });
      say('GitHub: ' + res.login + ' ✓');
      renderGhAuth(box);
    } catch (err) {
      fail('GitHub: ' + err.message);
      btn.disabled = false;
    }
  };
  inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') btn.click(); });
  row.append(btn);
  box.append(row);
  const hint = document.createElement('div');
  hint.className = 'pempty';
  hint.style.textAlign = 'left';
  hint.style.padding = '6px 2px';
  hint.textContent = t('gh_howto');
  box.append(hint);
}

ui.setClose.addEventListener('click', closeSettings);
ui.settingsPanel.addEventListener('click', (ev) => { if (ev.target === ui.settingsPanel) closeSettings(); });
ui.settingsBtn.addEventListener('click', openSettings);

/* ---------- живой фид: фид сменился на диске — галактика обновляется сама ---------- */

setInterval(async () => {
  if (state.scanning || state.feed === null) return;
  try {
    const ver = await api('/api/feed-version');
    if (!state.feedMtime) { state.feedMtime = ver.mtime; return; }
    if (ver.mtime && ver.mtime !== state.feedMtime) {
      state.feedMtime = ver.mtime;
      await loadFeed();
      say('фид обновился (' + new Date(ver.mtime * 1000).toLocaleTimeString() + ')');
    }
  } catch (e) { /* сервер спит — попробуем в следующий тик */ }
}, 6000);

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
  if (state.scanning) { say(t('busy_scan')); return; }
  try {
    applySettings(await api('/api/settings'));
  } catch (e) { /* дефолтная тема уже применена */ }
  say(rescan ? t('rescan_start') : t('feed_reading'));
  try {
    if (rescan) {
      const res = await api('/api/scan', {});
      if (res.scanning) { waitScan(res.root); return; }
    }
    state.feed = await api('/galaxy.json');
  } catch (err) {
    fail(t('fail_data') + err.message + '. ' + t('fail_server_hint'));
    return;
  }
  refreshUI();
  loadRoots();
  say(t('ready') + state.feed.projects.length + ', ' + t('feed_from') + ' ' + state.feed.generated_at_iso);
}

/* ---------- настройки: тема, язык, свой стиль ---------- */

function applySettings(s) {
  state.settings = s = s || {};
  const theme = s.theme || 'darkmatter';
  const custom = s.custom || {};
  state.lang = s.lang || 'ru';
  if (theme === 'custom') {
    document.body.dataset.theme = 'darkmatter';
    const rootStyle = document.documentElement.style;
    if (custom.accent) rootStyle.setProperty('--accent', custom.accent);
    if (custom.accent2) rootStyle.setProperty('--accent2', custom.accent2);
    if (custom.bg) rootStyle.setProperty('--bg', custom.bg);
    state.palette = {
      dust: custom.dust || '#cfd8ff',
      warm: hexToRgb(custom.accent) || CANVAS_THEMES.darkmatter.warm,
      cool: hexToRgb(custom.accent2) || CANVAS_THEMES.darkmatter.cool,
      accent: custom.accent || CANVAS_THEMES.darkmatter.accent,
      accent2: custom.accent2 || CANVAS_THEMES.darkmatter.accent2,
    };
  } else {
    document.body.dataset.theme = theme;
    const rootStyle = document.documentElement.style;
    ['--accent', '--accent2', '--bg'].forEach((v) => rootStyle.removeProperty(v));
    state.palette = CANVAS_THEMES[theme] || CANVAS_THEMES.darkmatter;
  }
  applyLang();
  resize();                                        // фон перестраивается в палитре темы
}

function refreshUI() {
  state.bornAt = performance.now();                  // звёзды разгораются каскадом
  buildStars();
  spawnCosmicEvents();
  renderTop();
  renderLegend();
  renderDock(true);                              // карточки-папки влетают каскадом
}

/* события из диффа сканов: сверхновые (резко поправились) и рождения (новые проекты) */
function spawnCosmicEvents() {
  state.fx = [];
  if (!Object.keys(state.prev).length) return;       // первый скан — без драмы
  state.stars.forEach((star) => {
    const prev = state.prev[star.node.path];
    if (prev === undefined) {
      if (star.node.score > 0) {
        state.fx.push({ star, kind: 'birth', born: performance.now() + star.index * 50 });
      }
    } else if (star.node.score - prev >= 12) {
      state.fx.push({ star, kind: 'nova', born: performance.now() + 400 });
    }
  });
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
  document.body.classList.add('scanning');           // пульс: статус и вордмарк дышат
  say('сканирую ' + root + ' — большим папкам нужно время, галактика обновится сама');
  pollScan((st) => {
    state.scanning = false;
    ui.rootApply.disabled = false;
    document.body.classList.remove('scanning');
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
  if (res.scanning) { state.warpT0 = performance.now(); waitScan(res.root); return; }
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
  state.prev = state.feed.prev || {};
  state.meta = state.feed.meta || {};
}

/* совпадение с поиском: имя, стек или попадание по содержимому */
function matchQ(star) {
  const q = state.query;
  if (!q) return true;
  return state.contentHits.has(star.node.path) ||
         star.node.name.toLowerCase().includes(q) ||
         (star.node.stacks || []).join(' ').toLowerCase().includes(q);
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
    row.title = 'двойной клик — курс на кластер';
    row.innerHTML = '<i style="background:' + (STACK_COLORS[stack] || '#888') + '"></i>' +
      esc(stack) + ' ' + count;
    row.ondblclick = () => {
      const pos = state.feed.clusters[stack];
      if (pos) {
        flyTo({ x: pos[0] * SPREAD, y: pos[1] * SPREAD, z: pos[2] * SPREAD });
        say('курс на кластер ' + stack);
      }
    };
    stacks.append(row);
  });
  ui.legend.append(stacks);

  const sep = document.createElement('span');
  sep.className = 'sep';
  ui.legend.append(sep);

  const pills = document.createElement('div');
  pills.className = 'grp';

  // теги пользователя: клик — фильтр галактики по тегу
  const tagUniverse = new Set();
  Object.values(state.meta).forEach((m) => (m.tags || []).forEach((t) => tagUniverse.add(t)));
  if (tagUniverse.size) {
    [...tagUniverse].sort().forEach((tag) => {
      const pill = document.createElement('button');
      pill.className = 'pill';
      const on = [...state.tagFilter].some((t) => t.toLowerCase() === tag.toLowerCase());
      pill.setAttribute('aria-pressed', String(on));
      pill.innerHTML = '<i style="background:var(--accent)"></i>' + esc(tag);
      pill.onclick = () => {
        const hit = [...state.tagFilter].find((t) => t.toLowerCase() === tag.toLowerCase());
        if (hit) state.tagFilter.delete(hit); else state.tagFilter.add(tag);
        renderLegend();
        renderDock();
      };
      pills.append(pill);
    });
  }

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
  rescan.textContent = t('rescan_pill');
  rescan.onclick = () => init(true);
  pills.append(rescan);

  const cosmosBtn = document.createElement('button');
  cosmosBtn.className = 'pill ghost';
  cosmosBtn.setAttribute('aria-pressed', String(!motionOff()));
  cosmosBtn.title = 'анимации космоса: дрейф, дыхание, параллакс от курсора';
  cosmosBtn.textContent = motionOff() ? t('cosmos_off') : t('cosmos_on');
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
  if (node.status === 'abandoned') return t('idle_word') + ' ' + node.idle_days + 'd';
  return statusLabel(node.status);
}

function renderDock(stagger) {
  ui.dock.innerHTML = '';
  const visibleStars = state.stars.filter(visible).sort((a, b) => b.node.score - a.node.score);
  if (!visibleStars.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'никого не видно — включи статусы в легенде выше или просканируй папку';
    ui.dock.append(empty);
    return;
  }
  visibleStars.forEach((star, i) => {
    const n = star.node;
    const item = document.createElement('div');
    item.className = 'item' + (star === state.selected ? ' active' : '') +
      (!matchQ(star) ? ' dim' : '');
    item.title = n.path;
    if (stagger) {
      item.classList.add('enter');
      item.style.animationDelay = Math.min(i * 26, 620) + 'ms';
    }
    // папка окрашена цветом стека; на hover «приоткрывается» (CSS)
    item.innerHTML =
      '<div class="nm" style="--stack:' + star.color + '">' +
      '<svg class="fold" viewBox="0 0 16 16" aria-hidden="true">' +
      '<path class="f-back" d="M1.5 4.6c0-.9.7-1.6 1.6-1.6h3l1.4 1.5h5.4c.9 0 1.6.7 1.6 1.6v.6H1.5z"/>' +
      '<path class="f-front" d="M1.5 6.9h13l-1.4 5c-.15.62-.7 1.1-1.35 1.1H4.25c-.65 0-1.2-.48-1.35-1.1z"/>' +
      '</svg><span>' + esc(n.name) + '</span></div>' +
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
  const pal = state.palette || CANVAS_THEMES.darkmatter;

  b.fillStyle = pal.dust;
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
    bokeh(rnd() * W, rnd() * H, rnd() * 42 + 14, pal.warm, rnd() * .12 + .04);
  }
  for (let i = 0; i < 18; i++) {
    bokeh(rnd() * W, rnd() * H, rnd() * 32 + 10, pal.cool, rnd() * .10 + .03);
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

function visible(star) {
  if (state.hidden.has(star.node.status)) return false;
  if (state.tagFilter.size) {
    const tags = (state.meta[star.node.path] || {}).tags || [];
    if (!tags.some((t) => state.tagFilter.has(t.toLowerCase()))) return false;
  }
  return true;
}

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

function drawBlackHole(star, pr, r, now) {
  const R = Math.max(6, r * 2.4);
  // гравитационный профиль: чернильное ядро, вокруг — искривлённый свет
  const g = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, R * 2.2);
  g.addColorStop(0, 'rgba(0,0,0,1)');
  g.addColorStop(0.42, 'rgba(2,2,6,.96)');
  g.addColorStop(0.55, 'rgba(30,22,60,.55)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(pr.x, pr.y, R * 2.2, 0, Math.PI * 2);
  ctx.fill();
  // фотонное кольцо
  ctx.strokeStyle = 'rgba(255,214,150,.7)';
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.arc(pr.x, pr.y, R * 0.62, 0, Math.PI * 2);
  ctx.stroke();
  // аккреционные дуги — встречное вращение, наклонный эллипс
  for (let i = 0; i < 3; i++) {
    const a0 = (now / (650 + i * 240)) * (i % 2 ? -1 : 1) + i * 2.1;
    ctx.strokeStyle = hexA(i === 1 ? '#ffd479' : '#9d8cff', 0.55 - i * 0.12);
    ctx.lineWidth = 1.5 - i * 0.3;
    ctx.beginPath();
    ctx.ellipse(pr.x, pr.y, R * (0.95 + i * 0.28), R * (0.5 + i * 0.14), 0.35, a0, a0 + Math.PI * 0.9);
    ctx.stroke();
  }
}

function drawStars(order) {
  const now = performance.now();
  order.forEach((item) => {
    const star = item.star, pr = item.pr;
    // дыхание размера в противофазе к мерцанию — звезда не точка, а живой сгусток
    const breathe = state.cosmosStill ? 1 : 1 + 0.05 * Math.sin(now / 1500 + star.index * 1.93);
    const r = Math.max(1.4, star.size * pr.s * 1.3 * breathe);
    const alive = star.node.status === 'alive';
    star.screen = { x: pr.x, y: pr.y, r: r + 6, s: pr.s };

    // разгорание после загрузки фида: каждая звезда зажигается со своей задержкой
    const raw = Math.max(0, Math.min(1, (now - state.bornAt - star.index * 14) / 300));
    const appear = raw * (2 - raw);
    if (appear <= 0) return;
    const on = matchQ(star);                       // поиск-затмение: чужие уходят в тень
    ctx.globalAlpha = appear * (state.query && !on ? 0.07 : 1);

    // мерцание всей галактики: у каждой звезды своя фаза — небо живое
    const tw = state.cosmosStill ? 1 : 0.82 + 0.18 * Math.sin(now / 620 + star.index * 2.7);
    const isHover = star === state.hover && star !== state.selected;
    const hole = star.node.score < 30;             // мёртвое — в чёрную дыру

    if (hole) {
      drawBlackHole(star, pr, r, now);
    } else {
      const glowA = (alive ? 0.5 : 0.3) * tw * (isHover ? 1.7 : 1);
      const glowR = r * 6.5 * (isHover ? 1.3 : 1);
      const glow = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, glowR);
      glow.addColorStop(0, hexA(star.color, glowA));
      glow.addColorStop(0.35, hexA(star.color, glowA * 0.35));
      glow.addColorStop(1, hexA(star.color, 0));
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, glowR, 0, Math.PI * 2);
      ctx.fill();

      const core = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, r);
      core.addColorStop(0, '#ffffff');
      core.addColorStop(1, star.color);
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r, 0, Math.PI * 2);
      ctx.fill();

      // дифракционные лучи у трёх самых ярких — как на снимках телескопа
      if (!state.cosmosStill && state.rank.get(star.index) < 3) {
        const L = r * 4.6;
        ctx.strokeStyle = hexA(star.color, 0.30 * tw);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pr.x - L, pr.y); ctx.lineTo(pr.x + L, pr.y);
        ctx.moveTo(pr.x, pr.y - L); ctx.lineTo(pr.x, pr.y + L);
        ctx.stroke();
      }
    }

    if (isHover) {
      ctx.strokeStyle = 'rgba(242, 244, 255, .45)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r + 6, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (!hole && (star.node.status === 'broken' || star.node.status === 'abandoned')) {
      let ringR = r + 4.5, ringA = 0.55;
      if (star.node.status === 'broken' && !state.cosmosStill) {
        // пульсар: сломанный проект мигает, как маяк бедствия
        const pulse = Math.pow(Math.max(0, Math.sin(now / 900 + star.index * 1.3)), 8);
        ringR += pulse * 7;
        ringA += pulse * 0.35;
      }
      ctx.strokeStyle = hexA(star.status, ringA);
      ctx.lineWidth = 1.1;
      if (star.node.status === 'broken') ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, ringR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (star === state.selected) {
      // расходящиеся рипплы — «сигнал» от выбранной звезды
      for (let k = 0; k < 2; k++) {
        const t = ((now / 1500) + k * 0.5) % 1;
        ctx.strokeStyle = 'rgba(200, 212, 255,' + ((1 - t) * 0.5).toFixed(3) + ')';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(pr.x, pr.y, r + 7 + t * 30, 0, Math.PI * 2);
        ctx.stroke();
      }
      // орбитальные спутники по псевдо-3D эллипсу — звезда «с системой»
      for (let i = 0; i < 3; i++) {
        const a = now / 950 + i * (Math.PI * 2 / 3);
        ctx.fillStyle = 'rgba(226, 232, 255, .9)';
        ctx.beginPath();
        ctx.arc(pr.x + Math.cos(a) * (r + 15), pr.y + Math.sin(a) * (r + 15) * 0.42, 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
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
    // TODO-рой: каждый маркер — янтарная частица на орбите своей звезды
    const todoDots = Math.min(star.node.todos || 0, 10);
    if (todoDots > 0 && pr.s > 0.45 && !state.cosmosStill) {
      ctx.fillStyle = 'rgba(255,212,121,' + (0.5 * appear).toFixed(3) + ')';
      const orbitBase = 1300 + (star.index % 5) * 170;
      for (let i = 0; i < todoDots; i++) {
        const a = now / orbitBase + i * (Math.PI * 2 / todoDots);
        const orbR = r + 9 + (i % 3) * 3.5;
        ctx.beginPath();
        ctx.arc(pr.x + Math.cos(a) * orbR, pr.y + Math.sin(a) * orbR * 0.45, 1.1, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    if (labelWorthy(star) && pr.s > 0.35) {
      const sel = star === state.selected || star === state.hover;
      ctx.font = (sel ? '450 ' : '300 ') + '11px "Segoe UI", sans-serif';
      ctx.fillStyle = sel ? 'rgba(242,244,255,.9)' : 'rgba(242,244,255,.55)';
      ctx.textAlign = 'center';
      ctx.fillText(star.node.name + ' · ' + star.node.score, pr.x, pr.y - r - 9);
    }
    ctx.globalAlpha = 1;
  });
}

function labelWorthy(star) {
  if (state.query) return matchQ(star);            // в поиске подписаны только совпадения
  return star === state.hover || star === state.selected || state.rank.get(star.index) < TOP_LABELS;
}

let projected = [];
function draw() {
  if (!state.feed) return;
  state.cosmosStill = motionOff();
  stepFly();                                                  // плавный полёт камеры к цели
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
  drawFx(performance.now());
  drawWarp(performance.now());
}

/* сверхновые и рождения из диффа сканов */
function drawFx(now) {
  for (let i = state.fx.length - 1; i >= 0; i--) {
    const fx = state.fx[i];
    const life = fx.kind === 'nova' ? 2000 : 1100;
    const t = (now - fx.born) / life;
    if (t >= 1) { state.fx.splice(i, 1); continue; }
    if (t < 0) continue;                           // ещё не родилось — ждёт своей задержки
    const pr = project(fx.star.x, fx.star.y, fx.star.z);
    const r = Math.max(4, fx.star.size * pr.s * 2);
    const k = 1 - t;
    if (fx.kind === 'nova') {
      if (t < 0.25) {                              // короткая белая вспышка в начале
        const g = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, r * 10);
        g.addColorStop(0, 'rgba(255,255,255,' + (0.85 * (1 - t / 0.25)).toFixed(3) + ')');
        g.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(pr.x, pr.y, r * 10, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.strokeStyle = 'rgba(222,232,255,' + (0.75 * k).toFixed(3) + ')';
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r * (1.5 + t * 9), 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeStyle = hexA(fx.star.color, 0.5 * k);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r * (1 + t * 6), 0, Math.PI * 2);
      ctx.stroke();
    } else {                                       // рождение: зелёный приветственный круг
      ctx.strokeStyle = hexA('#7ef0b2', 0.7 * k);
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r * (1 + t * 4), 0, Math.PI * 2);
      ctx.stroke();
    }
  }
}

/* гиперпространство при смене корня: разгон → вспышка → новая галактика разгорается */
function drawWarp(now) {
  if (!state.warpT0) return;
  const t = (now - state.warpT0) / 950;
  if (t >= 1) { state.warpT0 = 0; return; }
  const k = t < 0.55 ? t / 0.55 : (1 - t) / 0.45;
  const cx = state.width / 2, cy = state.height / 2;
  const maxR = Math.hypot(cx, cy);
  for (let i = 0; i < 90; i++) {
    const a = i * 2.399 + Math.floor(i / 7) * 0.11;
    const r0 = ((i * 53) % 100) / 100 * maxR * 0.9 + 30;
    const len = 50 + 260 * t * (0.4 + (i % 5) * 0.15);
    const x1 = cx + Math.cos(a) * r0, y1 = cy + Math.sin(a) * r0;
    const x2 = cx + Math.cos(a) * (r0 + len), y2 = cy + Math.sin(a) * (r0 + len);
    ctx.strokeStyle = 'rgba(205,220,255,' + (0.5 * k).toFixed(3) + ')';
    ctx.lineWidth = 1.1 + (i % 3) * 0.4;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }
  ctx.fillStyle = 'rgba(238,242,255,' + (0.5 * Math.pow(k, 3)).toFixed(3) + ')';
  ctx.fillRect(0, 0, state.width, state.height);
}

/* ---------- полёт камеры к выбранной папке ---------- */

function angleNear(current, target) {
  let t = target;
  while (t - current > Math.PI) t -= Math.PI * 2;
  while (current - t > Math.PI) t += Math.PI * 2;
  return t;
}

function flyTo(star) {
  const yaw = Math.atan2(star.x, star.z);
  const z1 = star.x * Math.sin(yaw) + star.z * Math.cos(yaw);
  const pitch = Math.atan2(star.y, Math.max(1e-6, z1));
  state.fly = {
    yaw: angleNear(state.yaw, yaw),
    pitch: Math.max(-1.25, Math.min(1.25, angleNear(state.pitch, pitch))),
    zoom: Math.max(state.zoom, 1.5),
  };
}

function stepFly() {
  if (!state.fly) return;
  const f = state.fly;
  let settled = true;
  for (const k of ['yaw', 'pitch', 'zoom']) {
    const d = f[k] - state[k];
    if (Math.abs(d) > 0.0008) { state[k] += d * 0.075; settled = false; }
    else state[k] = f[k];
  }
  if (settled) state.fly = null;
}

/* ---------- инерция и ленивый дрейф камеры ---------- */

function stepCameraIdle() {
  if (drag) return;
  if (state.spin) {
    // юзер «бросил» галактику — катимся по инерции и плавно гасим
    state.yaw += state.spin.yaw;
    state.pitch = Math.max(-1.25, Math.min(1.25, state.pitch + state.spin.pitch));
    state.spin.yaw *= 0.93;
    state.spin.pitch *= 0.93;
    if (Math.abs(state.spin.yaw) < 1e-5 && Math.abs(state.spin.pitch) < 1e-5) state.spin = null;
    return;
  }
  if (!state.cosmosStill && !state.fly && !state.selected &&
      performance.now() - state.lastAction > 12000) {
    state.yaw += 0.00038;                        // вселенная вращается и без нас
  }
}

function pick(mx, my) {
  let best = null, bestDist = Infinity;
  for (const star of state.stars) {
    if (!visible(star) || !matchQ(star)) continue;  // в поиске кликаем только по совпадениям
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
    '<small>' + esc(n.stack) + ' · ' + statusLabel(n.status) + ' · ' +
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
  flyTo(star);                                   // камера сама доезжает до папки
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
    '<polyline points="' + poly + '" fill="none" stroke="' + accentColor() + '" stroke-width="1.6"/>' +
    '</svg><div class="fact" style="border-bottom:0"><span>' + t('hist') + '</span>' +
    '<span>' + t('hist_last') + ' ' + pts.length + ' ' + t('hist_scans') + '</span></div>';
}

async function loadHistory(star) {
  const box = document.getElementById('sparkBox');
  if (!box) return;
  try {
    const data = await api('/api/history?path=' + encodeURIComponent(star.node.path));
    box.innerHTML = sparkline(data.history) ||
      '<div class="fact" style="border-bottom:0"><span>' + t('hist') + '</span>' +
      '<span>' + t('hist_none') + '</span></div>';
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
    const rows = data.checks.map((c) => {
      const mark = c.ok === null ? '<span style="color:#ffd479">◐</span>'
        : (c.ok ? '<span style="color:var(--good)">✓</span>'
                : '<span style="color:var(--bad)">✗</span>');
      return '<div class="doctorrow"><span>' + mark + ' ' + esc(c.check) + '</span>' +
             '<span>' + esc(c.detail || '') + '</span></div>';
    }).join('');
    if (out) out.innerHTML = '<div class="kick" style="margin-top:14px">' + t('kick_diag') + '</div>' + rows;
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
  const meta = state.meta[n.path] || { tags: [], note: '' };
  const penalties = (n.penalties || []).map((p) => '<li>' + esc(p.why) + ' (' + p.points + ')</li>').join('');
  const bonuses = (n.bonuses || []).map((b) => '<li>+' + b.points + ' ' + esc(b.why) + '</li>').join('');

  const junk = n.junk_bytes || 0;
  const diskHtml = junk > 0
    ? '<div class="kick" style="margin-top:14px">' + t('junk_kick') + esc(humanBytes(junk)) + '</div>' +
      (n.junk_parts || []).map((p) =>
        '<div class="junkrow"><span>' + esc(p.name) + '</span>' +
        '<span class="bytes">' + esc(humanBytes(p.bytes)) + '</span>' +
        '<button data-clean="' + esc(p.name) + '">' + t('clean_btn') + '</button></div>').join('')
    : '';
  const warns = [];
  if (n.secrets > 0) warns.push('найдено секретов: ' + n.secrets);
  if (n.env_leak_risk) warns.push('.env не в .gitignore');
  const warnHtml = warns.length
    ? '<div class="warnbox">⚠ ' + warns.map(esc).join(' · ') + '</div>' : '';

  ui.detail.innerHTML =
    '<button class="close" title="закрыть (Esc)">×</button>' +
    '<div class="kick">' + t('kick') + '</div>' +
    '<h2>' + esc(n.name) + '</h2>' +
    '<div class="path">' + esc(n.path) + '</div>' +
    '<div class="scoreline"><span class="big">' + n.score + '</span>' +
    '<span class="of">/ 100</span>' +
    '<span class="badge st-' + n.status + '" style="border-color:' + star.status + '55;color:' + star.status + '">' +
    esc(statusLabel(n.status)) + '</span></div>' +
    '<div class="meter"><i style="width:' + Math.max(2, n.score) + '%;background:linear-gradient(90deg,' +
    accentColor() + ',' + star.status + ')"></i></div>' +
    '<div class="facts">' +
    fact(t('f_stack'), n.stacks.join(', ') || '—') +
    fact(t('f_idle'), n.idle_days + ' ' + pluralDays(n.idle_days)) +
    fact(t('f_branch'), n.branch || '—') +
    fact(t('f_deps'), String(n.deps)) +
    fact(t('f_todos'), String(n.todos)) +
    fact(t('f_weight'), humanBytes(n.total_bytes)) +
    fact(t('f_readme'), n.has_readme ? t('yes') : t('no')) +
    '</div>' +
    '<div class="tagrow" id="tagRow"></div>' +
    '<textarea class="notebox" id="noteBox" maxlength="2000" ' +
    'placeholder="' + t('note_ph') + '">' + esc(meta.note) + '</textarea>' +
    warnHtml +
    (penalties ? '<ul class="why">' + penalties + '</ul>' : '') +
    (bonuses ? '<ul class="why bonus">' + bonuses + '</ul>' : '') +
    diskHtml +
    '<div id="sparkBox"></div>' +
    '<div class="acts">' +
    '<div class="abtn main" data-open="code">VS Code</div>' +
    '<div class="abtn" data-open="explorer">' + t('b_folder') + '</div>' +
    '<div class="abtn" data-open="terminal">' + t('b_terminal') + '</div>' +
    '<div class="abtn" id="runBtn">' + t('b_run') + '</div>' +
    '<div class="abtn" id="resurrectBtn" title="venv / npm install / .env.example">' + t('b_res') + '</div>' +
    '<div class="abtn" id="doctorBtn">' + t('b_doctor') + '</div>' +
    (n.has_git ? '' : '<div class="abtn" id="gitBtn">' + t('b_git') + '</div>') +
    (n.has_readme ? '' : '<div class="abtn" id="readmeBtn">' + t('b_readme') + '</div>') +
    '<div class="abtn" data-copy="path">' + t('b_copy') + '</div>' +
    '<div id="ghBox"></div>' +
    '</div>' +
    '<div id="runBox"></div><div id="resBox"></div><div id="doctorOut"></div>';

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
  const readmeBtn = ui.detail.querySelector('#readmeBtn');
  if (readmeBtn) readmeBtn.onclick = async () => {
    readmeBtn.classList.add('disabled');
    try {
      const res = await api('/api/readme', { path: n.path });
      if (res.written) {
        say('README.md сгенерирован — теперь своими словами');
        await init(true);
        const again = state.byName[star.node.name];
        if (again) select(again);
      } else {
        say(res.reason || 'README не понадобился');
        readmeBtn.classList.remove('disabled');
      }
    } catch (err) {
      fail('README не сгенерировался: ' + err.message);
      readmeBtn.classList.remove('disabled');
    }
  };

  renderTags(star, meta);
  wireNote(star);
  wireRun(star);
  wireResurrect(star);
  renderGhBox(star);

  loadHistory(star);
}

/* ---------- теги и заметка ---------- */

function renderTags(star, meta) {
  const row = ui.detail.querySelector('#tagRow');
  if (!row) return;
  row.innerHTML = '';
  meta.tags.forEach((tag) => {
    const chip = document.createElement('span');
    chip.className = 'tagchip';
    chip.textContent = tag + ' ';
    const x = document.createElement('i');
    x.textContent = '×';
    x.title = 'убрать тег';
    x.onclick = () => saveTags(star, meta.tags.filter((t) => t !== tag));
    chip.append(x);
    row.append(chip);
  });
  const input = document.createElement('input');
  input.className = 'taginput';
  input.placeholder = t('tag_ph');
  input.maxLength = 24;
  input.onkeydown = (ev) => {
    if (ev.key === 'Enter' && input.value.trim()) {
      saveTags(star, meta.tags.concat([input.value.trim()]));
      ev.stopPropagation();
    }
  };
  row.append(input);
}

async function saveTags(star, tags) {
  try {
    const res = await api('/api/tags', { path: star.node.path, tags });
    state.meta[star.node.path] = { ...(state.meta[star.node.path] || {}), tags: res.tags };
    renderTags(star, state.meta[star.node.path]);
    renderLegend();                                  // фильтры по тегам обновились
    renderDock();
    say('теги: ' + (res.tags.join(', ') || '—'));
  } catch (err) {
    fail('теги не сохранились: ' + err.message);
  }
}

function wireNote(star) {
  const box = ui.detail.querySelector('#noteBox');
  if (!box) return;
  box.addEventListener('keydown', (ev) => ev.stopPropagation());
  box.addEventListener('change', async () => {
    try {
      await api('/api/note', { path: star.node.path, note: box.value });
      state.meta[star.node.path] = { ...(state.meta[star.node.path] || {}), note: box.value };
      say('заметка сохранена');
    } catch (err) {
      fail('заметка не сохранилась: ' + err.message);
    }
  });
}

/* ---------- Run в один клик ---------- */

let runPoll = null;

function wireRun(star) {
  const btn = ui.detail.querySelector('#runBtn');
  if (!btn) return;
  api('/api/run-status?path=' + encodeURIComponent(star.node.path)).then((st) => {
    if (!ui.detail.querySelector('#runBtn')) return;   // карточку уже перерисовали
    if (st.running) {
      btn.textContent = 'Остановить';
      btn.classList.add('going');
      btn.onclick = async () => {
        await api('/api/run-stop', { path: star.node.path });
        wireRun(star);
      };
      renderRunLog(st.node.path, st);
      startRunPoll(star.node.path);
    } else {
      btn.textContent = 'Запустить';
      btn.classList.remove('going');
      btn.onclick = async () => {
        btn.classList.add('disabled');
        try {
          const res = await api('/api/run', { path: star.node.path, confirm: true });
          say('запущено: ' + (res.cmd || []).join(' ') + ' (pid ' + res.pid + ')');
          wireRun(star);
        } catch (err) {
          fail('Не запустилось: ' + err.message);
        } finally {
          btn.classList.remove('disabled');
        }
      };
      if (st.log && st.log.length) renderRunLog(st.node.path, st);
      stopRunPoll();
    }
  }).catch(() => {});
}

function renderRunLog(path, st) {
  const box = ui.detail.querySelector('#runBox');
  if (!box) return;
  const head = '<div class="kick" style="margin-top:14px">' +
    (st.running ? t('runlog_run') + (st.cmd || []).join(' ') : t('runlog_done') +
      (st.exit === null ? '?' : st.exit) + ')') + '</div>';
  const lines = (st.log || []).map((l) => esc(l)).join('\n');
  box.innerHTML = head + '<div class="runlog">' + (lines || t('runlog_quiet')) + '</div>';
  box.querySelector('.runlog').scrollTop = 1e9;
}

function startRunPoll(path) {
  stopRunPoll();
  runPoll = setInterval(async () => {
    if (!ui.detail.classList.contains('open')) { stopRunPoll(); return; }
    try {
      const st = await api('/api/run-status?path=' + encodeURIComponent(path));
      renderRunLog(path, st);
      if (!st.running) { stopRunPoll(); wireRun(state.selected || { node: { path } }); }
    } catch (e) { /* жить дальше */ }
  }, 1500);
}

function stopRunPoll() {
  if (runPoll) { clearInterval(runPoll); runPoll = null; }
}

/* ---------- Resurrect ---------- */

function wireResurrect(star) {
  const btn = ui.detail.querySelector('#resurrectBtn');
  if (!btn) return;
  btn.onclick = async () => {
    if (!window.confirm('Воскресить «' + star.node.name + '»? Это создаст .venv/npm install ' +
        'и сгенерирует .env.example (если его нет). Код не трогается.')) return;
    btn.classList.add('disabled');
    try {
      await api('/api/resurrect', { path: star.node.path, confirm: true });
      pollResurrect(star);
    } catch (err) {
      fail('Не воскресилось: ' + err.message);
      btn.classList.remove('disabled');
    }
  };
  // если воскрешение уже идёт — подхватываем лог
  api('/api/resurrect-status?path=' + encodeURIComponent(star.node.path)).then((st) => {
    if (st.running) {
      btn.classList.add('disabled');
      renderResLog(st);
      pollResurrect(star);
    }
  }).catch(() => {});
}

function renderResLog(st) {
  const box = ui.detail.querySelector('#resBox');
  if (!box) return;
  const lines = (st.log || []).map((l) => esc(l)).join('\n');
  box.innerHTML = '<div class="kick" style="margin-top:14px">' + t('res_kick') +
    esc(st.stage || '') + (st.running ? '…' : '') + '</div>' +
    '<div class="runlog">' + (lines || '…') + '</div>';
  box.querySelector('.runlog').scrollTop = 1e9;
}

function pollResurrect(star) {
  const timer = setInterval(async () => {
    if (!ui.detail.classList.contains('open')) { clearInterval(timer); return; }
    try {
      const st = await api('/api/resurrect-status?path=' + encodeURIComponent(star.node.path));
      renderResLog(st);
      if (!st.running) {
        clearInterval(timer);
        const btn = ui.detail.querySelector('#resurrectBtn');
        if (btn) btn.classList.remove('disabled');
        if (st.error) { fail(st.error); return; }
        say('воскрешение готово — перезапускаю скан');
        await init(true);
        const again = state.byName[star.node.name];
        if (again) select(again);
      }
    } catch (e) { /* ждём дальше */ }
  }, 1500);
}

function pluralDays(days) {
  const d = Math.abs(days) % 100;
  const d1 = d % 10;
  if (d > 10 && d < 20) return 'дней';
  if (d1 > 1 && d1 < 5) return 'дня';
  if (d1 === 1) return 'день';
  return 'дней';
}

/* ---------- GitHub в карточке: публикация, приватность, настройки, релизы ---------- */

function ghLine(text, cls) {
  const div = document.createElement('div');
  div.className = 'ghline' + (cls ? ' ' + cls : '');
  div.innerHTML = text;
  return div;
}

function ghSwitch(labelText, checked, onChange) {
  const wrap = document.createElement('label');
  wrap.className = 'ghline';
  wrap.style.cursor = 'pointer';
  const sw = document.createElement('span');
  sw.className = 'switch';
  const inp = document.createElement('input');
  inp.type = 'checkbox';
  inp.checked = !!checked;
  const knob = document.createElement('i');
  sw.append(inp, knob);
  const txt = document.createElement('span');
  txt.textContent = labelText;
  inp.addEventListener('change', () => onChange(inp.checked));
  wrap.append(sw, txt);
  return { wrap, inp };
}

async function renderGhBox(star) {
  const box = ui.detail.querySelector('#ghBox');
  if (!box) return;
  box.innerHTML = '<div class="kick" style="margin-top:16px">GitHub</div>' +
    '<div class="pempty">' + t('p_reading') + '</div>';
  let info;
  try {
    info = await api('/api/gh/repo?path=' + encodeURIComponent(star.node.path));
  } catch (err) {
    box.innerHTML = '<div class="kick" style="margin-top:16px">GitHub</div>' +
      '<div class="pempty">' + esc(err.message) + '</div>';
    return;
  }
  box.innerHTML = '<div class="kick" style="margin-top:16px">GitHub</div>';
  if (!info.has_git) return;                     // нет git — кнопка «Создать git» уже рядом

  if (!info.authed) {
    const row = ghLine(esc(t('gh_no_auth')));
    const btn = document.createElement('button');
    btn.className = 'langBtn';
    btn.textContent = t('settings');
    btn.onclick = openSettings;
    row.append(btn);
    box.append(row);
    return;
  }

  if (!info.owner_repo) {
    // публикация: имя репо + приватность
    const row = document.createElement('div');
    row.className = 'setrow';
    const nameInp = document.createElement('input');
    nameInp.className = 'searchbox';
    nameInp.style.width = '200px';
    nameInp.value = star.node.name;
    row.append(nameInp);
    const priv = ghSwitch(t('gh_private'), true, () => {});
    priv.inp.id = 'ghPrivateChk';
    row.append(priv.wrap);
    const go = document.createElement('button');
    go.className = 'langBtn';
    go.textContent = t('gh_publish');
    go.onclick = async () => {
      go.disabled = true;
      try {
        const res = await api('/api/gh/publish', {
          path: star.node.path, name: nameInp.value,
          private: document.getElementById('ghPrivateChk').checked,
        });
        say('GitHub: ' + res.repo + ' ✓');
        renderGhBox(star);
      } catch (err) {
        fail('GitHub: ' + err.message);
        go.disabled = false;
      }
    };
    row.append(go);
    box.append(row);
    return;
  }

  // репозиторий есть: ссылка, приватность, описание, issues/wiki
  const link = ghLine('• <a href="' + esc(info.html_url || ('https://github.com/' + info.owner_repo)) +
    '" target="_blank" style="color:var(--accent2)">' + esc(info.owner_repo) + '</a>' +
    (info.private ? ' · <span style="color:var(--warn)">private</span>' : ' · public'));
  box.append(link);

  const privRow = ghSwitch(t('gh_private'), !!info.private, (on) => {
    api('/api/gh/repo-settings', { path: star.node.path, private: on })
      .then(() => say('GitHub: ' + (on ? 'private' : 'public') + ' ✓'))
      .catch((err) => fail('GitHub: ' + err.message));
  });
  box.append(privRow.wrap);

  const issues = ghSwitch('issues', info.has_issues !== false, (on) => {
    api('/api/gh/repo-settings', { path: star.node.path, has_issues: on })
      .then(() => say('issues: ' + (on ? 'on' : 'off')))
      .catch((err) => fail('GitHub: ' + err.message));
  });
  box.append(issues.wrap);

  const wiki = ghSwitch('wiki', info.has_wiki !== false, (on) => {
    api('/api/gh/repo-settings', { path: star.node.path, has_wiki: on })
      .then(() => say('wiki: ' + (on ? 'on' : 'off')))
      .catch((err) => fail('GitHub: ' + err.message));
  });
  box.append(wiki.wrap);

  const descRow = document.createElement('div');
  descRow.className = 'setrow';
  const descInp = document.createElement('input');
  descInp.className = 'searchbox';
  descInp.style.width = '220px';
  descInp.placeholder = t('gh_desc_ph');
  descInp.value = info.description || '';
  descRow.append(descInp);
  const descBtn = document.createElement('button');
  descBtn.className = 'langBtn';
  descBtn.textContent = t('gh_save');
  descBtn.onclick = () => {
    api('/api/gh/repo-settings', { path: star.node.path, description: descInp.value })
      .then(() => say('description ✓'))
      .catch((err) => fail('GitHub: ' + err.message));
  };
  descRow.append(descBtn);
  box.append(descRow);

  // релизы
  const relKick = document.createElement('div');
  relKick.className = 'secKick';
  relKick.style.borderTop = 'none';
  relKick.style.paddingTop = '6px';
  relKick.textContent = t('gh_release');
  box.append(relKick);
  const relRow = document.createElement('div');
  relRow.className = 'setrow';
  const tagInp = document.createElement('input');
  tagInp.className = 'searchbox';
  tagInp.style.width = '120px';
  tagInp.placeholder = t('gh_tag_ph');
  relRow.append(tagInp);
  const nameInp = document.createElement('input');
  nameInp.className = 'searchbox';
  nameInp.style.width = '170px';
  nameInp.placeholder = t('gh_name_ph');
  relRow.append(nameInp);
  const relBtn = document.createElement('button');
  relBtn.className = 'langBtn';
  relBtn.textContent = t('gh_release');
  relBtn.onclick = async () => {
    if (!tagInp.value.trim()) { say(t('gh_tag_ph')); return; }
    relBtn.disabled = true;
    try {
      const res = await api('/api/gh/release', {
        path: star.node.path, tag: tagInp.value.trim(),
        name: nameInp.value.trim(), body: '', target: info.default_branch || '',
      });
      say('release ' + res.tag + ' ✓');
      if (res.url) window.open(res.url, '_blank');
      relBtn.disabled = false;
    } catch (err) {
      fail('GitHub: ' + err.message);
      relBtn.disabled = false;
    }
  };
  relRow.append(relBtn);
  box.append(relRow);
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
  state.lastAction = performance.now();
  state.spin = null;                             // новый бросок начинается с чистого листа
  drag = { x: ev.clientX, y: ev.clientY, moved: false };
  state.fly = null;                              // юзер рулит камерой сам — полёт отменяем
  canvas.classList.add('dragging');
  canvas.setPointerCapture(ev.pointerId);
});

canvas.addEventListener('pointermove', (ev) => {
  state.lastAction = performance.now();
  if (drag) {
    const dx = ev.clientX - drag.x;
    const dy = ev.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    state.yaw += dx * 0.006;
    state.pitch = Math.max(-1.25, Math.min(1.25, state.pitch + dy * 0.006));
    state.spin = { yaw: dx * 0.006, pitch: dy * 0.006 };     // последний вектор — в инерцию
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
  state.lastAction = performance.now();
  state.zoom = Math.max(0.35, Math.min(3.5, state.zoom * Math.exp(-ev.deltaY * 0.0012)));
}, { passive: false });

window.addEventListener('keydown', (ev) => {
  if (ev.target === ui.rootInput || ev.target === ui.search) return;
  state.lastAction = performance.now();
  if (ev.key === '/') {                            // мгновенный фокус на поиск
    ev.preventDefault();
    ui.search.focus();
    return;
  }
  if (ev.key === 'Escape') {
    if (pickerOpen()) { closePicker(); return; }
    if (digestOpen()) { closeDigest(); return; }
    if (settingsOpen()) { closeSettings(); return; }
    state.fly = { yaw: 0.6, pitch: -0.34, zoom: 1 };   // домой — плавно, а не телепортом
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
  stepCameraIdle();
  draw();
  requestAnimationFrame(loop);
}

resize();
init(false);
requestAnimationFrame(loop);
