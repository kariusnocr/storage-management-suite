/* ==========================================================================
   Karius Academic System (KAS) v1.5.0 — Frontend Workspace Engine
   Modular Vanilla JS · Zero External Dependencies · Offline & SAC Safe
   ========================================================================== */

const fmt = (n) => Number(n || 0).toLocaleString('vi-VN');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}[c]));

let _vaultsCache = [];
let _rulesPayload = null;
let _aiPayload = null;
let _chatHistory = [];
let _cmdHistory = [];
let _cmdHistIdx = -1;
let _latestUpdateInfo = null;

/* ==================== NAVIGATION METADATA ==================== */

const NAV_META = {
  overview: { group: 'Kho Tri Thức', label: 'Tổng quan', desc: 'Chỉ số kho, phân bố dung lượng & tác vụ nhanh' },
  vaults:   { group: 'Kho Tri Thức', label: 'Kho Dữ Liệu', desc: 'Kết nối đa kho Local FS & Google Drive' },
  search:   { group: 'Kho Tri Thức', label: 'Tìm kiếm FTS5', desc: 'Tra cứu toàn văn SQLite FTS5 có dấu & không dấu' },
  catalog:  { group: 'Quản trị & Chuẩn hóa', label: 'Danh Mục V7', desc: 'Chuẩn hóa & tinh gọn bảng danh mục thông minh' },
  rules:    { group: 'Quản trị & Chuẩn hóa', label: 'Quy Tắc Đặt Tên', desc: 'Tùy chỉnh preset, regex & bộ thử thời gian thực' },
  audit:    { group: 'Quản trị & Chuẩn hóa', label: 'Kiểm toán', desc: 'Phát hiện sai chuẩn tên, rác hệ thống & cấu trúc' },
  undo:     { group: 'Quản trị & Chuẩn hóa', label: 'Hoàn tác', desc: 'Nhật kí Unified Undo Journal theo từng kho' },
  ai:       { group: 'Trợ Lý & Công cụ', label: 'Trợ Lý AI & Agent', desc: 'Chatbot nội bộ, LLM API & máy chủ MCP' },
  console:  { group: 'Trợ Lý & Công cụ', label: 'Dòng Lệnh (Console)', desc: 'Chạy mọi lệnh kas trực tiếp không cần PowerShell' },
  account:  { group: 'Hệ thống', label: 'Tài Khoản & Kết Nối', desc: 'Khóa ứng dụng, Google Drive OAuth, GitHub & Webhook' },
  doctor:   { group: 'Hệ thống', label: 'Chẩn đoán & Tự cài', desc: 'Kiểm tra môi trường, tự cài CLI & OCR Tiếng Việt' },
  settings: { group: 'Hệ thống', label: 'Cài Đặt & Cập Nhật', desc: 'Giao diện, Auto-Update SHA-256 & Gỡ cài đặt an toàn' },
};

/* ==================== CORE FETCH & AUTH GUARD ==================== */

async function apiFetch(url, opts) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && data.locked) {
    const ov = document.getElementById('lockOverlay');
    if (ov) ov.classList.add('open');
  }
  return { ok: r.ok, status: r.status, data };
}

/* ==================== TOAST NOTIFICATIONS ==================== */

function showToast(message, type = 'info', ttl = 3800) {
  const stack = document.getElementById('toastStack');
  if (!stack) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.setAttribute('role', 'status');
  el.innerHTML = `<span>${esc(message)}</span><button class="toast-close" aria-label="Đóng">&times;</button>`;
  const close = () => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(6px)';
    el.style.transition = 'opacity 140ms, transform 140ms';
    setTimeout(() => el.remove(), 150);
  };
  el.querySelector('.toast-close').addEventListener('click', close);
  stack.appendChild(el);
  if (ttl > 0) setTimeout(close, ttl);
}

/* ==================== CUSTOM CONFIRM / PROMPT MODAL ==================== */

let _confirmResolve = null;

function closeConfirmModal(result) {
  const ov = document.getElementById('confirmOverlay');
  if (ov) ov.classList.remove('open');
  const fn = _confirmResolve;
  _confirmResolve = null;
  if (typeof fn === 'function') fn(result);
}

function showConfirmModal({
  title = 'Xác nhận thao tác',
  message = '',
  confirmText = 'Xác nhận',
  cancelText = 'Hủy bỏ',
  danger = false,
  requireTyped = '',
  placeholder = '',
} = {}) {
  return new Promise((resolve) => {
    const ov = document.getElementById('confirmOverlay');
    const titleEl = document.getElementById('confirmTitle');
    const msgEl = document.getElementById('confirmMessage');
    const typedWrap = document.getElementById('confirmTypedWrap');
    const typedLbl = document.getElementById('confirmTypedLabel');
    const typedInp = document.getElementById('confirmTypedInput');
    const cancelBtn = document.getElementById('confirmCancelBtn');
    const okBtn = document.getElementById('confirmOkBtn');

    if (!ov) {
      resolve(false);
      return;
    }
    _confirmResolve = resolve;
    titleEl.textContent = title;
    msgEl.textContent = message;
    cancelBtn.textContent = cancelText;
    okBtn.textContent = confirmText;
    okBtn.className = danger ? 'btn danger' : 'btn';

    const expected = String(requireTyped || '').trim().toUpperCase();
    if (expected) {
      typedWrap.style.display = 'block';
      typedLbl.innerHTML = `Nhập chính xác <code>${esc(expected)}</code> để tiếp tục:`;
      typedInp.value = '';
      typedInp.placeholder = placeholder || expected;
      okBtn.disabled = true;
      typedInp.oninput = () => {
        okBtn.disabled = typedInp.value.trim().toUpperCase() !== expected;
      };
      typedInp.onkeydown = (e) => {
        if (e.key === 'Enter' && !okBtn.disabled) closeConfirmModal(true);
      };
    } else {
      typedWrap.style.display = 'none';
      typedInp.value = '';
      typedInp.oninput = null;
      typedInp.onkeydown = null;
      okBtn.disabled = false;
    }

    cancelBtn.onclick = () => closeConfirmModal(false);
    okBtn.onclick = () => closeConfirmModal(true);
    ov.classList.add('open');
    setTimeout(() => {
      if (expected) typedInp.focus();
      else okBtn.focus();
    }, 30);
  });
}

/* ==================== SIDEBAR, NAVIGATION & THEME ==================== */

function restoreSidebarState() {
  const shell = document.getElementById('appShell');
  if (!shell) return;
  try {
    if (localStorage.getItem('kas_sidebar_collapsed') === '1') {
      shell.classList.add('sidebar-collapsed');
    }
  } catch (_e) {
    // ignore storage errors
  }
}

function toggleSidebar() {
  const shell = document.getElementById('appShell');
  if (!shell) return;
  const collapsed = shell.classList.toggle('sidebar-collapsed');
  try {
    localStorage.setItem('kas_sidebar_collapsed', collapsed ? '1' : '0');
  } catch (_e) {
    // ignore storage errors
  }
}

function toggleMobileNav() {
  const shell = document.getElementById('appShell');
  if (shell) shell.classList.toggle('mobile-nav-open');
}

function closeMobileNav() {
  const shell = document.getElementById('appShell');
  if (shell) shell.classList.remove('mobile-nav-open');
}

function updateThemeButton(theme) {
  const btn = document.getElementById('themeToggleBtn');
  if (!btn) return;
  const isLight = theme === 'light';
  btn.title = isLight ? 'Chuyển sang giao diện Tối (Obsidian Ink)' : 'Chuyển sang giao diện Sáng (Archival Paper)';
  btn.setAttribute('aria-label', btn.title);
  btn.innerHTML = isLight
    ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
    : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
}

async function toggleTheme() {
  const h = document.documentElement;
  const next = h.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  h.setAttribute('data-theme', next);
  updateThemeButton(next);
  const sTheme = document.getElementById('sTheme');
  if (sTheme) sTheme.value = next;
  await apiFetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme: next }),
  });
  showToast(next === 'light' ? 'Đã chuyển sang giao diện Sáng (Archival Paper)' : 'Đã chuyển sang giao diện Tối (Obsidian Ink)', 'info', 2200);
}

function openTab(tabName) {
  const meta = NAV_META[tabName] || NAV_META.overview;
  document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === tabName));
  document.querySelectorAll('.section').forEach((s) => s.classList.remove('active'));
  const el = document.getElementById('tab-' + tabName);
  if (el) el.classList.add('active');

  const cg = document.getElementById('crumbGroup');
  const ct = document.getElementById('crumbTitle');
  if (cg) cg.textContent = meta.group;
  if (ct) ct.textContent = meta.label;
  closeMobileNav();

  if (tabName === 'vaults') loadVaults();
  if (tabName === 'overview') loadOverview();
  if (tabName === 'search') setTimeout(() => { const i = document.getElementById('searchInput'); if (i) i.focus(); }, 40);
  if (tabName === 'console') loadConsole();
  if (tabName === 'rules') loadNamingRules();
  if (tabName === 'ai') loadAiPanel();
  if (tabName === 'account') loadAccountAndIntegrations();
  if (tabName === 'settings') loadAppSettings();
  if (tabName === 'catalog') loadCatalogPlan();
  if (tabName === 'audit') loadAudit();
  if (tabName === 'undo') loadUndo();
  if (tabName === 'doctor') loadDoctor();
}

function openConsolePrompt(prefill = '') {
  openTab('console');
  setTimeout(() => {
    const inp = document.getElementById('consoleInput');
    if (!inp) return;
    if (prefill) inp.value = prefill;
    inp.focus();
  }, 50);
}

/* ==================== GLOBAL COMMAND PALETTE (CTRL+K) ==================== */

let _paletteItems = [];
let _paletteSelIdx = 0;
let _paletteSearchTimer = null;
let _paletteLiveFiles = [];
let _paletteLastQuery = '';

function openCommandPalette() {
  const ov = document.getElementById('paletteOverlay');
  const inp = document.getElementById('paletteInput');
  if (!ov || !inp) return;
  ov.classList.add('open');
  inp.value = '';
  _paletteLiveFiles = [];
  _paletteLastQuery = '';
  _paletteSelIdx = 0;
  renderPaletteList('');
  setTimeout(() => inp.focus(), 20);
}

function closeCommandPalette() {
  const ov = document.getElementById('paletteOverlay');
  if (ov) ov.classList.remove('open');
}

function _buildStaticPaletteEntries() {
  const entries = [];
  Object.entries(NAV_META).forEach(([tabId, m]) => {
    entries.push({
      group: 'Điều hướng nhanh',
      title: m.label,
      sub: m.desc,
      keywords: `${m.label} ${m.group} ${m.desc} ${tabId}`.toLowerCase(),
      run: () => openTab(tabId),
    });
  });

  entries.push(
    {
      group: 'Tác vụ tức thì',
      title: 'Quét chỉ mục kho hiện tại (kas quet)',
      sub: 'Lập chỉ mục SQLite FTS5 & đồng bộ cấu trúc',
      keywords: 'quet scan index chi muc kho',
      run: () => {
        openTab('overview');
        runBackgroundTask('quet', [], 'overviewConsole');
      },
    },
    {
      group: 'Tác vụ tức thì',
      title: 'Kiểm tra bản cập nhật KAS mới nhất',
      sub: 'Kết nối GitHub Releases & xác thực SHA-256',
      keywords: 'update cap nhat release version',
      run: () => {
        openTab('settings');
        checkUpdates(true);
      },
    },
    {
      group: 'Tác vụ tức thì',
      title: 'Tự động cài công cụ & thư viện thiếu (kas setup)',
      sub: 'Python, gh, git, 7z, ffmpeg, tesseract + vie.traineddata',
      keywords: 'setup doctor cai dat ocr tesseract gh',
      run: () => {
        openTab('doctor');
        runAutoSetup('all');
      },
    },
    {
      group: 'Tác vụ tức thì',
      title: 'Chuyển đổi giao diện Sáng / Tối',
      sub: 'Obsidian Ink (Dark) ↔ Archival Paper (Light)',
      keywords: 'theme sang toi dark light giao dien',
      run: () => toggleTheme(),
    },
    {
      group: 'Tác vụ tức thì',
      title: 'Thu gọn / Mở rộng thanh điều hướng (Ctrl+B)',
      sub: 'Chuyển chế độ Sidebar đầy đủ và thanh biểu tượng',
      keywords: 'sidebar menu thu gon rail',
      run: () => toggleSidebar(),
    },
    {
      group: 'Tác vụ tức thì',
      title: 'Làm mới toàn bộ dữ liệu',
      sub: 'Đồng bộ lại kho, cài đặt và chỉ số tổng quan',
      keywords: 'refresh reload lam moi',
      run: () => refreshAll(),
    }
  );

  (_vaultsCache || []).forEach((v) => {
    entries.push({
      group: 'Chuyển Kho Dữ Liệu',
      title: `Chuyển kho: ${v.name}`,
      sub: `${v.source_kind === 'local' ? 'Cục bộ' : 'Google Drive'} · ${v.slug}`,
      keywords: `vault kho ${v.name} ${v.slug} ${v.root}`.toLowerCase(),
      run: () => switchVault(v.slug),
    });
  });

  return entries;
}

function renderPaletteList(rawQuery) {
  const listEl = document.getElementById('paletteList');
  if (!listEl) return;
  const q = String(rawQuery || '').trim();
  const qLow = q.toLowerCase();
  const all = _buildStaticPaletteEntries();
  let matched = qLow ? all.filter((it) => it.keywords.includes(qLow) || it.title.toLowerCase().includes(qLow)) : all.slice(0, 14);

  const combined = [];
  if (q && _paletteLiveFiles.length) {
    _paletteLiveFiles.forEach((f) => {
      combined.push({
        group: `Tệp tin FTS5 (${_paletteLiveFiles.length})`,
        title: f.name,
        sub: `${f.parent_path || ''} · ${f.size_human || ''}`,
        run: () => {
          openTab('search');
          const si = document.getElementById('searchInput');
          if (si) {
            si.value = q;
            runSearch();
          }
        },
      });
    });
  }

  matched.slice(0, 14).forEach((m) => combined.push(m));

  if (q) {
    combined.push({
      group: 'Dòng Lệnh KAS',
      title: `Chạy trong Console: kas ${q.replace(/^kas\s+/i, '')}`,
      sub: 'Thực thi trực tiếp trong KAS Command Console',
      run: () => {
        openConsolePrompt(q.replace(/^kas\s+/i, ''));
        setTimeout(() => runConsoleCmd(), 90);
      },
    });
  }

  _paletteItems = combined;
  if (_paletteSelIdx >= _paletteItems.length) _paletteSelIdx = 0;

  if (!_paletteItems.length) {
    listEl.innerHTML = '<div style="padding:18px; text-align:center; color:var(--muted); font-size:13px;">Không tìm thấy kết quả phù hợp.</div>';
    return;
  }

  let lastGroup = '';
  let html = '';
  _paletteItems.forEach((it, idx) => {
    if (it.group !== lastGroup) {
      html += `<div class="palette-group">${esc(it.group)}</div>`;
      lastGroup = it.group;
    }
    html += `
      <button type="button" class="palette-item ${idx === _paletteSelIdx ? 'selected' : ''}" data-pidx="${idx}">
        <span>${esc(it.title)}</span>
        <span class="palette-item-sub">${esc(it.sub || '')}</span>
      </button>`;
  });
  listEl.innerHTML = html;
  listEl.querySelectorAll('.palette-item').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = Number(btn.dataset.pidx);
      executePaletteIndex(idx);
    });
  });
}

function executePaletteIndex(idx) {
  const it = _paletteItems[idx];
  closeCommandPalette();
  if (it && typeof it.run === 'function') it.run();
}

function onPaletteInput(val) {
  const q = String(val || '').trim();
  _paletteSelIdx = 0;
  _paletteLastQuery = q;
  if (q.length < 2) {
    _paletteLiveFiles = [];
    renderPaletteList(q);
    return;
  }
  renderPaletteList(q);
  clearTimeout(_paletteSearchTimer);
  _paletteSearchTimer = setTimeout(async () => {
    const { ok, data } = await apiFetch('/api/search?q=' + encodeURIComponent(q) + '&limit=6');
    if (!ok || _paletteLastQuery !== q) return;
    _paletteLiveFiles = data.results || [];
    renderPaletteList(q);
  }, 180);
}

function onPaletteKey(e) {
  if (e.key === 'Escape') {
    e.preventDefault();
    closeCommandPalette();
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (_paletteItems.length) {
      _paletteSelIdx = (_paletteSelIdx + 1) % _paletteItems.length;
      renderPaletteList(document.getElementById('paletteInput').value);
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (_paletteItems.length) {
      _paletteSelIdx = (_paletteSelIdx - 1 + _paletteItems.length) % _paletteItems.length;
      renderPaletteList(document.getElementById('paletteInput').value);
    }
  } else if (e.key === 'Enter') {
    e.preventDefault();
    executePaletteIndex(_paletteSelIdx);
  }
}

/* ==================== KHÓA / ĐĂNG NHẬP KAS ==================== */

async function checkAccountGate() {
  const { data: st } = await apiFetch('/api/account/status');
  const btn = document.getElementById('headerAccountBtn');
  if (btn) {
    if (st.has_account && st.account) {
      btn.textContent = st.authenticated ? st.account.display_name : `Đã khóa · ${st.account.username}`;
    } else {
      btn.textContent = 'Đăng nhập / Kết nối';
    }
  }
  const ov = document.getElementById('lockOverlay');
  if (st.locked) {
    const lu = document.getElementById('lockUser');
    if (lu) lu.value = (st.account && st.account.username) || '';
    if (ov) ov.classList.add('open');
    return true;
  }
  if (ov) ov.classList.remove('open');
  return false;
}

async function submitLockLogin() {
  const username = document.getElementById('lockUser').value.trim();
  const password = document.getElementById('lockPass').value;
  const errEl = document.getElementById('lockErr');
  errEl.textContent = '';
  const { ok, data } = await apiFetch('/api/account/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!ok) {
    errEl.textContent = data.detail || 'Đăng nhập thất bại.';
    return;
  }
  document.getElementById('lockPass').value = '';
  document.getElementById('lockOverlay').classList.remove('open');
  showToast('Đã mở khóa phiên làm việc KAS.', 'ok');
  await refreshAll();
}

/* ==================== DÒNG LỆNH TÍCH HỢP (CONSOLE) ==================== */

async function loadConsole() {
  const { ok, data } = await apiFetch('/api/console/history');
  if (!ok) return;
  _cmdHistory = (data.history || []).map((h) => h.command);
  document.getElementById('consoleQuickChips').innerHTML = (data.quick_commands || []).map((q) =>
    `<button type="button" class="chip" onclick="runQuickConsoleCmd('${esc(q.cmd)}')"><strong>${esc(q.label)}</strong> · <code>${esc(q.cmd)}</code></button>`
  ).join('');
  document.getElementById('consoleHistoryBody').innerHTML = (data.history || []).slice(0, 25).map((h) => {
    const cls = h.returncode === 0 ? 'ok' : 'err';
    const cleanCmd = h.command.replace(/^kas\s+/, '');
    return `<tr>
      <td class="mono">${esc(h.command)}</td>
      <td><span class="pill ${cls}">${esc(h.returncode)}</span></td>
      <td>${fmt(h.elapsed_ms)} ms</td>
      <td style="color:var(--muted)">${esc(h.finished_utc)}</td>
      <td><button class="btn secondary sm" onclick="runQuickConsoleCmd('${esc(cleanCmd)}')">Chạy lại</button></td>
    </tr>`;
  }).join('') || '<tr><td colspan="5" style="color:var(--muted);">Chưa có lệnh nào được thực thi.</td></tr>';
}

function onConsoleKey(e) {
  const inp = document.getElementById('consoleInput');
  if (e.key === 'Enter') {
    e.preventDefault();
    runConsoleCmd();
  } else if (e.key === 'ArrowUp') {
    if (_cmdHistory.length) {
      _cmdHistIdx = Math.min(_cmdHistory.length - 1, _cmdHistIdx + 1);
      inp.value = _cmdHistory[_cmdHistIdx].replace(/^kas\s+/, '');
    }
  } else if (e.key === 'ArrowDown') {
    if (_cmdHistIdx > 0) {
      _cmdHistIdx -= 1;
      inp.value = _cmdHistory[_cmdHistIdx].replace(/^kas\s+/, '');
    } else {
      _cmdHistIdx = -1;
      inp.value = '';
    }
  }
}

function runQuickConsoleCmd(cmd) {
  document.getElementById('consoleInput').value = cmd;
  runConsoleCmd();
}

async function runConsoleCmd() {
  const inp = document.getElementById('consoleInput');
  const outEl = document.getElementById('consoleOutput');
  const badge = document.getElementById('consoleStatusBadge');
  const btn = document.getElementById('consoleRunBtn');
  const cmd = inp.value.trim();
  if (!cmd) return;
  _cmdHistIdx = -1;
  btn.disabled = true;
  badge.className = 'pill warn';
  badge.textContent = 'Đang chạy...';
  outEl.textContent = `$ kas ${cmd.replace(/^kas\s+/i, '')}\nĐang thực thi...`;

  const { ok, data: job } = await apiFetch('/api/console/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd }),
  });
  if (!ok) {
    badge.className = 'pill err';
    badge.textContent = 'Lỗi cú pháp';
    outEl.textContent = `[LỖI] ${job.detail || 'Không thể chạy lệnh'}`;
    btn.disabled = false;
    showToast(job.detail || 'Lỗi cú pháp lệnh', 'err');
    return;
  }
  const poll = setInterval(async () => {
    const { data: st } = await apiFetch('/api/console/jobs/' + encodeURIComponent(job.id));
    if (st.status !== 'running') {
      clearInterval(poll);
      btn.disabled = false;
      badge.className = st.returncode === 0 ? 'pill ok' : 'pill err';
      badge.textContent = st.returncode === 0 ? `Thành công (${st.elapsed_ms} ms)` : `Mã lỗi ${st.returncode}`;
      outEl.textContent = `$ ${st.command}\n\n${st.output || '(Hoàn tất)'}`;
      await loadConsole();
      await loadVaults();
      await loadOverview();
    }
  }, 450);
}

async function clearConsoleHistory() {
  await apiFetch('/api/console/history/clear', { method: 'POST' });
  showToast('Đã xóa lịch sử dòng lệnh.', 'info');
  await loadConsole();
}

/* ==================== TÀI KHOẢN & KẾT NỐI BÊN THỨ 3 ==================== */

async function loadAccountAndIntegrations() {
  const { data: accSt } = await apiFetch('/api/account/status');
  const accBadge = document.getElementById('accBadge');
  if (accSt.has_account && accSt.account) {
    accBadge.className = 'pill ok';
    accBadge.textContent = accSt.require_login ? 'Đã tạo · Khóa BẬT' : 'Đã tạo · Khóa TẮT';
    document.getElementById('accRegisterBox').style.display = 'none';
    document.getElementById('accProfileBox').style.display = 'block';
    document.getElementById('profUser').value = accSt.account.username;
    document.getElementById('profName').value = accSt.account.display_name || '';
    document.getElementById('profEmail').value = accSt.account.email || '';
    document.getElementById('profReqLogin').checked = !!accSt.account.require_login;
  } else {
    accBadge.className = 'pill warn';
    accBadge.textContent = 'Chưa tạo tài khoản';
    document.getElementById('accRegisterBox').style.display = 'block';
    document.getElementById('accProfileBox').style.display = 'none';
  }

  const { ok, data: ig } = await apiFetch('/api/integrations');
  if (!ok) return;
  const gd = (ig.google_drive && ig.google_drive.auth) || {};
  const gdBadge = document.getElementById('gdBadge');
  gdBadge.className = gd.authenticated ? 'pill ok' : 'pill warn';
  gdBadge.textContent = gd.authenticated ? 'Đã đăng nhập OAuth 2.0' : 'Chưa đăng nhập';
  document.getElementById('gdMeta').innerHTML =
    `Thư viện API: <strong>${gd.libs_installed ? 'Sẵn sàng' : 'Chưa cài'}</strong> · ` +
    `credentials.json: <strong>${gd.credentials_exists ? 'Đã có' : 'Chưa có'}</strong> · ` +
    `token.json: <strong>${gd.token_exists ? 'Đã có' : 'Chưa có'}</strong><br>` +
    `<span class="mono">${esc(gd.credentials_path || '')}</span>`;

  const gh = ig.github || {};
  const ghBadge = document.getElementById('ghBadge');
  ghBadge.className = gh.connected ? 'pill ok' : 'pill warn';
  ghBadge.textContent = gh.connected ? `Đã kết nối (${gh.login || gh.method})` : 'Chưa kết nối';
  document.getElementById('ghMeta').textContent = gh.connected
    ? `Tài khoản: @${gh.login || '—'} · Phương thức: ${gh.method} · Token: ${gh.token_masked || 'gh CLI'}`
    : 'Nhập GitHub Personal Access Token (PAT) để đồng bộ kho riêng tư & kiểm tra cập nhật không giới hạn.';

  const ai = ig.ai_provider || {};
  document.getElementById('aiSummaryLine').innerHTML =
    `AI hiện tại: <span class="pill info">${esc(ai.provider || 'builtin_offline')}</span> · Model: <code>${esc(ai.model || '')}</code> · API Key: <strong>${ai.has_api_key ? esc(ai.api_key_masked) : 'Không cần / Chưa đặt'}</strong>`;

  document.getElementById('connectorsBody').innerHTML = (ig.connectors || []).map((c) => `
    <tr>
      <td><strong>${esc(c.name)}</strong></td>
      <td><span class="pill info">${esc(c.kind)}</span></td>
      <td class="mono">${esc(c.endpoint_url)}</td>
      <td>${c.has_api_key ? esc(c.api_key_masked) : '—'}</td>
      <td><button class="btn secondary sm" onclick="removeConnector('${esc(c.name)}')">Xóa</button></td>
    </tr>
  `).join('') || '<tr><td colspan="5" style="color:var(--muted);">Chưa có kết nối tùy chỉnh nào.</td></tr>';
}

async function registerAccount() {
  const payload = {
    username: document.getElementById('regUser').value.trim(),
    display_name: document.getElementById('regName').value.trim(),
    email: document.getElementById('regEmail').value.trim(),
    password: document.getElementById('regPass').value,
    require_login: document.getElementById('regReqLogin').checked,
  };
  const { ok, data } = await apiFetch('/api/account/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const txt = ok ? `Đã tạo tài khoản "${data.account.username}" thành công!` : (`Lỗi: ${data.detail}`);
  document.getElementById('accMsg').textContent = txt;
  showToast(txt, ok ? 'ok' : 'err');
  await checkAccountGate();
  await loadAccountAndIntegrations();
}

async function updateAccountProfile() {
  const payload = {
    display_name: document.getElementById('profName').value.trim(),
    email: document.getElementById('profEmail').value.trim(),
    require_login: document.getElementById('profReqLogin').checked,
  };
  const { ok, data } = await apiFetch('/api/account/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const txt = ok ? 'Đã cập nhật hồ sơ & trạng thái khóa bảo vệ.' : (`Lỗi: ${data.detail}`);
  document.getElementById('accMsg').textContent = txt;
  showToast(txt, ok ? 'ok' : 'err');
  await checkAccountGate();
  await loadAccountAndIntegrations();
}

async function changePassword() {
  const { ok, data } = await apiFetch('/api/account/password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      old_password: document.getElementById('oldPass').value,
      new_password: document.getElementById('newPass').value,
    }),
  });
  document.getElementById('oldPass').value = '';
  document.getElementById('newPass').value = '';
  const txt = ok ? data.message : (`Lỗi: ${data.detail}`);
  document.getElementById('accMsg').textContent = txt;
  showToast(txt, ok ? 'ok' : 'err');
}

async function logoutAccount() {
  await apiFetch('/api/account/logout', { method: 'POST' });
  showToast('Đã đăng xuất phiên làm việc.', 'info');
  await checkAccountGate();
  await loadAccountAndIntegrations();
}

function readCredsFile(evt) {
  const f = evt.target.files && evt.target.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => { document.getElementById('gdCredsJson').value = String(reader.result || ''); };
  reader.readAsText(f);
}

async function saveGoogleCreds() {
  const raw = document.getElementById('gdCredsJson').value.trim();
  const msg = document.getElementById('gdMsg');
  const { ok, data } = await apiFetch('/api/integrations/google/credentials', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credentials_json: raw }),
  });
  const txt = ok
    ? `Đã lưu credentials.json (${data.client_id_masked}) tại ${data.credentials_path}. Bấm Bước 2 để đăng nhập Google!`
    : (`Lỗi: ${data.detail}`);
  msg.textContent = txt;
  showToast(ok ? 'Đã lưu Google credentials.json' : txt, ok ? 'ok' : 'err');
  if (ok) document.getElementById('gdCredsJson').value = '';
  await loadAccountAndIntegrations();
}

async function startGoogleLogin() {
  const msg = document.getElementById('gdMsg');
  const btn = document.getElementById('gdLoginBtn');
  btn.disabled = true;
  msg.textContent = 'Đang mở trình duyệt đăng nhập Google OAuth 2.0...';
  const { ok, data } = await apiFetch('/api/integrations/google/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ open_browser: true }),
  });
  if (!ok) {
    const errTxt = 'Lỗi: ' + (data.detail || data.message || 'Không thể bắt đầu OAuth');
    msg.textContent = errTxt;
    showToast(errTxt, 'err');
    btn.disabled = false;
    return;
  }
  msg.textContent = data.message || 'Vui lòng hoàn tất đăng nhập trên trình duyệt vừa mở...';
  const poll = setInterval(async () => {
    const { data: st } = await apiFetch('/api/integrations/google/login-status');
    msg.textContent = st.message || st.status;
    if (st.status !== 'running') {
      clearInterval(poll);
      btn.disabled = false;
      showToast(st.message || 'Hoàn tất phiên OAuth Google Drive.', st.status === 'done' ? 'ok' : 'warn');
      await loadAccountAndIntegrations();
    }
  }, 1200);
}

async function logoutGoogleDrive() {
  const yes = await showConfirmModal({
    title: 'Đăng xuất Google Drive',
    message: 'Đăng xuất khỏi phiên Google Drive OAuth 2.0 trên máy tính này? Bạn có thể đăng nhập lại bất cứ lúc nào.',
    confirmText: 'Đăng xuất',
    danger: true,
  });
  if (!yes) return;
  await apiFetch('/api/integrations/google/logout', { method: 'POST' });
  document.getElementById('gdMsg').textContent = 'Đã đăng xuất Google Drive.';
  showToast('Đã đăng xuất Google Drive OAuth 2.0.', 'info');
  await loadAccountAndIntegrations();
}

async function connectGithub() {
  const tok = document.getElementById('ghTokenInput').value.trim();
  const { ok, data } = await apiFetch('/api/integrations/github/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: tok, verify: true }),
  });
  const txt = ok ? `Đã kết nối @${data.github.login}!` : (`Lỗi: ${data.detail}`);
  document.getElementById('ghMsg').textContent = txt;
  showToast(txt, ok ? 'ok' : 'err');
  if (ok) document.getElementById('ghTokenInput').value = '';
  await loadAccountAndIntegrations();
}

async function disconnectGithub() {
  await apiFetch('/api/integrations/github/disconnect', { method: 'POST' });
  document.getElementById('ghMsg').textContent = 'Đã ngắt kết nối GitHub.';
  showToast('Đã ngắt kết nối GitHub PAT.', 'info');
  await loadAccountAndIntegrations();
}

async function addConnector() {
  const { ok, data } = await apiFetch('/api/integrations/connectors/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: document.getElementById('connName').value.trim(),
      kind: document.getElementById('connKind').value,
      endpoint_url: document.getElementById('connUrl').value.trim(),
      api_key: document.getElementById('connKey').value.trim(),
    }),
  });
  if (!ok) {
    showToast('Lỗi: ' + (data.detail || 'Không thêm được kết nối'), 'err');
    return;
  }
  document.getElementById('connName').value = '';
  document.getElementById('connUrl').value = '';
  document.getElementById('connKey').value = '';
  showToast('Đã thêm kết nối dịch vụ bên thứ 3.', 'ok');
  await loadAccountAndIntegrations();
}

async function removeConnector(name) {
  await apiFetch('/api/integrations/connectors/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  showToast(`Đã gỡ kết nối "${name}".`, 'info');
  await loadAccountAndIntegrations();
}

/* ==================== CÀI ĐẶT, AUTO-UPDATE & GỠ CÀI ĐẶT ==================== */

async function loadAppSettings() {
  const { ok, data } = await apiFetch('/api/settings');
  if (!ok) return;
  const s = data.settings || {};
  const theme = s.theme || 'dark';
  document.documentElement.setAttribute('data-theme', theme);
  updateThemeButton(theme);
  document.getElementById('sTheme').value = theme;
  document.getElementById('sLang').value = s.language || 'vi';
  document.getElementById('sDefaultTab').value = s.default_tab || 'vaults';
  document.getElementById('sUiPort').value = s.ui_port || 8765;
  document.getElementById('sOpenBrowser').checked = !!s.open_browser_on_start;
  document.getElementById('sAutoUpdate').checked = !!s.auto_check_updates;
  document.getElementById('sAutoInstallUpdate').checked = !!s.auto_install_updates;
  document.getElementById('sUpdateChannel').value = s.update_channel || 'stable';
  document.getElementById('sUpdateInterval').value = s.update_check_interval_hours || 6;
  document.getElementById('sBackend').value = s.drive_backend || 'auto';
  document.getElementById('sWorkers').value = s.scan_workers || 32;
  document.getElementById('sCatMode').value = s.catalog_default_mode || 'smart';
  document.getElementById('sGhRepo').value = s.github_repo || 'kariusnocr/storage-management-suite';
  document.getElementById('sDataDir').value = s.data_dir_override || '';
  document.getElementById('sIncScan').checked = !!s.scan_incremental_default;
  document.getElementById('settingsPathsBox').textContent = JSON.stringify(data.paths || {}, null, 2);
  loadUninstallPlan();
  return s;
}

async function saveAppSettings() {
  const payload = {
    theme: document.getElementById('sTheme').value,
    language: document.getElementById('sLang').value,
    default_tab: document.getElementById('sDefaultTab').value,
    ui_port: Number(document.getElementById('sUiPort').value || 8765),
    open_browser_on_start: document.getElementById('sOpenBrowser').checked,
    auto_check_updates: document.getElementById('sAutoUpdate').checked,
    auto_install_updates: document.getElementById('sAutoInstallUpdate').checked,
    update_channel: document.getElementById('sUpdateChannel').value,
    update_check_interval_hours: Number(document.getElementById('sUpdateInterval').value || 6),
    drive_backend: document.getElementById('sBackend').value,
    scan_workers: Number(document.getElementById('sWorkers').value || 32),
    catalog_default_mode: document.getElementById('sCatMode').value,
    github_repo: document.getElementById('sGhRepo').value.trim(),
    data_dir_override: document.getElementById('sDataDir').value.trim(),
    scan_incremental_default: document.getElementById('sIncScan').checked,
  };
  const { ok, data } = await apiFetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const txt = ok ? `Đã lưu cài đặt tại ${data.saved_path}` : (`Lỗi: ${data.detail}`);
  document.getElementById('settingsMsg').textContent = txt;
  showToast(ok ? 'Đã lưu toàn bộ cài đặt KAS.' : txt, ok ? 'ok' : 'err');
  await loadAppSettings();
  await loadOverview();
}

async function resetAppSettings() {
  const yes = await showConfirmModal({
    title: 'Khôi phục cài đặt mặc định',
    message: 'Đặt lại toàn bộ cài đặt phần mềm về giá trị mặc định ban đầu?',
    confirmText: 'Khôi phục',
  });
  if (!yes) return;
  await apiFetch('/api/settings/reset', { method: 'POST' });
  document.getElementById('settingsMsg').textContent = 'Đã khôi phục cài đặt mặc định.';
  showToast('Đã khôi phục cài đặt mặc định.', 'info');
  await loadAppSettings();
}

function renderUpdateState(u) {
  _latestUpdateInfo = u;
  const box = document.getElementById('updateBox');
  const pill = document.getElementById('updateStatusPill');
  const banner = document.getElementById('updateBanner');
  const bannerTxt = document.getElementById('updateBannerText');
  const notesWrap = document.getElementById('updateNotesWrap');
  const notesBox = document.getElementById('updateNotesBox');
  const rbBtn = document.getElementById('btnRollbackUpdate');
  const histBody = document.getElementById('updateHistoryBody');

  if (!u || !u.ok) {
    if (pill) { pill.className = 'pill err'; pill.textContent = 'Lỗi kết nối'; }
    if (box) box.innerHTML = `<span class="pill err">Lỗi</span> ${esc((u && u.error) || 'Không thể kiểm tra cập nhật')}`;
    return;
  }

  if (u.update_available) {
    if (pill) { pill.className = 'pill warn'; pill.textContent = `Có bản mới v${u.latest_version}`; }
    if (box) {
      box.innerHTML = `<span class="pill warn">Có bản mới v${esc(u.latest_version)}!</span> Bản hiện tại: <code>v${esc(u.current_version)}</code> · <a href="${esc(u.release_url)}" target="_blank">${esc(u.release_name)}</a>${u.last_checked_utc ? ` · Kiểm tra lúc ${esc(u.last_checked_utc)}` : ''}`;
    }
    if (banner && !u.is_skipped) {
      banner.style.display = 'flex';
      bannerTxt.innerHTML = `Đã có <strong>Karius Academic System v${esc(u.latest_version)}</strong> (hiện tại: <code>v${esc(u.current_version)}</code>) — sẵn sàng tải &amp; xác thực SHA-256 tự động.`;
    } else if (banner) {
      banner.style.display = 'none';
    }
  } else {
    if (pill) { pill.className = 'pill ok'; pill.textContent = `Mới nhất (v${u.current_version})`; }
    if (box) {
      box.innerHTML = `<span class="pill ok">Bạn đang dùng bản mới nhất (v${esc(u.current_version)})</span> · <a href="${esc(u.release_url)}" target="_blank">${esc(u.release_name)}</a>${u.last_checked_utc ? ` · Kiểm tra lúc ${esc(u.last_checked_utc)}` : ''}`;
    }
    if (banner) banner.style.display = 'none';
  }

  if (u.release_notes && notesWrap && notesBox) {
    notesWrap.style.display = 'block';
    notesBox.textContent = u.release_notes;
  }
  if (rbBtn) {
    rbBtn.style.display = u.rollback_target ? 'inline-flex' : 'none';
    if (u.rollback_target) rbBtn.textContent = `Quay về v${u.rollback_target} (Rollback)`;
  }
  if (histBody) {
    histBody.innerHTML = (u.history || []).map((h) =>
      `<tr><td style="font-size:12px;">${esc(h.timestamp_utc)}</td><td><code>v${esc(h.from_version)} → v${esc(h.to_version)}</code></td><td>${esc(h.kind)}</td><td>${h.sha256_verified ? '<span class="pill ok">SHA-256 ✓</span>' : '<span class="pill info">HTTPS</span>'}</td></tr>`
    ).join('') || '<tr><td colspan="4" style="color:var(--muted);">Chưa có lịch sử cập nhật tự động nào.</td></tr>';
  }
}

async function checkUpdates(force = true) {
  const box = document.getElementById('updateBox');
  if (force && box) box.textContent = 'Đang kiểm tra bản phát hành mới nhất từ GitHub Releases...';
  const url = force ? '/api/update/check?force=true' : '/api/update/status';
  const { ok, data: u } = await apiFetch(url);
  if (ok) {
    renderUpdateState(u);
    if (force) {
      showToast(u.update_available ? `Đã tìm thấy bản mới v${u.latest_version}!` : `Bạn đang dùng bản mới nhất v${u.current_version}.`, u.update_available ? 'warn' : 'ok');
    }
  }
}

async function skipLatestUpdate() {
  if (!_latestUpdateInfo || !_latestUpdateInfo.latest_version) return;
  await apiFetch('/api/update/skip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: _latestUpdateInfo.latest_version }),
  });
  document.getElementById('updateBanner').style.display = 'none';
  showToast(`Đã ẩn nhắc nhở cho phiên bản v${_latestUpdateInfo.latest_version}.`, 'info');
}

function waitForServerReload(expectedVersion) {
  const out = document.getElementById('updateLogOut');
  let attempts = 0;
  const timer = setInterval(async () => {
    attempts += 1;
    try {
      const r = await fetch('/api/health', { cache: 'no-store' });
      if (r.ok) {
        const h = await r.json();
        if (!expectedVersion || h.version === expectedVersion || attempts >= 8) {
          clearInterval(timer);
          window.location.reload();
        }
      }
    } catch (_e) {
      if (out) out.textContent += '.';
    }
    if (attempts > 45) {
      clearInterval(timer);
      if (out) out.textContent += '\nMáy chủ đã khởi động xong — vui lòng tải lại cửa sổ (F5).';
    }
  }, 1200);
}

async function triggerAutoUpdate(isRollback = false) {
  const yes = await showConfirmModal({
    title: isRollback ? 'Quay về phiên bản trước (Rollback)' : 'Cập nhật tự động KAS (SHA-256 Verified)',
    message: isRollback
      ? 'Xác nhận quay về phiên bản trước đó? Máy chủ cục bộ KAS sẽ tự khởi động lại.'
      : 'Tự động tải gói phát hành từ GitHub Releases, kiểm chứng toàn vẹn mật mã SHA-256, cài đặt và tự khởi động lại KAS?',
    confirmText: isRollback ? 'Thực hiện Rollback' : 'Cập nhật ngay',
  });
  if (!yes) return;
  openTab('settings');
  const wrap = document.getElementById('updateLogWrap');
  const out = document.getElementById('updateLogOut');
  const btn = document.getElementById('btnApplyUpdate');
  const pill = document.getElementById('updateStatusPill');
  wrap.style.display = 'block';
  out.textContent = 'Đang khởi chạy tiến trình tự động cập nhật...';
  if (btn) btn.disabled = true;
  if (pill) { pill.className = 'pill warn'; pill.textContent = 'Đang cập nhật...'; }

  const { ok, data: job } = await apiFetch('/api/update/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rollback: !!isRollback, auto_restart: true }),
  });
  if (!ok || !job.id) {
    out.textContent = 'Lỗi: ' + (job.detail || 'Không thể khởi chạy cập nhật');
    showToast(job.detail || 'Không thể khởi chạy cập nhật', 'err');
    if (btn) btn.disabled = false;
    return;
  }

  const poll = async () => {
    try {
      const { ok: pok, data: cur } = await apiFetch('/api/update/jobs/' + encodeURIComponent(job.id));
      if (!pok) {
        waitForServerReload('');
        return;
      }
      out.textContent = (cur.logs || []).join('\n') || 'Đang xử lý...';
      out.scrollTop = out.scrollHeight;
      if (cur.status === 'running') {
        setTimeout(poll, 600);
        return;
      }
      if (btn) btn.disabled = false;
      if (cur.restarting) {
        if (pill) { pill.className = 'pill ok'; pill.textContent = `Đang khởi động lại → v${cur.to_version}...`; }
        showToast(`Đang khởi động lại sang KAS v${cur.to_version}...`, 'ok');
        waitForServerReload(cur.to_version);
        return;
      }
      if (cur.ok) {
        if (pill) { pill.className = 'pill ok'; pill.textContent = cur.updated ? `Đã cập nhật v${cur.to_version}` : 'Đã ở bản mới nhất'; }
        await checkUpdates(false);
      } else {
        if (pill) { pill.className = 'pill err'; pill.textContent = 'Cập nhật thất bại'; }
        showToast('Cập nhật gặp lỗi — kiểm tra nhật kí bên dưới.', 'err');
      }
    } catch (_err) {
      waitForServerReload('');
    }
  };
  setTimeout(poll, 400);
}

async function exportSettings() {
  const { data } = await apiFetch('/api/settings/export');
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `kas-backup-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  showToast('Đã xuất tệp sao lưu cấu hình JSON.', 'ok');
}

async function shutdownServer() {
  const yes = await showConfirmModal({
    title: 'Tắt máy chủ nền KAS',
    message: 'Cửa sổ giao diện sẽ ngừng kết nối cho tới khi bạn khởi chạy lại Karius Academic System.',
    confirmText: 'Tắt máy chủ',
    danger: true,
  });
  if (!yes) return;
  await apiFetch('/api/shutdown', { method: 'POST' });
  document.getElementById('settingsMsg').textContent = 'Đã gửi lệnh tắt máy chủ nền KAS.';
  showToast('Máy chủ nền KAS đang dừng.', 'warn');
}

async function loadUninstallPlan() {
  const rmCfg = !!(document.getElementById('unRmConfig') && document.getElementById('unRmConfig').checked);
  const rmData = !!(document.getElementById('unRmData') && document.getElementById('unRmData').checked);
  const { ok, data: p } = await apiFetch(`/api/uninstall/plan?remove_config=${rmCfg}&remove_data=${rmData}`);
  if (!ok) return;
  const body = document.getElementById('uninstallPlanBody');
  if (!body) return;
  body.innerHTML = (p.items || []).map((it) => {
    const pill = it.selected
      ? '<span class="pill err">Sẽ xóa</span>'
      : (it.exists ? '<span class="pill ok">Giữ lại</span>' : '<span class="pill">Không có</span>');
    const sz = it.size_human && it.size_human !== '—' && it.exists ? ` (${esc(it.size_human)})` : '';
    return `<tr><td>${pill}</td><td style="font-size:12px;">${esc(it.label)}${sz}</td><td style="font-size:11px; color:var(--muted);"><code>${esc(it.path)}</code></td></tr>`;
  }).join('');
  if (p.windows_powershell_cmd && document.getElementById('uninstallPsCmd')) {
    document.getElementById('uninstallPsCmd').textContent = p.windows_powershell_cmd;
  }
}

async function executeUninstallFromUi() {
  const rmCfg = !!document.getElementById('unRmConfig').checked;
  const rmData = !!document.getElementById('unRmData').checked;
  const extraTxt = (rmCfg || rmData)
    ? 'Bạn đã chọn xóa thêm cấu hình/dữ liệu chỉ mục của KAS. Thư mục tài liệu cá nhân và Google Drive vẫn được giữ nguyên tuyệt đối.'
    : 'Cấu hình (~/.config/kas) và dữ liệu chỉ mục (~/.local/share/kas) sẽ được giữ lại an toàn.';
  const confirmed = await showConfirmModal({
    title: 'Gỡ cài đặt Karius Academic System (KAS)',
    message: extraTxt,
    confirmText: 'Gỡ cài đặt vĩnh viễn',
    danger: true,
    requireTyped: 'GO-CAI-DAT',
    placeholder: 'GO-CAI-DAT',
  });
  if (!confirmed) {
    document.getElementById('uninstallMsg').textContent = 'Đã hủy thao tác gỡ cài đặt.';
    return;
  }
  const { ok, data } = await apiFetch('/api/uninstall/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ remove_config: rmCfg, remove_data: rmData, confirm: true, dry_run: false }),
  });
  const txt = ok
    ? (data.message || 'Đang gỡ cài đặt KAS — bạn có thể đóng cửa sổ này.')
    : ('Lỗi: ' + (data.detail || 'Không thể gỡ cài đặt'));
  document.getElementById('uninstallMsg').textContent = txt;
  showToast(txt, ok ? 'warn' : 'err', 6000);
}

/* ==================== KHO DỮ LIỆU (MULTI-VAULT) ==================== */

async function loadVaults() {
  const { ok, data: res } = await apiFetch('/api/vaults');
  if (!ok) return {};
  _vaultsCache = res.vaults || [];
  document.getElementById('vaultCount').textContent = _vaultsCache.length;
  document.getElementById('noVaultBanner').style.display = _vaultsCache.length ? 'none' : 'block';

  const dot = document.getElementById('vaultDot');
  if (dot) dot.style.background = _vaultsCache.length ? 'var(--ok)' : 'var(--warn)';

  const sel = document.getElementById('vaultSelect');
  if (!_vaultsCache.length) {
    sel.innerHTML = '<option value="">(Chưa kết nối kho nào)</option>';
  } else {
    sel.innerHTML = _vaultsCache.map((v) =>
      `<option value="${esc(v.slug)}" ${v.slug === res.active_slug ? 'selected' : ''}>${esc(v.name)} (${v.source_kind === 'local' ? 'Cục bộ' : 'Drive'})</option>`
    ).join('');
  }

  document.getElementById('vaultCards').innerHTML = _vaultsCache.map((v) => {
    const isAct = v.slug === res.active_slug;
    const kindBadge = v.source_kind === 'local'
      ? '<span class="pill ok">Local FS</span>'
      : '<span class="pill info">Google Drive</span>';
    const modeLabel = v.effective_mode === 'academic_v7' ? 'Chuẩn KAS V7' : 'Kho thường';
    return `
      <div class="card interactive ${isAct ? 'vault-active' : ''}">
        <div class="card-head">
          <strong style="font-size:15px;">${esc(v.name)}</strong>
          <div class="row-actions">${kindBadge}<span class="pill warn">${modeLabel}</span></div>
        </div>
        <div class="mono" style="color:var(--muted); margin-bottom:8px;">${esc(v.root)}</div>
        <div style="font-size:12px; color:var(--muted); margin-bottom:14px;">
          Mã kho: <code>${esc(v.slug)}</code> · Quét cuối: ${esc(v.last_scan_utc || 'chưa quét')}
        </div>
        <div class="row-actions">
          ${isAct
            ? '<span class="pill ok">Đang hoạt động</span>'
            : `<button class="btn sm" onclick="switchVault('${esc(v.slug)}')">Chọn kho</button>`}
          <button class="btn secondary sm" onclick="scanVault('${esc(v.slug)}')">Quét chỉ mục</button>
          <button class="btn secondary sm" onclick="removeVault('${esc(v.slug)}')">Gỡ</button>
        </div>
      </div>`;
  }).join('') || '<div class="card" style="color:var(--muted);">Chưa có kho nào được đăng ký. Hãy dán đường dẫn thư mục máy hoặc URL Google Drive vào khung phía trên.</div>';
  return res;
}

async function addVault() {
  const source = document.getElementById('vSource').value.trim();
  const name = document.getElementById('vName').value.trim();
  const mode = document.getElementById('vMode').value;
  const msg = document.getElementById('vaultFormMsg');
  if (!source) {
    msg.textContent = 'Vui lòng nhập đường dẫn hoặc URL Google Drive.';
    showToast('Vui lòng nhập đường dẫn thư mục hoặc URL Google Drive.', 'warn');
    return;
  }
  msg.textContent = 'Đang kết nối kho...';
  const { ok, data } = await apiFetch('/api/vaults/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, name: name || null, mode, activate: true }),
  });
  if (!ok) {
    const errTxt = 'Lỗi: ' + (data.detail || 'Không thể kết nối');
    msg.textContent = errTxt;
    showToast(errTxt, 'err');
    return;
  }
  document.getElementById('vSource').value = '';
  document.getElementById('vName').value = '';
  msg.textContent = `Đã kết nối kho "${data.vault.name}" (${data.vault.slug}).`;
  showToast(`Đã kết nối & kích hoạt kho "${data.vault.name}".`, 'ok');
  await refreshAll();
}

async function switchVault(slug) {
  if (!slug) return;
  const { ok } = await apiFetch('/api/vaults/activate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slug, persist: true }),
  });
  if (ok) showToast(`Đã chuyển sang kho "${slug}".`, 'info', 2200);
  await refreshAll();
}

async function removeVault(slug) {
  const yes = await showConfirmModal({
    title: `Gỡ kho "${slug}"`,
    message: 'Gỡ kho này khỏi danh sách quản lý KAS? Không xóa bất kỳ tệp tin hay thư mục gốc nào của bạn.',
    confirmText: 'Gỡ khỏi danh sách',
    danger: true,
  });
  if (!yes) return;
  await apiFetch('/api/vaults/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slug }),
  });
  showToast(`Đã gỡ kho "${slug}" khỏi danh sách quản lý.`, 'info');
  await refreshAll();
}

async function scanVault(slug) {
  await switchVault(slug);
  document.getElementById('vaultTaskBox').style.display = 'block';
  await runBackgroundTask('quet', [], 'vaultTaskOut');
}

async function runBackgroundTask(command, args, outId) {
  const outEl = document.getElementById(outId);
  outEl.style.display = 'block';
  outEl.textContent = `Đang chạy lệnh: kas ${command} ${args.join(' ')} ...`;
  const { ok, data: task } = await apiFetch('/api/tasks/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command, args }),
  });
  if (!ok) {
    outEl.textContent = 'Lỗi: ' + (task.detail || 'Không chạy được tác vụ');
    showToast(task.detail || 'Không chạy được tác vụ', 'err');
    return;
  }
  showToast(`Đang thực thi tác vụ "kas ${command}"...`, 'info', 2400);
  const poll = setInterval(async () => {
    const { data: st } = await apiFetch('/api/tasks/' + encodeURIComponent(task.id));
    outEl.textContent = st.output || `Trạng thái: ${st.status}...`;
    if (st.status !== 'running') {
      clearInterval(poll);
      showToast(st.status === 'done' ? `Hoàn tất "kas ${command}".` : `Tác vụ "kas ${command}" kết thúc với cảnh báo.`, st.status === 'done' ? 'ok' : 'warn');
      await loadVaults();
      await loadOverview();
    }
  }, 900);
}

async function initVaultStructure() {
  const yes = await showConfirmModal({
    title: 'Khởi tạo khung thư mục Chuẩn KAS V7',
    message: 'Tạo tự động khung thư mục chuẩn ([00] TỔNG QUAN, [01] DANH SÁCH, [02] NHẬT KÍ, [07] KIỂM TRA) cho kho đang chọn?',
    confirmText: 'Khởi tạo khung V7',
  });
  if (!yes) return;
  const { ok, data: res } = await apiFetch('/api/vaults/init-structure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm: true }),
  });
  showToast(ok ? `Đã khởi tạo khung Chuẩn KAS cho "${res.root_name}".` : `Lỗi: ${res.detail}`, ok ? 'ok' : 'err');
  await refreshAll();
}

/* ==================== QUY TẮC ĐẶT TÊN ==================== */

function fillRulesForm(r) {
  document.getElementById('rFolderIndexStyle').value = r.folder_index_style || 'bracket_2';
  document.getElementById('rFolderCase').value = r.folder_case || 'upper';
  document.getElementById('rFileCase').value = r.file_case || 'title';
  document.getElementById('rFileSep').value = r.file_separator ?? ' - ';
  document.getElementById('rMaxLen').value = r.max_name_length ?? 180;
  document.getElementById('rForbiddenChars').value = r.forbidden_chars || '';
  document.getElementById('rFolderReqIdx').checked = !!r.folder_require_index_prefix;
  document.getElementById('rFolderNoUnder').checked = !!r.folder_forbid_underscore;
  document.getElementById('rFileNoIdx').checked = !!r.file_forbid_index_prefix;
  document.getElementById('rFileNoDate').checked = !!r.file_forbid_date_prefix;
  document.getElementById('rFileReqExtra').checked = !!r.file_require_extra_info;
  document.getElementById('rFileNoUnder').checked = !!r.file_forbid_underscore;
  document.getElementById('rLowerExt').checked = !!r.lowercase_extension;
  document.getElementById('rUnicodeNfc').checked = !!r.unicode_nfc;
  document.getElementById('rStripAccents').checked = !!r.strip_accents;
  document.getElementById('rAcronyms').value = Object.values(r.acronyms_upper || {}).join(', ');
  document.getElementById('rIgnored').value = (r.ignored_folders || []).join(', ');
  document.getElementById('rReplacements').value = Object.entries(r.custom_replacements || {})
    .map(([k, v]) => `${k} => ${v}`).join('\n');
  document.getElementById('rRegexBlacklist').value = (r.custom_regex_blacklist || []).join('\n');
}

function collectRulesForm(presetOverride) {
  const acMap = {};
  document.getElementById('rAcronyms').value.split(',').map((x) => x.trim()).filter(Boolean).forEach((x) => {
    acMap[x.toLowerCase()] = x;
  });
  const repMap = {};
  document.getElementById('rReplacements').value.split('\n').map((x) => x.trim()).filter(Boolean).forEach((line) => {
    const idx = line.indexOf('=>');
    if (idx > 0) repMap[line.slice(0, idx).trim()] = line.slice(idx + 2).trim();
  });
  return {
    preset: presetOverride || 'custom',
    folder_index_style: document.getElementById('rFolderIndexStyle').value,
    folder_case: document.getElementById('rFolderCase').value,
    file_case: document.getElementById('rFileCase').value,
    file_separator: document.getElementById('rFileSep').value,
    max_name_length: Number(document.getElementById('rMaxLen').value || 0),
    forbidden_chars: document.getElementById('rForbiddenChars').value,
    folder_require_index_prefix: document.getElementById('rFolderReqIdx').checked,
    folder_forbid_underscore: document.getElementById('rFolderNoUnder').checked,
    file_forbid_index_prefix: document.getElementById('rFileNoIdx').checked,
    file_forbid_date_prefix: document.getElementById('rFileNoDate').checked,
    file_require_extra_info: document.getElementById('rFileReqExtra').checked,
    file_forbid_underscore: document.getElementById('rFileNoUnder').checked,
    lowercase_extension: document.getElementById('rLowerExt').checked,
    unicode_nfc: document.getElementById('rUnicodeNfc').checked,
    strip_accents: document.getElementById('rStripAccents').checked,
    acronyms_upper: acMap,
    ignored_folders: document.getElementById('rIgnored').value.split(',').map((x) => x.trim()).filter(Boolean),
    custom_replacements: repMap,
    custom_regex_blacklist: document.getElementById('rRegexBlacklist').value.split('\n').map((x) => x.trim()).filter(Boolean),
  };
}

async function loadNamingRules() {
  const { ok, data: d } = await apiFetch('/api/rules');
  if (!ok) return;
  _rulesPayload = d;
  document.getElementById('rulesSourceMeta').textContent = `Preset hiện hành: ${d.rules.preset} · Nguồn: ${d.source}`;
  document.getElementById('presetCards').innerHTML = Object.entries(d.presets || {}).map(([key, meta]) => `
    <div class="card interactive ${d.rules.preset === key ? 'preset-active' : ''}" style="cursor:pointer;" onclick="selectPreset('${esc(key)}')">
      <div class="card-head" style="margin-bottom:6px;">
        <strong>${esc(meta.name)}</strong>
        <span class="pill ${d.rules.preset === key ? 'ok' : 'info'}">${esc(key)}</span>
      </div>
      <div style="font-size:12px; color:var(--muted);">${esc(meta.description)}</div>
    </div>
  `).join('');
  fillRulesForm(d.rules);
  await livePreviewRule();
}

async function selectPreset(presetKey) {
  if (!_rulesPayload || !_rulesPayload.presets[presetKey]) return;
  fillRulesForm(_rulesPayload.presets[presetKey].rules);
  document.getElementById('rulesSaveMsg').textContent = `Đã nạp mẫu "${presetKey}" — bấm "Lưu cho Kho hiện tại" hoặc "Lưu mặc định Toàn cục" để áp dụng.`;
  await livePreviewRule(presetKey);
}

async function saveNamingRules(scope) {
  const rules = collectRulesForm();
  const { ok, data: r } = await apiFetch('/api/rules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope, rules }),
  });
  const txt = ok
    ? `Đã lưu quy tắc đặt tên (${scope === 'global' ? 'Toàn cục' : 'Kho hiện tại'}) tại: ${r.saved_path}`
    : `Lỗi: ${r.detail}`;
  document.getElementById('rulesSaveMsg').textContent = txt;
  showToast(ok ? 'Đã lưu quy tắc đặt tên.' : txt, ok ? 'ok' : 'err');
  await loadNamingRules();
}

async function resetNamingRules(scope) {
  await apiFetch('/api/rules/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope }),
  });
  document.getElementById('rulesSaveMsg').textContent = 'Đã khôi phục quy tắc đặt tên về mặc định của kho.';
  showToast('Đã khôi phục quy tắc đặt tên mặc định.', 'info');
  await loadNamingRules();
}

async function livePreviewRule(presetOverride) {
  const sample = document.getElementById('ruleTestInput').value;
  const isFolder = document.getElementById('ruleTestIsFolder').checked;
  const box = document.getElementById('rulePreviewBox');
  if (!sample) { box.innerHTML = ''; return; }
  const rules = collectRulesForm(presetOverride);
  const { ok, data: res } = await apiFetch('/api/rules/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: sample, is_folder: isFolder, rules }),
  });
  if (!ok) return;
  const item = (res.results || [])[0];
  if (!item) return;
  const badge = item.compliant
    ? '<span class="pill ok">ĐẠT CHUẨN 100%</span>'
    : `<span class="pill warn">${item.issues.length} PHÁT HIỆN</span>`;
  const issuesHtml = item.issues.map((i) => {
    const cls = i.severity === 'LỖI' ? 'err' : (i.severity === 'CẢNH BÁO' ? 'warn' : 'info');
    return `<div style="margin-top:6px;"><span class="pill ${cls}">${esc(i.severity)}</span> <code>${esc(i.code)}</code> — ${esc(i.description)}</div>`;
  }).join('');
  box.innerHTML = `
    <div class="row-actions" style="margin-bottom:8px;">${badge} <span>Gốc: <code>${esc(item.original)}</code></span> → <span>Đề xuất: <strong style="color:var(--ok);">${esc(item.suggested)}</strong></span></div>
    ${issuesHtml}
  `;
}

/* ==================== TRỢ LÝ AI & AGENT (MCP) ==================== */

async function loadAiPanel() {
  const { ok, data: d } = await apiFetch('/api/ai/config');
  if (!ok) return;
  _aiPayload = d;
  const c = d.config || {};
  document.getElementById('aiProvider').value = c.provider || 'builtin_offline';
  document.getElementById('aiModel').value = c.model || '';
  document.getElementById('aiBaseUrl').value = c.base_url || '';
  document.getElementById('aiApiKey').value = '';
  document.getElementById('aiKeyStatus').textContent = c.has_api_key ? `(Đã lưu: ${c.api_key_masked})` : '(Chưa đặt)';
  document.getElementById('aiActiveBadge').textContent = `Provider: ${c.provider} · Model: ${c.model}`;
  renderMcpSnippet();
  if (_chatHistory.length === 0 && !document.getElementById('chatBox').children.length) {
    appendChat('bot', 'Xin chào! Tôi là Trợ Lý AI & Agent của Karius Academic System (KAS). Hãy bấm một gợi ý phía trên hoặc nhập câu hỏi bất kỳ để thao tác trên kho dữ liệu của bạn.');
  }
}

function onAiProviderChange() {
  if (!_aiPayload) return;
  const p = document.getElementById('aiProvider').value;
  const meta = _aiPayload.providers[p];
  if (meta) {
    document.getElementById('aiModel').value = meta.default_model || '';
    document.getElementById('aiBaseUrl').value = meta.default_base_url || '';
  }
}

async function saveAiConfig(clearKey) {
  const payload = {
    provider: document.getElementById('aiProvider').value,
    model: document.getElementById('aiModel').value.trim(),
    base_url: document.getElementById('aiBaseUrl').value.trim(),
    clear_api_key: !!clearKey,
  };
  const k = document.getElementById('aiApiKey').value.trim();
  if (k && !clearKey) payload.api_key = k;
  const { ok, data: r } = await apiFetch('/api/ai/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  document.getElementById('aiCfgMsg').textContent = ok ? 'Đã lưu!' : ('Lỗi: ' + r.detail);
  showToast(ok ? 'Đã lưu cấu hình AI Provider.' : ('Lỗi: ' + r.detail), ok ? 'ok' : 'err');
  await loadAiPanel();
}

function renderMcpSnippet() {
  if (!_aiPayload || !_aiPayload.mcp) return;
  const key = document.getElementById('mcpClientSel').value;
  const cfgObj = _aiPayload.mcp[key] || _aiPayload.mcp.claude_desktop;
  document.getElementById('mcpJsonBox').textContent = JSON.stringify(cfgObj, null, 2);
}

async function copyMcpJson() {
  const txt = document.getElementById('mcpJsonBox').textContent;
  try {
    await navigator.clipboard.writeText(txt);
    document.getElementById('mcpCopyMsg').textContent = 'Đã sao chép!';
    showToast('Đã sao chép cấu hình MCP JSON vào bộ nhớ tạm.', 'ok', 2200);
    setTimeout(() => { document.getElementById('mcpCopyMsg').textContent = ''; }, 2500);
  } catch (_e) {
    document.getElementById('mcpCopyMsg').textContent = 'Hãy bôi đen & Ctrl+C';
  }
}

function appendChat(role, text, toolCalls) {
  const box = document.getElementById('chatBox');
  const div = document.createElement('div');
  div.className = 'chat-msg ' + (role === 'user' ? 'user' : 'bot');
  let html = '';
  if (toolCalls && toolCalls.length) {
    html += '<div class="chat-tools">' + toolCalls.map((t) => `<span class="pill info">MCP · ${esc(t.tool)}</span>`).join('') + '</div>';
  }
  html += esc(text);
  div.innerHTML = html;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function clearChat() {
  _chatHistory = [];
  document.getElementById('chatBox').innerHTML = '';
  appendChat('bot', 'Đã làm mới cuộc hội thoại. Bạn muốn tra cứu hoặc kiểm toán gì trên kho hiện tại?');
}

function quickAsk(text) {
  document.getElementById('chatInput').value = text;
  sendChat();
}

async function sendChat() {
  const inp = document.getElementById('chatInput');
  const btn = document.getElementById('chatSendBtn');
  const msg = inp.value.trim();
  if (!msg) return;
  inp.value = '';
  appendChat('user', msg);
  btn.disabled = true;
  btn.textContent = 'Đang xử lý...';
  try {
    const { ok, data } = await apiFetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, history: _chatHistory.slice(-10) }),
    });
    if (!ok) {
      appendChat('bot', 'Lỗi AI Provider: ' + (data.detail || 'Không phản hồi'));
    } else {
      appendChat('bot', data.reply || '', data.tool_calls || []);
      _chatHistory.push({ role: 'user', content: msg });
      _chatHistory.push({ role: 'assistant', content: data.reply || '' });
    }
  } catch (err) {
    appendChat('bot', 'Không thể kết nối máy chủ cục bộ: ' + err);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Gửi';
  }
}

/* ==================== TỔNG QUAN / TÌM KIẾM / V7 / KIỂM TOÁN / UNDO / DOCTOR ==================== */

async function loadOverview() {
  const { ok, data: d } = await apiFetch('/api/overview');
  if (!ok) return;
  const verEl = document.getElementById('verTag');
  if (verEl) verEl.textContent = 'v' + d.version;
  document.title = `Karius Academic System (KAS) v${d.version}`;
  const modeText = d.vault_mode === 'academic_v7' ? 'Chuẩn KAS V7' : 'Kho thường';
  const subEl = document.getElementById('rootSubtitle');
  if (subEl) {
    subEl.textContent = d.has_vault
      ? `Kho đang chọn: ${d.root_name} · ${modeText} · backend=${d.drive_backend.selected}`
      : 'Chưa chọn kho — vào mục "Kho Dữ Liệu" để kết nối thư mục máy tính hoặc Google Drive';
  }

  const cv7 = d.catalog_v7 || {};
  const targetCat = Number(cv7.target_eligible_catalogs || 0);
  const renameCnt = Number(cv7.renames_count || 0);
  const v7Pct = targetCat > 0 ? Math.max(8, Math.min(100, Math.round(((targetCat - renameCnt) / targetCat) * 100))) : 100;
  const junkCnt = Number(d.system_junk_count || 0);

  const kpis = [
    { t: 'Tổng thư mục', v: fmt(d.stats.folders), s: `Cập nhật: ${d.stats.last_import_utc || 'chưa quét'}`, bar: null },
    { t: 'Tổng tệp tin', v: fmt(d.stats.files), s: `SQLite FTS5: ${d.stats.db_size_human}`, bar: null },
    { t: 'Tổng dung lượng', v: d.stats.size_human, s: `Chế độ: ${modeText}`, bar: null },
    {
      t: 'Danh mục V7',
      v: `${fmt(cv7.existing_sheets || 0)} → ${fmt(targetCat)}`,
      s: `Đổi tên: ${fmt(renameCnt)} · Tinh gọn: ${fmt(cv7.prunes_count || 0)}`,
      bar: { pct: v7Pct, cls: renameCnt === 0 ? 'ok' : '' },
    },
    {
      t: 'Rác hệ thống',
      v: fmt(junkCnt),
      s: junkCnt === 0 ? 'Kho sạch sẽ (.DS_Store / Thumbs.db)' : 'MACOSX / .DS_Store / Thumbs.db',
      bar: { pct: junkCnt === 0 ? 100 : Math.min(100, junkCnt * 12), cls: junkCnt === 0 ? 'ok' : 'warn' },
    },
  ];
  document.getElementById('kpiGrid').innerHTML = kpis.map((k) => `
    <div class="card">
      <div class="card-title">${esc(k.t)}</div>
      <div class="card-val">${esc(k.v)}</div>
      <div class="card-sub">${esc(k.s)}</div>
      ${k.bar ? `<div class="kpi-bar ${k.bar.cls}"><span style="width:${k.bar.pct}%"></span></div>` : ''}
    </div>
  `).join('');

  const branches = d.branches || [];
  const totalBytes = Math.max(1, branches.reduce((acc, b) => acc + Number(b.bytes || 0), 0));
  const maxBytes = Math.max(1, ...branches.map((b) => Number(b.bytes || 0)));

  document.getElementById('branchTable').innerHTML = branches.map((b) => {
    const bytes = Number(b.bytes || 0);
    const relPct = Math.max(bytes > 0 ? 4 : 0, Math.round((bytes / maxBytes) * 100));
    const sharePct = Math.round((bytes / totalBytes) * 100);
    return `
      <tr>
        <td><strong>${esc(b.name)}</strong></td>
        <td>${fmt(b.folders)}</td>
        <td>${fmt(b.files)}</td>
        <td>
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="min-width:66px; font-weight:600;">${esc(b.size_human)}</span>
            <span style="font-size:11px; color:var(--muted); min-width:34px;">${sharePct}%</span>
          </div>
        </td>
        <td class="bar-cell">
          <div class="storage-bar-track" title="${esc(b.name)}: ${esc(b.size_human)} (${sharePct}%)">
            <div class="storage-bar-fill" style="width:${relPct}%"></div>
          </div>
        </td>
      </tr>`;
  }).join('') || '<tr><td colspan="5" style="color:var(--muted);">Chưa có chỉ mục — bấm "Quét chỉ mục kho" ở góc trên để lập chỉ mục ngay.</td></tr>';
}

async function runSearch() {
  const q = document.getElementById('searchInput').value.trim();
  if (!q) return;
  const { ok, data: d } = await apiFetch('/api/search?q=' + encodeURIComponent(q));
  if (!ok) return;
  document.getElementById('searchMeta').textContent = `Tìm thấy ${fmt(d.count)} kết quả trong ${d.elapsed_ms} ms`;
  document.getElementById('searchBody').innerHTML = (d.results || []).map((r) =>
    `<tr><td><strong>${esc(r.name)}</strong></td><td style="color:var(--muted)">${esc(r.parent_path)}</td><td>${esc(r.size_human)}</td><td><a href="${esc(r.url)}" target="_blank">Mở</a></td></tr>`
  ).join('') || '<tr><td colspan="4" style="color:var(--muted);">Không có kết quả phù hợp.</td></tr>';
}

async function loadCatalogPlan() {
  const mode = document.getElementById('catMode').value;
  const { ok, data: d } = await apiFetch('/api/catalog-v7/plan?mode=' + encodeURIComponent(mode));
  if (!ok) return;
  const s = d.summary || {};
  const cards = [
    ['Bảng hiện có', fmt(s.existing_sheets)],
    ['Mục tiêu tinh gọn V7', fmt(s.target_eligible_catalogs)],
    ['Đổi tên chuẩn V7', fmt(s.renames_count)],
    ['Tinh gọn / Rác kỹ thuật', `${fmt(s.prunes_count)} (${fmt(s.prunes_junk_count)} rác)`],
  ];
  document.getElementById('catKpis').innerHTML = cards.map(([t, v]) =>
    `<div class="card"><div class="card-title">${esc(t)}</div><div class="card-val">${esc(v)}</div></div>`
  ).join('');
  document.getElementById('catRenamesBody').innerHTML = (d.renames || []).slice(0, 50).map((r) =>
    `<tr><td>${esc(r.old_name)}</td><td><span class="pill ok">${esc(r.new_name)}</span></td><td style="color:var(--muted)">${esc(r.source_path)}</td></tr>`
  ).join('') || '<tr><td colspan="3" style="color:var(--muted);">Không có bảng danh mục nào cần đổi tên.</td></tr>';
}

async function executeCatalogV7() {
  const mode = document.getElementById('catMode').value;
  const yes = await showConfirmModal({
    title: 'Thực thi Chuẩn Danh Mục V7',
    message: 'Xác nhận áp dụng chuẩn hóa Danh Mục V7 lên kho đang chọn? Mọi thao tác đều lưu trong Unified Undo Journal và có thể hoàn tác 1 bước.',
    confirmText: 'Thực thi V7',
  });
  if (!yes) return;
  const { data: r } = await apiFetch('/api/catalog-v7/execute', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, apply_prunes: true, confirm: true }),
  });
  showToast(`Hoàn tất V7: đổi tên ${r.renamed || 0}, tinh gọn ${r.pruned || 0}, lỗi ${(r.errors || []).length}. Mã lô: ${r.batch_id || '—'}`, (r.errors || []).length ? 'warn' : 'ok', 5000);
  await refreshAll();
}

async function loadAudit() {
  const { ok, data: d } = await apiFetch('/api/audit?limit=100');
  if (!ok) return;
  document.getElementById('auditTitle').textContent = `Kiểm toán kho (chế độ: ${d.vault_mode === 'academic_v7' ? 'Chuẩn KAS V7' : 'Kho thường'})`;
  document.getElementById('auditSummary').innerHTML = (d.by_code || []).slice(0, 12).map((x) => {
    const cls = x.severity === 'LỖI' ? 'err' : (x.severity === 'CẢNH BÁO' ? 'warn' : 'ok');
    return `<span class="pill ${cls}">${esc(x.code)}: ${fmt(x.count)}</span>`;
  }).join('') || '<span class="pill ok">Không phát hiện vấn đề nào</span>';
  document.getElementById('auditBody').innerHTML = (d.items || []).map((it) => {
    const cls = it.severity === 'LỖI' ? 'err' : (it.severity === 'CẢNH BÁO' ? 'warn' : 'ok');
    return `<tr><td><span class="pill ${cls}">${esc(it.severity)}</span></td><td><code>${esc(it.code)}</code></td><td>${esc(it.name)}</td><td>${esc(it.description)}</td><td>${esc(it.suggestion)}</td></tr>`;
  }).join('') || '<tr><td colspan="5" style="color:var(--muted);">Không có vi phạm.</td></tr>';
}

async function loadUndo() {
  const { ok, data: d } = await apiFetch('/api/undo/batches');
  if (!ok) return;
  document.getElementById('undoBody').innerHTML = (d.batches || []).map((b) =>
    `<tr><td><code>${esc(b.batch_id)}</code></td><td>${esc(b.kind)}</td><td>${fmt(b.action_count)}</td><td>${esc(b.description)}</td><td>${b.undone_at ? '<span class="pill ok">Đã hoàn tác</span>' : '<span class="pill warn">Có thể hoàn tác</span>'}</td><td>${b.undone_at ? '' : `<button class="btn secondary sm" onclick="runUndo('${esc(b.batch_id)}')">Hoàn tác</button>`}</td></tr>`
  ).join('') || '<tr><td colspan="6" style="color:var(--muted);">Chưa có lô thao tác nào trong kho này.</td></tr>';
}

async function runUndo(bid) {
  const yes = await showConfirmModal({
    title: `Hoàn tác lô ${bid}`,
    message: 'Khôi phục tên và vị trí các tệp/thư mục về trạng thái trước khi chạy lô này?',
    confirmText: 'Hoàn tác ngay',
  });
  if (!yes) return;
  const { data: r } = await apiFetch(`/api/undo/${encodeURIComponent(bid)}?execute=true`, { method: 'POST' });
  showToast(`Kết quả hoàn tác: ${r.reverted || 0}/${r.total || 0} (lỗi: ${(r.errors || []).length})`, (r.errors || []).length ? 'warn' : 'ok');
  loadUndo();
}

async function loadDoctor() {
  const { ok, data: d } = await apiFetch('/api/doctor');
  if (!ok) return;
  document.getElementById('doctorOut').textContent = JSON.stringify(d, null, 2);

  const drv = d.drive || {};
  const apiOk = drv.api && drv.api.authenticated;
  const gh = d.github || {};
  const ocr = d.ocr || {};
  const plan = d.setup_plan || {};
  const pyOkCnt = (d.python_packages || []).filter((p) => p.ok).length;
  const pyTotCnt = (d.python_packages || []).length;
  const cliOkCnt = (d.cli_tools || []).filter((t) => t.ok).length;
  const cliTotCnt = (d.cli_tools || []).length;

  const kpis = [
    ['Trình điều khiển kho', drv.selected || 'local', apiOk ? 'Google Drive OAuth: Đã đăng nhập' : (drv.cli && drv.cli.available ? 'Cloud gdrive CLI sẵn sàng' : 'Local FS sẵn sàng')],
    ['GitHub (gh / PAT)', gh.authenticated ? 'Đã kết nối' : (gh.available ? 'Có gh CLI' : 'Chưa kết nối'), gh.pat_connected ? ('PAT: @' + (gh.pat_login || '')) : (gh.path || 'Chạy tự động cài')],
    ['OCR Tiếng Việt', ocr.vietnamese_ready ? 'vie+eng Sẵn sàng' : (ocr.vie_traineddata_downloaded ? 'Đã tải vie.traineddata' : 'Chưa cài'), ocr.lang ? ('Đang dùng: ' + ocr.lang) : 'Cần tesseract + vie.traineddata'],
    ['Thư viện Python', `${pyOkCnt} / ${pyTotCnt}`, (plan.missing_python || []).length ? `Thiếu ${plan.missing_python.length} thư viện khuyến nghị` : 'Đã đủ thư viện'],
    ['Công cụ hệ thống', `${cliOkCnt} / ${cliTotCnt}`, (plan.missing_tools || []).length ? `Thiếu ${plan.missing_tools.length} nhóm công cụ` : 'Đã cài đầy đủ'],
  ];
  document.getElementById('doctorKpis').innerHTML = kpis.map(([t, v, s]) =>
    `<div class="card"><div class="card-title">${esc(t)}</div><div class="card-val" style="font-size:18px;">${esc(v)}</div><div class="card-sub">${esc(s)}</div></div>`
  ).join('');

  document.getElementById('docPyBody').innerHTML = (d.python_packages || []).map((p) => {
    const badge = p.ok
      ? '<span class="pill ok">✓ Đã cài</span>'
      : (p.blocked_by_sac ? '<span class="pill warn">⚠ Bị SAC chặn</span>' : (p.required ? '<span class="pill err">✗ Thiếu</span>' : '<span class="pill warn">○ Chưa cài</span>'));
    const info = p.ok ? esc(p.version) : (p.blocked_by_sac ? 'KAS tự dự phòng thuần Python' : (p.name === 'pywebview' ? 'Tùy chọn (Windows SAC dùng Edge App)' : (p.required ? 'Bắt buộc' : 'Tùy chọn')));
    return `<tr><td><code>${esc(p.name)}</code></td><td>${badge}</td><td style="font-size:12px; color:var(--muted);">${info}</td></tr>`;
  }).join('');

  document.getElementById('docCliBody').innerHTML = (d.cli_tools || []).map((t) => {
    const badge = t.ok ? '<span class="pill ok">✓ Đã cài</span>' : '<span class="pill warn">○ Chưa cài</span>';
    return `<tr><td><code>${esc(t.name)}</code></td><td style="font-size:12px;">${esc(t.purpose)}</td><td style="font-size:12px; color:var(--muted);">${badge} ${t.path ? `<code>${esc(t.path)}</code>` : ''}</td></tr>`;
  }).join('');
}

async function runAutoSetup(scope) {
  const btn = document.getElementById('btnSetupAll');
  const wrap = document.getElementById('setupLogWrap');
  const out = document.getElementById('setupLogOut');
  const pill = document.getElementById('setupStatusPill');
  wrap.style.display = 'block';
  pill.style.display = 'inline-flex';
  pill.className = 'pill warn';
  pill.textContent = 'Đang tự động cài đặt...';
  out.textContent = 'Đang khởi chạy trình tự động cài đặt KAS...';
  if (btn) btn.disabled = true;

  const { ok, data: job } = await apiFetch('/api/setup/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope }),
  });
  if (!ok || !job.id) {
    pill.className = 'pill err';
    pill.textContent = 'Lỗi khởi chạy';
    out.textContent = job.detail || 'Không thể khởi chạy tác vụ cài đặt.';
    showToast(job.detail || 'Không thể khởi chạy tự cài đặt', 'err');
    if (btn) btn.disabled = false;
    return;
  }

  const poll = async () => {
    const { ok: pok, data: cur } = await apiFetch('/api/setup/jobs/' + encodeURIComponent(job.id));
    if (!pok) return;
    out.textContent = (cur.logs || []).join('\n') || 'Đang xử lý...';
    out.scrollTop = out.scrollHeight;
    if (cur.status === 'running') {
      setTimeout(poll, 700);
      return;
    }
    if (btn) btn.disabled = false;
    if (cur.status === 'done') {
      pill.className = 'pill ok';
      pill.textContent = 'Hoàn tất ✓';
      showToast('Đã tự động cài đặt công cụ & thư viện thành công!', 'ok');
    } else {
      pill.className = 'pill warn';
      pill.textContent = 'Hoàn tất (có cảnh báo)';
      showToast('Hoàn tất cài đặt với một số cảnh báo.', 'warn');
    }
    await loadDoctor();
  };
  setTimeout(poll, 400);
}

/* ==================== BOOTSTRAP & KEYBOARD SHORTCUTS ==================== */

async function refreshAll() {
  const locked = await checkAccountGate();
  if (locked) return;
  const s = await loadAppSettings();
  const v = await loadVaults();
  await loadOverview();
  if (s && s.auto_check_updates) {
    checkUpdates(false).catch(() => {});
  }
  if (!window._kasInitialized) {
    const targetTab = (s && s.default_tab && s.default_tab !== 'vaults')
      ? s.default_tab
      : ((v.vaults && v.vaults.length > 0) ? 'overview' : 'vaults');
    openTab(targetTab);
    window._kasInitialized = true;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  restoreSidebarState();
  updateThemeButton(document.documentElement.getAttribute('data-theme') || 'dark');

  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => openTab(btn.dataset.tab));
  });

  const paletteOv = document.getElementById('paletteOverlay');
  if (paletteOv) {
    paletteOv.addEventListener('click', (e) => {
      if (e.target === paletteOv) closeCommandPalette();
    });
  }

  const confirmOv = document.getElementById('confirmOverlay');
  if (confirmOv) {
    confirmOv.addEventListener('click', (e) => {
      if (e.target === confirmOv) closeConfirmModal(false);
    });
  }

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      const ov = document.getElementById('paletteOverlay');
      if (ov && ov.classList.contains('open')) closeCommandPalette();
      else openCommandPalette();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
      e.preventDefault();
      toggleSidebar();
    } else if (e.key === 'Escape') {
      const cOv = document.getElementById('confirmOverlay');
      if (cOv && cOv.classList.contains('open')) {
        closeConfirmModal(false);
        return;
      }
      const pOv = document.getElementById('paletteOverlay');
      if (pOv && pOv.classList.contains('open')) {
        closeCommandPalette();
      }
    }
  });

  refreshAll();
});
