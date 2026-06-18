(function () {
  const token = localStorage.getItem('access_token');
  if (!token) {
    window.location.href = '/login';
    return;
  }

  const STORE_KEY = 'apti_settings';
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

  // Settings nav — HTML uses class "nav-item", not "menu-item"
  document.querySelectorAll('.nav-item').forEach((item) => {
    item.addEventListener('click', () => activateSection(item.dataset.section));
  });

  // Eye-toggle buttons — HTML uses class "eye-btn" with data-target attribute
  document.querySelectorAll('.eye-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target;
      const input = document.getElementById(targetId);
      if (!input) return;
      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      const icon = btn.querySelector('i');
      if (icon) {
        icon.classList.toggle('fa-eye', !isPassword);
        icon.classList.toggle('fa-eye-slash', isPassword);
      }
    });
  });

  // Password strength meter
  document.getElementById('new-password')?.addEventListener('input', (e) => {
    const val = e.target.value;
    const bar = document.getElementById('pass-strength');
    if (!val) { bar && (bar.style.display = 'none'); return; }
    bar && (bar.style.display = '');
    const fill = document.getElementById('pass-bar');
    const label = document.getElementById('pass-label');
    let strength = 0;
    if (val.length >= 8) strength++;
    if (/[A-Z]/.test(val)) strength++;
    if (/[0-9]/.test(val)) strength++;
    if (/[^A-Za-z0-9]/.test(val)) strength++;
    const levels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
    const colors = ['', '#b45748', '#d4a017', '#6b9e5e', '#3f7d46'];
    if (fill) { fill.style.width = `${strength * 25}%`; fill.style.background = colors[strength]; }
    if (label) label.textContent = levels[strength];
  });

  // Button bindings — use correct IDs from the HTML
  document.getElementById('save-account')?.addEventListener('click', saveAccount);
  document.getElementById('change-password')?.addEventListener('click', changePassword);
  document.getElementById('save-preferences')?.addEventListener('click', () => saveLocalSection('preferences'));
  document.getElementById('save-notifications')?.addEventListener('click', () => saveLocalSection('notifications'));
  document.getElementById('save-privacy')?.addEventListener('click', () => saveLocalSection('privacy'));
  document.getElementById('export-data')?.addEventListener('click', downloadData); // HTML id is "export-data"
  document.getElementById('delete-account')?.addEventListener('click', deleteAccount);

  init();

  async function init() {
    loadLocalSettings();
    try {
      const profile = await api('/api/v1/auth/me');
      currentUser = profile.user;
      localStorage.setItem('user', JSON.stringify(currentUser));
      renderAccount();
    } catch (error) {
      if (error.status === 401 || error.status === 422) logout();
      else notify('Could not load account settings.', 'error');
    }
  }

  function activateSection(section) {
    // HTML uses class "nav-item", not "menu-item"
    document.querySelectorAll('.nav-item').forEach((item) => {
      item.classList.toggle('active', item.dataset.section === section);
    });
    document.querySelectorAll('.settings-section').forEach((panel) => {
      panel.classList.toggle('active', panel.id === `${section}-section`);
    });
  }

  function renderAccount() {
    // Update sidebar
    const sidebarName = document.getElementById('sidebar-username');
    if (sidebarName) sidebarName.textContent = currentUser.username || 'Student';

    // Update sidebar avatar circle with first letter
    const avatarCircle = document.getElementById('sidebar-avatar-circle');
    if (avatarCircle) avatarCircle.textContent = (currentUser.username || 'S')[0].toUpperCase();

    // HTML account section uses: acc-username, acc-email, acc-joined
    const usernameEl = document.getElementById('acc-username');
    if (usernameEl) usernameEl.value = currentUser.username || '';

    const emailEl = document.getElementById('acc-email');
    if (emailEl) emailEl.value = currentUser.email || '';

    const joinedEl = document.getElementById('acc-joined');
    if (joinedEl) joinedEl.value = formatDate(currentUser.created_at);
  }

  async function saveAccount() {
    // HTML uses acc-username
    const username = (document.getElementById('acc-username')?.value || '').trim();
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
      renderAccount();
      notify('Account settings saved.', 'success');
    } catch (error) {
      notify(error.message || 'Could not save account settings.', 'error');
    }
  }

  async function changePassword() {
    const oldPassword = document.getElementById('current-password')?.value || '';
    const newPassword = document.getElementById('new-password')?.value || '';
    const confirm = document.getElementById('confirm-password')?.value || '';

    if (!oldPassword || !newPassword || !confirm) {
      notify('Fill all password fields.', 'error');
      return;
    }
    if (newPassword.length < 8) {
      notify('New password must be at least 8 characters.', 'error');
      return;
    }
    if (newPassword !== confirm) {
      notify('New passwords do not match.', 'error');
      return;
    }

    try {
      await api('/api/v1/auth/me', {
        method: 'PUT',
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
      });
      ['current-password', 'new-password', 'confirm-password'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      // Hide strength bar
      const bar = document.getElementById('pass-strength');
      if (bar) bar.style.display = 'none';
      notify('Password changed successfully.', 'success');
    } catch (error) {
      notify(error.message || 'Could not change password.', 'error');
    }
  }

  function saveLocalSection(section) {
    const settings = getSettings();

    // Map to the actual IDs used in the HTML
    if (section === 'preferences') {
      settings.preferences = valuesFrom([
        'pref-difficulty', 'pref-timer', 'pref-explanations', 'pref-hints',
        'pref-duration', 'pref-questions',
      ]);
    }
    if (section === 'notifications') {
      // HTML uses: notif-daily, notif-weekly, notif-achievements, notif-leaderboard, notif-frequency
      settings.notifications = valuesFrom([
        'notif-daily', 'notif-weekly', 'notif-achievements',
        'notif-leaderboard', 'notif-frequency',
      ]);
    }
    if (section === 'privacy') {
      // HTML uses: priv-visibility, priv-show-stats, priv-show-xp, priv-analytics
      settings.privacy = valuesFrom([
        'priv-visibility', 'priv-show-stats', 'priv-show-xp', 'priv-analytics',
      ]);
    }
    setSettings(settings);
    notify(`${capitalize(section)} settings saved.`, 'success');
  }

  function loadLocalSettings() {
    const settings = getSettings();
    applyValues(settings.preferences || {});
    applyValues(settings.notifications || {});
    applyValues(settings.privacy || {});
  }

  async function downloadData() {
    try {
      const [profile, dashboard, bookmarks] = await Promise.all([
        api('/api/v1/auth/me'),
        api('/api/v1/dashboard/'),
        api('/api/v1/bookmarks/'),
      ]);
      const payload = {
        exported_at: new Date().toISOString(),
        profile: profile.user,
        dashboard,
        bookmarks,
        settings: getSettings(),
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'aptitude-account-data.json';
      link.click();
      URL.revokeObjectURL(link.href);
      notify('Data download started.', 'success');
    } catch {
      notify('Could not prepare data download.', 'error');
    }
  }

  async function deleteAccount() {
    const confirmed = confirm('Delete your account permanently? This cannot be undone.');
    if (!confirmed) return;

    try {
      await api('/api/v1/auth/me', { method: 'DELETE' });
      logout();
    } catch (error) {
      notify(error.message || 'Could not delete account.', 'error');
    }
  }

  function valuesFrom(ids) {
    return ids.reduce((acc, id) => {
      const el = document.getElementById(id);
      if (!el) return acc;
      acc[id] = el.type === 'checkbox' ? el.checked : el.value;
      return acc;
    }, {});
  }

  function applyValues(values) {
    Object.entries(values).forEach(([id, value]) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (el.type === 'checkbox') el.checked = Boolean(value);
      else el.value = value;
    });
  }

  function getSettings() {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
    } catch {
      return {};
    }
  }

  function setSettings(settings) {
    localStorage.setItem(STORE_KEY, JSON.stringify(settings));
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
    return data.data !== undefined ? data.data : data;
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

  function capitalize(value) {
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  function formatErrors(errors) {
    return Array.isArray(errors) ? errors.join(' ') : '';
  }

  function formatDate(value) {
    if (!value) return 'Recently';
    return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }
})();
