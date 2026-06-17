(function () {
  const token = localStorage.getItem('access_token');
  if (!token) {
    window.location.href = '/login';
    return;
  }

  const status = document.getElementById('bookmark-status');
  const list = document.getElementById('bookmark-list');

  document.querySelectorAll('[data-action="logout"]').forEach((item) => {
    item.addEventListener('click', logout);
  });

  loadBookmarks();

  async function loadBookmarks() {
    try {
      const data = await fetchJson('/api/v1/bookmarks/', true);
      renderBookmarks(data.bookmarks || []);
    } catch {
      status.textContent = 'Saved questions could not be loaded.';
    }
  }

  function renderBookmarks(bookmarks) {
    if (!bookmarks.length) {
      status.textContent = 'No saved questions yet.';
      list.innerHTML = `
        <article class="question-card">
          <h3>No saved questions</h3>
          <p>After submitting a test, use Save for Revision on questions you want to revisit.</p>
        </article>
      `;
      return;
    }

    status.textContent = `${bookmarks.length} saved question${bookmarks.length === 1 ? '' : 's'} ready for revision.`;
    list.innerHTML = bookmarks.map((bookmark) => {
      const question = bookmark.question || {};
      return `
        <article class="question-card">
          <div class="question-meta">
            <span>${escapeHtml(question.category_name || 'Aptitude')}</span>
            <span>${escapeHtml(question.difficulty || 'medium')}</span>
          </div>
          <h3>${escapeHtml(question.text || '')}</h3>
          <div class="options">
            ${(question.options || []).map((option, index) => `
              <div class="option-row ${index === question.correct_option ? 'saved-correct' : ''}">
                <span>${escapeHtml(option)}</span>
              </div>
            `).join('')}
          </div>
          ${question.explanation ? `<div class="answer-detail"><strong>Explanation:</strong><p>${escapeHtml(question.explanation)}</p></div>` : ''}
          ${bookmark.note ? `<p class="subtext">${escapeHtml(bookmark.note)}</p>` : ''}
        </article>
      `;
    }).join('');
  }

  async function fetchJson(url, needsAuth = false, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    };
    if (needsAuth) headers.Authorization = `Bearer ${token}`;

    const response = await fetch(url, { ...options, headers });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed');
    return data;
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
