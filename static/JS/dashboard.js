(function () {
  const token = localStorage.getItem('access_token');
  const user = readUser();

  if (!token) {
    window.location.href = '/login';
    return;
  }

  document.querySelectorAll('[data-page]').forEach((item) => {
    item.addEventListener('click', () => {
      window.location.href = item.dataset.page;
    });
  });

  document.querySelectorAll('[data-action="logout"]').forEach((item) => {
    item.addEventListener('click', logout);
  });

  if (user?.username) {
    document.getElementById('profile-name').textContent = user.username;
    document.getElementById('dashboard-title').textContent = `${user.username}'s Dashboard`;
  }

  loadDashboard();

  async function loadDashboard() {
    try {
      const data = await apiGet('/api/v1/dashboard/');
      renderStats(data);
      renderTopics(data.category_breakdown || []);
      renderAttempts(data.recent_attempts || []);
      renderRecommendations(data);
    } catch (error) {
      if (error.status === 401 || error.status === 422) {
        logout();
        return;
      }
      showDashboardError('Dashboard data could not be loaded. Try logging in again.');
    }
  }

  function renderStats(data) {
    const stats = data.stats || {};
    const profile = data.user || user || {};

    setText('stat-tests', stats.total_tests || 0);
    setText('stat-questions', stats.total_questions_solved || 0);
    setText('stat-accuracy', `${Math.round(stats.accuracy_percentage || 0)}%`);
    setText('stat-xp', profile.total_xp || 0);
    setText('stat-streak', profile.daily_streak || 0);
  }

  function renderTopics(topics) {
    const box = document.getElementById('topic-progress');
    if (!topics.length) {
      box.innerHTML = '<div class="empty-state">Complete a test to see your topic progress.</div>';
      return;
    }

    box.innerHTML = topics.map((topic) => {
      const accuracy = Math.round(topic.accuracy || 0);
      return `
        <div class="progress-item">
          <div class="progress-top">
            <span>${escapeHtml(topic.category_name)}</span>
            <span>${accuracy}%</span>
          </div>
          <div class="bar">
            <div class="fill" style="width: ${accuracy}%"></div>
          </div>
          <p class="muted">${topic.correct}/${topic.attempted} correct</p>
        </div>
      `;
    }).join('');
  }

  function renderAttempts(attempts) {
    const box = document.getElementById('recent-attempts');
    if (!attempts.length) {
      box.innerHTML = '<div class="empty-state">No test attempts yet. Start a test to build your history.</div>';
      return;
    }

    box.innerHTML = attempts.map((attempt) => {
      const accuracy = Math.round(attempt.accuracy || 0);
      return `
        <div class="reward-card">
          <h4>${escapeHtml(attempt.category_name || 'Mixed')}</h4>
          <div class="small-bar">
            <div class="small-fill" style="width: ${accuracy}%"></div>
          </div>
          <p>${accuracy}% accuracy</p>
          <p class="muted">${attempt.correct_answers}/${attempt.total_questions} correct · ${attempt.xp_earned} XP</p>
        </div>
      `;
    }).join('');
  }

  function renderRecommendations(data) {
    const box = document.getElementById('recommendations');
    const weak = data.weak_topics || [];
    const strong = data.strong_topics || [];

    if (!weak.length && !strong.length) {
      box.innerHTML = '<div class="empty-state">Your recommendations will appear after your first test.</div>';
      return;
    }

    const items = [
      ...weak.map((t) => ({ label: t.category_name || t, type: 'Needs Practice', accuracy: t.accuracy })),
      ...strong.map((t) => ({ label: t.category_name || t, type: 'Strong Topic', accuracy: t.accuracy })),
    ];

    box.innerHTML = items.slice(0, 6).map((item) => {
      const cls = item.type === 'Needs Practice' ? 'needs-practice' : 'strong-topic';
      return `<div class="focus-pill ${cls}">
        <span>${escapeHtml(item.label)}</span>
        <small>${escapeHtml(item.type)}${item.accuracy !== undefined ? ' · ' + Math.round(item.accuracy) + '%' : ''}</small>
      </div>`;
    }).join('');
  }

  async function apiGet(url) {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || 'Request failed');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function readUser() {
    try {
      return JSON.parse(localStorage.getItem('user') || 'null');
    } catch {
      return null;
    }
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function showDashboardError(message) {
    document.getElementById('topic-progress').innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  }

  function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
})();
