// ── Admin Panel JS ────────────────────────────────────────────────────────────
'use strict';

const API_BASE = '/api/v1';
let categoriesData = [];
let qPage = 1;
let usersPage = 1;
let charts = {};

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    const token = localStorage.getItem('access_token');
    if (!token) { window.location.href = '/login'; return; }

    const ok = await loadUserInfo();
    if (!ok) return; // blocked by role check / promotion UI shown

    await loadCategories();
    await loadDashboard();
    setupSidebar();
    setupSearchDebounce();
});

// ── Sidebar ───────────────────────────────────────────────────────────────────
function setupSidebar() {
    document.querySelectorAll('.admin-menu-item[data-section]').forEach(item => {
        item.addEventListener('click', () => showSection(item.dataset.section));
    });
    document.querySelector('[data-action="logout"]')?.addEventListener('click', () => {
        localStorage.clear();
        window.location.href = '/login';
    });
}

function showSection(name) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.admin-menu-item').forEach(i => i.classList.remove('active'));
    const sec = document.getElementById(`${name}-section`);
    if (sec) sec.classList.add('active');
    document.querySelector(`[data-section="${name}"]`)?.classList.add('active');
    document.getElementById('section-title').textContent =
        name.replace('-', ' ').replace(/\b\w/g, c => c.toUpperCase());

    if (name === 'questions') loadQuestions();
    if (name === 'users') loadUsers();
    if (name === 'categories') loadCategories();
    if (name === 'analytics') loadAnalytics();
}

// ── User Info + Admin Gate ────────────────────────────────────────────────────
async function loadUserInfo() {
    try {
        const res = await apiFetch(`${API_BASE}/auth/me`);
        const json = await res.json();
        if (!res.ok) { window.location.href = '/login'; return false; }

        const data = json.data;

        if (data.user.role !== 'admin') {
            showPromotionUI(data.user);
            return false;
        }

        document.getElementById('admin-username').textContent = data.user.username;
        const initial = data.user.username[0].toUpperCase();
        document.getElementById('admin-avatar-circle').textContent = initial;
        return true;
    } catch {
        window.location.href = '/login';
        return false;
    }
}

function showPromotionUI(user) {
    document.querySelector('.admin-sidebar').style.display = 'none';
    const main = document.querySelector('.admin-main');
    main.innerHTML = `
        <div class="promotion-wrap">
            <div class="promotion-card">
                <div class="promo-icon">🔐</div>
                <h2>Admin Access Required</h2>
                <p>Logged in as <strong>${escapeHtml(user.username)}</strong> (${escapeHtml(user.email)})</p>
                <p class="promo-sub">Your account role is <code>${user.role}</code>. Admin access is needed to view this panel.</p>

                <div class="promo-divider"><span>Promote via Secret Key</span></div>
                <p class="promo-hint">Ask your server administrator for the <code>ADMIN_SECRET_KEY</code>, then enter it below.</p>

                <div class="promo-form">
                    <input type="password" id="promo-secret" class="promo-input" placeholder="Enter admin secret key…" />
                    <button class="btn-primary" id="promo-btn" onclick="promoteToAdmin()">
                        <i class="fas fa-shield-alt"></i> Promote Me to Admin
                    </button>
                </div>
                <div id="promo-msg" class="promo-msg"></div>

                <div class="promo-divider"><span>Or use the terminal</span></div>
                <div class="promo-code">
                    <code>flask --app app make-admin ${escapeHtml(user.email)}</code>
                </div>
                <p class="promo-hint">Run this on the server, then refresh this page.</p>

                <div class="promo-footer">
                    <a href="/Dashboard" class="btn-secondary-link">← Back to Dashboard</a>
                    <button class="btn-secondary" onclick="localStorage.clear(); window.location.href='/login'">Log out</button>
                </div>
            </div>
        </div>
    `;
}

async function promoteToAdmin() {
    const secret = document.getElementById('promo-secret')?.value.trim();
    const msgEl = document.getElementById('promo-msg');
    const btn = document.getElementById('promo-btn');

    if (!secret) {
        if (msgEl) { msgEl.textContent = 'Please enter the secret key.'; msgEl.className = 'promo-msg error'; }
        return;
    }

    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Promoting…'; }

    const res = await apiFetch(`${API_BASE}/auth/make-admin`, {
        method: 'POST',
        body: JSON.stringify({ secret_key: secret })
    });
    const data = await res.json();

    if (!res.ok) {
        if (msgEl) { msgEl.textContent = data.error || 'Promotion failed. Check the secret key.'; msgEl.className = 'promo-msg error'; }
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-shield-alt"></i> Promote Me to Admin'; }
        return;
    }

    if (msgEl) { msgEl.textContent = '✅ You are now admin! Reloading…'; msgEl.className = 'promo-msg success'; }
    setTimeout(() => window.location.reload(), 1200);
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDashboard() {
    try {
        const res = await apiFetch(`${API_BASE}/admin/dashboard`);
        if (res.status === 403) { showNotification('Admin access denied', 'error'); return; }
        if (!res.ok) throw new Error();
        const data = await res.json();
        const s = data.stats;

        setText('stat-total-users', s.total_users);
        setText('stat-total-questions', s.total_questions);
        setText('stat-total-tests', s.total_tests);
        setText('stat-total-categories', s.total_categories);
        setText('stat-avg-accuracy', `${s.avg_accuracy}%`);
        setText('stat-admin-users', s.admin_users);
        setText('stat-new-users', `+${s.new_users_7d} this week`);
        setText('stat-active-q', `${s.active_questions} active`);
        setText('stat-tests-7d', `+${s.tests_7d} this week`);

        renderCharts(data.charts);
        renderTopUsers(data.top_users);
        renderRecentActivity(data.recent_activity);
    } catch (e) {
        showNotification('Failed to load dashboard data', 'error');
    }
}

function renderCharts(charts_data) {
    destroyChart('registrations-chart');
    destroyChart('tests-chart');
    destroyChart('category-chart');
    destroyChart('difficulty-chart');

    const gold = '#ead690';

    charts['registrations-chart'] = new Chart(document.getElementById('registrations-chart'), {
        type: 'line',
        data: {
            labels: charts_data.daily_registrations.map(d => d.date),
            datasets: [{
                label: 'New Users',
                data: charts_data.daily_registrations.map(d => d.count),
                borderColor: gold,
                backgroundColor: 'rgba(234,214,144,0.15)',
                fill: true, tension: 0.4, pointBackgroundColor: gold,
            }]
        },
        options: chartOptions()
    });

    charts['tests-chart'] = new Chart(document.getElementById('tests-chart'), {
        type: 'bar',
        data: {
            labels: charts_data.daily_tests.map(d => d.date),
            datasets: [{
                label: 'Tests',
                data: charts_data.daily_tests.map(d => d.count),
                backgroundColor: 'rgba(234,214,144,0.7)',
                borderColor: gold, borderWidth: 1, borderRadius: 4,
            }]
        },
        options: chartOptions()
    });

    const catColors = ['#ead690','#a29bfe','#fd79a8','#55efc4','#74b9ff','#fdcb6e','#e17055','#00cec9','#6c5ce7'];
    charts['category-chart'] = new Chart(document.getElementById('category-chart'), {
        type: 'doughnut',
        data: {
            labels: charts_data.questions_by_category.map(d => d.category),
            datasets: [{
                data: charts_data.questions_by_category.map(d => d.count),
                backgroundColor: catColors, borderWidth: 2, borderColor: '#fff',
            }]
        },
        options: { plugins: { legend: { position: 'bottom', labels: { color: '#333', font: { size: 11 } } } }, cutout: '60%' }
    });

    const diffColors = { easy: '#55efc4', medium: '#fdcb6e', hard: '#e17055' };
    charts['difficulty-chart'] = new Chart(document.getElementById('difficulty-chart'), {
        type: 'pie',
        data: {
            labels: charts_data.questions_by_difficulty.map(d => d.difficulty),
            datasets: [{
                data: charts_data.questions_by_difficulty.map(d => d.count),
                backgroundColor: charts_data.questions_by_difficulty.map(d => diffColors[d.difficulty] || '#a29bfe'),
                borderWidth: 2, borderColor: '#fff',
            }]
        },
        options: { plugins: { legend: { position: 'bottom', labels: { color: '#333' } } } }
    });
}

function chartOptions() {
    return {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
            x: { ticks: { color: '#555', font: { size: 10 } }, grid: { color: 'rgba(0,0,0,0.04)' } },
            y: { ticks: { color: '#555' }, grid: { color: 'rgba(0,0,0,0.04)' }, beginAtZero: true }
        }
    };
}

function destroyChart(id) { if (charts[id]) { charts[id].destroy(); delete charts[id]; } }

function renderTopUsers(users) {
    const tbody = document.getElementById('top-users-body');
    if (!tbody) return;
    tbody.innerHTML = users.map((u, i) => `
        <tr>
            <td>${i + 1}</td>
            <td>${u.username}</td>
            <td><strong>${u.xp.toLocaleString()}</strong></td>
            <td><span class="badge badge-${u.role}">${u.role}</span></td>
        </tr>
    `).join('');
}

function renderRecentActivity(activity) {
    const el = document.getElementById('recent-activity-list');
    if (!el) return;
    if (!activity.length) { el.innerHTML = '<p class="empty-msg">No recent activity</p>'; return; }
    el.innerHTML = activity.map(a => `
        <div class="activity-item">
            <div class="activity-info">
                <strong>${a.user}</strong>
                <span>${a.category}</span>
            </div>
            <div class="activity-meta">
                <span class="accuracy-badge ${a.score >= 70 ? 'good' : a.score >= 40 ? 'ok' : 'bad'}">${a.score}%</span>
                <small>${a.date}</small>
            </div>
        </div>
    `).join('');
}

// ── Analytics ─────────────────────────────────────────────────────────────────
async function loadAnalytics() {
    try {
        const res = await apiFetch(`${API_BASE}/admin/analytics/summary`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        const perf = data.category_performance;

        destroyChart('cat-performance-chart');
        charts['cat-performance-chart'] = new Chart(document.getElementById('cat-performance-chart'), {
            type: 'bar',
            data: {
                labels: perf.map(p => p.category.replace('Technical - ', '')),
                datasets: [
                    { label: 'Avg Accuracy %', data: perf.map(p => p.avg_accuracy), backgroundColor: 'rgba(234,214,144,0.8)', borderColor: '#ead690', borderWidth: 1, borderRadius: 4 },
                    { label: 'Attempts', data: perf.map(p => p.attempts), backgroundColor: 'rgba(108,92,231,0.7)', borderColor: '#6c5ce7', borderWidth: 1, borderRadius: 4 }
                ]
            },
            options: {
                responsive: true,
                plugins: { legend: { labels: { color: '#333' } } },
                scales: {
                    x: { ticks: { color: '#555', font: { size: 11 } } },
                    y: { beginAtZero: true, ticks: { color: '#555' } }
                }
            }
        });

        const tbody = document.getElementById('cat-perf-body');
        tbody.innerHTML = perf.map(p => `
            <tr>
                <td>${p.category}</td>
                <td>${p.attempts}</td>
                <td>
                    <div class="accuracy-bar-wrap">
                        <div class="accuracy-bar" style="width:${p.avg_accuracy}%; background:${p.avg_accuracy >= 70 ? '#55efc4' : p.avg_accuracy >= 40 ? '#fdcb6e' : '#e17055'}"></div>
                        <span>${p.avg_accuracy}%</span>
                    </div>
                </td>
                <td>${p.avg_xp}</td>
            </tr>
        `).join('');
    } catch { showNotification('Failed to load analytics', 'error'); }
}

// ── Categories ────────────────────────────────────────────────────────────────
async function loadCategories() {
    try {
        const res = await apiFetch(`${API_BASE}/admin/categories`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        categoriesData = data.categories;
        populateCategorySelects();
        displayCategories();
    } catch { showNotification('Failed to load categories', 'error'); }
}

function populateCategorySelects() {
    ['#q-category', '#category-filter'].forEach(sel => {
        const el = document.querySelector(sel);
        if (!el) return;
        const isFilter = sel === '#category-filter';
        el.innerHTML = `<option value="">${isFilter ? 'All Categories' : 'Select Category'}</option>`;
        categoriesData.forEach(c => { el.innerHTML += `<option value="${c.id}">${c.icon || ''} ${c.name}</option>`; });
    });
}

function displayCategories() {
    const grid = document.getElementById('categories-grid');
    if (!grid) return;
    grid.innerHTML = categoriesData.map(c => `
        <div class="category-card">
            <div class="cat-icon">${c.icon || '📚'}</div>
            <div class="cat-info">
                <h4>${c.name}</h4>
                <p>${c.description || ''}</p>
                <span class="cat-count">${c.question_count || 0} questions</span>
            </div>
        </div>
    `).join('');
}

async function createCategory() {
    const name = document.getElementById('cat-name').value.trim();
    const icon = document.getElementById('cat-icon').value.trim();
    const desc = document.getElementById('cat-desc').value.trim();
    if (!name) { showNotification('Category name required', 'error'); return; }
    const res = await apiFetch(`${API_BASE}/admin/categories`, {
        method: 'POST', body: JSON.stringify({ name, icon: icon || '📚', description: desc })
    });
    const data = await res.json();
    if (!res.ok) { showNotification(data.error || 'Failed to create category', 'error'); return; }
    showNotification('Category created!', 'success');
    document.getElementById('add-cat-form').style.display = 'none';
    ['cat-name', 'cat-icon', 'cat-desc'].forEach(id => document.getElementById(id).value = '');
    await loadCategories();
}

// ── Questions ─────────────────────────────────────────────────────────────────
async function loadQuestions(page = 1) {
    qPage = page;
    const search = document.getElementById('q-search')?.value.trim() || '';
    const catId = document.getElementById('category-filter')?.value || '';
    const diff = document.getElementById('difficulty-filter')?.value || '';
    let url = `${API_BASE}/admin/questions?page=${page}&per_page=15`;
    if (catId) url += `&category_id=${catId}`;
    if (diff) url += `&difficulty=${diff}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    const res = await apiFetch(url);
    if (!res.ok) { showNotification('Failed to load questions', 'error'); return; }
    const data = await res.json();

    const tbody = document.getElementById('questions-tbody');
    if (!data.questions.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">No questions found</td></tr>';
    } else {
        tbody.innerHTML = data.questions.map(q => `
            <tr>
                <td>${q.id}</td>
                <td class="q-text-cell" title="${escapeHtml(q.text)}">${escapeHtml(q.text.substring(0, 60))}${q.text.length > 60 ? '…' : ''}</td>
                <td>${q.category_name || '—'}</td>
                <td><span class="badge badge-${q.difficulty}">${q.difficulty}</span></td>
                <td><span class="badge badge-${q.is_active ? 'active' : 'inactive'}">${q.is_active ? 'Active' : 'Inactive'}</span></td>
                <td class="actions-cell">
                    <button class="btn-icon btn-edit" onclick='openEditQuestion(${JSON.stringify(q)})'><i class="fas fa-edit"></i></button>
                    <button class="btn-icon btn-toggle" onclick="toggleQuestion(${q.id}, ${!q.is_active})" title="${q.is_active ? 'Deactivate' : 'Activate'}">
                        <i class="fas fa-${q.is_active ? 'eye-slash' : 'eye'}"></i>
                    </button>
                    <button class="btn-icon btn-delete" onclick="deleteQuestion(${q.id})"><i class="fas fa-trash"></i></button>
                </td>
            </tr>
        `).join('');
    }
    renderPagination('q-pagination', data.page, data.pages, 'loadQuestions');
}

function openEditQuestion(q) {
    document.getElementById('edit-question-id').value = q.id;
    document.getElementById('q-form-title').textContent = 'Edit Question';
    document.getElementById('q-submit-label').textContent = 'Update Question';
    document.getElementById('q-text').value = q.text;
    document.getElementById('q-difficulty').value = q.difficulty;
    document.getElementById('q-explanation').value = q.explanation || '';
    document.getElementById('q-tags').value = Array.isArray(q.tags) ? q.tags.join(', ') : (q.tags || '');
    document.getElementById('q-correct').value = q.correct_option;
    if (q.category_id) document.getElementById('q-category').value = q.category_id;
    q.options.forEach((opt, i) => { const el = document.getElementById(`opt-${i}`); if (el) el.value = opt; });
    showSection('add-question');
}

function resetQuestionForm() {
    document.getElementById('edit-question-id').value = '';
    document.getElementById('q-form-title').textContent = 'Add New Question';
    document.getElementById('q-submit-label').textContent = 'Save Question';
    ['q-text', 'q-explanation', 'q-tags'].forEach(id => document.getElementById(id).value = '');
    ['opt-0','opt-1','opt-2','opt-3'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('q-difficulty').value = 'medium';
    document.getElementById('q-correct').value = '0';
    document.getElementById('q-category').value = '';
}

async function submitQuestion() {
    const editId = document.getElementById('edit-question-id').value;
    const catId = document.getElementById('q-category').value;
    const text = document.getElementById('q-text').value.trim();
    const opts = ['opt-0','opt-1','opt-2','opt-3'].map(id => document.getElementById(id).value.trim());
    const correct = parseInt(document.getElementById('q-correct').value);
    const diff = document.getElementById('q-difficulty').value;
    const explanation = document.getElementById('q-explanation').value.trim();
    const tags = document.getElementById('q-tags').value.trim();

    if (!catId) { showNotification('Select a category', 'error'); return; }
    if (!text) { showNotification('Enter question text', 'error'); return; }
    if (opts.some(o => !o)) { showNotification('Fill all 4 answer options', 'error'); return; }

    const body = { category_id: parseInt(catId), text, options: opts, correct_option: correct, difficulty: diff, explanation, tags };
    const isEdit = !!editId;
    const url = isEdit ? `${API_BASE}/admin/questions/${editId}` : `${API_BASE}/admin/questions`;
    const res = await apiFetch(url, { method: isEdit ? 'PUT' : 'POST', body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) { showNotification(data.error || data.errors?.[0] || 'Failed', 'error'); return; }
    showNotification(isEdit ? 'Question updated!' : 'Question created!', 'success');
    resetQuestionForm();
    showSection('questions');
}

async function toggleQuestion(id, isActive) {
    const res = await apiFetch(`${API_BASE}/admin/questions/${id}`, { method: 'PUT', body: JSON.stringify({ is_active: isActive }) });
    if (!res.ok) { showNotification('Failed to update', 'error'); return; }
    showNotification(`Question ${isActive ? 'activated' : 'deactivated'}`, 'success');
    loadQuestions(qPage);
}

async function deleteQuestion(id) {
    if (!confirm('Delete this question permanently?')) return;
    const res = await apiFetch(`${API_BASE}/admin/questions/${id}`, { method: 'DELETE' });
    if (!res.ok) { showNotification('Failed to delete', 'error'); return; }
    showNotification('Question deleted', 'success');
    loadQuestions(qPage);
}

// ── Users ─────────────────────────────────────────────────────────────────────
async function loadUsers(page = 1) {
    usersPage = page;
    const search = document.getElementById('user-search')?.value.trim() || '';
    const role = document.getElementById('role-filter')?.value || '';
    let url = `${API_BASE}/admin/users?page=${page}&per_page=15`;
    if (role) url += `&role=${role}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    const res = await apiFetch(url);
    if (!res.ok) { showNotification('Failed to load users', 'error'); return; }
    const data = await res.json();

    const tbody = document.getElementById('users-tbody');
    if (!data.users.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">No users found</td></tr>';
    } else {
        tbody.innerHTML = data.users.map(u => `
            <tr>
                <td>${u.id}</td>
                <td><strong>${escapeHtml(u.username)}</strong></td>
                <td>${escapeHtml(u.email)}</td>
                <td><span class="badge badge-${u.role}">${u.role}</span></td>
                <td>${u.total_xp.toLocaleString()}</td>
                <td>${u.tests_taken}</td>
                <td>${u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                <td class="actions-cell">
                    <button class="btn-icon btn-edit" onclick="toggleUserRole(${u.id}, '${u.role === 'admin' ? 'student' : 'admin'}')" title="${u.role === 'admin' ? 'Remove admin' : 'Make admin'}">
                        <i class="fas fa-${u.role === 'admin' ? 'user-minus' : 'user-plus'}"></i>
                    </button>
                    <button class="btn-icon btn-delete" onclick="deleteUser(${u.id})"><i class="fas fa-trash"></i></button>
                </td>
            </tr>
        `).join('');
    }
    renderPagination('users-pagination', data.page, data.pages, 'loadUsers');
}

async function toggleUserRole(id, newRole) {
    if (!confirm(`Change this user to ${newRole}?`)) return;
    const res = await apiFetch(`${API_BASE}/admin/users/${id}/role`, { method: 'PUT', body: JSON.stringify({ role: newRole }) });
    if (!res.ok) { showNotification('Failed to update role', 'error'); return; }
    showNotification(`User role changed to ${newRole}`, 'success');
    loadUsers(usersPage);
}

async function deleteUser(id) {
    if (!confirm('Delete this user and all their data?')) return;
    const res = await apiFetch(`${API_BASE}/admin/users/${id}`, { method: 'DELETE' });
    if (!res.ok) { const d = await res.json(); showNotification(d.error || 'Failed', 'error'); return; }
    showNotification('User deleted', 'success');
    loadUsers(usersPage);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function apiFetch(url, opts = {}) {
    return fetch(url, {
        ...opts,
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
            ...(opts.headers || {})
        }
    });
}

function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }

function escapeHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderPagination(containerId, currentPage, totalPages, fnName) {
    const el = document.getElementById(containerId);
    if (!el || totalPages <= 1) { if (el) el.innerHTML = ''; return; }
    let html = '';
    if (currentPage > 1) html += `<button onclick="${fnName}(${currentPage - 1})">‹</button>`;
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || Math.abs(i - currentPage) <= 2) {
            html += `<button class="${i === currentPage ? 'active' : ''}" onclick="${fnName}(${i})">${i}</button>`;
        } else if (Math.abs(i - currentPage) === 3) {
            html += '<span>…</span>';
        }
    }
    if (currentPage < totalPages) html += `<button onclick="${fnName}(${currentPage + 1})">›</button>`;
    el.innerHTML = html;
}

function setupSearchDebounce() {
    let t;
    document.getElementById('q-search')?.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => loadQuestions(1), 400); });
    document.getElementById('user-search')?.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => loadUsers(1), 400); });
}

function showNotification(message, type = 'info') {
    const el = document.getElementById('notification');
    if (!el) return;
    el.textContent = message;
    el.className = `notification notification-${type} show`;
    setTimeout(() => el.classList.remove('show'), 3500);
}