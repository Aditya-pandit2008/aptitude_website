(function () {
  'use strict';

  // ── Auth guard ────────────────────────────────────────────────────────────
  const token = localStorage.getItem('access_token');
  if (!token) { window.location.href = '/login'; return; }

  // ── User level system ─────────────────────────────────────────────────────
  // Tracks rolling accuracy across sessions to auto-adjust difficulty
  const LEVEL_KEY = 'apti_user_level';     // 'beginner' | 'intermediate' | 'advanced'
  const HISTORY_KEY = 'apti_score_history'; // last N accuracy values

  function getUserLevel() {
    return localStorage.getItem(LEVEL_KEY) || 'beginner';
  }

  function updateUserLevel(accuracy) {
    // Keep last 5 test accuracies
    let history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    history.push(accuracy);
    if (history.length > 5) history = history.slice(-5);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));

    const avg = history.reduce((a, b) => a + b, 0) / history.length;
    let newLevel;
    if (avg >= 75) newLevel = 'advanced';
    else if (avg >= 45) newLevel = 'intermediate';
    else newLevel = 'beginner';

    const prev = getUserLevel();
    localStorage.setItem(LEVEL_KEY, newLevel);
    return { newLevel, prev, avg: Math.round(avg) };
  }

  // Map user level → Groq difficulty label
  function levelToDifficulty(level) {
    return { beginner: 'easy', intermediate: 'medium', advanced: 'hard' }[level] || 'medium';
  }

  // ── State ─────────────────────────────────────────────────────────────────
  const state = {
    categories: [],
    questions: [],
    startedAt: null,
    timerId: null,
    timeLimit: 600,
    remaining: 600,
    submitted: false,
    selectedCategory: '',
    selectedCategoryName: '',
    userLevel: getUserLevel(),
  };

  // ── DOM nodes ─────────────────────────────────────────────────────────────
  const nodes = {
    categoryList:     document.getElementById('category-list'),
    categorySelect:   document.getElementById('category-select'),
    difficultySelect: document.getElementById('difficulty-select'),
    countSelect:      document.getElementById('count-select'),
    timerSelect:      document.getElementById('timer-select'),
    search:           document.getElementById('question-search'),
    start:            document.getElementById('start-test'),
    status:           document.getElementById('test-status'),
    timerText:        document.getElementById('timer-text'),
    questionArea:     document.getElementById('question-area'),
    result:           document.getElementById('result-panel'),
    sidebar:          document.getElementById('sidebar'),
    menuBtn:          document.getElementById('menu-btn'),
    closeBtn:         document.getElementById('close-btn'),
    levelBadge:       document.getElementById('user-level-badge'),
    levelInfo:        document.getElementById('level-info'),
  };

  // ── Wire up sidebar + controls ────────────────────────────────────────────
  nodes.menuBtn?.addEventListener('click',  () => nodes.sidebar.classList.add('show'));
  nodes.closeBtn?.addEventListener('click', () => nodes.sidebar.classList.remove('show'));
  nodes.start?.addEventListener('click', startTest);
  nodes.search?.addEventListener('input', filterCategories);

  document.querySelectorAll('[data-action="logout"]').forEach(el =>
    el.addEventListener('click', logout)
  );

  // Sync difficulty select to user level on page load
  syncDifficultyToLevel();
  renderLevelBadge();
  loadCategories();

  // When user manually changes difficulty, store override
  nodes.difficultySelect?.addEventListener('change', function () {
    // Allow manual override but don't persist as level change
  });

  // ── Level UI ──────────────────────────────────────────────────────────────
  function syncDifficultyToLevel() {
    if (!nodes.difficultySelect) return;
    nodes.difficultySelect.value = levelToDifficulty(state.userLevel);
  }

  function renderLevelBadge() {
    if (!nodes.levelBadge) return;
    const labels = { beginner: '🟢 Beginner', intermediate: '🟡 Intermediate', advanced: '🔴 Advanced' };
    nodes.levelBadge.textContent = labels[state.userLevel] || state.userLevel;
    nodes.levelBadge.className = `level-badge level-${state.userLevel}`;

    if (nodes.levelInfo) {
      const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
      const avg = history.length
        ? Math.round(history.reduce((a, b) => a + b, 0) / history.length)
        : null;
      nodes.levelInfo.textContent = avg !== null
        ? `Avg accuracy: ${avg}% over last ${history.length} test(s)`
        : 'Complete a test to calibrate your level.';
    }
  }

  // ── Load categories from backend ──────────────────────────────────────────
  async function loadCategories() {
    try {
      const data = await fetchJson('/api/v1/questions/categories');
      state.categories = data.categories || [];
      renderCategories(state.categories);
    } catch {
      if (nodes.categoryList)
        nodes.categoryList.innerHTML = '<li>Topics could not be loaded.</li>';
    }
  }

  function renderCategories(categories) {
    if (!nodes.categorySelect || !nodes.categoryList) return;
    nodes.categorySelect.innerHTML = '<option value="">Mixed Aptitude</option>';
    nodes.categoryList.innerHTML = '';

    categories.forEach(cat => {
      const opt = document.createElement('option');
      opt.value = cat.id;
      opt.textContent = cat.name;
      nodes.categorySelect.appendChild(opt);

      const li = document.createElement('li');
      li.innerHTML = `<i class="fa-solid fa-layer-group"></i> ${escapeHtml(cat.name)}`;
      li.addEventListener('click', () => {
        nodes.categorySelect.value = cat.id;
        nodes.sidebar.classList.remove('show');
        startTest();
      });
      nodes.categoryList.appendChild(li);
    });
  }

  function filterCategories() {
    const q = nodes.search.value.trim().toLowerCase();
    const filtered = state.categories.filter(c =>
      c.name.toLowerCase().includes(q) || (c.description || '').toLowerCase().includes(q)
    );
    renderCategories(filtered);
  }

  // ── GROQ API call (direct from frontend via backend proxy) ────────────────
  // The backend /api/v1/ai/aptitude-questions already calls Groq.
  // We pass difficulty based on user level (auto or manual).

  async function generateQuestionsViaGroq(category, categoryId, difficulty, count) {
    const data = await fetchJson('/api/v1/ai/aptitude-questions', true, {
      method: 'POST',
      body: JSON.stringify({
        category,
        category_id: categoryId ? Number(categoryId) : null,
        difficulty,
        count,
      }),
    });
    return data.questions || [];
  }

  // ── Start test ────────────────────────────────────────────────────────────
  async function startTest() {
    const categoryId   = nodes.categorySelect?.value || '';
    const categoryName = getSelectedCategoryName();
    const count        = Number(nodes.countSelect?.value || 10);
    const timerVal     = Number(nodes.timerSelect?.value || 600);

    // Use user-level difficulty unless manually overridden
    const autoLevel    = levelToDifficulty(state.userLevel);
    const difficulty   = nodes.difficultySelect?.value || autoLevel;

    clearTimer();
    state.selectedCategory     = categoryId;
    state.selectedCategoryName = categoryName;
    state.startedAt            = null;      // set after questions load
    state.timeLimit            = timerVal;
    state.remaining            = timerVal;
    state.submitted            = false;

    if (nodes.result)  { nodes.result.classList.add('hidden'); nodes.result.innerHTML = ''; }
    if (nodes.questionArea) nodes.questionArea.innerHTML = '';

    const levelLabel = state.userLevel.charAt(0).toUpperCase() + state.userLevel.slice(1);
    if (nodes.status)
      nodes.status.textContent = `✨ Generating ${count} Groq AI questions — Level: ${levelLabel} (${difficulty})…`;
    updateTimerText();

    try {
      state.questions = await generateQuestionsViaGroq(categoryName, categoryId, difficulty, count);
      state.startedAt = Date.now();
      renderQuestions();
    } catch (error) {
      if (error.status === 401 || error.status === 422) { logout(); return; }
      if (nodes.status) {
        if (error.status === 503)
          nodes.status.textContent = '⚠️ AI not configured. Add GROQ_API_KEY in backend/.env and restart Flask.';
        else
          nodes.status.textContent = '⚠️ Could not generate questions. Check your GROQ_API_KEY and try again.';
      }
    }
  }

  // ── Render question cards ─────────────────────────────────────────────────
  function renderQuestions() {
    if (!state.questions.length) {
      if (nodes.status)
        nodes.status.textContent = 'No questions were generated. Try a different topic or difficulty.';
      return;
    }

    const levelLabel = state.userLevel.charAt(0).toUpperCase() + state.userLevel.slice(1);
    if (nodes.status)
      nodes.status.textContent =
        `${state.questions.length} AI questions ready (${levelLabel} level) — select one answer per question, then submit.`;

    nodes.questionArea.innerHTML = state.questions.map((q, i) => `
      <article class="question-card" data-index="${i}">
        <div class="question-meta">
          <span>Question ${i + 1} of ${state.questions.length}</span>
          <span>${escapeHtml(q.category_name || state.selectedCategoryName)} · ${escapeHtml(q.difficulty)}</span>
        </div>
        <h3>${escapeHtml(q.text)}</h3>
        <div class="options" id="options-${i}">
          ${q.options.map((opt, oi) => `
            <label class="option-row" id="opt-${i}-${oi}">
              <input type="radio" name="q${i}" value="${oi}">
              <span>${escapeHtml(opt)}</span>
            </label>
          `).join('')}
        </div>
      </article>
    `).join('');

    // Submit button
    const btn = document.createElement('button');
    btn.id        = 'submit-test';
    btn.className = 'primary-btn submit-btn';
    btn.innerHTML = '<i class="fa-solid fa-check"></i> Submit Test';
    btn.addEventListener('click', submitTest);
    nodes.questionArea.appendChild(btn);

    startTimer();
  }

  // ── Submit & score ────────────────────────────────────────────────────────
  async function submitTest() {
    if (state.submitted) return;
    state.submitted = true;
    clearTimer();

    const answers = state.questions.map((q, i) => {
      const checked = document.querySelector(`input[name="q${i}"]:checked`);
      return {
        questionIndex:   i,
        selected_option: checked ? Number(checked.value) : null,
        correct_option:  parseInt(q.correct_option, 10),
        is_correct:      checked ? Number(checked.value) === parseInt(q.correct_option, 10) : false,
      };
    });

    const timeTaken    = Math.round((Date.now() - state.startedAt) / 1000);
    const correctCount = answers.filter(a => a.is_correct).length;
    const total        = state.questions.length;
    const accuracy     = total ? Math.round((correctCount / total) * 100) : 0;
    const xp           = correctCount * 10 + 25;

    // Disable inputs
    nodes.questionArea.querySelectorAll('input[type="radio"]').forEach(r => r.disabled = true);
    document.getElementById('submit-test')?.remove();

    // ── Update user level based on this test ─────────────────────────────
    const { newLevel, prev, avg } = updateUserLevel(accuracy);
    state.userLevel = newLevel;
    renderLevelBadge();
    syncDifficultyToLevel();

    let levelMsg = '';
    if (newLevel !== prev) {
      const up = ['beginner','intermediate','advanced'].indexOf(newLevel) >
                 ['beginner','intermediate','advanced'].indexOf(prev);
      levelMsg = up
        ? `🎉 Level up! You're now <strong>${newLevel}</strong>.`
        : `📉 Level adjusted to <strong>${newLevel}</strong>. Keep practicing!`;
    } else {
      levelMsg = `Level: <strong>${newLevel}</strong> (avg ${avg}%)`;
    }

    if (nodes.status)
      nodes.status.innerHTML = `Test complete! ${correctCount}/${total} correct in ${formatTime(timeTaken)}. ${levelMsg}`;

    if (nodes.result) {
      nodes.result.classList.remove('hidden');
      nodes.result.innerHTML = `
        <div class="result-summary">
          <p class="eyebrow">Result</p>
          <h2>${accuracy}%</h2>
          <p>${correctCount}/${total} correct &nbsp;·&nbsp; ${xp} XP &nbsp;·&nbsp; ${formatTime(timeTaken)}</p>
          <p class="level-result-info">${levelMsg}</p>
        </div>
        <div class="result-actions">
          <button class="primary-btn" id="retry-btn">
            <i class="fa-solid fa-rotate-right"></i> New Test
          </button>
          <a class="secondary-btn" href="/Dashboard">
            <i class="fa-solid fa-table-columns"></i> Dashboard
          </a>
        </div>
      `;
      document.getElementById('retry-btn').addEventListener('click', startTest);
    }

    showAnswerReview(answers);

    // Save to backend (best-effort)
    try {
      const backendAnswers = state.questions.map((q, i) => ({
        question_id:     q.id,
        selected_option: answers[i].selected_option,
        time_spent:      Math.max(1, Math.round(timeTaken / total)),
      }));
      await fetchJson('/api/v1/tests/submit', true, {
        method: 'POST',
        body: JSON.stringify({
          answers:     backendAnswers,
          time_taken:  timeTaken,
          category_id: state.selectedCategory ? Number(state.selectedCategory) : null,
        }),
      });
    } catch { /* silent */ }
  }

  // ── Answer review ─────────────────────────────────────────────────────────
  function showAnswerReview(answers) {
    answers.forEach((answer, i) => {
      const card = document.querySelector(`.question-card[data-index="${i}"]`);
      if (!card) return;
      const q = state.questions[i];

      q.options.forEach((_, oi) => {
        const label = document.getElementById(`opt-${i}-${oi}`);
        if (!label) return;
        label.classList.remove('option-correct', 'option-wrong');
        if (oi === parseInt(q.correct_option, 10)) label.classList.add('option-correct');
        else if (oi === answer.selected_option && !answer.is_correct) label.classList.add('option-wrong');
      });

      const skipped    = answer.selected_option === null;
      const statusIcon = skipped ? '⏭️' : answer.is_correct ? '✅' : '❌';
      const statusText = skipped ? 'Skipped' : answer.is_correct ? 'Correct!' : 'Incorrect';
      const yourAnswer = skipped
        ? 'Not answered'
        : escapeHtml(q.options[answer.selected_option] || `Option ${answer.selected_option + 1}`);
     const correctIdx = (q.correct_option !== undefined && q.correct_option !== null)
        ? parseInt(q.correct_option, 10)
        : NaN;
      const correctText = escapeHtml(
        (!isNaN(correctIdx) && q.options[correctIdx])
          ? q.options[correctIdx]
          : 'Unknown'
      );
      const detail = document.createElement('div');
      detail.className = 'answer-detail';
      detail.innerHTML = `
        <div class="answer-status ${skipped ? 'skipped' : answer.is_correct ? 'correct' : 'wrong'}">
          ${statusIcon} <strong>${statusText}</strong>
        </div>
        ${!answer.is_correct || skipped
          ? `<p class="your-ans"><span>Your answer:</span> ${yourAnswer}</p>` : ''}
        <p class="correct-ans"><span>Correct answer:</span> ${correctText}</p>
        ${q.explanation ? `<p class="explanation">💡 ${escapeHtml(q.explanation)}</p>` : ''}
      `;
      card.appendChild(detail);
    });
  }

  // ── Timer ─────────────────────────────────────────────────────────────────
  function startTimer() {
    clearTimer();
    updateTimerText();
    state.timerId = window.setInterval(() => {
      state.remaining -= 1;
      updateTimerText();
      if (state.remaining <= 0) {
        if (nodes.status) nodes.status.textContent = 'Time is up! Submitting automatically…';
        submitTest();
      }
    }, 1000);
  }

  function clearTimer() {
    if (state.timerId) { window.clearInterval(state.timerId); state.timerId = null; }
  }

  function updateTimerText() {
    if (!nodes.timerText) return;
    nodes.timerText.textContent = state.startedAt
      ? `Time left: ${formatTime(Math.max(state.remaining, 0))}`
      : 'Timer not started';
    nodes.timerText.classList.toggle('timer-danger', state.remaining <= 30 && !!state.startedAt);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function formatTime(s) {
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }

  function getSelectedCategoryName() {
    const sel = nodes.categorySelect?.options[nodes.categorySelect.selectedIndex];
    return sel ? sel.textContent.trim() : 'Mixed Aptitude';
  }

  async function fetchJson(url, needsAuth = false, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (needsAuth) headers.Authorization = `Bearer ${token}`;
    const res  = await fetch(url, { ...options, headers });
    const data = await res.json();
    if (!res.ok) {
      const err = new Error(data.error || 'Request failed');
      err.status = res.status;
      throw err;
    }
    return data.data !== undefined ? data.data : data;
  }

  function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  }

  function escapeHtml(v) {
    return String(v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
})();