// ============================================================
// Study Python for Finance — Web Shell controller
// ============================================================

const $  = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

// ---------- State -------------------------------------------------------
const state = {
  view: 'dashboard',
  chapters: [],
  progress: {},
  testSets: [],
  testResults: [],
  // Current chapter session
  currentChapter: null,      // entry from chapters list
  currentDetail:  null,      // full chapter detail (from bridge.chapterDetailJson)
  currentPageIndex: 0,
  currentAnswers: {},        // page index -> {blank_id: value}
  showingResult: false,      // overlay flag
  lastResult: null,
  // Test session
  test: null,
  // { id, title, phase, questions, qIndex, answers: [{}...], outcomes: ['pass'|'fail'|'skip'|null...],
  //   timerEnd, timerInterval, startedAt, paused }
  // Last activity (used by the dashboard Continue card)
  lastActivity: null,  // { chapterId, lastPageIndex, openedAt }
};

const LAST_ACTIVITY_KEY = 'studypy.lastActivity';
function loadLastActivity() {
  try {
    const raw = localStorage.getItem(LAST_ACTIVITY_KEY);
    if (raw) state.lastActivity = JSON.parse(raw);
  } catch (e) {}
}
function saveLastActivity() {
  try {
    if (state.lastActivity) localStorage.setItem(LAST_ACTIVITY_KEY, JSON.stringify(state.lastActivity));
    else localStorage.removeItem(LAST_ACTIVITY_KEY);
  } catch (e) {}
}
function bumpLastActivity(chapterId, pageIndex) {
  state.lastActivity = { chapterId, lastPageIndex: pageIndex, openedAt: Date.now() };
  saveLastActivity();
}
function clearLastActivity() {
  state.lastActivity = null;
  saveLastActivity();
}

let bridge = null;

// ---------- Theme management -------------------------------------------
const THEME_KEY = 'studypy.theme';

function getStoredTheme() {
  try { return localStorage.getItem(THEME_KEY) || 'dark'; }
  catch (e) { return 'dark'; }
}
function setStoredTheme(value) {
  try { localStorage.setItem(THEME_KEY, value); } catch (e) {}
}
function applyTheme(name) {
  const body = document.body;
  // Resolve "system" → dark/light using prefers-color-scheme
  let resolved = name;
  if (name === 'system') {
    const mql = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)');
    resolved = (mql && mql.matches) ? 'light' : 'dark';
  }
  body.classList.remove('theme-dark', 'theme-light');
  body.classList.add(resolved === 'light' ? 'theme-light' : 'theme-dark');
  body.dataset.themeChoice = name;
}
function initTheme() {
  const choice = getStoredTheme();
  applyTheme(choice);
  // Keep "system" in sync with OS changes
  if (window.matchMedia) {
    const mql = window.matchMedia('(prefers-color-scheme: light)');
    if (mql.addEventListener) {
      mql.addEventListener('change', () => {
        if (document.body.dataset.themeChoice === 'system') applyTheme('system');
      });
    }
  }
}
function wireSettings() {
  const cur = getStoredTheme();
  document.querySelectorAll('input[name="theme"]').forEach(inp => {
    inp.checked = (inp.value === cur);
    inp.addEventListener('change', () => {
      if (inp.checked) {
        setStoredTheme(inp.value);
        applyTheme(inp.value);
      }
    });
  });

  // Danger zone: clear learning data
  const clearBtn = document.getElementById('btn-clear-data');
  const modal    = document.getElementById('confirm-clear');
  const cancel   = document.getElementById('confirm-clear-cancel');
  const ok       = document.getElementById('confirm-clear-ok');
  if (clearBtn && modal) {
    clearBtn.addEventListener('click', () => { modal.hidden = false; });
    cancel?.addEventListener('click', () => { modal.hidden = true;  });
    modal.querySelector('.modal__scrim')?.addEventListener('click', () => { modal.hidden = true; });
    ok?.addEventListener('click', () => {
      if (bridge && typeof bridge.clearLearningData === 'function') {
        bridge.clearLearningData((json) => {
          modal.hidden = true;
          let r;
          try { r = JSON.parse(json); } catch (e) { r = { ok: false }; }
          if (r.ok) {
            const c = r.removed || {};
            toast(`削除完了：章 ${c.chapter_progress || 0} 件 / 提出 ${c.submissions || 0} 件 / テスト ${c.test_results || 0} 件`);
            // Also clear the local "Continue" pointer so the dashboard
            // doesn't keep pointing at a chapter the user just cleared.
            clearLastActivity();
            // Re-pull bootstrap so all views reflect the empty state
            if (typeof bridge.bootstrapJson === 'function') {
              bridge.bootstrapJson((b) => {
                try {
                  const d = JSON.parse(b);
                  state.chapters    = d.chapters    || [];
                  state.progress    = d.progress    || {};
                  state.testSets    = d.testSets    || [];
                  state.testResults = d.testResults || [];
                  renderAll();
                } catch (e) { console.warn('bootstrap re-fetch failed', e); }
              });
            }
          } else {
            toast('削除に失敗しました：' + (r.error || 'unknown'));
          }
        });
      } else {
        modal.hidden = true;
        toast('Python アプリ経由で起動してください');
      }
    });
  }
}

// ---------- Utilities ---------------------------------------------------
function escapeHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Minimal Python-ish syntax highlighter for static code blocks. Highlights
// keywords, builtins, strings, numbers and comments. The result is HTML
// with class names matching styles.css.
const PY_KW = new Set([
  'False','None','True','and','as','assert','async','await','break','class',
  'continue','def','del','elif','else','except','finally','for','from','global',
  'if','import','in','is','lambda','nonlocal','not','or','pass','raise','return',
  'try','while','with','yield','match','case'
]);
const PY_BI = new Set([
  'print','len','range','sum','min','max','abs','round','int','float','str',
  'bool','list','dict','set','tuple','enumerate','zip','map','filter','sorted',
  'reversed','open','input','type','isinstance','hasattr','getattr','setattr',
  'iter','next','any','all'
]);
function highlightPy(src) {
  // Tokenize with one pass — keep it simple.
  const out = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    // Comment
    if (c === '#') {
      let j = i;
      while (j < src.length && src[j] !== '\n') j++;
      out.push(`<span class="cm">${escapeHtml(src.slice(i, j))}</span>`);
      i = j; continue;
    }
    // Triple-string or string
    if (c === '"' || c === "'") {
      const q = c;
      // triple?
      const triple = src[i+1] === q && src[i+2] === q;
      let j = i + (triple ? 3 : 1);
      while (j < src.length) {
        if (triple) {
          if (src[j] === q && src[j+1] === q && src[j+2] === q) { j += 3; break; }
          j++;
        } else {
          if (src[j] === '\\') { j += 2; continue; }
          if (src[j] === q) { j++; break; }
          if (src[j] === '\n') break;  // unterminated; bail out
          j++;
        }
      }
      out.push(`<span class="str">${escapeHtml(src.slice(i, j))}</span>`);
      i = j; continue;
    }
    // Number
    if (/[0-9]/.test(c)) {
      let j = i;
      while (j < src.length && /[0-9_.eE+\-jJ]/.test(src[j])) {
        // Crude: stop at + or - if not preceded by e/E
        if ((src[j] === '+' || src[j] === '-') && j > i && !/[eE]/.test(src[j-1])) break;
        j++;
      }
      out.push(`<span class="num">${escapeHtml(src.slice(i, j))}</span>`);
      i = j; continue;
    }
    // Identifier
    if (/[A-Za-z_]/.test(c)) {
      let j = i + 1;
      while (j < src.length && /[A-Za-z0-9_]/.test(src[j])) j++;
      const word = src.slice(i, j);
      if (PY_KW.has(word))      out.push(`<span class="kw">${word}</span>`);
      else if (PY_BI.has(word)) out.push(`<span class="bi">${word}</span>`);
      else if (src[j] === '(')  out.push(`<span class="fn">${word}</span>`);
      else                       out.push(escapeHtml(word));
      i = j; continue;
    }
    // Other
    out.push(escapeHtml(c));
    i++;
  }
  return out.join('');
}

// Render code with line-number gutter, optionally inserting <span class="blank"
// contenteditable="true"> in place of {{slot:id}} markers.
function renderCodeBlock(src, opts = {}) {
  const {
    fileLabel = 'sample.py',
    runnable = true,
    slots = null,           // {id: value} -> populates contenteditable blanks
  } = opts;
  // Replace {{slot:id}} markers with placeholders that survive highlighting.
  const slotMap = new Map();
  let counter = 0;
  const tokenized = src.replace(/\{\{slot:([A-Za-z_][\w]*)\}\}/g, (_, id) => {
    const token = `__SLOT_${counter}__`;
    slotMap.set(token, id);
    counter++;
    return token;
  });
  let highlighted = highlightPy(tokenized);
  // Restore slots as contenteditable blanks
  for (const [tok, id] of slotMap.entries()) {
    const initial = slots && id in slots ? slots[id] : '';
    const replacement = `<span class="blank" contenteditable="true" data-slot="${id}" spellcheck="false">${escapeHtml(initial)}</span>`;
    highlighted = highlighted.replace(tok, replacement);
  }
  // Add line numbers
  const lines = highlighted.split('\n');
  // Drop a trailing empty line if YAML had a final newline
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  const numbered = lines.map((ln, i) =>
    `<span class="ln">${i + 1}</span>${ln}`
  ).join('\n');
  const runBtn = runnable ? `<button class="editor__run">▷ RUN</button>` : '';
  return `
    <div class="editor">
      <div class="editor__head">
        <span class="name">${escapeHtml(fileLabel)}</span>
        <span class="spacer"></span>
        ${runBtn}
      </div>
      <div class="editor__body" spellcheck="false">${numbered}</div>
    </div>
    <div class="output"><div class="output__head">Output</div><span class="output__placeholder" style="color:var(--ink-5)">RUN を押すと実行されます。</span></div>
  `;
}

// Wait for the KaTeX CDN scripts (auto-render) to finish loading, then
// call cb. Retries every 60ms for up to 5 s; gives up silently after that.
function ensureKatex(cb) {
  if (typeof window.renderMathInElement === 'function') { cb(); return; }
  let n = 0;
  const t = setInterval(() => {
    if (typeof window.renderMathInElement === 'function') {
      clearInterval(t); cb();
    } else if (++n > 80) {
      clearInterval(t);  // give up
    }
  }, 60);
}

// Run KaTeX auto-render against a DOM element. Safe to call before the
// KaTeX CDN scripts have finished loading — it will wait and retry.
function applyMath(root) {
  if (!root) return;
  ensureKatex(() => {
    try {
      window.renderMathInElement(root, {
        delimiters: [
          { left: '$$', right: '$$', display: true  },
          { left: '$',  right: '$',  display: false },
          { left: '\\[', right: '\\]', display: true  },
          { left: '\\(', right: '\\)', display: false },
        ],
        throwOnError: false,
        strict: false,
      });
    } catch (e) {
      console.warn('KaTeX render failed', e);
    }
  });
}

// Render simple markdown subset: paragraphs, headings, bold, inline code,
// fenced code. Sufficient for our chapter content.
function renderMarkdown(md) {
  if (!md) return '';
  // Fenced code first (avoid mangling)
  const fenced = [];
  md = md.replace(/```([a-zA-Z]*)\n([\s\S]*?)```/g, (_, lang, body) => {
    fenced.push(body); return ` ${fenced.length - 1} `;
  });
  let html = escapeHtml(md);
  // Headings (## .. ###)
  html = html.replace(/^(#{2,3})\s+(.+)$/gm, (_, h, txt) => {
    const level = h.length === 2 ? 'h3' : 'h4';
    return `<${level}>${txt}</${level}>`;
  });
  // Bold **x**
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Italic *x*
  html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  // Inline code `x`
  html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  // Paragraphs (double newline)
  html = html.split(/\n{2,}/).map(p => {
    if (/^<(h\d|ul|ol|pre)/i.test(p.trim())) return p;
    return `<p>${p.replace(/\n/g, '<br/>')}</p>`;
  }).join('\n');
  // Restore fenced blocks with highlighting
  html = html.replace(/ (\d+) /g, (_, i) => {
    return `<pre class="md-code">${highlightPy(fenced[+i])}</pre>`;
  });
  return html;
}

// ---------- Renderers (dashboard / chapters / tests / history) ----------
const PHASE_LABEL = {
  A: 'Python 文法基礎', B: '数値ライブラリ', C: '金融計算 (CMA)',
  D: 'ML / DL',         E: '外部連携',       F: 'アプリ開発',
};

function renderDashboard() {
  // Continue target priority:
  //   1. Most recently opened chapter (lastActivity) — even if completed
  //   2. Any chapter currently in_progress
  //   3. First not-yet-done chapter
  //   4. The very first chapter
  let target = null;
  let lastIdx = null;
  const lastId = state.lastActivity?.chapterId;
  if (lastId) {
    target = state.chapters.find(c => c.id === lastId) || null;
    if (target) lastIdx = state.lastActivity.lastPageIndex || 0;
  }
  if (!target) {
    const inProg = state.chapters.find(c => state.progress[c.id]?.status === 'in_progress');
    const firstUndone = state.chapters.find(c => state.progress[c.id]?.status !== 'done');
    target = inProg || firstUndone || state.chapters[0];
    if (target) {
      lastIdx = state.progress[target.id]?.lastPageIndex ?? 0;
    }
  }
  if (target) {
    $('#cont-phase').textContent = `Phase ${target.phase}`;
    $('#cont-ch').textContent    = `Ch ${String(target.id).padStart(2,'0')}`;
    $('#cont-title').textContent = target.title;
    $('#cont-desc').textContent  = target.desc || '';
    const idx = (lastIdx ?? 0);
    $('#cont-page').textContent  = `ページ ${idx + 1} / ${target.pages}`;
    const hasActivity = !!state.lastActivity;
    $('#hero-sub').textContent   = hasActivity
      ? `前回の続きから、Phase ${target.phase} · ${target.title} を再開できます。`
      : `第 ${String(target.id).padStart(2,'0')} 章「${target.title}」から学習を始めましょう。`;
  }

  const phasesEl = $('#phases');
  phasesEl.innerHTML = '';
  for (const ph of ['A','B','C','D','E','F']) {
    const chs = state.chapters.filter(c => c.phase === ph);
    if (chs.length === 0) continue;
    const done = chs.filter(c => state.progress[c.id]?.status === 'done').length;
    const now  = chs.findIndex(c => state.progress[c.id]?.status === 'in_progress');
    const pct  = chs.length ? Math.round(done / chs.length * 100) : 0;
    const segs = chs.map((_, i) => {
      const cls = i < done ? 'is-done' : (i === now ? 'is-now' : '');
      return `<span class="phase__seg ${cls}"></span>`;
    }).join('');
    phasesEl.insertAdjacentHTML('beforeend', `
      <div class="phase">
        <div class="phase__badge">${ph}</div>
        <div class="phase__meta">
          <div class="phase__title">Phase ${ph} · ${escapeHtml(PHASE_LABEL[ph])}</div>
          <div class="phase__sub">${done} / ${chs.length} 章</div>
        </div>
        <div class="phase__bar">${segs}</div>
        <div class="phase__pct">${pct}%</div>
      </div>
    `);
  }

  const total  = state.chapters.length;
  const done   = Object.values(state.progress).filter(p => p.status === 'done').length;
  const inProg2 = Object.values(state.progress).filter(p => p.status === 'in_progress').length;
  const avg    = state.testResults.length
    ? Math.round(state.testResults.reduce((a, r) => a + r.score, 0) / state.testResults.length)
    : null;
  $('#s-total').textContent  = total;
  $('#s-done').textContent   = done;
  $('#s-inprog').textContent = inProg2;
  $('#s-avg').textContent    = avg !== null ? `${avg}%` : '—';

  const inProgHint = $('#s-inprog-hint');
  if (inProgHint) inProgHint.textContent = inProg2 === 0
    ? '未着手の章から始めましょう。' : `あと ${inProg2} 章で次のフェーズへ`;

  const avgHint = $('#s-avg-hint');
  if (avgHint) {
    if (avg !== null) {
      const passed = state.testResults.filter(r => r.pass).length;
      avgHint.textContent = `${state.testResults.length} 回 · ${passed} 回合格`;
    } else {
      avgHint.textContent = 'テストを受けるとここに平均点が表示されます。';
    }
  }

  // Spark chart with X-axis labels (latest 7 days of test scores).
  renderSparkChart();
}

// Build a 7-day score sparkline from state.testResults, drawing an axis
// underneath with day labels (Mon/Tue/...) so the chart is interpretable.
function renderSparkChart() {
  const host = $('#spark');
  const axis = $('#spark-axis');
  const note = $('#spark-note');
  if (!host || !axis) return;

  // Compute scores by day for the past 7 days.
  const today = new Date();
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    days.push(d);
  }
  const fmtKey = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const dayLabels = ['日','月','火','水','木','金','土'];
  const dayKeys = days.map(fmtKey);

  // Aggregate avg score per day.
  const scoresByDay = Object.fromEntries(dayKeys.map(k => [k, []]));
  for (const r of state.testResults) {
    if (scoresByDay[r.date] != null) scoresByDay[r.date].push(r.score);
  }
  const points = dayKeys.map(k => {
    const arr = scoresByDay[k];
    return arr.length ? Math.round(arr.reduce((a,b)=>a+b,0)/arr.length) : null;
  });

  const hasData = points.some(p => p !== null);

  if (!hasData) {
    host.innerHTML = `
      <div style="height:48px;display:flex;align-items:center;justify-content:center;
                  color:var(--ink-5);font-size:11px;border:1px dashed var(--line-2);">
        テスト履歴がありません — 受験するとここに 7 日間の推移が表示されます
      </div>
    `;
    axis.innerHTML = '';
    if (note) note.textContent = '最近 7 日 · データなし';
    return;
  }

  // Scale points (null → bottom of chart visually muted).
  const W = 220, H = 48, PAD = 4;
  const xs = dayKeys.map((_, i) => PAD + (W - 2*PAD) * i / (dayKeys.length - 1));
  const ys = points.map(p => p === null ? null : H - PAD - (H - 2*PAD) * (p / 100));
  const pathPts = xs.map((x, i) => ys[i] === null ? null : `${x.toFixed(1)},${ys[i].toFixed(1)}`)
                    .filter(Boolean).join(' ');
  const rail = `M ${PAD} ${H - PAD} L ${W - PAD} ${H - PAD}`;
  const gridLines = [0.25, 0.5, 0.75].map(t => {
    const y = PAD + (H - 2*PAD) * t;
    return `<line x1="${PAD}" y1="${y}" x2="${W - PAD}" y2="${y}"
              stroke="rgba(255,255,255,0.06)" stroke-width="1" stroke-dasharray="2 3"/>`;
  }).join('');
  const dots = xs.map((x, i) => ys[i] !== null
    ? `<circle cx="${x.toFixed(1)}" cy="${ys[i].toFixed(1)}" r="2" fill="#ef4444"/>`
    : '').join('');
  host.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="56">
      ${gridLines}
      <path d="${rail}" stroke="rgba(255,255,255,0.18)" stroke-width="1" fill="none"/>
      <polyline points="${pathPts}" fill="none" stroke="#ef4444" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>
      ${dots}
    </svg>
  `;

  // Axis labels (one per day)
  axis.innerHTML = days.map(d => {
    const isToday = fmtKey(d) === fmtKey(today);
    return `<span${isToday ? ' style="color:var(--ink-3);font-weight:700"' : ''}>${d.getMonth()+1}/${d.getDate()}（${dayLabels[d.getDay()]}）</span>`;
  }).join('');

  if (note) note.textContent = '最近 7 日 · 縦軸 0〜100%（テスト得点率）';
}

function renderChapters() {
  const grid = $('#chap-grid');
  grid.innerHTML = '';

  // Group by phase, preserving phase order A → F
  const phaseOrder = ['A','B','C','D','E','F'];
  const byPhase = {};
  for (const c of state.chapters) {
    (byPhase[c.phase] = byPhase[c.phase] || []).push(c);
  }

  for (const ph of phaseOrder) {
    const chs = byPhase[ph];
    if (!chs || !chs.length) continue;
    const done    = chs.filter(c => state.progress[c.id]?.status === 'done').length;
    const inProg  = chs.filter(c => state.progress[c.id]?.status === 'in_progress').length;

    const section = document.createElement('section');
    section.className = 'phase-section';
    section.innerHTML = `
      <header class="phase-section__head">
        <div class="phase-section__badge">${ph}</div>
        <div>
          <div class="phase-section__title">Phase ${ph}</div>
          <div class="phase-section__sub">${escapeHtml(PHASE_LABEL[ph] || '')}</div>
        </div>
        <div class="phase-section__count">${done} 完了 · ${inProg} 進行中 · 全 ${chs.length} 章</div>
      </header>
      <div class="chap-grid"></div>
    `;
    const subgrid = section.querySelector('.chap-grid');
    for (const c of chs) {
      const p = state.progress[c.id];
      const status = p?.status === 'done' ? 'done'
                   : p?.status === 'in_progress' ? 'now'
                   : 'todo';
      const statusLabel = { done: '完了', now: '進行中', todo: '未着手' }[status];
      const card = document.createElement('button');
      card.className = 'chap-card';
      card.dataset.status = status;
      card.innerHTML = `
        <div class="chap-card__head">
          <span class="num">Ch ${String(c.id).padStart(2,'0')}</span>
          <span>·</span>
          <span>Phase ${c.phase}</span>
        </div>
        <div class="chap-card__title">${escapeHtml(c.title)}</div>
        <div class="chap-card__desc">${escapeHtml(c.desc || '')}</div>
        <div class="chap-card__foot">
          <span class="chap-card__status" data-s="${status}">${statusLabel}</span>
          <span>${c.pages} ページ</span>
        </div>
      `;
      card.addEventListener('click', () => openChapter(c.id));
      subgrid.appendChild(card);
    }
    grid.appendChild(section);
  }
}

function renderTests() {
  const grid = $('#test-grid');
  grid.innerHTML = '';
  if (state.testSets.length === 0) {
    grid.innerHTML = `<div class="history__empty">テストセットがありません。</div>`;
    return;
  }
  for (const ts of state.testSets) {
    const card = document.createElement('div');
    card.className = 'test-card';
    card.innerHTML = `
      <div class="test-card__phase">Phase ${ts.phase}</div>
      <div class="test-card__title">${escapeHtml(ts.title)}</div>
      <div class="test-card__meta">
        <span class="tag">${ts.questions} 問</span>
        <span class="tag">${ts.minutes} 分</span>
        <span class="tag">合格 60%</span>
      </div>
      <button class="btn btn--primary">テストを開始</button>
    `;
    card.querySelector('button').addEventListener('click', () => startTest(ts.id));
    grid.appendChild(card);
  }
}

function renderHistory() {
  const list = $('#history-list');
  if (state.testResults.length === 0) {
    list.innerHTML = `<div class="history__empty">履歴はまだありません。最初のテストを受けてみましょう。</div>`;
    return;
  }
  list.innerHTML = '';
  for (const r of state.testResults) {
    const row = document.createElement('div');
    row.className = 'history__row';
    row.innerHTML = `
      <div class="history__date">${escapeHtml(r.date)}</div>
      <div class="history__title">${escapeHtml(r.title)}</div>
      <div class="history__score ${r.pass ? 'is-pass' : 'is-fail'}">${r.score}%</div>
      <div>${r.pass ? '<span class="chap-card__status" data-s="done">合格</span>' : '<span class="chap-card__status" data-s="todo">不合格</span>'}</div>
    `;
    list.appendChild(row);
  }
}

// ---------- Test runner ------------------------------------------------
function startTest(testId) {
  if (!bridge || typeof bridge.testSetDetailJson !== 'function') {
    toast('テストデータが読み込めません');
    return;
  }
  bridge.testSetDetailJson(testId, (json) => {
    let detail;
    try { detail = JSON.parse(json); }
    catch (e) { toast('テストデータの解析に失敗しました'); return; }
    if (detail.error) { toast(detail.error); return; }
    state.test = {
      id: detail.id,
      title: detail.title,
      phase: detail.phase,
      pass_score: detail.pass_score || 0.6,
      questions: detail.questions,
      qIndex: 0,
      answers: detail.questions.map(() => ({})),
      outcomes: detail.questions.map(() => null),
      timerEnd: Date.now() + (detail.time_limit_minutes || 30) * 60 * 1000,
      startedAt: new Date().toISOString(),
      timerInterval: null,
    };
    showView('test-runner');
    setCrumb('実力テスト', detail.title);
    $('#tr-phase').textContent = `Phase ${detail.phase}`;
    $('#tr-title').textContent = detail.title;
    paintTestQuestion();
    startTestTimer();
  });
}

function startTestTimer() {
  if (state.test?.timerInterval) clearInterval(state.test.timerInterval);
  const tick = () => {
    if (!state.test) return;
    const remain = state.test.timerEnd - Date.now();
    const wrap = $('#tr-timer');
    const valEl = wrap?.querySelector('.tr-timer__value');
    if (remain <= 0) {
      if (valEl) valEl.textContent = '00:00';
      clearInterval(state.test.timerInterval);
      finishTest(/*timeout*/true);
      return;
    }
    const total = Math.ceil(remain / 1000);
    const mm = String(Math.floor(total / 60)).padStart(2, '0');
    const ss = String(total % 60).padStart(2, '0');
    if (valEl) valEl.textContent = `${mm}:${ss}`;
    if (wrap) {
      wrap.classList.toggle('is-warn', remain < 5 * 60 * 1000 && remain >= 60 * 1000);
      wrap.classList.toggle('is-crit', remain < 60 * 1000);
    }
  };
  tick();
  state.test.timerInterval = setInterval(tick, 500);
}

function paintTestQuestion() {
  const t = state.test;
  if (!t) return;
  const q = t.questions[t.qIndex];
  $('#tr-counter').textContent = `Q ${t.qIndex + 1} / ${t.questions.length}`;
  $('#tr-prog').style.width = `${(t.qIndex) / t.questions.length * 100}%`;

  const body = $('#tr-body');
  body.innerHTML = '';
  const wrap = document.createElement('div');
  wrap.className = 'tq';
  const answers = t.answers[t.qIndex] || {};
  const editorHtml = renderCodeBlock(q.code_template, {
    fileLabel: `q${String(t.qIndex + 1).padStart(2,'0')}.py`,
    runnable: true,
    slots: answers,
  });
  wrap.innerHTML = `
    <div class="tq__intro">
      <span class="kicker"><span class="dot"></span> QUESTION ${t.qIndex + 1}</span>
      <h2 class="tq__title">${escapeHtml(q.title)}</h2>
      <div class="tq__prompt lesson__md">${renderMarkdown(q.prompt)}</div>
    </div>
    <div class="lesson__right">${editorHtml}</div>
  `;
  body.appendChild(wrap);
  wireEditors(body);
  applyMath(body);

  // Persist input changes into state.test.answers
  setTimeout(() => {
    body.querySelectorAll('.blank').forEach(el => {
      el.addEventListener('input', () => {
        if (!t.answers[t.qIndex]) t.answers[t.qIndex] = {};
        t.answers[t.qIndex][el.dataset.slot] = el.textContent;
      });
    });
  }, 0);
}

function gotoNextQuestion() {
  const t = state.test;
  if (!t) return;
  if (t.qIndex < t.questions.length - 1) {
    t.qIndex++;
    paintTestQuestion();
  } else {
    finishTest(false);
  }
}

function submitTestQuestion() {
  const t = state.test;
  if (!t) return;
  // Capture latest blank values
  const answers = t.answers[t.qIndex] || {};
  document.querySelectorAll('#tr-body .blank').forEach(el => {
    answers[el.dataset.slot] = el.textContent;
  });
  t.answers[t.qIndex] = answers;
  if (bridge && typeof bridge.gradeTestQuestion === 'function') {
    bridge.gradeTestQuestion(t.id, t.qIndex, JSON.stringify(answers), (json) => {
      let r;
      try { r = JSON.parse(json); } catch (e) { r = { ok: false }; }
      t.outcomes[t.qIndex] = r.ok && r.passed ? 'pass' : 'fail';
      gotoNextQuestion();
    });
  } else {
    // Fallback: simple equality
    const q = t.questions[t.qIndex];
    const ok = (q.blanks || []).every(b => (answers[b.id] || '').trim() === b.canonical_answer.trim());
    t.outcomes[t.qIndex] = ok ? 'pass' : 'fail';
    gotoNextQuestion();
  }
}

function skipTestQuestion() {
  const t = state.test;
  if (!t) return;
  t.outcomes[t.qIndex] = 'skip';
  gotoNextQuestion();
}

function abortTest() {
  if (!state.test) return;
  if (!confirm('テストを中止しますか？ 進捗は保存されません。')) return;
  clearInterval(state.test.timerInterval);
  state.test = null;
  showView('tests');
}

function finishTest(timeout) {
  const t = state.test;
  if (!t) return;
  clearInterval(t.timerInterval);

  const passed = t.outcomes.filter(o => o === 'pass').length;
  const total  = t.questions.length;
  const ratio  = passed / total;
  const isPass = ratio >= (t.pass_score || 0.6);
  const elapsedSec = Math.round((Date.now() - new Date(t.startedAt).getTime()) / 1000);

  // Persist to DB
  if (bridge && typeof bridge.recordTestResult === 'function') {
    const payload = {
      test_id: t.id,
      score: passed,
      total: total,
      seconds: elapsedSec,
      started_at: t.startedAt,
      perQuestion: t.outcomes.map((o, i) => ({ index: i, outcome: o || 'skip' })),
    };
    bridge.recordTestResult(JSON.stringify(payload), () => {
      if (typeof bridge.bootstrapJson === 'function') {
        bridge.bootstrapJson((j) => {
          try { const d = JSON.parse(j); state.testResults = d.testResults || state.testResults; renderHistory(); renderDashboard(); } catch (e) {}
        });
      }
    });
  }

  // Show result page
  showTestResult({ passed, total, ratio, isPass, elapsedSec, timeout, outcomes: t.outcomes.slice(), title: t.title, phase: t.phase, id: t.id });
  state.test = null;
}

function showTestResult(r) {
  showView('test-result');
  setCrumb('実力テスト', r.title, '結果');
  const minutes = Math.floor(r.elapsedSec / 60);
  const seconds = r.elapsedSec % 60;
  const grid = r.outcomes.map((o, i) => {
    const cls = o === 'pass' ? 'is-pass' : o === 'skip' ? 'is-skip' : 'is-fail';
    return `<div class="test-result__q ${cls}" title="Q${i+1}">${i + 1}</div>`;
  }).join('');

  $('#tr-result').innerHTML = `
    <span class="kicker"><span class="dot"></span> RESULT · Phase ${r.phase}</span>
    <h1 style="font-size:32px;font-weight:800;letter-spacing:-0.6px;">${escapeHtml(r.title)}</h1>
    <div class="test-result__verdict ${r.isPass ? 'is-pass' : 'is-fail'}">${r.isPass ? 'PASS' : 'FAIL'}</div>
    <div class="test-result__score">${r.passed} / ${r.total}　（${Math.round(r.ratio * 100)}%）</div>
    <div class="test-result__bar"><div class="test-result__bar-fill" style="width:${Math.round(r.ratio * 100)}%"></div></div>
    <p class="test-result__sub">
      所要時間 <strong>${minutes}分 ${seconds}秒</strong>${r.timeout ? '（タイムアウト）' : ''}　·
      合格基準 60%　·
      ${r.isPass ? '合格おめでとうございます！' : 'もう一度挑戦してみましょう。'}
    </p>
    <div class="test-result__qgrid">${grid}</div>
    <div class="test-result__actions">
      <button class="btn btn--secondary" data-act="back">テスト一覧へ戻る</button>
      <button class="btn btn--primary" data-act="retry">もう一度受ける</button>
    </div>
  `;
  setTimeout(() => {
    $('#tr-result [data-act="back"]')?.addEventListener('click', () => showView('tests'));
    $('#tr-result [data-act="retry"]')?.addEventListener('click', () => startTest(r.id));
  }, 0);
}

// ---------- Chapter detail view ----------------------------------------
function openChapter(id) {
  const ch = state.chapters.find(c => c.id === id);
  if (!ch) return;
  state.currentChapter   = ch;
  // Prefer the last activity position if it matches; otherwise fall back to repo progress
  const lastIdx = (state.lastActivity?.chapterId === id)
    ? state.lastActivity.lastPageIndex
    : (state.progress[id]?.lastPageIndex || 0);
  state.currentPageIndex = lastIdx;
  state.currentAnswers   = {};
  state.showingResult    = false;
  state.lastResult       = null;
  // Record activity + local progress (so dashboard reflects immediately)
  bumpLastActivity(id, state.currentPageIndex);
  if (!state.progress[id] || state.progress[id].status !== 'done') {
    state.progress[id] = { status: 'in_progress', lastPageIndex: state.currentPageIndex };
  }
  showView('chapter');
  setCrumb(`Phase ${ch.phase}`, `Ch ${String(ch.id).padStart(2,'0')}`, ch.title);
  $('#chap-phase').textContent = `Phase ${ch.phase}`;
  $('#chap-num').textContent   = `Ch ${String(ch.id).padStart(2,'0')}`;
  $('#chap-title').textContent = ch.title;

  // Load detail (real YAML data via bridge; otherwise empty)
  if (bridge && typeof bridge.chapterDetailJson === 'function') {
    bridge.chapterDetailJson(id, (json) => {
      try {
        state.currentDetail = JSON.parse(json);
        // If detail has different page count, clamp current page index
        const total = state.currentDetail.pages.length;
        if (state.currentPageIndex >= total) state.currentPageIndex = total - 1;
        paintChapterPage();
      } catch (e) {
        console.error('chapterDetailJson parse failed', e, json);
        renderPaintFallback();
      }
    });
  } else {
    renderPaintFallback();
  }
}

function renderPaintFallback() {
  // bridge unavailable — show a placeholder so the UI doesn't break.
  $('#chap-body').innerHTML = `
    <div class="lesson lesson--single">
      <div class="lesson__intro">
        <span class="kicker"><span class="dot"></span> Offline</span>
        <h2 class="lesson__title">章データを読み込めませんでした</h2>
        <p class="lesson__body">Python アプリ経由で起動してください。デモ単独ではコンテンツが読めません。</p>
      </div>
    </div>
  `;
  $('#chap-count').textContent = '— / —';
  $('#chap-prog').style.width = '0%';
}

function paintChapterPage() {
  const det = state.currentDetail;
  if (!det) { renderPaintFallback(); return; }
  const i = state.currentPageIndex;
  const total = det.pages.length;
  const page = det.pages[i];

  $('#chap-count').textContent = `${String(i+1).padStart(2,'0')} / ${String(total).padStart(2,'0')}`;
  $('#chap-prog').style.width = `${(i+1)/total*100}%`;

  // Dots (only if ≤ 16 pages)
  const dotsEl = $('#chap-dots');
  dotsEl.innerHTML = '';
  if (total <= 16) {
    for (let k = 0; k < total; k++) {
      const d = document.createElement('span');
      if (k <  i) d.className = 'is-done';
      if (k === i) d.className = 'is-now';
      dotsEl.appendChild(d);
    }
  }

  // Body
  const body = $('#chap-body');
  body.innerHTML = '';
  if (state.showingResult) {
    body.appendChild(makeResultOverlay(state.lastResult, page));
  } else if (page.kind === 'sample') {
    body.appendChild(makeSamplePage(page));
  } else if (page.kind === 'exercise') {
    body.appendChild(makeExercisePage(page, i));
  } else if (page.kind === 'reading') {
    body.appendChild(makeReadingPage(page, i));
  } else {
    body.innerHTML = `<div class="lesson"><div class="lesson__intro"><h2 class="lesson__title">未対応のページ種別: ${page.kind}</h2></div></div>`;
  }
  wireEditors(body);
  // Render any LaTeX math ($...$ / $$...$$) inside the lesson body
  applyMath(body);

  // Footer / mascot
  updateFooterAndMascot(page);
}

function setMascot(mood, speech) {
  const img = $('#mascot-img');
  if (img) {
    const m = ['normal','happy','sad','explain'].includes(mood) ? mood : 'explain';
    img.src = `../resources/stickman/${m}.png`;
    img.alt = m;
  }
  if (speech != null) $('#mascot-speech').textContent = speech;
}

function updateFooterAndMascot(page) {
  const total = state.currentDetail.pages.length;
  const i = state.currentPageIndex;

  if (state.showingResult) {
    $('#next-btn').textContent =
      (i === total - 1 && state.lastResult?.passed) ? '章を完了する'
      : (state.lastResult?.passed ? '次のページ' : 'もう一度');
    setMascot(
      state.lastResult?.passed ? 'happy' : 'sad',
      state.lastResult?.passed
        ? (state.lastResult.feedback?.correct || 'よくできました！')
        : (state.lastResult.feedback?.wrong_hint1 || 'もう少し！書き方を見直してみよう。')
    );
    return;
  }

  if (page.kind === 'sample') {
    $('#next-btn').textContent = (i === total - 1) ? '章を完了する' : '次へ';
    setMascot(page.stickman || 'explain', page.stickman_speech || 'サンプルを見てみよう。実行ボタンを押すと結果が見られるよ。');
  } else if (page.kind === 'exercise') {
    $('#next-btn').textContent = '提出';
    setMascot('explain', 'コードの空欄を埋めて提出ボタンを押そう。');
  } else if (page.kind === 'reading') {
    $('#next-btn').textContent = '提出';
    setMascot(page.stickman || 'explain', page.stickman_speech || 'コードを読んで、正しい選択肢を選ぼう。');
  }
}

// ---------- Page renderers (real data) ---------------------------------
function makeSamplePage(page) {
  const wrap = document.createElement('div');
  wrap.className = 'lesson';
  const editorHtml = page.sample_code
    ? renderCodeBlock(page.sample_code, { fileLabel: 'sample.py', runnable: !!page.runnable })
    : '';
  wrap.innerHTML = `
    <div class="lesson__intro">
      <span class="kicker"><span class="dot"></span> SAMPLE</span>
      <h2 class="lesson__title">${escapeHtml(page.title)}</h2>
      <div class="lesson__body lesson__md">${renderMarkdown(page.markdown)}</div>
      ${page.expected_output ? `<div class="lesson__note">期待される出力：<code style="font-family:'JetBrains Mono'">${escapeHtml(page.expected_output)}</code></div>` : ''}
    </div>
    <div class="lesson__right">${editorHtml}</div>
  `;
  return wrap;
}

function makeExercisePage(page, pageIndex) {
  const wrap = document.createElement('div');
  wrap.className = 'lesson';
  const answers = state.currentAnswers[pageIndex] || {};
  const editorHtml = renderCodeBlock(page.code_template, {
    fileLabel: 'exercise.py',
    runnable: true,
    slots: answers,
  });
  const hints = (page.hints || []).slice(0, 3);
  const hintsHtml = hints.length
    ? `
      <div class="hint-box" data-revealed="0" data-total="${hints.length}">
        <button class="hint-box__btn" type="button">
          <span class="hint-box__icon">💡</span>
          <span class="hint-box__label">ヒントを見る</span>
          <span class="hint-box__count">0 / ${hints.length}</span>
        </button>
        <ol class="hint-box__list">
          ${hints.map((h, i) => `<li class="hint-box__item" data-i="${i}" hidden><span class="hint-box__num">ヒント ${i + 1}</span><span class="hint-box__text">${escapeHtml(h)}</span></li>`).join('')}
        </ol>
      </div>
    `
    : '';
  wrap.innerHTML = `
    <div class="lesson__intro">
      <span class="kicker"><span class="dot"></span> EXERCISE</span>
      <h2 class="lesson__title">${escapeHtml(page.title)}</h2>
      <div class="lesson__body lesson__md">${renderMarkdown(page.prompt)}</div>
      ${hintsHtml}
    </div>
    <div class="lesson__right">${editorHtml}</div>
  `;
  // Persist user edits back to state on input
  setTimeout(() => {
    wrap.querySelectorAll('.blank').forEach(el => {
      el.addEventListener('input', () => {
        if (!state.currentAnswers[pageIndex]) state.currentAnswers[pageIndex] = {};
        state.currentAnswers[pageIndex][el.dataset.slot] = el.textContent;
      });
    });
    // Stepwise hint reveal: each click reveals one more hint
    const box = wrap.querySelector('.hint-box');
    if (box) {
      const btn  = box.querySelector('.hint-box__btn');
      const lbl  = box.querySelector('.hint-box__label');
      const cnt  = box.querySelector('.hint-box__count');
      const items = [...box.querySelectorAll('.hint-box__item')];
      const total = items.length;
      btn.addEventListener('click', () => {
        let rev = parseInt(box.dataset.revealed || '0', 10);
        if (rev >= total) return;
        items[rev].hidden = false;
        rev++;
        box.dataset.revealed = String(rev);
        cnt.textContent = `${rev} / ${total}`;
        if (rev === total) {
          lbl.textContent = 'すべてのヒントを表示しました';
          btn.disabled = true;
        } else {
          lbl.textContent = '次のヒントを見る';
        }
      });
    }
  }, 0);
  return wrap;
}

function makeReadingPage(page, pageIndex) {
  const wrap = document.createElement('div');
  wrap.className = 'lesson lesson--reading';
  const codeHtml = `
    <div class="editor">
      <div class="editor__head"><span class="name">${escapeHtml(page.code_file_label || 'snippet.py')}</span><span class="spacer"></span></div>
      <div class="editor__body">${page.code.split('\n').map((ln, i) =>
        `<span class="ln">${i + 1}</span>${highlightPy(ln)}`).join('\n')}</div>
    </div>
  `;
  const choicesHtml = page.choices.map((c, i) => `
    <label class="choice">
      <input type="radio" name="reading-${pageIndex}" value="${i}" />
      <span class="choice__dot"></span>
      <span class="choice__txt">${escapeHtml(c)}</span>
    </label>
  `).join('');
  wrap.innerHTML = `
    <div class="lesson__intro">
      <span class="kicker"><span class="dot"></span> READING</span>
      <h2 class="lesson__title">${escapeHtml(page.title)}</h2>
      <div class="lesson__body lesson__md">${renderMarkdown(page.prompt)}</div>
      <div class="choices">${choicesHtml}</div>
    </div>
    <div class="lesson__right">${codeHtml}</div>
  `;
  return wrap;
}

function makeResultOverlay(result, page) {
  const wrap = document.createElement('div');
  wrap.className = 'result';
  const passed = !!result?.passed;
  const sub = passed
    ? (result?.feedback?.correct || 'よくできました！次へ進みましょう。')
    : (result?.feedback?.wrong_hint1 || 'もう少し！書き方を見直してみましょう。');
  let detail = '';
  if (!passed && result?.stderr) {
    detail = `<pre class="result__detail">${escapeHtml(result.stderr.slice(0, 400))}</pre>`;
  } else if (!passed && result?.stdout) {
    detail = `<pre class="result__detail">出力: ${escapeHtml(result.stdout.slice(0, 400))}</pre>`;
  }
  if (result?.kind === 'reading' && !passed && result.explanation) {
    detail = `<div class="result__detail">${escapeHtml(result.explanation)}</div>`;
  }
  wrap.innerHTML = `
    <span class="kicker"><span class="dot"></span> RESULT</span>
    <div class="result__verdict ${passed ? 'is-correct' : 'is-incorrect'}">${passed ? 'Correct' : 'Incorrect'}</div>
    <p class="result__sub">${escapeHtml(sub)}</p>
    ${detail}
    <div class="result__actions">
      ${passed
        ? ''
        : `<button class="btn btn--secondary" data-act="retry">もう一度 <kbd class="kbd-on-btn">↺</kbd></button>`}
      <button class="btn btn--primary" data-act="next">${passed ? '次へ進む' : '次のページ'} <kbd class="kbd-on-btn">↵</kbd></button>
    </div>
  `;
  setTimeout(() => {
    wrap.querySelector('[data-act="retry"]')?.addEventListener('click', () => {
      state.showingResult = false;
      state.lastResult    = null;
      paintChapterPage();
    });
    wrap.querySelector('[data-act="next"]')?.addEventListener('click', advanceChapter);
  }, 0);
  return wrap;
}

// ---------- Submit / advance --------------------------------------------
function submitCurrentPage() {
  const det  = state.currentDetail;
  const i    = state.currentPageIndex;
  if (!det) return;
  const page = det.pages[i];

  if (page.kind === 'sample') {
    advanceChapter();
    return;
  }
  if (page.kind === 'exercise') {
    const answers = state.currentAnswers[i] || {};
    // Capture any contenteditable values that haven't fired input yet
    document.querySelectorAll('.blank').forEach(el => {
      answers[el.dataset.slot] = el.textContent;
    });
    state.currentAnswers[i] = answers;
    if (bridge && typeof bridge.gradeExercise === 'function') {
      bridge.gradeExercise(state.currentChapter.id, i,
        JSON.stringify(answers), (json) => {
          try {
            const r = JSON.parse(json);
            state.lastResult    = { ...r, kind: 'exercise', feedback: page.feedback };
            state.showingResult = true;
            paintChapterPage();
          } catch (e) { console.error('gradeExercise parse failed', e); }
        });
    } else {
      // Local fallback: simple string equality with canonical answers.
      const blanks = page.blanks || [];
      const ok = blanks.every(b => (answers[b.id] || '').trim() === b.canonical_answer.trim());
      state.lastResult    = { passed: ok, kind: 'exercise', feedback: page.feedback };
      state.showingResult = true;
      paintChapterPage();
    }
    return;
  }
  if (page.kind === 'reading') {
    const sel = document.querySelector(`input[name="reading-${i}"]:checked`);
    if (!sel) { toast('選択肢を選んでから提出してください'); return; }
    const selected = parseInt(sel.value, 10);
    if (bridge && typeof bridge.gradeReading === 'function') {
      bridge.gradeReading(state.currentChapter.id, i, selected, (json) => {
        try {
          const r = JSON.parse(json);
          state.lastResult    = { ...r, kind: 'reading' };
          state.showingResult = true;
          paintChapterPage();
        } catch (e) { console.error('gradeReading parse failed', e); }
      });
    } else {
      state.lastResult    = { passed: true, kind: 'reading' };
      state.showingResult = true;
      paintChapterPage();
    }
  }
}

function advanceChapter() {
  const det = state.currentDetail;
  if (!det) return;
  state.showingResult = false;
  state.lastResult    = null;
  if (state.currentPageIndex < det.pages.length - 1) {
    state.currentPageIndex++;
    // Update both transient and local-mirror state
    state.progress[state.currentChapter.id] = {
      status: 'in_progress', lastPageIndex: state.currentPageIndex,
    };
    bumpLastActivity(state.currentChapter.id, state.currentPageIndex);
    if (bridge && typeof bridge.saveProgress === 'function') {
      bridge.saveProgress(state.currentChapter.id, state.currentPageIndex, false);
    }
    paintChapterPage();
  } else {
    // Chapter complete
    if (bridge && typeof bridge.saveProgress === 'function') {
      bridge.saveProgress(state.currentChapter.id, det.pages.length - 1, true);
    }
    state.progress[state.currentChapter.id] = { status: 'done', lastPageIndex: det.pages.length - 1 };
    bumpLastActivity(state.currentChapter.id, det.pages.length - 1);
    renderChapters(); renderDashboard();
    showView('dashboard');
    toast(`第 ${String(state.currentChapter.id).padStart(2,'0')} 章「${state.currentChapter.title}」をクリアしました`);
  }
}

// ---------- RUN button --------------------------------------------------
function extractCode(editorBody) {
  let out = '';
  function walk(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      out += node.nodeValue;
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      if (node.classList && node.classList.contains('ln')) return;
      if (node.classList && node.classList.contains('blank')) {
        out += node.textContent;
        return;
      }
      for (const c of node.childNodes) walk(c);
    }
  }
  for (const c of editorBody.childNodes) walk(c);
  return out.replace(/ /g, ' ').replace(/\r/g, '');
}

function renderOutput(target, result) {
  if (!target) return;
  const status = result.status || 'ok';
  const stdout = escapeHtml(result.stdout || '');
  const stderr = escapeHtml(result.stderr || '');
  let body = '';
  if (status === 'ok') {
    body = stdout
      ? `<pre style="margin:0;font-family:inherit;white-space:pre-wrap;">${stdout}</pre>`
      : '<span style="color:var(--ink-5)">（値を返すコードでは標準出力が出ません）</span>';
  } else {
    const en = result.error_name ? `<strong style="color:var(--accent-h);">${escapeHtml(result.error_name)}</strong>` : '';
    const ev = result.error_value ? ` <span>${escapeHtml(result.error_value)}</span>` : '';
    const head = (en || ev) ? `<div style="margin-bottom:6px;font-size:12.5px;">${en}${ev}</div>` : '';
    const detail = stderr || stdout || 'エラーが発生しました';
    body = `${head}<pre style="margin:0;font-family:inherit;color:var(--accent-h);white-space:pre-wrap;max-height:240px;overflow:auto;font-size:11.5px;line-height:1.55;">${detail}</pre>`;
  }
  target.innerHTML = `<div class="output__head">${status === 'ok' ? 'Output' : 'Error'}</div>${body}`;
}

function runEditorCode(editor) {
  const body   = editor.querySelector('.editor__body');
  const output = editor.parentElement.querySelector('.output')
              || editor.closest('.lesson__right')?.querySelector('.output')
              || editor.closest('.lesson')?.querySelector('.output');
  const code = extractCode(body);
  if (output) {
    output.innerHTML = `<div class="output__head">Running…</div><span style="color:var(--ink-4)">実行中…</span>`;
  }
  if (bridge && typeof bridge.runCode === 'function') {
    try {
      bridge.runCode(code, (resultJson) => {
        let parsed;
        try { parsed = JSON.parse(resultJson); }
        catch (e) { parsed = { status: 'error', stdout: '', stderr: String(resultJson) }; }
        renderOutput(output, parsed);
      });
      return;
    } catch (e) {
      console.warn('bridge.runCode failed, fallback', e);
    }
  }
  renderOutput(output, fakeRun(code));
}

function fakeRun(code) {
  try {
    const printLines = [];
    const re = /print\s*\(\s*([^)]+?)\s*\)/g;
    let m;
    while ((m = re.exec(code)) !== null) printLines.push(m[1]);
    const loop = code.match(/for\s+(\w+)\s+in\s+\[([^\]]+)\]\s*:\s*[\s\S]*?print\(\s*\1\s*\)/);
    if (loop) {
      const items = loop[2].split(',').map(s => s.trim().replace(/^['"]|['"]$/g, ''));
      return { status: 'ok', stdout: items.join('\n') + '\n', stderr: '' };
    }
    if (printLines.length) {
      const out = printLines.map(arg => {
        const s = arg.trim();
        if (/^['"].*['"]$/.test(s)) return s.slice(1, -1);
        return s;
      }).join('\n');
      return { status: 'ok', stdout: out + '\n', stderr: '' };
    }
    return { status: 'ok', stdout: '', stderr: '' };
  } catch (e) {
    return { status: 'error', stdout: '', stderr: String(e) };
  }
}

function wireEditors(root) {
  root.querySelectorAll('.editor__run').forEach(btn => {
    btn.addEventListener('click', () => {
      const editor = btn.closest('.editor');
      if (!editor) return;
      btn.style.background = 'var(--accent)';
      btn.style.color = '#fff';
      btn.style.borderColor = 'var(--accent)';
      setTimeout(() => { btn.style.background = ''; btn.style.color = ''; btn.style.borderColor = ''; }, 220);
      runEditorCode(editor);
    });
  });
}

// ---------- View switching ----------------------------------------------
function showView(name) {
  state.view = name;
  $$('.view').forEach(v => v.classList.toggle('is-active', v.dataset.view === name));
  $$('.nav__item').forEach(b => b.classList.toggle('is-active', b.dataset.view === name));
  const el = $(`.view[data-view="${name}"]`);
  if (el) { el.style.animation = 'none'; void el.offsetWidth; el.style.animation = ''; }
  setCrumb(displayName(name));
  // Whenever the user lands back on the dashboard, refresh it so the
  // Continue card reflects the most recent activity.
  if (name === 'dashboard') renderDashboard();
}

function displayName(slug) {
  return {
    dashboard: 'ダッシュボード', chapters: '章を学ぶ', practice: '練習問題',
    tests: '実力テスト', history: '学習履歴', references: 'リファレンス',
    settings: '設定', chapter: '章', 'test-runner': '実力テスト',
    'test-result': 'テスト結果',
  }[slug] || slug;
}

function setCrumb(...parts) {
  const el = $('#crumbs');
  el.innerHTML = '';
  parts.forEach((p, i) => {
    const span = document.createElement('span');
    if (i === parts.length - 1) { span.className = 'crumbs__current'; span.textContent = p; }
    else                          { span.textContent = p; }
    el.appendChild(span);
    if (i < parts.length - 1) {
      const sep = document.createElement('span'); sep.className = 'sep'; sep.textContent = '›';
      el.appendChild(sep);
    }
  });
}

// ---------- Command palette --------------------------------------------
const palette = {
  el: () => $('#palette'),
  open() {
    this.el().hidden = false;
    $('#palette-input').value = '';
    $('#palette-input').focus();
    this.refresh('');
  },
  close() { this.el().hidden = true; },
  toggle() { this.el().hidden ? this.open() : this.close(); },
  selectedIdx: 0,
  rows: [],
  buildActions() {
    const acts = [
      { id: 'nav.dashboard', group: 'ナビゲート', glyph: '◇', title: 'ダッシュボードを開く', sub: 'Continue & 進捗', kbd: ['Ctrl','1'], run: () => showView('dashboard') },
      { id: 'nav.chapters',  group: 'ナビゲート', glyph: '▤', title: '章一覧を開く',         sub: 'Phase A〜F',       kbd: ['Ctrl','2'], run: () => showView('chapters') },
      { id: 'nav.tests',     group: 'ナビゲート', glyph: '✓', title: '実力テスト',           sub: 'Phase 別 10 問',    kbd: ['Ctrl','4'], run: () => showView('tests') },
      { id: 'nav.history',   group: 'ナビゲート', glyph: '≡', title: '学習履歴',             sub: '過去のスコア',      kbd: ['Ctrl','5'], run: () => showView('history') },
      { id: 'resume',        group: 'ナビゲート', glyph: '▶', title: 'つづきから再開',       sub: '最後の位置から',    kbd: ['Ctrl','R'], run: () => {
          const inProg = state.chapters.find(c => state.progress[c.id]?.status === 'in_progress');
          if (inProg) openChapter(inProg.id);
        }},
      { id: 'ui.references', group: 'ヘルプ', glyph: '✎', title: 'リファレンス早見表を開く', sub: 'Python / numpy / pandas', kbd: null, run: () => showView('references') },
      { id: 'ui.help',       group: 'ヘルプ', glyph: '?', title: 'ショートカット一覧', sub: 'キーボード操作', kbd: ['?'], run: () => help.open() },
      { id: 'ui.sidebar',    group: 'ヘルプ', glyph: '◧', title: 'サイドバーを切替',   sub: '表示 / 非表示',    kbd: ['Ctrl','B'], run: () => toggleSidebar() },
    ];
    for (const ts of state.testSets) {
      acts.push({ id: `test.${ts.id}`, group: 'テスト', glyph: '✓',
                  title: `テストを受ける: ${ts.title}`,
                  sub: `Phase ${ts.phase} · ${ts.questions} 問 · ${ts.minutes} 分`,
                  run: () => startTest(ts.id) });
    }
    for (const ch of state.chapters) {
      acts.push({ id: `chapter.${ch.id}`, group: '章', glyph: '❯',
                  title: `第 ${String(ch.id).padStart(2,'0')} 章 ${ch.title}`,
                  sub: `Phase ${ch.phase}`,
                  run: () => openChapter(ch.id) });
    }
    return acts;
  },
  refresh(query) {
    const q = (query || '').toLowerCase().trim();
    const all = this.buildActions();
    const filtered = q ? all.filter(a =>
      a.title.toLowerCase().includes(q) || a.sub.toLowerCase().includes(q) || a.id.toLowerCase().includes(q)
    ) : all;
    const order = ['ナビゲート','章','テスト','ヘルプ','設定'];
    const groups = {};
    filtered.forEach(a => { (groups[a.group] = groups[a.group] || []).push(a); });
    const list = $('#palette-list');
    list.innerHTML = ''; this.rows = [];
    for (const g of order) {
      if (!groups[g]) continue;
      list.insertAdjacentHTML('beforeend', `<div class="palette__group">${g}</div>`);
      for (const a of groups[g]) {
        const row = document.createElement('div');
        row.className = 'palette__row';
        const kbdHtml = a.kbd ? a.kbd.map(k => `<kbd>${k}</kbd>`).join('') : '';
        row.innerHTML = `
          <span class="glyph">${a.glyph}</span>
          <span class="title">${escapeHtml(a.title)}</span>
          <span class="sub">${escapeHtml(a.sub)}</span>
          ${kbdHtml}
        `;
        row.addEventListener('click', () => { this.close(); a.run(); });
        list.appendChild(row);
        this.rows.push({ row, action: a });
      }
    }
    this.selectedIdx = 0;
    this.updateSelection();
    $('#palette-count').textContent = `${filtered.length} 件`;
  },
  updateSelection() {
    this.rows.forEach((r, i) => r.row.classList.toggle('is-selected', i === this.selectedIdx));
    const sel = this.rows[this.selectedIdx];
    if (sel) sel.row.scrollIntoView({ block: 'nearest' });
  },
  move(d) {
    if (!this.rows.length) return;
    this.selectedIdx = (this.selectedIdx + d + this.rows.length) % this.rows.length;
    this.updateSelection();
  },
  execute() {
    const sel = this.rows[this.selectedIdx];
    if (!sel) return;
    this.close();
    sel.action.run();
  },
};

const help = {
  el: () => $('#help'),
  open()  { this.el().hidden = false; },
  close() { this.el().hidden = true; },
};

function toggleSidebar() {
  const sb = $('.sidebar');
  const cur = sb.dataset.collapsed === 'true';
  sb.dataset.collapsed = !cur;
  sb.style.display = !cur ? 'none' : '';
}

function toast(msg) {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    el.style.cssText = `
      position: fixed; bottom: 48px; left: 50%; transform: translateX(-50%);
      padding: 10px 16px; background: var(--surface-3); color: var(--ink);
      border: 1px solid var(--line-3); font-size: 13px; z-index: 100;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
    `;
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.style.opacity = 1;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.style.opacity = 0, 1800);
}

// ---------- Bindings ----------------------------------------------------
function bindUi() {
  $$('.nav__item').forEach(btn => btn.addEventListener('click', () => showView(btn.dataset.view)));
  $$('.qa__row').forEach(btn  => btn.addEventListener('click', () => showView(btn.dataset.view)));
  $('#open-palette-top')?.addEventListener('click', () => palette.open());
  $('#brand-home')?.addEventListener('click', (e) => { e.preventDefault(); showView('dashboard'); });

  $('#resume-btn').addEventListener('click', () => {
    const lastId = state.lastActivity?.chapterId;
    const lastCh = lastId ? state.chapters.find(c => c.id === lastId) : null;
    if (lastCh) {
      openChapter(lastCh.id);
      return;
    }
    const inProg = state.chapters.find(c => state.progress[c.id]?.status === 'in_progress');
    const first  = state.chapters.find(c => state.progress[c.id]?.status !== 'done') || state.chapters[0];
    openChapter((inProg || first).id);
  });
  $('#browse-btn').addEventListener('click', () => showView('chapters'));

  $('#chap-close').addEventListener('click', () => showView('chapters'));

  // Test runner buttons
  $('#tr-submit')?.addEventListener('click', submitTestQuestion);
  $('#tr-skip')?.addEventListener('click', skipTestQuestion);
  $('#tr-abort')?.addEventListener('click', abortTest);

  $('#next-btn').addEventListener('click', () => {
    if (state.showingResult) {
      // After an incorrect submission, "next" goes back to retry the page.
      if (!state.lastResult?.passed) {
        state.showingResult = false;
        state.lastResult    = null;
        paintChapterPage();
      } else {
        advanceChapter();
      }
    } else {
      submitCurrentPage();
    }
  });

  $('#palette-input').addEventListener('input',   e => palette.refresh(e.target.value));
  $('#palette-input').addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { palette.move(+1); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { palette.move(-1); e.preventDefault(); }
    else if (e.key === 'Enter') { palette.execute(); e.preventDefault(); }
    else if (e.key === 'Escape') { palette.close(); }
  });
  $('.palette__scrim').addEventListener('click', () => palette.close());
  $('.help__scrim').addEventListener('click', () => help.close());

  document.addEventListener('keydown', e => {
    const isCmd = e.ctrlKey || e.metaKey;
    const inEditable = document.activeElement && (
      document.activeElement.matches('input, textarea') ||
      document.activeElement.isContentEditable
    );
    if (isCmd && e.key.toLowerCase() === 'k') { e.preventDefault(); palette.toggle(); return; }
    if (isCmd && e.key.toLowerCase() === 'b') { e.preventDefault(); toggleSidebar(); return; }
    if (e.key === '?' && !inEditable) { e.preventDefault(); help.open(); return; }
    if (e.key === 'Escape') {
      if (!palette.el().hidden) { palette.close(); return; }
      if (!help.el().hidden)    { help.close();    return; }
    }
    if (isCmd) {
      const map = { '1':'dashboard', '2':'chapters', '3':'practice', '4':'tests', '5':'history' };
      if (map[e.key]) { e.preventDefault(); showView(map[e.key]); return; }
      if (e.key.toLowerCase() === 'r') {
        e.preventDefault();
        const inProg = state.chapters.find(c => state.progress[c.id]?.status === 'in_progress');
        if (inProg) openChapter(inProg.id);
      }
    }
    // Chapter view: no Back action (only forward via Enter / Submit).

    // Test runner shortcuts
    if (state.view === 'test-runner' && !inEditable) {
      if (e.key === 'Enter') { e.preventDefault(); submitTestQuestion(); }
      else if (e.key.toLowerCase() === 's') { e.preventDefault(); skipTestQuestion(); }
    }
  });
}

// ---------- QWebChannel bridge ------------------------------------------
function connectBridge() {
  if (typeof QWebChannel === 'undefined') return;
  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.bridge;
    if (!bridge) return;
    if (typeof bridge.bootstrapJson === 'function') {
      bridge.bootstrapJson((json) => {
        try {
          const data = JSON.parse(json);
          if (data.chapters)    state.chapters    = data.chapters;
          if (data.progress)    state.progress    = data.progress;
          if (data.testSets)    state.testSets    = data.testSets;
          if (data.testResults) state.testResults = data.testResults;
          renderAll();  // includes practice (which now uses bridge)
        } catch (e) { console.warn('bootstrap parse failed', e); }
      });
    }
    if (bridge.kernelState && bridge.kernelState.connect) {
      bridge.kernelState.connect((s) => {
        $('#kernel-pill').dataset.state = s;
        $('#kernel-pill .kernel-pill__label').textContent = s;
        $('#status-kernel').textContent = `kernel: ${s}`;
      });
    }
  });
}

function renderAll() {
  renderDashboard();
  renderChapters();
  renderTests();
  renderHistory();
  renderReferences();
  renderPractice();
}

// ---------- Practice (cross-chapter reading problems) -------------------
function renderPractice() {
  const host = $('#practice-grid');
  if (!host) return;
  if (!bridge || typeof bridge.practiceProblemsJson !== 'function') {
    host.innerHTML = `<div class="practice-empty">Python アプリ経由で起動してください。練習問題は実章データから生成されます。</div>`;
    return;
  }
  bridge.practiceProblemsJson((json) => {
    let data;
    try { data = JSON.parse(json); }
    catch (e) { host.innerHTML = `<div class="practice-empty">問題の解析に失敗しました。</div>`; return; }
    const problems = data.problems || [];
    if (!problems.length) {
      host.innerHTML = `<div class="practice-empty">Reading 問題がまだ用意されていません。各章を進めるとここに復習用の問題が並びます。</div>`;
      return;
    }
    // Group by phase, preserve phase order
    const order = ['A','B','C','D','E','F'];
    const buckets = {};
    for (const p of problems) (buckets[p.phase] = buckets[p.phase] || []).push(p);
    host.innerHTML = '';
    for (const ph of order) {
      const items = buckets[ph];
      if (!items || !items.length) continue;
      const section = document.createElement('section');
      section.className = 'practice-phase';
      section.innerHTML = `
        <header class="practice-phase__head">
          <div class="practice-phase__badge">${ph}</div>
          <div>
            <div class="practice-phase__title">Phase ${ph} · ${escapeHtml(PHASE_LABEL[ph] || '')}</div>
          </div>
          <div class="practice-phase__count">${items.length} 問</div>
        </header>
        <div class="practice-list"></div>
      `;
      const list = section.querySelector('.practice-list');
      for (const it of items) {
        const card = document.createElement('button');
        card.className = 'practice-item';
        card.innerHTML = `
          <div class="practice-item__head">
            <span class="num">Ch ${String(it.chapterId).padStart(2,'0')}</span>
            <span>·</span>
            <span>Reading</span>
          </div>
          <div class="practice-item__title">${escapeHtml(it.title)}</div>
          <div class="practice-item__desc">${escapeHtml(it.chapterTitle)}</div>
          <div class="practice-item__foot">
            <span class="practice-item__choices">${it.choices.length} 択</span>
            <span>正答を選ぶと採点されます</span>
          </div>
        `;
        card.addEventListener('click', () => openPracticeProblem(it));
        list.appendChild(card);
      }
      host.appendChild(section);
    }
  });
}

function openPracticeProblem(item) {
  // Open the host chapter, then jump to the specific reading page index.
  // Reuses the existing chapter view (handles reading pages natively).
  openChapter(item.chapterId);
  // Wait briefly for chapterDetailJson to populate, then jump.
  let n = 0;
  const t = setInterval(() => {
    if (state.currentDetail && state.currentDetail.id === item.chapterId) {
      clearInterval(t);
      state.currentPageIndex = item.pageIndex;
      state.showingResult = false;
      state.lastResult = null;
      paintChapterPage();
    } else if (++n > 40) {
      clearInterval(t);
    }
  }, 50);
}

// ---------- References (reference cheat-sheet) --------------------------
const REFERENCES = [
  {
    id: 'builtins', label: '組込み関数',
    items: [
      { name: 'print', sig: "print(*objects, sep=' ', end='\\n')", desc: '値を標準出力に出す。', ex: 'print("Hello", 42)' },
      { name: 'len',   sig: 'len(s)',              desc: '長さ（要素数）を返す。',    ex: 'len([1,2,3])  # 3' },
      { name: 'range', sig: 'range(start, stop[, step])', desc: '連続整数のイテレータ。', ex: 'list(range(3))  # [0,1,2]' },
      { name: 'sum',   sig: 'sum(iter, start=0)',  desc: '要素の合計。',              ex: 'sum([1,2,3])  # 6' },
      { name: 'min/max', sig: 'min(iter) / max(iter)', desc: '最小値 / 最大値。',      ex: 'max([3,1,2])  # 3' },
      { name: 'abs',   sig: 'abs(x)',              desc: '絶対値。',                  ex: 'abs(-3)  # 3' },
      { name: 'round', sig: 'round(x, ndigits=0)', desc: '四捨五入。',                ex: 'round(3.14159, 2)  # 3.14' },
      { name: 'int / float / str', sig: 'int("3") / float("1.5") / str(42)', desc: '型変換。', ex: 'int("12") + 1  # 13' },
      { name: 'list / dict / set', sig: 'list(iter) / dict(...) / set(iter)', desc: 'コンテナ生成。', ex: 'list("abc")  # ["a","b","c"]' },
      { name: 'enumerate', sig: 'enumerate(iter, start=0)', desc: 'インデックス付きで反復。', ex: 'for i,v in enumerate(["a","b"]): ...' },
      { name: 'zip',   sig: 'zip(*iters)',         desc: '同時反復。',                ex: 'list(zip([1,2],[3,4]))  # [(1,3),(2,4)]' },
      { name: 'sorted',sig: 'sorted(iter, key=None, reverse=False)', desc: '新しいソート済みリスト。', ex: 'sorted([3,1,2])  # [1,2,3]' },
      { name: 'isinstance', sig: 'isinstance(obj, cls)', desc: '型チェック。',         ex: 'isinstance(3, int)  # True' },
    ],
  },
  {
    id: 'strings', label: '文字列メソッド',
    items: [
      { name: '.upper / .lower', sig: 's.upper() / s.lower()', desc: '大文字 / 小文字化。', ex: '"Hi".upper()  # "HI"' },
      { name: '.strip', sig: "s.strip([chars])", desc: '前後の空白を削除。',         ex: '" a ".strip()  # "a"' },
      { name: '.split', sig: "s.split(sep=None)", desc: '区切り文字で分割。',         ex: '"a,b,c".split(",")  # ["a","b","c"]' },
      { name: '.join',  sig: '"-".join(iter)',   desc: 'リストを連結。',             ex: '",".join(["a","b"])  # "a,b"' },
      { name: '.replace', sig: 's.replace(old, new)', desc: '置換。',                ex: '"abc".replace("b","X")  # "aXc"' },
      { name: '.startswith / .endswith', sig: 's.startswith(pre)', desc: '前方 / 後方一致。', ex: '"file.csv".endswith(".csv")  # True' },
      { name: 'f-string', sig: 'f"{name}={value:.2f}"', desc: '式埋め込み + 書式。', ex: 'f"π = {3.14159:.2f}"  # "π = 3.14"' },
    ],
  },
  {
    id: 'collections', label: 'リスト / 辞書 / 集合',
    items: [
      { name: 'list 索引', sig: 'xs[i] / xs[i:j]', desc: '要素 / スライス取得。',     ex: '[10,20,30][1:]  # [20,30]' },
      { name: 'list.append', sig: 'xs.append(x)', desc: '末尾に追加。',              ex: 'xs.append(4)' },
      { name: 'list.extend', sig: 'xs.extend(iter)', desc: '複数追加。',             ex: 'xs.extend([5,6])' },
      { name: 'list内包', sig: '[f(x) for x in xs if cond]', desc: '宣言的に生成。', ex: '[x*x for x in range(5)]' },
      { name: 'dict 索引', sig: 'd[key] / d.get(key, default)', desc: '値の取得。',  ex: 'd.get("k", 0)' },
      { name: 'dict.items', sig: 'd.items()',     desc: 'キー・値ペアで反復。',      ex: 'for k,v in d.items(): ...' },
      { name: 'set 演算', sig: 'a | b / a & b / a - b', desc: '和 / 積 / 差。',      ex: '{1,2} & {2,3}  # {2}' },
    ],
  },
  {
    id: 'control', label: '制御構造 / 関数',
    items: [
      { name: 'if / elif / else', sig: 'if cond:\\n    ...\\nelif cond2:\\n    ...', desc: '分岐。', ex: 'if x > 0: print("正")' },
      { name: 'for', sig: 'for x in iter:\\n    ...', desc: '反復。',                ex: 'for v in [1,2,3]: print(v)' },
      { name: 'while', sig: 'while cond:\\n    ...', desc: '条件付き反復。',         ex: 'while n < 10: n += 1' },
      { name: 'def',  sig: 'def f(x, y=1):\\n    return x + y', desc: '関数定義。',   ex: 'def add(a,b): return a+b' },
      { name: 'lambda', sig: 'lambda x: x*2', desc: '1 行関数（式）。',              ex: 'sorted(xs, key=lambda p: p.score)' },
      { name: 'try / except', sig: 'try:\\n    ...\\nexcept Type as e:\\n    ...', desc: '例外処理。', ex: 'try: 1/0\\nexcept ZeroDivisionError: ...' },
    ],
  },
  {
    id: 'stdlib', label: '標準ライブラリ',
    items: [
      { name: 'math', sig: 'import math',          desc: '数学関数（sqrt, log, sin, ...）。', ex: 'math.sqrt(2)  # 1.414...' },
      { name: 'random', sig: 'import random',      desc: '乱数（randint, choice, sample, ...）。', ex: 'random.randint(1, 6)' },
      { name: 'statistics', sig: 'import statistics', desc: '記述統計（mean, stdev, median）。', ex: 'statistics.mean([1,2,3])' },
      { name: 'datetime', sig: 'from datetime import datetime, timedelta', desc: '日付・時刻。', ex: 'datetime.now() + timedelta(days=1)' },
      { name: 'pathlib', sig: 'from pathlib import Path', desc: 'パス操作。',         ex: 'Path("data.csv").read_text()' },
      { name: 'json',   sig: 'import json',         desc: 'JSON のパースと書き出し。', ex: 'json.dumps({"a":1})' },
    ],
  },
  {
    id: 'numpy', label: 'numpy',
    items: [
      { name: 'np.array', sig: 'np.array([1,2,3])', desc: '配列生成。',               ex: 'a = np.array([[1,2],[3,4]])' },
      { name: 'np.zeros / np.ones', sig: 'np.zeros((m,n)) / np.ones((m,n))', desc: '0 / 1 配列。', ex: 'np.zeros(3)  # [0,0,0]' },
      { name: 'np.arange / np.linspace', sig: 'np.arange(0,1,0.1) / np.linspace(0,1,11)', desc: '等差配列。', ex: 'np.linspace(0,1,5)' },
      { name: 'a.shape / a.dtype', sig: 'a.shape',  desc: '形状 / 型。',              ex: 'np.zeros((2,3)).shape  # (2,3)' },
      { name: 'スライス',sig: 'a[1:, :2]',          desc: '部分配列。',                ex: 'a[:, 0]  # 1 列目' },
      { name: 'a.mean / a.std / a.sum', sig: 'a.mean(axis=0)', desc: '集約。',         ex: 'a.mean(axis=0)' },
      { name: '行列積',  sig: 'a @ b / np.dot(a,b)', desc: '行列積。',                 ex: 'a @ b' },
      { name: 'np.where', sig: 'np.where(cond, x, y)', desc: '条件選択。',             ex: 'np.where(a > 0, a, 0)' },
      { name: 'np.random', sig: 'np.random.normal(0,1,size=100)', desc: '乱数。',     ex: 'np.random.seed(0); np.random.randn(3)' },
    ],
  },
  {
    id: 'pandas', label: 'pandas',
    items: [
      { name: 'pd.DataFrame', sig: 'pd.DataFrame({"a":[1,2]})', desc: '表データ。',   ex: 'df = pd.DataFrame({"x":[1,2,3]})' },
      { name: 'pd.read_csv', sig: 'pd.read_csv("file.csv", parse_dates=["date"])', desc: 'CSV 読込。', ex: 'df = pd.read_csv("data.csv")' },
      { name: 'df.head / .info / .describe', sig: 'df.head() / df.describe()', desc: '概観。', ex: 'df.describe()' },
      { name: '列・行参照', sig: "df['col'] / df.loc[i] / df.iloc[i]", desc: '取得。', ex: 'df.loc[df.x > 0]' },
      { name: 'df.groupby', sig: 'df.groupby("k")["v"].mean()', desc: 'グルーピング。', ex: 'df.groupby("phase").size()' },
      { name: 'df.merge',  sig: 'a.merge(b, on="id", how="left")', desc: '結合。',    ex: 'left.merge(right, on="key")' },
      { name: 'df.pivot_table', sig: 'df.pivot_table(index="i", columns="c", values="v")', desc: 'ピボット。', ex: '' },
      { name: '日付インデックス', sig: 'df.set_index("date")', desc: '時系列化。',    ex: 'df.resample("M").mean()' },
      { name: 'df.to_csv', sig: 'df.to_csv("out.csv", index=False)', desc: '書き出し。', ex: '' },
    ],
  },
  {
    id: 'matplotlib', label: 'matplotlib',
    items: [
      { name: 'import', sig: 'import matplotlib.pyplot as plt', desc: '慣習的に plt と省略。', ex: 'import matplotlib.pyplot as plt' },
      { name: 'plt.plot', sig: 'plt.plot(x, y)', desc: '折れ線。',                   ex: 'plt.plot([1,2,3], [4,5,6])' },
      { name: 'plt.bar / plt.scatter / plt.hist', sig: 'plt.scatter(x,y)', desc: '棒・散布・度数分布。', ex: 'plt.hist(returns, bins=30)' },
      { name: 'plt.xlabel / .title / .legend', sig: 'plt.xlabel("Date")', desc: '軸ラベル等。', ex: 'plt.title("Returns")' },
      { name: 'plt.show', sig: 'plt.show()', desc: 'カーネルで描画。',               ex: 'plt.show()' },
      { name: 'subplots', sig: 'fig, ax = plt.subplots(2, 1)', desc: '複数軸。',     ex: 'ax[0].plot(x, y)' },
    ],
  },
  {
    id: 'scipy_sklearn', label: 'scipy / scikit-learn',
    items: [
      { name: 'scipy.stats', sig: 'from scipy import stats', desc: '統計検定・分布。', ex: 'stats.norm.cdf(1.96)  # ≒ 0.975' },
      { name: 'scipy.optimize.minimize', sig: 'minimize(fun, x0, method="SLSQP")', desc: '最適化。', ex: 'minimize(lambda x: (x-3)**2, x0=0)' },
      { name: 'sklearn 基本フロー', sig: 'model.fit(X,y); model.predict(X_test)', desc: '訓練 → 予測。', ex: 'LinearRegression().fit(X,y)' },
      { name: 'train_test_split', sig: 'train_test_split(X, y, test_size=0.2)', desc: 'データ分割。', ex: 'Xtr,Xte,ytr,yte = train_test_split(X,y)' },
      { name: 'cross_val_score', sig: 'cross_val_score(model, X, y, cv=5)', desc: '交差検証。', ex: '' },
      { name: '評価指標', sig: 'mean_squared_error / r2_score / accuracy_score', desc: '回帰 / 分類。', ex: 'r2_score(y, y_pred)' },
    ],
  },
];

function renderReferences() {
  const cats = $('#ref-cats');
  const sections = $('#ref-sections');
  if (!cats || !sections) return;
  cats.innerHTML = '';
  for (const c of REFERENCES) {
    const btn = document.createElement('button');
    btn.className = 'ref-cat';
    btn.textContent = c.label;
    btn.dataset.id = c.id;
    btn.addEventListener('click', () => {
      const el = document.getElementById(`ref-${c.id}`);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    cats.appendChild(btn);
  }
  sections.innerHTML = '';
  for (const c of REFERENCES) {
    const sec = document.createElement('section');
    sec.className = 'ref-section';
    sec.id = `ref-${c.id}`;
    const itemsHtml = c.items.map(it => `
      <article class="ref-item" data-q="${escapeHtml((it.name + ' ' + it.desc + ' ' + (it.sig||'') + ' ' + (it.ex||'')).toLowerCase())}">
        <div class="ref-item__name">${escapeHtml(it.name)}</div>
        <pre class="ref-item__sig">${highlightPy(it.sig)}</pre>
        <p class="ref-item__desc">${escapeHtml(it.desc)}</p>
        ${it.ex ? `<pre class="ref-item__ex">${highlightPy(it.ex.replace(/\\n/g, '\n'))}</pre>` : ''}
      </article>
    `).join('');
    sec.innerHTML = `
      <header class="ref-section__head">
        <span class="kicker"><span class="dot"></span> ${escapeHtml(c.label)}</span>
        <span class="ref-section__count">${c.items.length} 項目</span>
      </header>
      <div class="ref-grid">${itemsHtml}</div>
    `;
    sections.appendChild(sec);
  }
  // Wire search
  const search = $('#ref-search');
  if (search && !search.dataset.bound) {
    search.dataset.bound = '1';
    search.addEventListener('input', () => {
      const q = search.value.toLowerCase().trim();
      let hidden = 0, shown = 0;
      document.querySelectorAll('.ref-item').forEach(it => {
        const hit = !q || it.dataset.q.includes(q);
        it.style.display = hit ? '' : 'none';
        if (hit) shown++; else hidden++;
      });
      // Hide empty sections
      document.querySelectorAll('.ref-section').forEach(sec => {
        const anyVisible = [...sec.querySelectorAll('.ref-item')].some(i => i.style.display !== 'none');
        sec.style.display = anyVisible ? '' : 'none';
      });
    });
  }
}

// ---------- Mock seed (only used when no bridge) ------------------------
function seedMock() {
  state.chapters = [
    { id: 1, phase: 'A', title: 'はじめての Python', desc: 'print と基本操作', pages: 8 },
  ];
  state.progress = {};
  state.testSets = [];
  state.testResults = [];
}

// ---------- Boot --------------------------------------------------------
initTheme();
loadLastActivity();
seedMock();
bindUi();
renderAll();
wireSettings();
showView('dashboard');
connectBridge();
