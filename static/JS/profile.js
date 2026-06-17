(function () {
  const token = localStorage.getItem('access_token');
  if (!token) {
    window.location.href = '/login';
    return;
  }

  let currentUser = null;

  // Sidebar navigation
  document.querySelectorAll('[data-page]').forEach((item) => {
    item.addEventListener('click', () => {
      window.location.href = item.dataset.page;
    });
  });

  document.querySelectorAll('[data-action="logout"]').forEach((item) => {
    item.addEventListener('click', logout);
  });

  document.getElementById('cancel-edit')?.addEventListener('click', fillProfileForm);
  document.getElementById('edit-profile-form')?.addEventListener('submit', saveProfile);

  // Avatar badge click — placeholder for future photo upload
  document.getElementById('avatar-badge')?.addEventListener('click', () => {
    notify('Photo upload coming soon!', 'success');
  });

  init();

  async function init() {
    try {
      const profile = await api('/api/v1/auth/me');
      currentUser = profile.user;
      localStorage.setItem('user', JSON.stringify(currentUser));
      renderUser(currentUser);

      const [dashboard, bookmarks] = await Promise.all([
        api('/api/v1/dashboard/'),
        api('/api/v1/bookmarks/?per_page=1'),
      ]);
      renderStats(dashboard, bookmarks.total || 0);
      renderActivity(dashboard.recent_attempts || []);

      // Fetch leaderboard rank separately
      try {
        const lb = await api('/api/v1/leaderboard/');
        const myEntry = (lb.leaderboard || []).find(
          (e) => e.user_id === currentUser.id || e.username === currentUser.username
        );
        if (myEntry) {
          setText('rank-position', `#${myEntry.rank}`);
        } else {
          setText('rank-position', '--');
        }
      } catch {
        setText('rank-position', '--');
      }
    } catch (error) {
      if (error.status === 401 || error.status === 422) logout();
      else notify('Profile could not be loaded.', 'error');
    }
  }

  function renderUser(user) {
    setText('profile-name', user.username);
    setText('profile-email', user.email);
    setText('sidebar-username', user.username);
    setText('profile-joined', formatDate(user.created_at));

    // Support both img-based sidebar avatar and circle-div avatar
    const sidebarImg = document.getElementById('sidebar-avatar');
    if (sidebarImg && sidebarImg.tagName === 'IMG') {
      sidebarImg.alt = user.username;
    }
    const avatarCircle = document.getElementById('sidebar-avatar-circle');
    if (avatarCircle) {
      avatarCircle.textContent = (user.username || 'S')[0].toUpperCase();
    }

    fillProfileForm();
  }

  function fillProfileForm() {
    if (!currentUser) return;
    const usernameEl = document.getElementById('edit-username');
    const emailEl = document.getElementById('edit-email');
    if (usernameEl) usernameEl.value = currentUser.username || '';
    if (emailEl) emailEl.value = currentUser.email || '';
  }

  function renderStats(data, bookmarkCount) {
    const stats = data.stats || {};
    const user = data.user || currentUser || {};
    const totalQuestions = Number(stats.total_questions_solved || stats.total_questions || 0);
    const correct = Number(stats.total_correct || 0);

    setText('stat-tests-taken', stats.total_tests || 0);
    setText('stat-total-xp', user.total_xp || 0);
    setText('stat-avg-accuracy', `${Math.round(stats.accuracy_percentage || stats.avg_accuracy || 0)}%`);
    setText('stat-streak', user.daily_streak || 0);
    setText('correct-answers', correct);
    setText('incorrect-answers', stats.total_incorrect ?? Math.max(totalQuestions - correct, 0));
    setText('bookmarked-questions', bookmarkCount);
  }

  function renderActivity(attempts) {
    const box = document.getElementById('activity-list');
    if (!box) return;

    if (!attempts.length) {
      box.innerHTML = '<p class="empty">No test activity yet. Start a practice test to build your profile.</p>';
      return;
    }

    box.innerHTML = attempts.map((attempt) => `
      <div class="activity-item">
        <div>
          <strong>${escapeHtml(attempt.category_name || 'Mixed Test')}</strong>
          <p>${attempt.correct_answers}/${attempt.total_questions} correct &mdash; ${Math.round(attempt.accuracy || 0)}% accuracy</p>
        </div>
        <span>${formatDate(attempt.completed_at)}</span>
      </div>
    `).join('');
  }

  async function saveProfile(event) {
    event.preventDefault();
    const username = (document.getElementById('edit-username')?.value || '').trim();
    if (username.length < 3) {
      notify('Username must be at least 3 characters.', 'error');
      return;
    }

    try {
      const data = await api('/api/v1/auth/me', {
        method: 'PUT',
        body: JSON.stringify({ username }),
      });
      currentUser = data.user;
      localStorage.setItem('user', JSON.stringify(currentUser));
      renderUser(currentUser);
      notify('Profile updated successfully.', 'success');
    } catch (error) {
      notify(error.message || 'Could not save profile.', 'error');
    }
  }

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...(options.headers || {}),
      },
    });
    const data = await response.json();
    if (!response.ok) {
      const err = new Error(data.error || formatErrors(data.errors) || 'Request failed');
      err.status = response.status;
      throw err;
    }
    return data;
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function formatDate(value) {
    if (!value) return 'Recently';
    return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function notify(message, type) {
    const box = document.getElementById('notification');
    if (!box) return;
    box.textContent = message;
    box.className = `notification active ${type}`;
    setTimeout(() => box.classList.remove('active'), 3000);
  }

  function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  }

  function formatErrors(errors) {
    return Array.isArray(errors) ? errors.join(' ') : '';
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
