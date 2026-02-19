/* ═══════════════════════════════════════════════════════════════════
   Evidentia — Next-Generation Research Agent UI
   Application Logic (with Authentication)
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  // ─── State ─────────────────────────────────────────────────────
  const state = {
    ws: null,
    currentResult: null,
    startTime: null,
    timerInterval: null,
    toolCallCount: 0,
    evidenceCount: 0,
    coverage: 0,
    runHistory: [],
    pdfLibrary: [],
    sidebarOpen: false,
    // Auth state (persisted in localStorage for permanent sessions)
    token: null,
    userId: null,
    userEmail: null,
    authMode: 'register', // 'login' or 'register'
    // Projects
    projects: [],
    activeProjectId: null,
    // Systematic Review
    reviewMode: false,
    reviewWs: null,
    reviewStartTime: null,
    reviewTimerInterval: null,
    reviewPapers: { included: [], excluded: [], uncertain: [] },
    reviewPrisma: null,
  };

  // ─── DOM References ────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    sidebar:          $('#sidebar'),
    sidebarOverlay:   $('#sidebar-overlay'),
    sidebarToggle:    $('#sidebar-toggle'),
    sidebarClose:     $('#sidebar-close'),
    mainContent:      $('#main-content'),
    landing:          $('#landing'),
    workspace:        $('#workspace'),
    newQueryBtn:      $('#new-query-btn'),
    queryForm:        $('#query-form'),
    queryInput:       $('#query-input'),
    querySubmit:      $('#query-submit'),
    activeQueryText:  $('#active-query-text'),
    traceTimeline:    $('#trace-timeline'),
    tracePhase:       $('#trace-phase'),
    claimsContainer:  $('#claims-container'),
    resultsSummary:   $('#results-summary'),
    exportButtons:    $('#export-buttons'),
    statTools:        $('#stat-tools'),
    statEvidence:     $('#stat-evidence'),
    statCoverage:     $('#stat-coverage'),
    statTime:         $('#stat-time'),
    toolsList:        $('#tools-list'),
    historyList:      $('#history-list'),
    pdfLibrary:       $('#pdf-library'),
    pdfDropzone:      $('#pdf-dropzone'),
    pdfFileInput:     $('#pdf-file-input'),
    uploadProgressWrap: $('#upload-progress-wrap'),
    uploadProgress:   $('#upload-progress'),
    uploadFilename:   $('#upload-filename'),
    uploadStatus:     $('#upload-status'),
    toastContainer:   $('#toast-container'),
    // Auth modal elements
    authOverlay:      $('#auth-overlay'),
    authForm:         $('#auth-form'),
    authEmail:        $('#auth-email'),
    authPassword:     $('#auth-password'),
    authError:        $('#auth-error'),
    authSubmit:       $('#auth-submit'),
    authSubtitle:     $('#auth-subtitle'),
    authSwitchText:   $('#auth-switch-text'),
    authSwitchBtn:    $('#auth-switch-btn'),
    // Projects
    projectsList:     $('#projects-list'),
    projectSelect:    $('#project-select'),
    projectSelector:  $('#project-selector'),
    newProjectBtn:    $('#new-project-btn'),
    quickCreateProject: $('#quick-create-project'),
    // Review
    modeQuery:        $('#mode-query'),
    modeReview:       $('#mode-review'),
    reviewFormSection: $('#review-form-section'),
    reviewForm:       $('#review-form'),
    reviewQuestion:   $('#review-question'),
    reviewMaxResults: $('#review-max-results'),
    reviewMaxResultsVal: $('#review-max-results-val'),
    reviewWorkspace:  $('#review-workspace'),
    reviewQueryText:  $('#review-query-text'),
    reviewElapsed:    $('#review-elapsed'),
    prismaIdentified: $('#prisma-identified'),
    prismaUnique:     $('#prisma-unique'),
    prismaDupesNote:  $('#prisma-dupes-note'),
    prismaScreened:   $('#prisma-screened'),
    prismaIncluded:   $('#prisma-included'),
    prismaExcluded:   $('#prisma-excluded'),
    prismaUncertain:  $('#prisma-uncertain'),
    prismaDbBreakdown: $('#prisma-db-breakdown'),
    prismaScreeningProgress: $('#prisma-screening-progress'),
    reviewExportButtons: $('#review-export-buttons'),
    reviewModeBadge:  $('#review-mode-badge'),
    reviewRunHash:    $('#review-run-hash'),
    tabIncludedCount: $('#tab-included-count'),
    tabExcludedCount: $('#tab-excluded-count'),
    tabUncertainCount: $('#tab-uncertain-count'),
    reviewPapersIncluded: $('#review-papers-included'),
    reviewPapersExcluded: $('#review-papers-excluded'),
    reviewPapersUncertain: $('#review-papers-uncertain'),
    // Settings / Account
    settingsOverlay:   $('#settings-overlay'),
    settingsClose:     $('#settings-close'),
    settingsBtn:       $('#settings-btn'),
    signoutBtn:        $('#signout-btn'),
    signoutSettingsBtn: $('#signout-settings-btn'),
    generateApiKeyBtn: $('#generate-api-key-btn'),
    settingsEmail:     $('#settings-email'),
    settingsUserId:    $('#settings-user-id'),
    settingsApiKey:    $('#settings-api-key'),
    accountEmail:      $('#account-email'),
    accountAvatar:     $('#account-avatar'),
  };

  // ─── Initialize ────────────────────────────────────────────────
  function init() {
    bindEvents();
    bindAuthEvents();
    bindProjectEvents();
    bindReviewEvents();
    bindSettingsEvents();
    loadTools();

    // Try to restore session from localStorage
    if (tryRestoreSession()) {
      loadHistory();
      loadPdfLibrary();
      hideAuthModal();
    } else {
      loadHistory();
      loadPdfLibrary();
      showAuthModal();
    }
  }

  function tryRestoreSession() {
    try {
      const saved = localStorage.getItem('evidentia_session');
      if (!saved) return false;
      const session = JSON.parse(saved);
      if (!session.token || !session.userId) return false;
      // Check if token is expired by decoding payload
      const payload = JSON.parse(atob(session.token.split('.')[1]));
      if (payload.exp && payload.exp * 1000 < Date.now()) {
        localStorage.removeItem('evidentia_session');
        return false;
      }
      state.token = session.token;
      state.userId = session.userId;
      state.userEmail = session.email || '';
      return true;
    } catch (e) {
      localStorage.removeItem('evidentia_session');
      return false;
    }
  }

  function saveSession() {
    try {
      localStorage.setItem('evidentia_session', JSON.stringify({
        token: state.token,
        userId: state.userId,
        email: state.userEmail,
      }));
    } catch (e) { /* ignore */ }
  }

  function clearSession() {
    state.token = null;
    state.userId = null;
    state.userEmail = null;
    localStorage.removeItem('evidentia_session');
  }

  // ═══════════════════════════════════════════════════════════════
  // AUTHENTICATION
  // ═══════════════════════════════════════════════════════════════

  function showAuthModal() {
    dom.authOverlay.style.display = 'flex';
    dom.mainContent.classList.add('blurred');
    setAuthMode(state.authMode);
    dom.authEmail.focus();
  }

  function hideAuthModal() {
    dom.authOverlay.style.display = 'none';
    dom.mainContent.classList.remove('blurred');
    updateAccountUI();
    loadProjects();
  }

  function setAuthMode(mode) {
    state.authMode = mode;
    if (mode === 'register') {
      dom.authSubtitle.textContent = 'Create an account to start researching';
      dom.authSubmit.textContent = 'Create Account';
      dom.authSwitchText.textContent = 'Already have an account?';
      dom.authSwitchBtn.textContent = 'Sign In';
    } else {
      dom.authSubtitle.textContent = 'Sign in to start researching';
      dom.authSubmit.textContent = 'Sign In';
      dom.authSwitchText.textContent = "Don't have an account?";
      dom.authSwitchBtn.textContent = 'Register';
    }
    dom.authError.style.display = 'none';
  }

  function showAuthError(message) {
    dom.authError.textContent = message;
    dom.authError.style.display = 'block';
  }

  function bindAuthEvents() {
    // Auth form submit
    dom.authForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = dom.authEmail.value.trim();
      const password = dom.authPassword.value;

      if (!email || !password) return;

      dom.authSubmit.disabled = true;
      dom.authSubmit.textContent = state.authMode === 'login' ? 'Signing in...' : 'Creating account...';
      dom.authError.style.display = 'none';

      try {
        // Try the selected mode first
        const primaryEndpoint = state.authMode === 'login' ? '/api/v1/auth/login' : '/api/v1/auth/register';
        let resp = await fetch(primaryEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        let data = await resp.json();

        // Auto-fallback: if login fails (no account), try register; if register fails (already exists), try login
        if (!resp.ok) {
          const fallbackEndpoint = state.authMode === 'login' ? '/api/v1/auth/register' : '/api/v1/auth/login';
          const fallbackResp = await fetch(fallbackEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
          });
          const fallbackData = await fallbackResp.json();

          if (fallbackResp.ok) {
            resp = fallbackResp;
            data = fallbackData;
          } else {
            // Both failed — show error from whichever is more relevant
            showAuthError(data.detail || fallbackData.detail || 'Authentication failed');
            return;
          }
        }

        state.token = data.access_token;
        state.userId = data.user_id;
        state.userEmail = email;
        saveSession();

        // Reload history/pdfs for this user
        loadHistory();
        loadPdfLibrary();
        hideAuthModal();
        const isNew = resp.url.includes('register');
        showToast(isNew ? 'Welcome! Account created.' : 'Welcome back!', 'success');

      } catch (err) {
        showAuthError('Network error. Is the server running?');
      } finally {
        dom.authSubmit.disabled = false;
        setAuthMode(state.authMode); // Reset button text
      }
    });

    // Toggle between login/register
    dom.authSwitchBtn.addEventListener('click', () => {
      setAuthMode(state.authMode === 'login' ? 'register' : 'login');
    });
  }

  // ═══════════════════════════════════════════════════════════════
  // SETTINGS & ACCOUNT
  // ═══════════════════════════════════════════════════════════════

  function updateAccountUI() {
    const email = state.userEmail || '';
    const initial = email ? email[0].toUpperCase() : '?';
    if (dom.accountAvatar) dom.accountAvatar.textContent = initial;
    if (dom.accountEmail) dom.accountEmail.textContent = email || 'Not signed in';
    if (dom.settingsEmail) dom.settingsEmail.textContent = email || '—';
    if (dom.settingsUserId) dom.settingsUserId.textContent = state.userId || '—';
  }

  function showSettings() {
    updateAccountUI();
    dom.settingsOverlay.style.display = 'flex';
  }

  function hideSettings() {
    dom.settingsOverlay.style.display = 'none';
  }

  function signOut() {
    clearSession();
    state.runHistory = [];
    state.pdfLibrary = [];
    renderHistory();
    renderPdfLibrary();
    hideSettings();
    showAuthModal();
    showToast('Signed out.', 'info');
  }

  function bindSettingsEvents() {
    if (dom.settingsBtn) dom.settingsBtn.addEventListener('click', showSettings);
    if (dom.settingsClose) dom.settingsClose.addEventListener('click', hideSettings);
    if (dom.signoutBtn) dom.signoutBtn.addEventListener('click', signOut);
    if (dom.signoutSettingsBtn) dom.signoutSettingsBtn.addEventListener('click', signOut);

    // Close settings on overlay click
    if (dom.settingsOverlay) dom.settingsOverlay.addEventListener('click', (e) => {
      if (e.target === dom.settingsOverlay) hideSettings();
    });

    // Generate API key
    if (dom.generateApiKeyBtn) dom.generateApiKeyBtn.addEventListener('click', async () => {
      try {
        dom.generateApiKeyBtn.disabled = true;
        dom.generateApiKeyBtn.textContent = 'Generating...';
        const resp = await authFetch('/api/v1/auth/api-key', { method: 'POST' });
        const data = await resp.json();
        if (resp.ok && data.api_key) {
          dom.settingsApiKey.textContent = data.api_key;
          dom.settingsApiKey.classList.add('settings-api-key--visible');
          showToast('API key generated. Copy it now — it won\'t be shown again.', 'success');
        } else {
          showToast(data.detail || 'Failed to generate key', 'error');
        }
      } catch (err) {
        showToast('Failed to generate API key.', 'error');
      } finally {
        dom.generateApiKeyBtn.disabled = false;
        dom.generateApiKeyBtn.textContent = 'Generate Key';
      }
    });
  }

  /**
   * Authenticated fetch wrapper.
   * Automatically adds Authorization header and handles 401 responses.
   */
  async function authFetch(url, options = {}) {
    const headers = { ...(options.headers || {}) };

    if (state.token) {
      headers['Authorization'] = `Bearer ${state.token}`;
    }

    const resp = await fetch(url, { ...options, headers });

    if (resp.status === 401) {
      // Token expired or invalid — force re-login
      clearSession();
      showAuthModal();
      showToast('Session expired. Please sign in again.', 'warning');
      throw new Error('Unauthorized');
    }

    return resp;
  }

  // ─── Event Bindings ────────────────────────────────────────────
  function bindEvents() {
    // Query form
    dom.queryForm.addEventListener('submit', (e) => {
      e.preventDefault();
      runQuery();
    });

    // Enter to submit (Shift+Enter for newline)
    dom.queryInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        runQuery();
      }
    });

    // Auto-resize textarea
    dom.queryInput.addEventListener('input', () => {
      dom.queryInput.style.height = 'auto';
      dom.queryInput.style.height = Math.min(dom.queryInput.scrollHeight, 200) + 'px';
    });

    // Example chips
    $$('.chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        dom.queryInput.value = chip.dataset.query;
        dom.queryInput.focus();
        dom.queryInput.dispatchEvent(new Event('input'));
      });
    });

    // New query button
    dom.newQueryBtn.addEventListener('click', resetToLanding);

    // Sidebar toggle
    dom.sidebarToggle.addEventListener('click', openSidebar);
    dom.sidebarClose.addEventListener('click', closeSidebar);
    dom.sidebarOverlay.addEventListener('click', closeSidebar);

    // PDF upload via drag-and-drop
    dom.pdfDropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dom.pdfDropzone.classList.add('dragover');
    });
    dom.pdfDropzone.addEventListener('dragleave', () => {
      dom.pdfDropzone.classList.remove('dragover');
    });
    dom.pdfDropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dom.pdfDropzone.classList.remove('dragover');
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        handlePdfUpload(files[0]);
      }
    });

    // PDF upload via file picker
    dom.pdfFileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        handlePdfUpload(e.target.files[0]);
      }
      e.target.value = '';
    });

    // Click on dropzone triggers file picker
    dom.pdfDropzone.addEventListener('click', (e) => {
      if (e.target.tagName !== 'LABEL') {
        dom.pdfFileInput.click();
      }
    });

    // Export buttons
    dom.exportButtons.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-export]');
      if (!btn) return;
      const format = btn.dataset.export;
      exportCitations(format);
    });

    // Keyboard shortcut: Escape to close sidebar
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && state.sidebarOpen) {
        closeSidebar();
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════
  // SIDEBAR
  // ═══════════════════════════════════════════════════════════════

  function openSidebar() {
    state.sidebarOpen = true;
    dom.sidebar.classList.add('open');
    dom.sidebarOverlay.classList.add('active');
  }

  function closeSidebar() {
    state.sidebarOpen = false;
    dom.sidebar.classList.remove('open');
    dom.sidebarOverlay.classList.remove('active');
  }

  // ═══════════════════════════════════════════════════════════════
  // LOAD TOOLS
  // ═══════════════════════════════════════════════════════════════

  async function loadTools() {
    try {
      const resp = await fetch('/api/v1/tools');
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.tools && Array.isArray(data.tools)) {
        dom.toolsList.innerHTML = data.tools.map((t) => `
          <li class="tool-item" data-tool="${esc(t.name || t.id || '')}">
            <span class="tool-dot"></span>
            <span class="tool-name">${esc(t.name || t.id || 'Unknown')}</span>
            <span class="tool-status">idle</span>
          </li>
        `).join('');
      }
    } catch (e) {
      // Tools endpoint unavailable; keep the default static list
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // QUERY EXECUTION
  // ═══════════════════════════════════════════════════════════════

  function runQuery() {
    const query = dom.queryInput.value.trim();
    if (!query) return;

    // Require auth
    if (!state.token) {
      showAuthModal();
      showToast('Please sign in to run queries.', 'warning');
      return;
    }

    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      showToast('A query is already running.', 'warning');
      return;
    }

    // Reset counters
    state.toolCallCount = 0;
    state.evidenceCount = 0;
    state.coverage = 0;
    state.currentResult = null;

    // Switch to workspace view
    dom.landing.style.display = 'none';
    dom.workspace.style.display = 'flex';
    dom.newQueryBtn.style.display = 'inline-flex';
    dom.activeQueryText.textContent = query;

    // Reset UI elements
    dom.traceTimeline.innerHTML = '';
    dom.claimsContainer.innerHTML = renderPlaceholder();
    dom.resultsSummary.style.display = 'none';
    dom.resultsSummary.textContent = '';
    dom.exportButtons.style.display = 'none';
    dom.querySubmit.disabled = true;

    updateStats(0, 0, 0, 0);
    setPhase('running', 'Starting');
    resetToolStatuses();
    startTimer();

    // WebSocket connection with auth token
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const tokenParam = state.token ? `?token=${encodeURIComponent(state.token)}` : '';
    const ws = new WebSocket(`${protocol}//${location.host}/ws/query${tokenParam}`);
    state.ws = ws;

    ws.onopen = () => {
      const msg = { query };
      if (state.activeProjectId) msg.project_id = state.activeProjectId;
      ws.send(JSON.stringify(msg));
      addTraceStep('info', 'Connecting to agent...', null);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleWsEvent(msg);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = () => {
      addTraceStep('tool-error', 'Connection error', 'Could not reach the agent. Is the server running?');
      setPhase('failed', 'Error');
      stopTimer();
      dom.querySubmit.disabled = false;
      showToast('WebSocket connection failed.', 'error');
    };

    ws.onclose = () => {
      state.ws = null;
      dom.querySubmit.disabled = false;
    };
  }

  // ═══════════════════════════════════════════════════════════════
  // WEBSOCKET EVENT HANDLING
  // ═══════════════════════════════════════════════════════════════

  function handleWsEvent(msg) {
    const type = msg.type;
    const data = msg.data || msg;

    switch (type) {
      case 'run_started':
        addTraceStep('phase-step', `Research started`, `"${esc(data.query)}"`);
        break;

      case 'phase':
        handlePhase(data);
        break;

      case 'plan_ready':
        handlePlanReady(data);
        break;

      case 'tool_calling':
        handleToolCalling(data);
        break;

      case 'tool_result':
        handleToolResult(data);
        break;

      case 'tool_error':
        handleToolError(data);
        break;

      case 'fallback':
        handleFallback(data);
        break;

      case 'evidence_check':
        handleEvidenceCheck(data);
        break;

      case 'budget_warning':
        addTraceStep('warning', 'Budget warning', esc(data.message));
        showToast(data.message, 'warning');
        break;

      case 'completed':
        handleCompleted(data);
        break;

      case 'failed':
        handleFailed(data);
        break;

      case 'error':
        addTraceStep('tool-error', 'Error', esc(data.message || 'An unknown error occurred'));
        setPhase('failed', 'Error');
        stopTimer();
        showToast(data.message || 'An error occurred', 'error');
        // If auth error, show login modal
        if (data.message && data.message.toLowerCase().includes('authentication')) {
          clearSession();
          showAuthModal();
        }
        break;

      default:
        console.log('Unknown event type:', type, data);
    }
  }

  // ─── Phase ─────────────────────────────────────────────────────
  function handlePhase(data) {
    const phaseNames = {
      decompose: 'Decomposing',
      gather: 'Gathering',
      synthesize: 'Synthesizing',
    };
    const phaseName = phaseNames[data.phase] || data.phase;
    setPhase(data.phase, phaseName);

    const iter = data.iteration ? ` (iteration ${data.iteration})` : '';
    addTraceStep('phase-step', `${phaseName}${iter}`, esc(data.message));
  }

  // ─── Plan Ready ────────────────────────────────────────────────
  function handlePlanReady(data) {
    const subQuestions = data.sub_questions || [];
    const step = addTraceStep('phase-step', `Plan ready: ${esc(data.scope || '')}`, `${subQuestions.length} sub-question${subQuestions.length !== 1 ? 's' : ''}`);

    if (subQuestions.length > 0) {
      const subDiv = document.createElement('div');
      subDiv.className = 'trace-subquestions';
      subQuestions.forEach((sq) => {
        const item = document.createElement('div');
        item.className = 'trace-subquestion';
        item.innerHTML = `<strong>${esc(sq.id || '')}</strong> ${esc(sq.question)} <code>${esc(sq.evidence_type || '')}</code>`;
        subDiv.appendChild(item);
      });
      step.querySelector('.trace-body').appendChild(subDiv);
    }
  }

  // ─── Tool Calling ──────────────────────────────────────────────
  function handleToolCalling(data) {
    state.toolCallCount++;
    animateStat(dom.statTools, state.toolCallCount);
    setToolStatus(data.tool, 'active', 'calling');

    const reason = data.reason ? `Reason: ${esc(data.reason)}` : '';
    addTraceStep('tool-call', `Calling <code>${esc(data.tool)}</code>`, `${esc(data.question || '')} ${reason}`);
  }

  // ─── Tool Result ───────────────────────────────────────────────
  function handleToolResult(data) {
    state.evidenceCount += (data.evidence_count || 0);
    animateStat(dom.statEvidence, state.evidenceCount);
    setToolStatus(data.tool, '', 'idle');

    addTraceStep('tool-result', `<code>${esc(data.tool)}</code> returned ${data.evidence_count || 0} result${data.evidence_count !== 1 ? 's' : ''}`, esc(data.summary || ''));
  }

  // ─── Tool Error ────────────────────────────────────────────────
  function handleToolError(data) {
    setToolStatus(data.tool, 'error', 'error');
    addTraceStep('tool-error', `<code>${esc(data.tool)}</code> failed`, esc(data.error || 'Unknown error'));
    showToast(`${data.tool} failed: ${data.error || 'Unknown error'}`, 'error');
  }

  // ─── Fallback ──────────────────────────────────────────────────
  function handleFallback(data) {
    setToolStatus(data.from_tool, 'error', 'failed');
    setToolStatus(data.to_tool, 'active', 'calling');
    addTraceStep('fallback', `Fallback: ${esc(data.from_tool)} failed`, `Trying <code>${esc(data.to_tool)}</code> instead`);
  }

  // ─── Evidence Check ────────────────────────────────────────────
  function handleEvidenceCheck(data) {
    state.coverage = Math.round((data.coverage || 0) * 100);
    animateStat(dom.statCoverage, state.coverage, '%');
    state.evidenceCount = data.total_evidence || state.evidenceCount;
    animateStat(dom.statEvidence, state.evidenceCount);

    addTraceStep('evidence', `Evidence check: ${state.coverage}% coverage`, `${data.answered || 0} answered, ${data.gaps || 0} gaps, ${data.total_evidence || 0} fragments`);
  }

  // ─── Completed ─────────────────────────────────────────────────
  function handleCompleted(data) {
    state.currentResult = data;
    setPhase('completed', 'Completed');
    stopTimer();
    resetToolStatuses();

    // Final stats
    if (data.total_tool_calls) {
      state.toolCallCount = data.total_tool_calls;
      animateStat(dom.statTools, state.toolCallCount);
    }
    if (data.elapsed_seconds) {
      updateElapsed(data.elapsed_seconds);
    }

    addTraceStep('tool-result', 'Analysis complete', `${(data.claims || []).length} claims extracted in ${data.elapsed_seconds || '?'}s`);

    // Show summary
    if (data.summary) {
      dom.resultsSummary.textContent = data.summary;
      dom.resultsSummary.style.display = 'block';
    }

    // Show claims
    renderClaims(data.claims || []);

    // Show export buttons
    if (data.claims && data.claims.length > 0) {
      dom.exportButtons.style.display = 'flex';
    }

    // Add to run history
    addToHistory(dom.activeQueryText.textContent, data);

    showToast(`Research complete: ${(data.claims || []).length} claims found.`, 'success');
  }

  // ─── Failed ────────────────────────────────────────────────────
  function handleFailed(data) {
    setPhase('failed', 'Failed');
    stopTimer();
    resetToolStatuses();
    addTraceStep('tool-error', 'Agent failed', esc(data.reason || 'Unknown reason'));
    showToast(`Research failed: ${data.reason || 'Unknown reason'}`, 'error');
  }

  // ═══════════════════════════════════════════════════════════════
  // TRACE RENDERING
  // ═══════════════════════════════════════════════════════════════

  function addTraceStep(type, label, detail) {
    // Remove active spinner from previous step
    const prevActive = dom.traceTimeline.querySelector('.trace-dot.active');
    if (prevActive) {
      prevActive.classList.remove('active');
    }

    const step = document.createElement('div');
    step.className = `trace-step ${type}`;

    const dotSymbols = {
      'phase-step': '\u25CF',
      'tool-call':  '\u26A1',
      'tool-result': '\u2713',
      'tool-error': '\u2717',
      'fallback':   '\u21BB',
      'evidence':   '\u25C6',
      'warning':    '\u26A0',
      'info':       '\u25CB',
    };

    const isActive = ['phase-step', 'tool-call', 'info'].includes(type);

    step.innerHTML = `
      <div class="trace-dot ${isActive ? 'active' : ''}">${dotSymbols[type] || '\u25CB'}</div>
      <div class="trace-body">
        <div class="trace-label">${label}</div>
        ${detail ? `<div class="trace-detail">${detail}</div>` : ''}
      </div>
    `;

    dom.traceTimeline.appendChild(step);
    dom.traceTimeline.scrollTop = dom.traceTimeline.scrollHeight;

    return step;
  }

  // ═══════════════════════════════════════════════════════════════
  // CLAIMS RENDERING
  // ═══════════════════════════════════════════════════════════════

  function renderClaims(claims) {
    if (!claims || claims.length === 0) {
      dom.claimsContainer.innerHTML = renderPlaceholder('No claims were extracted from this query.');
      return;
    }

    dom.claimsContainer.innerHTML = '';
    claims.forEach((claim, index) => {
      const card = createClaimCard(claim, index + 1);
      card.style.animationDelay = `${index * 80}ms`;
      dom.claimsContainer.appendChild(card);
    });
  }

  function createClaimCard(claim, num) {
    const card = document.createElement('div');
    card.className = 'claim-card';

    const statement = claim.statement || '';

    // Header — clickable to expand/collapse
    const header = document.createElement('div');
    header.className = 'claim-header';
    header.innerHTML = `
      <span class="claim-number">${num}</span>
      <span class="claim-statement truncated">${esc(statement)}</span>
      <span class="confidence-badge ${esc(claim.confidence || 'medium')}">${esc(claim.confidence || 'unknown')}</span>
      <svg class="claim-expand-icon" width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    `;

    // Click header to expand/collapse
    header.addEventListener('click', () => {
      card.classList.toggle('expanded');
    });
    card.appendChild(header);

    // Expanded body — full statement + metadata
    const body = document.createElement('div');
    body.className = 'claim-body';
    body.innerHTML = `<p style="margin:0">${esc(statement)}</p>`;
    card.appendChild(body);

    // Citations section (collapsible)
    const citations = claim.citations || [];
    const evidenceSpans = claim.evidence_spans || [];
    const conflicting = claim.conflicting_evidence || [];
    const totalItems = citations.length + evidenceSpans.length + conflicting.length;

    if (totalItems > 0) {
      const citationsSection = document.createElement('div');
      citationsSection.className = 'claim-citations';

      const toggleId = `citations-${claim.id || num}`;

      const toggle = document.createElement('button');
      toggle.className = 'citations-toggle';
      toggle.innerHTML = `
        <span>Citations & Evidence (${totalItems})</span>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 4.5l3 3 3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      `;

      const body = document.createElement('div');
      body.className = 'citations-body';
      body.id = toggleId;

      // Citations
      if (citations.length > 0) {
        body.innerHTML += `<div class="evidence-section-title">Sources</div>`;
        citations.forEach((c) => {
          body.innerHTML += renderCitationItem(c);
        });
      }

      // Evidence spans
      if (evidenceSpans.length > 0) {
        body.innerHTML += `<div class="evidence-section-title">Evidence</div>`;
        evidenceSpans.forEach((e) => {
          body.innerHTML += `<div class="evidence-span">"${esc(e.text || '')}"</div>`;
        });
      }

      // Conflicting evidence
      if (conflicting.length > 0) {
        body.innerHTML += `<div class="evidence-section-title" style="color:var(--rose)">Conflicting Evidence</div>`;
        conflicting.forEach((e) => {
          body.innerHTML += `<div class="evidence-span conflicting-span">"${esc(e.text || '')}"</div>`;
        });
      }

      toggle.addEventListener('click', () => {
        toggle.classList.toggle('open');
        body.classList.toggle('open');
      });

      citationsSection.appendChild(toggle);
      citationsSection.appendChild(body);
      card.appendChild(citationsSection);
    }

    return card;
  }

  function renderCitationItem(c) {
    const paperUrl = c.url || (c.doi ? `https://doi.org/${c.doi}` : '');
    let html = `<div class="citation-item">`;
    if (paperUrl) {
      html += `<a class="citation-title citation-title--link" href="${esc(paperUrl)}" target="_blank" rel="noopener">${esc(c.title || 'Untitled')}</a>`;
    } else {
      html += `<div class="citation-title">${esc(c.title || 'Untitled')}</div>`;
    }
    if (c.authors && c.authors.length) {
      html += `<div class="citation-authors">${esc(c.authors.join(', '))}</div>`;
    }
    html += `<div class="citation-meta">`;
    if (c.doi) {
      html += `<a class="citation-doi citation-doi--link" href="https://doi.org/${esc(c.doi)}" target="_blank" rel="noopener">DOI: ${esc(c.doi)}</a>`;
    }
    if (c.published_date) {
      html += `<span class="citation-date">${esc(c.published_date)}</span>`;
    }
    html += `</div></div>`;
    return html;
  }

  function renderPlaceholder(message) {
    return `
      <div class="results-placeholder">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 4" opacity="0.3"/><path d="M24 16v8l6 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"/></svg>
        <p>${message || 'Results will appear here once the agent completes its analysis.'}</p>
      </div>
    `;
  }

  // ═══════════════════════════════════════════════════════════════
  // PDF UPLOAD
  // ═══════════════════════════════════════════════════════════════

  function handlePdfUpload(file) {
    if (!file) return;

    if (!state.token) {
      showAuthModal();
      showToast('Please sign in to upload PDFs.', 'warning');
      return;
    }

    if (file.type !== 'application/pdf') {
      showToast('Only PDF files are supported.', 'error');
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      showToast('File is too large. Maximum size is 50 MB.', 'error');
      return;
    }

    // Show progress UI
    dom.pdfDropzone.style.display = 'none';
    dom.uploadProgressWrap.style.display = 'block';
    dom.uploadFilename.textContent = file.name;
    dom.uploadProgress.style.width = '0%';
    dom.uploadStatus.textContent = 'Uploading...';
    dom.uploadStatus.className = 'upload-status';

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        dom.uploadProgress.style.width = pct + '%';
        dom.uploadStatus.textContent = `Uploading... ${pct}%`;
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status === 401) {
        clearSession();
        showAuthModal();
        showToast('Session expired. Please sign in again.', 'warning');
        dom.pdfDropzone.style.display = 'flex';
        dom.uploadProgressWrap.style.display = 'none';
        return;
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        dom.uploadProgress.style.width = '100%';
        dom.uploadStatus.textContent = 'Upload complete';
        dom.uploadStatus.className = 'upload-status success';
        showToast(`PDF "${file.name}" uploaded successfully.`, 'success');
        addToPdfLibrary(file.name);

        // Reset after delay
        setTimeout(() => {
          dom.pdfDropzone.style.display = 'flex';
          dom.uploadProgressWrap.style.display = 'none';
        }, 2000);
      } else {
        let errMsg = 'Upload failed';
        try {
          const resp = JSON.parse(xhr.responseText);
          errMsg = resp.detail || resp.message || errMsg;
        } catch (e) { /* ignore */ }

        dom.uploadStatus.textContent = errMsg;
        dom.uploadStatus.className = 'upload-status error';
        showToast(errMsg, 'error');

        setTimeout(() => {
          dom.pdfDropzone.style.display = 'flex';
          dom.uploadProgressWrap.style.display = 'none';
        }, 3000);
      }
    });

    xhr.addEventListener('error', () => {
      dom.uploadStatus.textContent = 'Upload failed — network error';
      dom.uploadStatus.className = 'upload-status error';
      showToast('Upload failed due to a network error.', 'error');

      setTimeout(() => {
        dom.pdfDropzone.style.display = 'flex';
        dom.uploadProgressWrap.style.display = 'none';
      }, 3000);
    });

    xhr.open('POST', '/api/v1/upload/pdf');
    // Add auth header to XHR
    if (state.token) {
      xhr.setRequestHeader('Authorization', `Bearer ${state.token}`);
    }
    xhr.send(formData);
  }

  // ═══════════════════════════════════════════════════════════════
  // CITATION EXPORT
  // ═══════════════════════════════════════════════════════════════

  function exportCitations(format) {
    if (!state.currentResult || !state.currentResult.claims) {
      showToast('No results to export.', 'warning');
      return;
    }

    // Collect all unique citations
    const citationMap = new Map();
    state.currentResult.claims.forEach((claim) => {
      (claim.citations || []).forEach((c) => {
        const key = c.source_id || c.doi || c.title || JSON.stringify(c);
        if (!citationMap.has(key)) {
          citationMap.set(key, c);
        }
      });
    });

    const citations = Array.from(citationMap.values());
    if (citations.length === 0) {
      showToast('No citations found in results.', 'warning');
      return;
    }

    let content = '';
    let filename = '';
    let mimeType = 'text/plain';

    switch (format) {
      case 'bibtex':
        content = generateBibTeX(citations);
        filename = 'evidentia_references.bib';
        break;
      case 'ris':
        content = generateRIS(citations);
        filename = 'evidentia_references.ris';
        break;
      case 'apa':
        content = generateAPA(citations);
        filename = 'evidentia_references_apa.txt';
        break;
      default:
        return;
    }

    downloadFile(content, filename, mimeType);
    showToast(`Exported ${citations.length} citation${citations.length !== 1 ? 's' : ''} as ${format.toUpperCase()}.`, 'success');
  }

  function generateBibTeX(citations) {
    return citations.map((c, i) => {
      const key = sanitizeKey(c.title || `ref${i + 1}`);
      let entry = `@article{${key},\n`;
      entry += `  title     = {${c.title || 'Untitled'}},\n`;
      if (c.authors && c.authors.length) {
        entry += `  author    = {${c.authors.join(' and ')}},\n`;
      }
      if (c.published_date) {
        const year = c.published_date.substring(0, 4);
        entry += `  year      = {${year}},\n`;
      }
      if (c.doi) {
        entry += `  doi       = {${c.doi}},\n`;
      }
      if (c.url) {
        entry += `  url       = {${c.url}},\n`;
      }
      entry += `}`;
      return entry;
    }).join('\n\n');
  }

  function generateRIS(citations) {
    return citations.map((c) => {
      let entry = 'TY  - JOUR\n';
      if (c.title) entry += `TI  - ${c.title}\n`;
      if (c.authors) {
        c.authors.forEach((a) => {
          entry += `AU  - ${a}\n`;
        });
      }
      if (c.published_date) {
        entry += `PY  - ${c.published_date.substring(0, 4)}\n`;
        entry += `DA  - ${c.published_date}\n`;
      }
      if (c.doi) entry += `DO  - ${c.doi}\n`;
      if (c.url) entry += `UR  - ${c.url}\n`;
      entry += 'ER  -\n';
      return entry;
    }).join('\n');
  }

  function generateAPA(citations) {
    return citations.map((c) => {
      let parts = [];

      // Authors
      if (c.authors && c.authors.length) {
        if (c.authors.length === 1) {
          parts.push(c.authors[0]);
        } else if (c.authors.length === 2) {
          parts.push(`${c.authors[0]} & ${c.authors[1]}`);
        } else {
          parts.push(`${c.authors[0]} et al.`);
        }
      } else {
        parts.push('Unknown Author');
      }

      // Year
      if (c.published_date) {
        parts.push(`(${c.published_date.substring(0, 4)})`);
      } else {
        parts.push('(n.d.)');
      }

      // Title
      parts.push(c.title || 'Untitled');

      let entry = parts.join('. ') + '.';

      if (c.doi) {
        entry += ` https://doi.org/${c.doi}`;
      } else if (c.url) {
        entry += ` Retrieved from ${c.url}`;
      }

      return entry;
    }).join('\n\n');
  }

  function sanitizeKey(str) {
    return str
      .toLowerCase()
      .replace(/[^a-z0-9]/g, '_')
      .replace(/_+/g, '_')
      .substring(0, 30);
  }

  function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ═══════════════════════════════════════════════════════════════
  // STATS & TIMER
  // ═══════════════════════════════════════════════════════════════

  function updateStats(tools, evidence, coverage, elapsed) {
    dom.statTools.textContent = tools;
    dom.statEvidence.textContent = evidence;
    dom.statCoverage.innerHTML = coverage + '<small>%</small>';
    dom.statTime.innerHTML = elapsed + '<small>s</small>';
  }

  function animateStat(el, targetValue, suffix) {
    const current = parseInt(el.textContent) || 0;
    if (current === targetValue) return;

    el.classList.add('animating');

    const duration = 400;
    const startTime = performance.now();

    function tick(now) {
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const val = Math.round(current + (targetValue - current) * eased);

      if (suffix) {
        el.innerHTML = val + `<small>${suffix}</small>`;
      } else {
        el.textContent = val;
      }

      if (progress < 1) {
        requestAnimationFrame(tick);
      } else {
        el.classList.remove('animating');
      }
    }

    requestAnimationFrame(tick);
  }

  function startTimer() {
    state.startTime = Date.now();
    clearInterval(state.timerInterval);
    state.timerInterval = setInterval(() => {
      const elapsed = ((Date.now() - state.startTime) / 1000).toFixed(1);
      dom.statTime.innerHTML = elapsed + '<small>s</small>';
    }, 100);
  }

  function stopTimer() {
    clearInterval(state.timerInterval);
    state.timerInterval = null;
  }

  function updateElapsed(seconds) {
    const val = typeof seconds === 'number' ? seconds.toFixed(1) : seconds;
    dom.statTime.innerHTML = val + '<small>s</small>';
  }

  // ═══════════════════════════════════════════════════════════════
  // TOOL STATUS
  // ═══════════════════════════════════════════════════════════════

  function setToolStatus(toolName, className, statusText) {
    if (!toolName) return;
    const normalized = toolName.toLowerCase().replace(/[\s-]/g, '_');

    const items = dom.toolsList.querySelectorAll('.tool-item');
    items.forEach((item) => {
      const itemTool = (item.dataset.tool || '').toLowerCase().replace(/[\s-]/g, '_');
      const itemName = (item.querySelector('.tool-name')?.textContent || '').toLowerCase().replace(/[\s-]/g, '_');

      if (itemTool === normalized || itemName === normalized || itemTool.includes(normalized) || normalized.includes(itemTool)) {
        item.className = `tool-item ${className}`;
        const statusEl = item.querySelector('.tool-status');
        if (statusEl) statusEl.textContent = statusText;
      }
    });
  }

  function resetToolStatuses() {
    dom.toolsList.querySelectorAll('.tool-item').forEach((item) => {
      item.className = 'tool-item';
      const statusEl = item.querySelector('.tool-status');
      if (statusEl) statusEl.textContent = 'idle';
    });
  }

  // ═══════════════════════════════════════════════════════════════
  // PHASE BADGE
  // ═══════════════════════════════════════════════════════════════

  function setPhase(phase, label) {
    dom.tracePhase.textContent = label;
    dom.tracePhase.className = `phase-badge ${phase}`;
  }

  // ═══════════════════════════════════════════════════════════════
  // RUN HISTORY
  // ═══════════════════════════════════════════════════════════════

  function addToHistory(query, data) {
    const entry = {
      query: query,
      timestamp: Date.now(),
      claimCount: (data.claims || []).length,
      elapsed: data.elapsed_seconds,
      data: data,
    };

    state.runHistory.unshift(entry);
    if (state.runHistory.length > 20) {
      state.runHistory.pop();
    }

    saveHistory();
    renderHistory();
  }

  function renderHistory() {
    if (state.runHistory.length === 0) {
      dom.historyList.innerHTML = '<li class="history-empty">No previous runs</li>';
      return;
    }

    dom.historyList.innerHTML = state.runHistory.map((entry, i) => {
      const timeAgo = formatTimeAgo(entry.timestamp);
      const truncated = entry.query.length > 36 ? entry.query.substring(0, 36) + '...' : entry.query;
      return `
        <li class="history-item" data-index="${i}" title="${esc(entry.query)}">
          <span class="history-item-dot"></span>
          <span class="history-item-text">${esc(truncated)}</span>
          <span class="history-item-time">${timeAgo}</span>
        </li>
      `;
    }).join('');

    // Click handler for history items
    dom.historyList.querySelectorAll('.history-item').forEach((item) => {
      item.addEventListener('click', () => {
        const idx = parseInt(item.dataset.index);
        const entry = state.runHistory[idx];
        if (entry && entry.data) {
          loadHistoryEntry(entry);
        }
      });
    });
  }

  function loadHistoryEntry(entry) {
    closeSidebar();

    dom.landing.style.display = 'none';
    dom.workspace.style.display = 'flex';
    dom.newQueryBtn.style.display = 'inline-flex';
    dom.activeQueryText.textContent = entry.query;

    dom.traceTimeline.innerHTML = '';
    addTraceStep('tool-result', 'Loaded from history', `${entry.claimCount} claims, ${entry.elapsed || '?'}s`);
    setPhase('completed', 'Completed');

    state.currentResult = entry.data;

    if (entry.data.summary) {
      dom.resultsSummary.textContent = entry.data.summary;
      dom.resultsSummary.style.display = 'block';
    }

    renderClaims(entry.data.claims || []);

    if (entry.data.claims && entry.data.claims.length > 0) {
      dom.exportButtons.style.display = 'flex';
    }

    updateStats(
      entry.data.total_tool_calls || 0,
      entry.data.total_evidence || 0,
      100,
      entry.data.elapsed_seconds || 0
    );
  }

  function _storageKey(base) {
    return state.userId ? `evidentia_${base}_${state.userId}` : `evidentia_${base}`;
  }

  function saveHistory() {
    try {
      const lite = state.runHistory.map((e) => ({
        query: e.query,
        timestamp: e.timestamp,
        claimCount: e.claimCount,
        elapsed: e.elapsed,
      }));
      localStorage.setItem(_storageKey('history'), JSON.stringify(lite));
    } catch (e) { /* localStorage full, ignore */ }
  }

  function loadHistory() {
    try {
      const stored = localStorage.getItem(_storageKey('history'));
      if (stored) {
        const lite = JSON.parse(stored);
        state.runHistory = lite.map((e) => ({ ...e, data: null }));
      } else {
        state.runHistory = [];
      }
      renderHistory();
    } catch (e) { /* ignore */ }
  }

  function formatTimeAgo(timestamp) {
    const seconds = Math.floor((Date.now() - timestamp) / 1000);
    if (seconds < 60) return 'now';
    if (seconds < 3600) return Math.floor(seconds / 60) + 'm';
    if (seconds < 86400) return Math.floor(seconds / 3600) + 'h';
    return Math.floor(seconds / 86400) + 'd';
  }

  // ═══════════════════════════════════════════════════════════════
  // PDF LIBRARY
  // ═══════════════════════════════════════════════════════════════

  function addToPdfLibrary(filename) {
    if (state.pdfLibrary.includes(filename)) return;
    state.pdfLibrary.push(filename);
    savePdfLibrary();
    renderPdfLibrary();
  }

  function renderPdfLibrary() {
    if (state.pdfLibrary.length === 0) {
      dom.pdfLibrary.innerHTML = '<li class="pdf-empty">No PDFs uploaded</li>';
      return;
    }

    dom.pdfLibrary.innerHTML = state.pdfLibrary.map((name) => `
      <li class="pdf-item">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M9 1H4a1 1 0 00-1 1v12a1 1 0 001 1h8a1 1 0 001-1V5L9 1z" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M9 1v4h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(name)}</span>
      </li>
    `).join('');
  }

  function savePdfLibrary() {
    try {
      localStorage.setItem(_storageKey('pdfs'), JSON.stringify(state.pdfLibrary));
    } catch (e) { /* ignore */ }
  }

  function loadPdfLibrary() {
    try {
      const stored = localStorage.getItem(_storageKey('pdfs'));
      if (stored) {
        state.pdfLibrary = JSON.parse(stored);
      } else {
        state.pdfLibrary = [];
      }
      renderPdfLibrary();
    } catch (e) { /* ignore */ }
  }

  // ═══════════════════════════════════════════════════════════════
  // NAVIGATION
  // ═══════════════════════════════════════════════════════════════

  function resetToLanding() {
    // Close any active WebSocket
    if (state.ws) {
      state.ws.close();
      state.ws = null;
    }
    stopTimer();

    dom.workspace.style.display = 'none';
    dom.landing.style.display = 'flex';
    dom.newQueryBtn.style.display = 'none';
    dom.querySubmit.disabled = false;
    dom.queryInput.value = '';
    dom.queryInput.style.height = 'auto';
    dom.queryInput.focus();
  }

  // ═══════════════════════════════════════════════════════════════
  // TOASTS
  // ═══════════════════════════════════════════════════════════════

  function showToast(message, type) {
    type = type || 'info';
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    dom.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('toast-out');
      toast.addEventListener('animationend', () => {
        toast.remove();
      });
    }, 4000);
  }

  // ═══════════════════════════════════════════════════════════════
  // PROJECTS
  // ═══════════════════════════════════════════════════════════════

  function bindProjectEvents() {
    if (dom.newProjectBtn) {
      dom.newProjectBtn.addEventListener('click', () => promptNewProject());
    }
    if (dom.quickCreateProject) {
      dom.quickCreateProject.addEventListener('click', () => promptNewProject());
    }
    if (dom.projectSelect) {
      dom.projectSelect.addEventListener('change', (e) => {
        state.activeProjectId = e.target.value || null;
      });
    }
  }

  async function loadProjects() {
    if (!state.token) return;
    try {
      const resp = await authFetch('/api/v1/projects');
      if (!resp.ok) return;
      const data = await resp.json();
      state.projects = data.projects || [];
      renderProjectsList();
      renderProjectSelect();
      // Show project selector if logged in
      if (dom.projectSelector) dom.projectSelector.style.display = 'flex';
    } catch (e) {
      // Silently fail — projects are optional
    }
  }

  function renderProjectsList() {
    if (!dom.projectsList) return;
    if (state.projects.length === 0) {
      dom.projectsList.innerHTML = '<li class="project-empty">No projects yet</li>';
      return;
    }
    dom.projectsList.innerHTML = state.projects.map(p => `
      <li class="project-item${state.activeProjectId === p.id ? ' active' : ''}" data-id="${esc(p.id)}">
        <span class="project-name">${esc(p.name)}</span>
        <span class="project-count">${p.run_count} runs</span>
      </li>
    `).join('');

    dom.projectsList.querySelectorAll('.project-item').forEach(el => {
      el.addEventListener('click', () => {
        state.activeProjectId = el.dataset.id;
        renderProjectsList();
        renderProjectSelect();
      });
    });
  }

  function renderProjectSelect() {
    if (!dom.projectSelect) return;
    const options = ['<option value="">No project</option>'];
    state.projects.forEach(p => {
      const sel = state.activeProjectId === p.id ? ' selected' : '';
      options.push(`<option value="${esc(p.id)}"${sel}>${esc(p.name)}</option>`);
    });
    dom.projectSelect.innerHTML = options.join('');
  }

  async function promptNewProject() {
    const name = prompt('Project name:');
    if (!name || !name.trim()) return;

    try {
      const resp = await authFetch('/api/v1/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!resp.ok) {
        showToast('Failed to create project', 'error');
        return;
      }
      const project = await resp.json();
      state.projects.unshift(project);
      state.activeProjectId = project.id;
      renderProjectsList();
      renderProjectSelect();
      showToast(`Project "${name.trim()}" created`, 'success');
    } catch (e) {
      showToast('Failed to create project', 'error');
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // SYSTEMATIC REVIEW
  // ═══════════════════════════════════════════════════════════════

  function bindReviewEvents() {
    // Mode tabs
    if (dom.modeQuery) {
      dom.modeQuery.addEventListener('click', () => switchMode('query'));
    }
    if (dom.modeReview) {
      dom.modeReview.addEventListener('click', () => switchMode('review'));
    }

    // Max results slider
    if (dom.reviewMaxResults) {
      dom.reviewMaxResults.addEventListener('input', () => {
        if (dom.reviewMaxResultsVal) dom.reviewMaxResultsVal.textContent = dom.reviewMaxResults.value;
      });
    }

    // Criteria add/remove
    if ($('#add-inclusion')) {
      $('#add-inclusion').addEventListener('click', () => addCriteriaRow('inclusion-list'));
    }
    if ($('#add-exclusion')) {
      $('#add-exclusion').addEventListener('click', () => addCriteriaRow('exclusion-list'));
    }

    // Review form submit
    if (dom.reviewForm) {
      dom.reviewForm.addEventListener('submit', (e) => {
        e.preventDefault();
        startReview();
      });
    }

    // Review tabs
    $$('.review-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const target = tab.dataset.tab;
        $$('.review-tab').forEach(t => t.classList.remove('review-tab--active'));
        tab.classList.add('review-tab--active');
        if (dom.reviewPapersIncluded) dom.reviewPapersIncluded.style.display = target === 'included' ? 'flex' : 'none';
        if (dom.reviewPapersExcluded) dom.reviewPapersExcluded.style.display = target === 'excluded' ? 'flex' : 'none';
        if (dom.reviewPapersUncertain) dom.reviewPapersUncertain.style.display = target === 'uncertain' ? 'flex' : 'none';
      });
    });

    // Review export buttons
    if (dom.reviewExportButtons) {
      dom.reviewExportButtons.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-review-export]');
        if (!btn) return;
        exportReview(btn.dataset.reviewExport);
      });
    }

    // Criteria remove delegation
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('criteria-remove')) {
        const item = e.target.closest('.criteria-item');
        const list = item.parentElement;
        if (list.children.length > 1) item.remove();
      }
    });
  }

  function switchMode(mode) {
    state.reviewMode = mode === 'review';
    if (dom.modeQuery) dom.modeQuery.classList.toggle('mode-tab--active', mode === 'query');
    if (dom.modeReview) dom.modeReview.classList.toggle('mode-tab--active', mode === 'review');
    if (dom.queryForm) dom.queryForm.style.display = mode === 'query' ? 'block' : 'none';
    if (dom.reviewFormSection) dom.reviewFormSection.style.display = mode === 'review' ? 'block' : 'none';
    // Hide elements not relevant in review mode
    const chips = $('.example-chips');
    if (chips) chips.style.display = mode === 'query' ? 'flex' : 'none';
    const upload = $('.upload-section');
    if (upload) upload.style.display = mode === 'query' ? 'block' : 'none';
  }

  function addCriteriaRow(listId) {
    const list = document.getElementById(listId);
    if (!list) return;
    const item = document.createElement('div');
    item.className = 'criteria-item';
    item.innerHTML = '<input type="text" class="criteria-input" placeholder="Enter criterion..." /><button type="button" class="btn btn-ghost btn-xs criteria-remove" title="Remove">&times;</button>';
    list.appendChild(item);
    item.querySelector('input').focus();
  }

  function startReview() {
    if (!state.token) {
      showAuthModal();
      showToast('Please sign in to run reviews.', 'warning');
      return;
    }

    if (state.reviewWs && state.reviewWs.readyState === WebSocket.OPEN) {
      showToast('A review is already running.', 'warning');
      return;
    }

    const question = dom.reviewQuestion.value.trim();
    if (!question || question.length < 10) {
      showToast('Research question must be at least 10 characters.', 'warning');
      return;
    }

    // Gather criteria
    const inclusion = [];
    $$('#inclusion-list .criteria-input').forEach(input => {
      const v = input.value.trim();
      if (v) inclusion.push(v);
    });
    const exclusion = [];
    $$('#exclusion-list .criteria-input').forEach(input => {
      const v = input.value.trim();
      if (v) exclusion.push(v);
    });

    if (inclusion.length === 0) {
      showToast('At least one inclusion criterion is required.', 'warning');
      return;
    }

    // Gather databases
    const databases = [];
    $$('.db-checkboxes input[type="checkbox"]:checked').forEach(cb => {
      databases.push(cb.value);
    });
    if (databases.length === 0) {
      showToast('Select at least one database.', 'warning');
      return;
    }

    const maxResults = parseInt(dom.reviewMaxResults.value) || 100;
    const reviewMode = document.querySelector('input[name="review-mode"]:checked')?.value || 'rigorous';

    // Switch to review workspace
    dom.landing.style.display = 'none';
    if (dom.workspace) dom.workspace.style.display = 'none';
    dom.reviewWorkspace.style.display = 'flex';
    dom.newQueryBtn.style.display = 'inline-flex';
    dom.reviewQueryText.textContent = question;

    // Reset PRISMA UI
    resetReviewUI();
    setReviewPhase('identification');
    startReviewTimer();

    // Connect WebSocket
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const tokenParam = state.token ? `?token=${encodeURIComponent(state.token)}` : '';
    const ws = new WebSocket(`${protocol}//${location.host}/ws/review${tokenParam}`);
    state.reviewWs = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({
        research_question: question,
        inclusion_criteria: inclusion,
        exclusion_criteria: exclusion,
        databases: databases,
        max_results_per_database: maxResults,
        mode: reviewMode,
        project_id: state.activeProjectId || undefined,
      }));
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleReviewEvent(msg);
      } catch (e) {
        console.error('Failed to parse review event:', e);
      }
    };

    ws.onerror = () => {
      showToast('Review connection failed.', 'error');
      stopReviewTimer();
    };

    ws.onclose = () => {
      state.reviewWs = null;
    };
  }

  function resetReviewUI() {
    state.reviewPapers = { included: [], excluded: [], uncertain: [] };
    state.reviewPrisma = null;
    if (dom.prismaIdentified) dom.prismaIdentified.textContent = '0';
    if (dom.prismaUnique) dom.prismaUnique.textContent = '0';
    if (dom.prismaDupesNote) dom.prismaDupesNote.textContent = '';
    if (dom.prismaScreened) dom.prismaScreened.textContent = '0';
    if (dom.prismaIncluded) dom.prismaIncluded.textContent = '0';
    if (dom.prismaExcluded) dom.prismaExcluded.textContent = '0';
    if (dom.prismaUncertain) dom.prismaUncertain.textContent = '0';
    if (dom.prismaDbBreakdown) dom.prismaDbBreakdown.textContent = '';
    if (dom.prismaScreeningProgress) dom.prismaScreeningProgress.textContent = '';
    if (dom.reviewPapersIncluded) dom.reviewPapersIncluded.innerHTML = '';
    if (dom.reviewPapersExcluded) dom.reviewPapersExcluded.innerHTML = '';
    if (dom.reviewPapersUncertain) dom.reviewPapersUncertain.innerHTML = '';
    if (dom.reviewExportButtons) dom.reviewExportButtons.style.display = 'none';
    if (dom.tabIncludedCount) dom.tabIncludedCount.textContent = '0';
    if (dom.tabExcludedCount) dom.tabExcludedCount.textContent = '0';
    if (dom.tabUncertainCount) dom.tabUncertainCount.textContent = '0';
    if (dom.reviewModeBadge) dom.reviewModeBadge.style.display = 'none';
    if (dom.reviewRunHash) dom.reviewRunHash.style.display = 'none';
    // Reset phases
    $$('.prisma-phase').forEach(el => { el.classList.remove('active', 'complete'); });
    // Reset quality and contradiction panels
    const qualitySummary = document.getElementById('quality-summary');
    if (qualitySummary) qualitySummary.style.display = 'none';
    const contradictionReport = document.getElementById('contradiction-report');
    if (contradictionReport) contradictionReport.style.display = 'none';
  }

  function handleReviewStarted(data) {
    // Show mode badge
    if (dom.reviewModeBadge) {
      const modeLabels = { fast: 'Fast', rigorous: 'Rigorous', publication: 'Publication' };
      dom.reviewModeBadge.textContent = modeLabels[data.mode] || data.mode;
      dom.reviewModeBadge.className = 'review-mode-badge review-mode-badge--' + (data.mode || 'rigorous');
      dom.reviewModeBadge.style.display = 'inline-block';
    }
    // Show run hash
    if (dom.reviewRunHash && data.run_hash) {
      dom.reviewRunHash.textContent = '#' + data.run_hash.substring(0, 8);
      dom.reviewRunHash.title = 'Reproducibility hash: ' + data.run_hash;
      dom.reviewRunHash.style.display = 'inline-block';
    }
    // Show info about screening config
    const passes = data.screening_passes || 1;
    const qualityEnabled = data.quality_scoring;
    const contradictionsEnabled = data.contradiction_detection;
    let infoMsg = `Mode: ${data.mode || 'rigorous'} | ${passes} screening pass${passes !== 1 ? 'es' : ''}`;
    if (qualityEnabled) infoMsg += ' | Quality scoring';
    if (contradictionsEnabled) infoMsg += ' | Contradiction detection';
    if (dom.prismaScreeningProgress) dom.prismaScreeningProgress.textContent = infoMsg;
  }

  function setReviewPhase(phase) {
    const order = ['identification', 'deduplication', 'screening', 'quality_scoring', 'contradiction_detection', 'complete'];
    const idx = order.indexOf(phase);
    order.forEach((p, i) => {
      const el = document.getElementById('phase-' + p);
      if (!el) return;
      el.classList.remove('active', 'complete');
      if (i < idx) el.classList.add('complete');
      else if (i === idx) el.classList.add('active');
    });
  }

  function startReviewTimer() {
    state.reviewStartTime = Date.now();
    clearInterval(state.reviewTimerInterval);
    state.reviewTimerInterval = setInterval(() => {
      const elapsed = ((Date.now() - state.reviewStartTime) / 1000).toFixed(1);
      if (dom.reviewElapsed) dom.reviewElapsed.textContent = elapsed + 's';
    }, 100);
  }

  function stopReviewTimer() {
    clearInterval(state.reviewTimerInterval);
    state.reviewTimerInterval = null;
  }

  function handleReviewEvent(msg) {
    const type = msg.type;
    const data = msg.data || msg;

    switch (type) {
      case 'review_started':
        handleReviewStarted(data);
        break;

      case 'review_phase_started':
        setReviewPhase(data.phase);
        break;

      case 'review_database_searching':
        setToolStatus(data.database, 'active', 'searching');
        break;

      case 'review_database_complete': {
        setToolStatus(data.database, '', 'idle');
        const count = data.count || 0;
        if (dom.prismaDbBreakdown) {
          const existing = dom.prismaDbBreakdown.textContent;
          const dbName = (data.database || '').replace('_search', '').replace('_', ' ');
          dom.prismaDbBreakdown.textContent = existing ? existing + ' | ' + dbName + ': ' + count : dbName + ': ' + count;
        }
        if (data.error) {
          showToast(`${data.database}: ${data.error}`, 'warning');
        }
        break;
      }

      case 'review_identification_complete':
        if (dom.prismaIdentified) dom.prismaIdentified.textContent = data.total || 0;
        break;

      case 'review_deduplication_complete':
        if (dom.prismaUnique) dom.prismaUnique.textContent = data.unique || 0;
        if (dom.prismaDupesNote) dom.prismaDupesNote.textContent = (data.duplicates || 0) + ' duplicates removed';
        if (dom.prismaScreened) dom.prismaScreened.textContent = data.unique || 0;
        break;

      case 'review_screening_progress':
        if (dom.prismaScreeningProgress) {
          dom.prismaScreeningProgress.textContent = `Screening: ${data.screened}/${data.total} (batch ${data.batch}/${data.total_batches})`;
        }
        break;

      case 'review_screening_complete':
        if (dom.prismaIncluded) dom.prismaIncluded.textContent = data.included || 0;
        if (dom.prismaExcluded) dom.prismaExcluded.textContent = data.excluded || 0;
        if (dom.prismaUncertain) dom.prismaUncertain.textContent = data.uncertain || 0;
        if (dom.prismaScreeningProgress) dom.prismaScreeningProgress.textContent = 'Screening complete';
        break;

      case 'review_quality_complete':
        handleQualityComplete(data);
        break;

      case 'review_contradictions_complete':
        handleContradictionsComplete(data);
        break;

      case 'review_completed':
        handleReviewCompleted(data);
        break;

      case 'review_failed':
        showToast(`Review failed: ${data.reason || 'Unknown error'}`, 'error');
        stopReviewTimer();
        break;

      case 'error':
        showToast(data.message || 'An error occurred', 'error');
        stopReviewTimer();
        if (data.message && data.message.toLowerCase().includes('authentication')) {
          clearSession();
          showAuthModal();
        }
        break;

      default:
        console.log('Unknown review event:', type, data);
    }
  }

  function handleQualityComplete(data) {
    const summaryEl = document.getElementById('quality-summary');
    const avgEl = document.getElementById('quality-avg-score');
    const distEl = document.getElementById('quality-grade-distribution');
    if (!summaryEl) return;

    summaryEl.style.display = 'block';

    if (data.error) {
      avgEl.textContent = '—';
      distEl.innerHTML = '<span class="quality-error">Quality scoring unavailable</span>';
      return;
    }

    const avg = data.average_score || 0;
    const grade = avg >= 0.8 ? 'A' : avg >= 0.65 ? 'B' : avg >= 0.5 ? 'C' : avg >= 0.35 ? 'D' : 'F';
    avgEl.textContent = grade + ' (' + (avg * 100).toFixed(0) + '%)';
    avgEl.className = 'quality-avg-badge quality-grade-' + grade.toLowerCase();

    const dist = data.grade_distribution || {};
    const grades = ['A', 'B', 'C', 'D', 'F'];
    distEl.innerHTML = grades.map(g => {
      const count = dist[g] || 0;
      if (count === 0) return '';
      return `<span class="quality-grade-pill quality-grade-${g.toLowerCase()}">${g}: ${count}</span>`;
    }).filter(Boolean).join('');
  }

  function handleContradictionsComplete(data) {
    const reportEl = document.getElementById('contradiction-report');
    const countEl = document.getElementById('contradiction-count');
    const summaryEl = document.getElementById('contradiction-summary');
    const listEl = document.getElementById('contradiction-list');
    const consensusEl = document.getElementById('consensus-areas');
    if (!reportEl) return;

    reportEl.style.display = 'block';

    if (data.error) {
      summaryEl.textContent = 'Contradiction analysis unavailable';
      return;
    }

    const total = data.total_contradictions || 0;
    countEl.textContent = total;
    countEl.className = 'contradiction-count-badge' + (total > 0 ? ' has-contradictions' : '');
    summaryEl.textContent = data.summary || '';

    // Type distribution
    const typeDist = data.type_distribution || {};
    const typeKeys = Object.keys(typeDist);
    if (typeKeys.length > 0) {
      const typeDistHtml = typeKeys.map(t => {
        const count = typeDist[t];
        return `<span class="contradiction-type-pill contradiction-type-${esc(t)}">${esc(t)}: ${count}</span>`;
      }).join('');
      summaryEl.innerHTML = esc(data.summary || '') + '<div class="contradiction-type-dist">' + typeDistHtml + '</div>';
    }

    // Render contradiction pairs
    const contradictions = data.contradictions || [];
    if (contradictions.length > 0) {
      listEl.innerHTML = contradictions.map(c => {
        const severityClass = 'severity-' + (c.severity || 'moderate');
        const ctype = c.contradiction_type || 'unknown';
        let html = `<div class="contradiction-item ${severityClass}">`;
        html += `<div class="contradiction-item-header">`;
        html += `<div class="contradiction-severity">${esc(c.severity || 'moderate').toUpperCase()}</div>`;
        html += `<span class="contradiction-type-badge contradiction-type-${esc(ctype)}">${esc(ctype)}</span>`;
        html += `</div>`;
        html += `<div class="contradiction-desc">${esc(c.description)}</div>`;
        // Evidence spans
        if (c.evidence_a) {
          html += `<div class="contradiction-evidence"><span class="contradiction-evidence-label">A:</span> "${esc(c.evidence_a)}"</div>`;
        }
        if (c.evidence_b) {
          html += `<div class="contradiction-evidence"><span class="contradiction-evidence-label">B:</span> "${esc(c.evidence_b)}"</div>`;
        }
        html += `<div class="contradiction-papers">`;
        html += `<span>${esc(c.paper_a_title || 'Paper ' + c.paper_a_index)}</span>`;
        html += `<span class="contradiction-vs">vs</span>`;
        html += `<span>${esc(c.paper_b_title || 'Paper ' + c.paper_b_index)}</span>`;
        html += `</div></div>`;
        return html;
      }).join('');
    }

    // Render consensus areas
    const consensus = data.consensus_areas || [];
    if (consensus.length > 0) {
      consensusEl.innerHTML = '<div class="consensus-header">Areas of Consensus</div>' +
        consensus.map(a => `<div class="consensus-item">${esc(a)}</div>`).join('');
    }
  }

  function handleReviewCompleted(data) {
    setReviewPhase('complete');
    stopReviewTimer();
    resetToolStatuses();

    if (data.elapsed_seconds && dom.reviewElapsed) {
      dom.reviewElapsed.textContent = data.elapsed_seconds + 's';
    }

    // Show run hash if available
    if (dom.reviewRunHash && data.run_hash) {
      dom.reviewRunHash.textContent = '#' + data.run_hash.substring(0, 8);
      dom.reviewRunHash.title = 'Reproducibility hash: ' + data.run_hash;
      dom.reviewRunHash.style.display = 'inline-block';
    }

    // Update PRISMA counts from final data
    const prisma = data.prisma || {};
    state.reviewPrisma = prisma;
    if (dom.prismaIdentified) dom.prismaIdentified.textContent = prisma.total_identified || 0;
    if (dom.prismaIncluded) dom.prismaIncluded.textContent = prisma.included_count || 0;
    if (dom.prismaExcluded) dom.prismaExcluded.textContent = prisma.excluded_at_screening || 0;
    if (dom.prismaUncertain) dom.prismaUncertain.textContent = prisma.uncertain_count || 0;

    // Process papers
    const papers = data.papers || [];
    state.reviewPapers = { included: [], excluded: [], uncertain: [] };
    papers.forEach(p => {
      if (p.is_duplicate) return;
      if (p.screening_decision === 'include') state.reviewPapers.included.push(p);
      else if (p.screening_decision === 'exclude') state.reviewPapers.excluded.push(p);
      else state.reviewPapers.uncertain.push(p);
    });

    // Update tab counts
    if (dom.tabIncludedCount) dom.tabIncludedCount.textContent = state.reviewPapers.included.length;
    if (dom.tabExcludedCount) dom.tabExcludedCount.textContent = state.reviewPapers.excluded.length;
    if (dom.tabUncertainCount) dom.tabUncertainCount.textContent = state.reviewPapers.uncertain.length;

    // Render paper lists
    renderPaperList(dom.reviewPapersIncluded, state.reviewPapers.included, false);
    renderPaperList(dom.reviewPapersExcluded, state.reviewPapers.excluded, false);
    renderPaperList(dom.reviewPapersUncertain, state.reviewPapers.uncertain, true);

    // Show export buttons
    if (dom.reviewExportButtons) dom.reviewExportButtons.style.display = 'flex';

    showToast(`Systematic review complete: ${state.reviewPapers.included.length} included, ${state.reviewPapers.uncertain.length} need review.`, 'success');
  }

  function renderPaperList(container, papers, showActions) {
    if (!container) return;
    if (papers.length === 0) {
      container.innerHTML = '<div class="results-placeholder"><p>No papers in this category.</p></div>';
      return;
    }
    container.innerHTML = papers.map((p, i) => {
      const authors = (p.authors || []).slice(0, 3).join(', ');
      const dbLabel = (p.source_database || '').replace('_search', '');
      let html = `<div class="paper-card" data-paper-index="${i}">`;
      html += '<div class="paper-card-header">';
      const paperLink = p.url || (p.doi ? `https://doi.org/${p.doi}` : '');
      if (paperLink) {
        html += `<a class="paper-title paper-title--link" href="${esc(paperLink)}" target="_blank" rel="noopener">${esc(p.title)}</a>`;
      } else {
        html += `<div class="paper-title">${esc(p.title)}</div>`;
      }
      // Quality score badge
      if (p.quality_grade) {
        const gradeClass = 'quality-grade-' + p.quality_grade.toLowerCase();
        const scorePercent = p.quality_score != null ? (p.quality_score * 100).toFixed(0) + '%' : '';
        html += `<span class="paper-quality-badge ${gradeClass}" title="Evidence Quality: ${scorePercent}">${p.quality_grade}</span>`;
      }
      html += '</div>';
      if (authors) html += `<div class="paper-authors">${esc(authors)}</div>`;
      html += '<div class="paper-meta">';
      if (p.doi) html += `<a href="https://doi.org/${esc(p.doi)}" target="_blank">${esc(p.doi)}</a>`;
      if (p.published_date) html += `<span>${esc(p.published_date)}</span>`;
      html += `<span class="paper-source-badge">${esc(dbLabel)}</span>`;
      if (p.citation_count != null) html += `<span>${p.citation_count} citations</span>`;
      html += '</div>';
      // Quality dimensions tooltip
      if (p.quality_dimensions) {
        const dims = p.quality_dimensions;
        const designLabel = (dims.study_design || 'unknown').replace(/_/g, ' ');
        html += '<div class="paper-quality-details">';
        html += `<span class="quality-design-tag">${esc(designLabel)}</span>`;
        if (dims.sample_size) html += `<span class="quality-detail-tag">N=${dims.sample_size}</span>`;
        if (dims.is_preregistered) html += '<span class="quality-detail-tag quality-good">Pre-registered</span>';
        if (dims.has_open_data) html += '<span class="quality-detail-tag quality-good">Open Data</span>';
        if (dims.has_control_group) html += '<span class="quality-detail-tag">Control Group</span>';
        if (dims.funding_bias_risk === 'high') html += '<span class="quality-detail-tag quality-warn">Industry Funded</span>';
        html += '</div>';
      }
      // Calibration info (agreement + votes)
      if (p.screening_agreement != null || (p.screening_votes && p.screening_votes.length > 1)) {
        html += '<div class="paper-calibration">';
        if (p.screening_agreement != null) {
          const agreePct = (p.screening_agreement * 100).toFixed(0);
          const agreeClass = p.screening_agreement >= 0.8 ? 'calibration-high' : p.screening_agreement >= 0.5 ? 'calibration-mid' : 'calibration-low';
          html += `<span class="calibration-badge ${agreeClass}" title="Inter-pass agreement">${agreePct}% agreement</span>`;
        }
        if (p.screening_votes && p.screening_votes.length > 1) {
          html += `<span class="calibration-votes" title="Votes across screening passes">${p.screening_votes.map(v => esc(v)).join(' / ')}</span>`;
        }
        html += '</div>';
      }
      // Criteria evaluations
      if (p.criteria_evaluations && p.criteria_evaluations.length > 0) {
        html += '<div class="paper-criteria-section">';
        html += '<div class="paper-criteria-toggle" onclick="this.parentElement.classList.toggle(\'open\')">';
        html += `<span>Criteria Evaluation (${p.criteria_evaluations.length})</span>`;
        html += '<svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2.5 4l2.5 2 2.5-2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>';
        html += '</div>';
        html += '<div class="paper-criteria-body">';
        p.criteria_evaluations.forEach(ce => {
          const metClass = ce.met === true ? 'criterion-met' : ce.met === false ? 'criterion-unmet' : 'criterion-unknown';
          const metIcon = ce.met === true ? '\u2713' : ce.met === false ? '\u2717' : '?';
          html += `<div class="criterion-eval ${metClass}">`;
          html += `<span class="criterion-icon">${metIcon}</span>`;
          html += `<span class="criterion-label">${esc(ce.criterion)}</span>`;
          if (ce.rationale) html += `<span class="criterion-rationale">${esc(ce.rationale)}</span>`;
          if (ce.evidence_span) html += `<div class="criterion-evidence">"${esc(ce.evidence_span)}"</div>`;
          html += '</div>';
        });
        html += '</div></div>';
      }
      // Evidence spans
      if (p.evidence_spans && p.evidence_spans.length > 0) {
        html += '<div class="paper-evidence-spans">';
        p.evidence_spans.forEach(span => {
          html += `<div class="paper-evidence-span">"${esc(span)}"</div>`;
        });
        html += '</div>';
      }
      if (p.exclusion_reason) html += `<div class="paper-reason">${esc(p.exclusion_reason)}</div>`;
      if (showActions) {
        html += '<div class="paper-actions">';
        html += `<button class="btn btn-xs btn-outline review-include-btn" onclick="window._reviewDecide(${i}, 'include')">Include</button>`;
        html += `<button class="btn btn-xs btn-outline review-exclude-btn" onclick="window._reviewDecide(${i}, 'exclude')" style="border-color:var(--rose);color:var(--rose);">Exclude</button>`;
        html += '</div>';
      }
      html += '</div>';
      return html;
    }).join('');
  }

  // Expose manual decision function globally for onclick handlers
  window._reviewDecide = function(paperIndex, decision) {
    const paper = state.reviewPapers.uncertain[paperIndex];
    if (!paper) return;
    paper.screening_decision = decision;
    paper.manually_reviewed = true;

    // Move paper
    state.reviewPapers.uncertain.splice(paperIndex, 1);
    if (decision === 'include') state.reviewPapers.included.push(paper);
    else state.reviewPapers.excluded.push(paper);

    // Re-render
    if (dom.tabIncludedCount) dom.tabIncludedCount.textContent = state.reviewPapers.included.length;
    if (dom.tabExcludedCount) dom.tabExcludedCount.textContent = state.reviewPapers.excluded.length;
    if (dom.tabUncertainCount) dom.tabUncertainCount.textContent = state.reviewPapers.uncertain.length;
    renderPaperList(dom.reviewPapersIncluded, state.reviewPapers.included, false);
    renderPaperList(dom.reviewPapersExcluded, state.reviewPapers.excluded, false);
    renderPaperList(dom.reviewPapersUncertain, state.reviewPapers.uncertain, true);

    showToast(`Paper ${decision === 'include' ? 'included' : 'excluded'}.`, 'success');
  };

  async function exportReview(format) {
    // Client-side export from in-memory papers
    const allPapers = [...state.reviewPapers.included, ...state.reviewPapers.excluded, ...state.reviewPapers.uncertain];
    if (allPapers.length === 0) {
      showToast('No papers to export.', 'warning');
      return;
    }

    let content = '';
    let filename = '';

    if (format === 'csv') {
      const headers = ['Title', 'Authors', 'DOI', 'URL', 'Published Date', 'Database', 'Decision', 'Reason'];
      const rows = [headers.join(',')];
      allPapers.forEach(p => {
        const row = [
          '"' + (p.title || '').replace(/"/g, '""') + '"',
          '"' + (p.authors || []).join('; ').replace(/"/g, '""') + '"',
          p.doi || '',
          p.url || '',
          p.published_date || '',
          p.source_database || '',
          p.screening_decision || '',
          '"' + (p.exclusion_reason || '').replace(/"/g, '""') + '"',
        ];
        rows.push(row.join(','));
      });
      content = rows.join('\n');
      filename = 'systematic_review.csv';
    } else if (format === 'bibtex') {
      content = state.reviewPapers.included.map((p, i) => {
        let entry = `@article{review_${i + 1},\n`;
        entry += `  title = {${p.title || 'Untitled'}},\n`;
        if (p.authors && p.authors.length) entry += `  author = {${p.authors.join(' and ')}},\n`;
        if (p.published_date) entry += `  year = {${(p.published_date || '').substring(0, 4)}},\n`;
        if (p.doi) entry += `  doi = {${p.doi}},\n`;
        if (p.url) entry += `  url = {${p.url}},\n`;
        entry += '}';
        return entry;
      }).join('\n\n');
      filename = 'systematic_review.bib';
    } else if (format === 'ris') {
      content = state.reviewPapers.included.map(p => {
        let entry = 'TY  - JOUR\n';
        entry += `TI  - ${p.title || ''}\n`;
        (p.authors || []).forEach(a => { entry += `AU  - ${a}\n`; });
        if (p.doi) entry += `DO  - ${p.doi}\n`;
        if (p.url) entry += `UR  - ${p.url}\n`;
        if (p.published_date) entry += `PY  - ${(p.published_date || '').substring(0, 4)}\n`;
        entry += 'ER  -\n';
        return entry;
      }).join('\n');
      filename = 'systematic_review.ris';
    }

    downloadFile(content, filename, 'text/plain');
    showToast(`Exported as ${format.toUpperCase()}.`, 'success');
  }

  // ═══════════════════════════════════════════════════════════════
  // UTILITIES
  // ═══════════════════════════════════════════════════════════════

  function esc(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  // ─── Boot ──────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
