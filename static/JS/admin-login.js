'use strict';

(function () {
  const form = document.getElementById('admin-login-form');
  const emailInput = document.getElementById('admin-login-email');
  const passwordInput = document.getElementById('admin-login-password');
  const submitButton = document.getElementById('admin-login-submit');
  const message = document.getElementById('admin-login-message');
  const passwordToggle = document.getElementById('admin-toggle-password');

  function showMessage(text, type) {
    message.textContent = text;
    message.className = `admin-login-message ${type || ''}`;
  }

  passwordToggle?.addEventListener('click', function () {
    const showPassword = passwordInput.type === 'password';
    passwordInput.type = showPassword ? 'text' : 'password';
    this.classList.toggle('fa-eye', !showPassword);
    this.classList.toggle('fa-eye-slash', showPassword);
  });

  form?.addEventListener('submit', async function (event) {
    event.preventDefault();
    const email = emailInput.value.trim();
    const password = passwordInput.value;

    if (!email || !password) {
      showMessage('Enter both email and password.', 'error');
      return;
    }

    submitButton.disabled = true;
    submitButton.querySelector('.btn-text').textContent = 'VERIFYING ACCESS…';
    showMessage('', '');

    try {
      const response = await fetch('/api/v1/auth/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const result = await response.json();
      const payload = result.data || result;

      if (!response.ok) {
        showMessage(result.error || 'Unable to sign in to the admin panel.', 'error');
        return;
      }

      localStorage.setItem('access_token', payload.access_token);
      localStorage.setItem('refresh_token', payload.refresh_token);
      localStorage.setItem('user', JSON.stringify(payload.user));
      showMessage('Admin access verified. Opening the panel…', 'success');
      window.setTimeout(() => { window.location.href = '/admin'; }, 600);
    } catch {
      showMessage('Unable to connect to the server. Please try again.', 'error');
    } finally {
      submitButton.disabled = false;
      submitButton.querySelector('.btn-text').textContent = 'LOGIN TO ADMIN PANEL';
    }
  });
})();
