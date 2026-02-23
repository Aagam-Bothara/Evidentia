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
    // Chat
    chatWs: null,
    chatOpen: false,
    chatMessages: [],
    chatUsers: [],
    chatUnread: 0,
    chatTypingTimeout: null,
    chatLastTypingSent: 0,
    chatAttachFile: null,
    // Ask PDF
    askPdfId: null,
    askPdfName: '',
    // Provenance
    provenanceData: null,
    // Reproducibility
    currentFingerprint: null,
    fingerprintHistory: {},  // run_id -> fingerprint dict
    // Review tracking
    currentReviewId: null,
    // Validation
    reviewValidated: false,
    customGoldBib: null,
    // Streaming
    streamingSummary: false,
    // Writing Workspace
    writingMode: 'plain',
    writingLayout: 'split',
    writingAutoConvert: false,
    writingDocId: null,
    writingDirty: false,
    writingAutoSaveTimer: null,
    writingConvertTimer: null,
    documents: [],
  };

  // ─── DOM References ────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    sidebar:          $('#sidebar'),
    sidebarOverlay:   $('#sidebar-overlay'),
    sidebarToggle:    $('#sidebar-toggle'),
    sidebarClose:     $('#sidebar-close'),
    brandHome:        $('#brand-home'),
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
    // Chat
    chatToggle:        $('#chatToggle'),
    chatPanel:         $('#chatPanel'),
    chatMessages:      $('#chatMessages'),
    chatForm:          $('#chatForm'),
    chatInput:         $('#chatInput'),
    chatPresence:      $('#chatPresence'),
    chatTyping:        $('#chatTyping'),
    chatUnread:        $('#chatUnread'),
    chatClose:         $('#chatClose'),
    chatEmojiBtn:      $('#chatEmojiBtn'),
    chatAttachBtn:     $('#chatAttachBtn'),
    chatGifBtn:        $('#chatGifBtn'),
    chatEmojiPicker:   $('#chatEmojiPicker'),
    chatGifPicker:     $('#chatGifPicker'),
    chatAttachPreview: $('#chatAttachPreview'),
    chatAttachThumb:   $('#chatAttachThumb'),
    chatAttachIcon:    $('#chatAttachIcon'),
    chatAttachName:    $('#chatAttachName'),
    chatAttachRemove:  $('#chatAttachRemove'),
    chatFileInput:     $('#chatFileInput'),
    emojiGrid:         $('#emojiGrid'),
    gifGrid:           $('#gifGrid'),
    gifSearchInput:    $('#gifSearchInput'),
    // Provenance
    provenanceBtn:           $('#provenance-btn'),
    provenancePanel:         $('#provenance-panel'),
    provenanceClose:         $('#provenance-close'),
    provenanceLinks:         $('#provenance-links'),
    provenanceCoverageFill:  $('#provenance-coverage-fill'),
    provenanceCoveragePct:   $('#provenance-coverage-pct'),
    provenanceUngrounded:    $('#provenance-ungrounded'),
    provenanceUngroundedList:$('#provenance-ungrounded-list'),
    // Project modal
    projectModalOverlay: $('#project-modal-overlay'),
    projectModalForm:    $('#project-modal-form'),
    projectModalName:    $('#project-modal-name'),
    projectModalClose:   $('#project-modal-close'),
    projectModalSubmit:  $('#project-modal-submit'),
    projectModalError:   $('#project-modal-error'),
    // Reproducibility
    reproOverlay:        $('#repro-overlay'),
    reproModalClose:     $('#repro-modal-close'),
    reproCompositeHash:  $('#repro-composite-hash'),
    reproCopyBtn:        $('#repro-copy-btn'),
    reproQueryHash:      $('#repro-query-hash'),
    reproEvidenceHash:   $('#repro-evidence-hash'),
    reproClaimsHash:     $('#repro-claims-hash'),
    reproToolCallsHash:  $('#repro-tool-calls-hash'),
    reproAuditTrail:     $('#repro-audit-trail'),
    reproVerifyBtn:      $('#repro-verify-btn'),
    reproVerifyStatus:   $('#repro-verify-status'),
    reproCompareSelect:  $('#repro-compare-select'),
    reproCompareBtn:     $('#repro-compare-btn'),
    reproCompareResults: $('#repro-compare-results'),
    // Import Library
    importLibraryBtn:    $('#import-library-btn'),
    bibFileInput:        $('#bib-file-input'),
    // PRISMA Download
    prismaPanelActions:  $('#prisma-panel-actions'),
    prismaDownloadBtn:   $('#prisma-download-btn'),
    prismaDownloadMenu:  $('#prisma-download-menu'),
    prismaPreviewOverlay: $('#prisma-preview-overlay'),
    prismaPreviewClose:  $('#prisma-preview-close'),
    prismaPreviewContent: $('#prisma-preview-content'),
    // Validate
    validateReviewBtn:   $('#validate-review-btn'),
    validationOverlay:   $('#validation-overlay'),
    validationClose:     $('#validation-close'),
    validationRunBtn:    $('#validation-run-btn'),
    validationBibInput:  $('#validation-bib-input'),
    validationCustomUpload: $('#validation-custom-upload'),
    validationError:     $('#validation-error'),
    validationConfig:    $('#validation-config'),
    validationResults:   $('#validation-results'),
    // Zotero Export
    zoteroExportBtn:     $('#zotero-export-btn'),
    zoteroExportOverlay: $('#zotero-export-overlay'),
    zoteroExportClose:   $('#zotero-export-close'),
    zoteroExportForm:    $('#zotero-export-form'),
    zoteroExportError:   $('#zotero-export-error'),
    zoteroExportProgress: $('#zotero-export-progress'),
    zoteroExportStatus:  $('#zotero-export-status'),
    zoteroExportSubmit:  $('#zotero-export-submit'),
    // Reproducible Badge
    reproducibleBadge:   $('#reproducible-badge'),
    // Dark Mode
    darkModeToggle:      $('#darkModeToggle'),
    darkModeIcon:        $('#darkModeIcon'),
    // Writing Workspace
    modeWrite:           $('#mode-write'),
    writingFormSection:  $('#writing-form-section'),
    writingDocList:      $('#writing-doc-list'),
    newDocBtn:           $('#new-doc-btn'),
    writingWorkspace:    $('#writing-workspace'),
    writingTitle:        $('#writing-title'),
    writingModePlain:    $('#writing-mode-plain'),
    writingModeLatex:    $('#writing-mode-latex'),
    writingLayoutSplit:  $('#writing-layout-split'),
    writingLayoutFull:   $('#writing-layout-full'),
    writingAutoConvert:  $('#writing-auto-convert'),
    writingConvertBtn:   $('#writing-convert-btn'),
    writingExportBtn:    $('#writing-export-btn'),
    writingSaveBtn:      $('#writing-save-btn'),
    writingEditor:       $('#writing-editor'),
    writingEditorLabel:  $('#writing-editor-label'),
    writingWordCount:    $('#writing-word-count'),
    writingInput:        $('#writing-input'),
    writingPreviewPane:  $('#writing-preview-pane'),
    writingCopyLatex:    $('#writing-copy-latex'),
    writingLatexOutput:  $('#writing-latex-output'),
    writingStatus:       $('#writing-status'),
    writingAutosaveStatus: $('#writing-autosave-status'),
    sidebarDocuments:    $('#sidebar-documents'),
    documentList:        $('#document-list'),
    templatePicker:      $('#template-picker'),
    templatePickerClose: $('#template-picker-close'),
    templateGrid:        $('#template-grid'),
  };

  // ─── View Transition Helpers ────────────────────────────────────
  function showView(el, animClass) {
    if (!el) return Promise.resolve();
    animClass = animClass || 'view-enter';
    return new Promise((resolve) => {
      el.style.display = el.dataset.display || 'flex';
      void el.offsetHeight;
      el.classList.remove('view-leave');
      el.classList.add(animClass);
      function onDone() {
        el.removeEventListener('animationend', onDone);
        el.classList.remove(animClass);
        resolve();
      }
      el.addEventListener('animationend', onDone);
    });
  }

  function hideView(el, animClass) {
    if (!el || el.style.display === 'none') return Promise.resolve();
    animClass = animClass || 'view-leave';
    return new Promise((resolve) => {
      el.classList.add(animClass);
      function onDone() {
        el.removeEventListener('animationend', onDone);
        el.classList.remove(animClass);
        el.style.display = 'none';
        resolve();
      }
      el.addEventListener('animationend', onDone);
    });
  }

  function showModal(overlay) {
    if (!overlay) return;
    overlay.style.display = 'flex';
    void overlay.offsetHeight;
    overlay.classList.add('fade-in');
    const panel = overlay.querySelector('.glass, .auth-card, .settings-panel, [class*="-panel"], [class*="-card"]');
    if (panel) panel.classList.add('modal-enter');
  }

  function hideModal(overlay) {
    if (!overlay) return;
    const panel = overlay.querySelector('.glass, .auth-card, .settings-panel, [class*="-panel"], [class*="-card"]');
    if (panel) {
      panel.classList.add('modal-leave');
      panel.addEventListener('animationend', function onDone() {
        panel.removeEventListener('animationend', onDone);
        panel.classList.remove('modal-leave', 'modal-enter');
        overlay.classList.remove('fade-in');
        overlay.style.display = 'none';
      });
    } else {
      overlay.style.display = 'none';
    }
  }

  function renderSkeletonClaims(count) {
    count = count || 3;
    let html = '';
    for (let i = 0; i < count; i++) {
      html += `<div class="skeleton-card" style="animation-delay: ${i * 0.1}s">
        <div class="skeleton skeleton-line" style="width:70%; height:18px; margin-bottom:14px;"></div>
        <div class="skeleton skeleton-line skeleton-line--full"></div>
        <div class="skeleton skeleton-line skeleton-line--medium"></div>
        <div class="skeleton skeleton-line skeleton-line--short"></div>
        <div class="skeleton skeleton-badge"></div>
      </div>`;
    }
    return html;
  }

  // ─── Initialize ────────────────────────────────────────────────
  function init() {
    bindEvents();
    bindAuthEvents();
    bindProjectEvents();
    bindReviewEvents();
    bindSettingsEvents();
    bindBYOKeyEvents();
    bindChatEvents();
    bindProjectModalEvents();
    bindProjectSettingsEvents();
    bindAskPdfEvents();
    bindCitationGraphEvents();
    bindExtractTableEvents();
    bindSynthesisEvents();
    bindReproEvents();
    bindProvenanceEvents();
    bindImportLibraryEvents();
    bindPrismaDownloadEvents();
    bindValidationEvents();
    bindZoteroExportEvents();
    bindDarkModeEvents();
    bindWritingEvents();
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
    // Scroll to top of welcome page
    const wp = dom.authOverlay.querySelector('.welcome-page');
    if (wp) wp.scrollTop = 0;
  }

  function hideAuthModal() {
    dom.authOverlay.style.display = 'none';
    dom.mainContent.classList.remove('blurred');
    updateAccountUI();
    loadProjects();
  }

  // Welcome page "Get Started" buttons → scroll to auth section
  (function initWelcomeButtons() {
    const heroBtn = $('#welcome-get-started-hero');
    const topBtn = $('#welcome-get-started-top');
    const authSection = $('#welcome-auth');
    const emailInput = $('#auth-email');
    function scrollToAuth() {
      if (authSection) {
        authSection.scrollIntoView({ behavior: 'smooth' });
        setTimeout(function() { if (emailInput) emailInput.focus(); }, 600);
      }
    }
    if (heroBtn) heroBtn.addEventListener('click', scrollToAuth);
    if (topBtn) topBtn.addEventListener('click', scrollToAuth);
  })();

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
    loadUserKeys();
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

  // ═══════════════════════════════════════════════════════════════
  // BYO-API KEY MANAGEMENT
  // ═══════════════════════════════════════════════════════════════

  var BYO_SERVICES = ['openai', 'anthropic', 'serpapi', 'semantic_scholar', 'ncbi', 'openalex'];

  async function loadUserKeys() {
    if (!state.token) return;
    try {
      var resp = await authFetch('/api/v1/keys');
      if (!resp.ok) return;
      var keys = await resp.json();
      // Reset all fields
      BYO_SERVICES.forEach(function(svc) {
        var input = document.getElementById('key-' + svc);
        var status = document.getElementById('key-status-' + svc);
        var row = input ? input.closest('.settings-api-key-row') : null;
        var deleteBtn = row ? row.querySelector('.settings-key-delete') : null;
        if (input) { input.value = ''; input.placeholder = input.getAttribute('data-orig-ph') || input.placeholder; }
        if (status) { status.textContent = ''; status.className = 'settings-key-status'; }
        if (deleteBtn) deleteBtn.style.display = 'none';
      });
      // Mark stored keys
      keys.forEach(function(k) {
        var input = document.getElementById('key-' + k.service);
        var status = document.getElementById('key-status-' + k.service);
        var row = input ? input.closest('.settings-api-key-row') : null;
        var deleteBtn = row ? row.querySelector('.settings-key-delete') : null;
        if (input) {
          if (!input.getAttribute('data-orig-ph')) input.setAttribute('data-orig-ph', input.placeholder);
          input.placeholder = k.masked_key;
          input.value = '';
        }
        if (status) { status.textContent = 'Saved'; status.className = 'settings-key-status settings-key-status--saved'; }
        if (deleteBtn) deleteBtn.style.display = '';
      });
    } catch (e) {
      // Key management is non-critical
    }
  }

  async function saveUserKey(service) {
    var input = document.getElementById('key-' + service);
    var value = input ? input.value.trim() : '';
    if (!value) { showToast('Please enter a key value.', 'warning'); return; }
    try {
      var resp = await authFetch('/api/v1/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service: service, api_key: value }),
      });
      if (resp.ok) {
        showToast(service + ' key saved.', 'success');
        loadUserKeys();
      } else {
        var data = await resp.json();
        showToast(data.detail || 'Failed to save key.', 'error');
      }
    } catch (e) {
      showToast('Failed to save key.', 'error');
    }
  }

  async function deleteUserKey(service) {
    try {
      var resp = await authFetch('/api/v1/keys/' + service, { method: 'DELETE' });
      if (resp.ok) {
        showToast(service + ' key removed.', 'info');
        loadUserKeys();
      } else {
        var data = await resp.json();
        showToast(data.detail || 'Failed to remove key.', 'error');
      }
    } catch (e) {
      showToast('Failed to remove key.', 'error');
    }
  }

  function bindBYOKeyEvents() {
    document.querySelectorAll('.settings-key-save').forEach(function(btn) {
      btn.addEventListener('click', function() { saveUserKey(btn.dataset.service); });
    });
    document.querySelectorAll('.settings-key-delete').forEach(function(btn) {
      btn.addEventListener('click', function() { deleteUserKey(btn.dataset.service); });
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

    // Brand logo → home
    if (dom.brandHome) {
      dom.brandHome.addEventListener('click', (e) => {
        e.preventDefault();
        closeSidebar();
        // Hide writing workspace if visible
        const writingWs = document.getElementById('writing-workspace');
        if (writingWs) writingWs.style.display = 'none';
        resetToLanding();
      });
    }

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
    state.provenanceData = null;

    // Switch to workspace view with animation
    dom.landing.style.display = 'none';
    dom.workspace.style.display = 'flex';
    dom.workspace.classList.add('view-enter');
    dom.workspace.addEventListener('animationend', function onDone() {
      dom.workspace.removeEventListener('animationend', onDone);
      dom.workspace.classList.remove('view-enter');
    });
    dom.newQueryBtn.style.display = 'inline-flex';
    dom.activeQueryText.textContent = query;

    // Reset UI elements
    dom.traceTimeline.innerHTML = '';
    dom.claimsContainer.innerHTML = renderSkeletonClaims(3);
    dom.resultsSummary.style.display = 'none';
    dom.resultsSummary.textContent = '';
    dom.exportButtons.style.display = 'none';
    dom.querySubmit.disabled = true;
    // Hide citation graph
    const graphBtn = document.getElementById('citation-graph-btn');
    if (graphBtn) graphBtn.style.display = 'none';
    const graphContainer = document.getElementById('citation-graph-container');
    if (graphContainer) graphContainer.style.display = 'none';
    // Hide provenance panel
    if (dom.provenancePanel) dom.provenancePanel.style.display = 'none';
    const provBtn = document.getElementById('provenance-btn');
    if (provBtn) provBtn.style.display = 'none';

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

      case 'synthesis_token':
        handleSynthesisToken(data);
        break;

      case 'budget_warning':
        addTraceStep('warning', 'Budget warning', esc(data.message));
        showToast(data.message, 'warning');
        break;

      case 'provenance':
        handleProvenance(data);
        break;

      case 'fingerprint':
        handleFingerprint(data);
        break;

      case 'completed':
        handleCompleted(data);
        break;

      case 'run_saved':
        // Attach persisted run_id to the latest history entry
        if (data.run_id && state.runHistory.length > 0) {
          state.runHistory[0].run_id = data.run_id;
          if (state.currentResult) state.currentResult.run_id = data.run_id;
          saveHistory();
        }
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

  // ─── Synthesis Token Streaming ────────────────────────────────
  function handleSynthesisToken(data) {
    if (!state.streamingSummary) {
      state.streamingSummary = true;
      dom.resultsSummary.textContent = '';
      dom.resultsSummary.style.display = 'block';
      dom.resultsSummary.classList.add('content-appear');
    }
    dom.resultsSummary.textContent += data.token;
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

    // Show summary (skip if already streamed token-by-token)
    if (data.summary && !state.streamingSummary) {
      dom.resultsSummary.textContent = data.summary;
      dom.resultsSummary.style.display = 'block';
      dom.resultsSummary.classList.add('content-appear');
    }
    state.streamingSummary = false;

    // Show claims
    renderClaims(data.claims || []);

    // Show export buttons with animation
    if (data.claims && data.claims.length > 0) {
      dom.exportButtons.style.display = 'flex';
      dom.exportButtons.classList.add('content-appear');
      const graphBtn = document.getElementById('citation-graph-btn');
      if (graphBtn) graphBtn.style.display = '';
      const extractBtn = document.getElementById('extract-table-btn');
      if (extractBtn) extractBtn.style.display = '';
      const provBtn = document.getElementById('provenance-btn');
      if (provBtn) provBtn.style.display = '';
    }

    // Render fingerprint badge if already available
    if (state.currentFingerprint) {
      renderFingerprintBadge();
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

        // Parse response to get PDF id for Ask feature
        let pdfId = '';
        try {
          const resp = JSON.parse(xhr.responseText);
          pdfId = resp.id || '';
        } catch (_e) { /* ignore */ }
        addToPdfLibrary(file.name, pdfId);

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
      case 'csl-json':
        exportCSLJSON();
        return;
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
      run_id: data.run_id || null,
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
      dom.historyList.innerHTML = `<li class="empty-state">
        <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <span class="empty-state-message">No previous runs</span>
      </li>`;
      return;
    }

    dom.historyList.innerHTML = state.runHistory.map((entry, i) => {
      const timeAgo = formatTimeAgo(entry.timestamp);
      const truncated = entry.query.length > 48 ? entry.query.substring(0, 48) + '...' : entry.query;
      const claimsBadge = entry.claimCount ? `<span class="history-item-meta-tag">${entry.claimCount} claims</span><span class="history-item-meta-dot"></span>` : '';
      return `
        <li class="history-item" data-index="${i}" title="${esc(entry.query)}">
          <div class="history-item-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          </div>
          <div class="history-item-body">
            <span class="history-item-text">${esc(truncated)}</span>
            <span class="history-item-meta">${claimsBadge}<span class="history-item-meta-tag">${timeAgo}</span></span>
          </div>
        </li>
      `;
    }).join('');

    // Click handler for history items
    dom.historyList.querySelectorAll('.history-item').forEach((item) => {
      item.addEventListener('click', async () => {
        const idx = parseInt(item.dataset.index);
        const entry = state.runHistory[idx];
        if (!entry) return;

        // If data is already loaded, use it directly
        if (entry.data) {
          loadHistoryEntry(entry);
          return;
        }

        // Fetch from API if we have a run_id
        if (entry.run_id) {
          try {
            item.style.opacity = '0.5';
            const resp = await authFetch('/api/v1/runs/' + encodeURIComponent(entry.run_id));
            if (resp.ok) {
              const data = await resp.json();
              entry.data = data;
              loadHistoryEntry(entry);
            } else {
              showToast('Could not load this run from the server.', 'warning');
            }
          } catch (err) {
            showToast('Failed to load run history.', 'error');
          } finally {
            item.style.opacity = '';
          }
          return;
        }

        showToast('Run data is no longer available.', 'warning');
      });
    });
  }

  function loadHistoryEntry(entry) {
    closeSidebar();

    dom.landing.style.display = 'none';
    dom.workspace.style.display = 'flex';
    dom.workspace.classList.add('view-enter');
    dom.workspace.addEventListener('animationend', function onDone() {
      dom.workspace.removeEventListener('animationend', onDone);
      dom.workspace.classList.remove('view-enter');
    });
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
      const graphBtn = document.getElementById('citation-graph-btn');
      if (graphBtn) graphBtn.style.display = '';
      const extractBtn = document.getElementById('extract-table-btn');
      if (extractBtn) extractBtn.style.display = '';
      const provBtn = document.getElementById('provenance-btn');
      if (provBtn) provBtn.style.display = '';
    }

    // Reset provenance state for history entry
    state.provenanceData = null;
    if (dom.provenancePanel) dom.provenancePanel.style.display = 'none';

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
        run_id: e.run_id || null,
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

      // Backfill missing run_ids from the server
      backfillRunIds();
    } catch (e) { /* ignore */ }
  }

  async function backfillRunIds() {
    // Check if any entries are missing run_id
    const needsBackfill = state.runHistory.some((e) => !e.run_id);
    if (!needsBackfill || !state.token) return;

    try {
      const resp = await authFetch('/api/v1/runs');
      if (!resp.ok) return;
      const runs = await resp.json();
      if (!runs || runs.length === 0) return;

      let changed = false;
      state.runHistory.forEach((entry) => {
        if (entry.run_id) return;
        // Match by query text (case-insensitive trim comparison)
        const match = runs.find((r) =>
          r.query && r.query.trim().toLowerCase() === entry.query.trim().toLowerCase()
        );
        if (match) {
          entry.run_id = match.run_id;
          changed = true;
        }
      });

      if (changed) {
        saveHistory();
        renderHistory();
      }
    } catch (e) { /* ignore backfill failures */ }
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

  function addToPdfLibrary(filename, pdfId) {
    // Support both old format (string) and new format ({id, filename})
    const exists = state.pdfLibrary.some((entry) =>
      typeof entry === 'string' ? entry === filename : entry.filename === filename
    );
    if (exists) return;
    state.pdfLibrary.push({ id: pdfId || '', filename: filename });
    savePdfLibrary();
    renderPdfLibrary();
  }

  function renderPdfLibrary() {
    if (state.pdfLibrary.length === 0) {
      dom.pdfLibrary.innerHTML = `<li class="empty-state">
        <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M7 21h10a2 2 0 0 0 2-2V9l-5-5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z" stroke-linecap="round" stroke-linejoin="round"/><polyline points="13 2 13 9 20 9" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <span class="empty-state-message">No PDFs uploaded</span>
      </li>`;
      return;
    }

    dom.pdfLibrary.innerHTML = state.pdfLibrary.map((entry) => {
      // Support both old format (string) and new format ({id, filename})
      const name = typeof entry === 'string' ? entry : entry.filename;
      const id = typeof entry === 'string' ? '' : (entry.id || '');
      const askBtn = id
        ? `<button class="pdf-ask-btn btn btn-xs btn-outline" data-id="${esc(id)}" data-name="${esc(name)}">Ask</button>`
        : '';
      return `<li class="pdf-item">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M9 1H4a1 1 0 00-1 1v12a1 1 0 001 1h8a1 1 0 001-1V5L9 1z" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M9 1v4h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(name)}</span>
        ${askBtn}
      </li>`;
    }).join('');

    // Bind Ask button events
    document.querySelectorAll('.pdf-ask-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        openAskPdf(btn.dataset.id, btn.dataset.name);
      });
    });
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
        const parsed = JSON.parse(stored);
        state.pdfLibrary = parsed.map((entry) =>
          typeof entry === 'string' ? { id: '', filename: entry } : entry
        );
      } else {
        state.pdfLibrary = [];
      }
      renderPdfLibrary();
    } catch (e) { /* ignore */ }

    // Also fetch from API to get correct DB UUIDs
    if (state.token) {
      authFetch('/api/v1/pdfs').then(async (resp) => {
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.pdfs && data.pdfs.length > 0) {
          state.pdfLibrary = data.pdfs.map((p) => ({ id: p.id, filename: p.filename }));
          savePdfLibrary();
          renderPdfLibrary();
        }
      }).catch(() => {});
    }
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
    dom.landing.classList.add('view-enter');
    dom.landing.addEventListener('animationend', function onDone() {
      dom.landing.removeEventListener('animationend', onDone);
      dom.landing.classList.remove('view-enter');
    });
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
        const prev = state.activeProjectId;
        state.activeProjectId = e.target.value || null;
        if (prev !== state.activeProjectId) {
          disconnectChat();
          updateChatVisibility();
        }
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
      updateChatVisibility();
      // Show project selector if logged in
      if (dom.projectSelector) dom.projectSelector.style.display = 'flex';
    } catch (e) {
      // Silently fail — projects are optional
    }
  }

  function renderProjectsList() {
    if (!dom.projectsList) return;
    if (state.projects.length === 0) {
      dom.projectsList.innerHTML = `<li class="empty-state">
        <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-6l-2-2H5a2 2 0 0 0-2 2z" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <span class="empty-state-message">No projects yet</span>
      </li>`;
      return;
    }
    dom.projectsList.innerHTML = state.projects.map(p => `
      <li class="project-item${state.activeProjectId === p.id ? ' active' : ''}" data-id="${esc(p.id)}">
        <span class="project-name">${esc(p.name)}</span>
        <div class="project-item-right">
          <span class="project-count">${p.run_count} runs</span>
          <button class="project-settings-btn" data-id="${esc(p.id)}" title="Project settings">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="2.5" r="1.5" fill="currentColor"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/><circle cx="8" cy="13.5" r="1.5" fill="currentColor"/></svg>
          </button>
        </div>
      </li>
    `).join('');

    dom.projectsList.querySelectorAll('.project-item').forEach(el => {
      el.addEventListener('click', (e) => {
        // Don't select project if clicking settings button
        if (e.target.closest('.project-settings-btn')) return;
        const prevProject = state.activeProjectId;
        state.activeProjectId = el.dataset.id;
        renderProjectsList();
        renderProjectSelect();
        // Reconnect chat if project changed
        if (prevProject !== state.activeProjectId) {
          disconnectChat();
          updateChatVisibility();
        }
      });
    });

    // Settings buttons
    dom.projectsList.querySelectorAll('.project-settings-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        openProjectSettings(btn.dataset.id);
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

  function promptNewProject() {
    if (dom.projectModalOverlay) {
      dom.projectModalOverlay.style.display = 'flex';
      if (dom.projectModalName) {
        dom.projectModalName.value = '';
        dom.projectModalName.focus();
      }
      if (dom.projectModalError) dom.projectModalError.style.display = 'none';
      if (dom.projectModalSubmit) {
        dom.projectModalSubmit.disabled = false;
        dom.projectModalSubmit.textContent = 'Create Project';
      }
    }
  }

  function closeProjectModal() {
    if (dom.projectModalOverlay) dom.projectModalOverlay.style.display = 'none';
  }

  function showProjectModalError(msg) {
    if (dom.projectModalError) {
      dom.projectModalError.textContent = msg;
      dom.projectModalError.style.display = 'block';
    }
  }

  function bindProjectModalEvents() {
    if (dom.projectModalForm) {
      dom.projectModalForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const name = (dom.projectModalName ? dom.projectModalName.value : '').trim();
        if (!name) return;

        if (dom.projectModalSubmit) {
          dom.projectModalSubmit.disabled = true;
          dom.projectModalSubmit.textContent = 'Creating...';
        }

        try {
          const resp = await authFetch('/api/v1/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
          });
          if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            showProjectModalError(data.detail || 'Failed to create project');
            return;
          }
          const project = await resp.json();
          state.projects.unshift(project);
          state.activeProjectId = project.id;
          renderProjectsList();
          renderProjectSelect();
          updateChatVisibility();
          closeProjectModal();
          showToast(`Project "${name}" created`, 'success');
        } catch (_e) {
          showProjectModalError('Failed to create project');
        } finally {
          if (dom.projectModalSubmit) {
            dom.projectModalSubmit.disabled = false;
            dom.projectModalSubmit.textContent = 'Create Project';
          }
        }
      });
    }

    if (dom.projectModalClose) {
      dom.projectModalClose.addEventListener('click', closeProjectModal);
    }

    if (dom.projectModalOverlay) {
      dom.projectModalOverlay.addEventListener('click', (e) => {
        if (e.target === dom.projectModalOverlay) closeProjectModal();
      });
    }

    // Close on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && dom.projectModalOverlay && dom.projectModalOverlay.style.display !== 'none') {
        closeProjectModal();
      }
    });
  }

  // ─── Project Settings ─────────────────────────────────────────

  function openProjectSettings(projectId) {
    const proj = state.projects.find(p => p.id === projectId);
    if (!proj) return;

    const overlay = document.getElementById('project-settings-overlay');
    if (!overlay) return;
    overlay.dataset.projectId = projectId;

    const nameInput = document.getElementById('project-settings-name');
    if (nameInput) nameInput.value = proj.name;

    const descInput = document.getElementById('project-settings-desc');
    if (descInput) descInput.value = proj.description || '';

    const errEl = document.getElementById('project-settings-error');
    if (errEl) errEl.style.display = 'none';

    const memberErr = document.getElementById('project-member-error');
    if (memberErr) memberErr.style.display = 'none';

    const emailInput = document.getElementById('project-add-member-email');
    if (emailInput) emailInput.value = '';

    overlay.style.display = 'flex';
    if (nameInput) nameInput.focus();

    // Load collaborators
    loadProjectMembers(projectId);
  }

  async function loadProjectMembers(projectId) {
    const listEl = document.getElementById('project-members-list');
    if (!listEl) return;
    listEl.innerHTML = '<div style="color:var(--text-tertiary);font-size:12px;padding:4px 0;">Loading...</div>';

    try {
      const resp = await fetch(`/api/v1/projects/${projectId}/collaborators`, {
        headers: { 'Authorization': `Bearer ${state.token}` },
      });
      if (!resp.ok) throw new Error('Failed');
      const data = await resp.json();
      const owner = data.owner || {};
      const collabs = data.collaborators || [];

      let html = '';
      // Owner
      if (owner.email) {
        html += `<div class="modal-member-row">
          <span class="modal-member-email">${esc(owner.email)}</span>
          <span class="modal-member-role owner">Owner</span>
        </div>`;
      }
      // Collaborators
      collabs.forEach(c => {
        html += `<div class="modal-member-row">
          <span class="modal-member-email">${esc(c.email)}</span>
          <span class="modal-member-role">${esc(c.role)}</span>
          <button class="modal-member-remove" data-email="${esc(c.email)}" title="Remove">&times;</button>
        </div>`;
      });

      if (!html) {
        html = '<div style="color:var(--text-tertiary);font-size:12px;padding:4px 0;">Only you (owner)</div>';
      }
      listEl.innerHTML = html;

      // Bind remove buttons
      listEl.querySelectorAll('.modal-member-remove').forEach(btn => {
        btn.addEventListener('click', async () => {
          const email = btn.dataset.email;
          try {
            const r = await fetch(`/api/v1/projects/${projectId}/collaborators/${encodeURIComponent(email)}`, {
              method: 'DELETE',
              headers: { 'Authorization': `Bearer ${state.token}` },
            });
            if (!r.ok) throw new Error('Failed');
            loadProjectMembers(projectId);
            showToast(`Removed ${email}`, 'success');
          } catch (_e) {
            showToast('Failed to remove member', 'error');
          }
        });
      });
    } catch (_e) {
      listEl.innerHTML = '<div style="color:var(--text-tertiary);font-size:12px;padding:4px 0;">Only you (owner)</div>';
    }
  }

  function closeProjectSettings() {
    const overlay = document.getElementById('project-settings-overlay');
    if (overlay) overlay.style.display = 'none';
  }

  function bindProjectSettingsEvents() {
    const overlay = document.getElementById('project-settings-overlay');
    const closeBtn = document.getElementById('project-settings-close');
    const form = document.getElementById('project-settings-form');
    const deleteBtn = document.getElementById('project-settings-delete');

    if (closeBtn) closeBtn.addEventListener('click', closeProjectSettings);
    if (overlay) overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeProjectSettings();
    });

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const projectId = overlay ? overlay.dataset.projectId : '';
        const nameInput = document.getElementById('project-settings-name');
        const descInput = document.getElementById('project-settings-desc');
        const name = nameInput ? nameInput.value.trim() : '';
        const desc = descInput ? descInput.value.trim() : '';
        if (!name) return;

        try {
          const resp = await fetch(`/api/v1/projects/${projectId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${state.token}` },
            body: JSON.stringify({ name, description: desc }),
          });
          if (!resp.ok) throw new Error('Update failed');
          const updated = await resp.json();
          const idx = state.projects.findIndex(p => p.id === projectId);
          if (idx >= 0) {
            state.projects[idx].name = updated.name;
            state.projects[idx].description = updated.description;
          }
          renderProjectsList();
          renderProjectSelect();
          closeProjectSettings();
          showToast('Project updated', 'success');
        } catch (_e) {
          const errEl = document.getElementById('project-settings-error');
          if (errEl) { errEl.textContent = 'Failed to update project'; errEl.style.display = 'block'; }
        }
      });
    }

    // Add collaborator
    const addMemberBtn = document.getElementById('project-add-member-btn');
    if (addMemberBtn) {
      addMemberBtn.addEventListener('click', async () => {
        const projectId = overlay ? overlay.dataset.projectId : '';
        const emailInput = document.getElementById('project-add-member-email');
        const memberErr = document.getElementById('project-member-error');
        const email = emailInput ? emailInput.value.trim() : '';
        if (!email) return;

        try {
          const resp = await fetch(`/api/v1/projects/${projectId}/collaborators`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${state.token}` },
            body: JSON.stringify({ email }),
          });
          if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to add');
          }
          if (emailInput) emailInput.value = '';
          if (memberErr) memberErr.style.display = 'none';
          loadProjectMembers(projectId);
          showToast(`Added ${email}`, 'success');
        } catch (e) {
          if (memberErr) {
            memberErr.textContent = e.message || 'Failed to add member';
            memberErr.style.display = 'block';
          }
        }
      });
    }

    if (deleteBtn) {
      deleteBtn.addEventListener('click', async () => {
        const projectId = overlay ? overlay.dataset.projectId : '';
        const proj = state.projects.find(p => p.id === projectId);
        if (!proj || !confirm(`Delete "${proj.name}"? This cannot be undone.`)) return;

        try {
          const resp = await fetch(`/api/v1/projects/${projectId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${state.token}` },
          });
          if (!resp.ok) throw new Error('Delete failed');
          state.projects = state.projects.filter(p => p.id !== projectId);
          if (state.activeProjectId === projectId) {
            state.activeProjectId = state.projects.length ? state.projects[0].id : null;
            disconnectChat();
          }
          renderProjectsList();
          renderProjectSelect();
          updateChatVisibility();
          closeProjectSettings();
          showToast('Project deleted', 'success');
        } catch (_e) {
          showToast('Failed to delete project', 'error');
        }
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && overlay && overlay.style.display !== 'none') {
        closeProjectSettings();
      }
    });
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
    if (dom.modeWrite) {
      dom.modeWrite.addEventListener('click', () => switchMode('write'));
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
    if (dom.modeWrite) dom.modeWrite.classList.toggle('mode-tab--active', mode === 'write');
    // Cross-fade form sections
    [
      { el: dom.queryForm, show: mode === 'query' },
      { el: dom.reviewFormSection, show: mode === 'review' },
      { el: dom.writingFormSection, show: mode === 'write' },
    ].forEach(({ el, show }) => {
      if (!el) return;
      if (show) {
        el.style.display = 'block';
        el.classList.add('tab-enter');
        el.addEventListener('animationend', function onDone() {
          el.removeEventListener('animationend', onDone);
          el.classList.remove('tab-enter');
        });
      } else {
        el.style.display = 'none';
        el.classList.remove('tab-enter');
      }
    });
    // Hide elements not relevant in review/write mode
    const chips = $('.example-chips');
    if (chips) chips.style.display = mode === 'query' ? 'flex' : 'none';
    const upload = $('.upload-section');
    if (upload) upload.style.display = mode === 'query' ? 'block' : 'none';
    // Show/hide sidebar documents
    if (dom.sidebarDocuments) dom.sidebarDocuments.style.display = mode === 'write' ? 'block' : 'none';
    // Load documents when switching to write mode
    if (mode === 'write') loadDocuments();
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

    // Switch to review workspace with animation
    dom.landing.style.display = 'none';
    if (dom.workspace) dom.workspace.style.display = 'none';
    dom.reviewWorkspace.style.display = 'flex';
    dom.reviewWorkspace.classList.add('view-enter');
    dom.reviewWorkspace.addEventListener('animationend', function onDone() {
      dom.reviewWorkspace.removeEventListener('animationend', onDone);
      dom.reviewWorkspace.classList.remove('view-enter');
    });
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
    // Reset new feature state
    state.currentReviewId = null;
    state.reviewValidated = false;
    state.customGoldBib = null;
    if (dom.prismaPanelActions) dom.prismaPanelActions.style.display = 'none';
    if (dom.reproducibleBadge) dom.reproducibleBadge.style.display = 'none';
    // Reset phases
    $$('.prisma-phase').forEach(el => { el.classList.remove('active', 'complete'); });
    // Reset quality and contradiction panels
    const qualitySummary = document.getElementById('quality-summary');
    if (qualitySummary) qualitySummary.style.display = 'none';
    const contradictionReport = document.getElementById('contradiction-report');
    if (contradictionReport) contradictionReport.style.display = 'none';
  }

  function handleReviewStarted(data) {
    // Track review ID for PRISMA download and validation
    if (data.review_id) state.currentReviewId = data.review_id;

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

    // Show PRISMA download and validate buttons
    if (dom.prismaPanelActions) dom.prismaPanelActions.style.display = 'flex';

    // Track review ID from completion data
    if (data.review_id) state.currentReviewId = data.review_id;

    // Check if badge should appear
    updateReproducibleBadge();

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

  // ═══════════════════════════════════════════════════════════════
  // REAL-TIME CHAT
  // ═══════════════════════════════════════════════════════════════

  // ─── Emoji Data ────────────────────────────────────────────────
  const EMOJI_DATA = [
    { cat: 'Smileys', emojis: ['\u{1F600}','\u{1F602}','\u{1F923}','\u{1F60D}','\u{1F970}','\u{1F60A}','\u{1F60E}','\u{1F914}','\u{1F92F}','\u{1F634}','\u{1F631}','\u{1F644}','\u{1F62D}','\u{1F973}','\u{1F624}','\u{1FAE1}','\u{1F91D}'] },
    { cat: 'Hands', emojis: ['\u{1F44D}','\u{1F44E}','\u{1F44F}','\u{1F64C}','\u{1F4AA}','\u{270C}\u{FE0F}','\u{1F91E}','\u{1F44B}','\u{1FAF6}','\u{261D}\u{FE0F}'] },
    { cat: 'Research', emojis: ['\u{1F4DD}','\u{1F4CA}','\u{1F4C8}','\u{1F4C9}','\u{1F52C}','\u{1F9EA}','\u{1F9EC}','\u{1F4A1}','\u{1F3AF}','\u{1F4CC}','\u{1F4CE}','\u{1F517}','\u{1F4BB}','\u{1F916}','\u{1F4DA}','\u{1F50D}'] },
    { cat: 'Symbols', emojis: ['\u{2705}','\u{274C}','\u{26A0}\u{FE0F}','\u{2139}\u{FE0F}','\u{2753}','\u{2757}','\u{1F4AF}','\u{2B50}','\u{1F525}','\u{2764}\u{FE0F}','\u{1F494}','\u{1F3C6}','\u{1F389}','\u{1F680}','\u{1F4A4}','\u{1F570}'] },
  ];

  let gifSearchTimeout = null;

  function bindChatEvents() {
    if (dom.chatToggle) {
      dom.chatToggle.addEventListener('click', toggleChat);
    }
    if (dom.chatClose) {
      dom.chatClose.addEventListener('click', closeChat);
    }
    if (dom.chatForm) {
      dom.chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        sendChatMessage();
      });
    }
    if (dom.chatInput) {
      dom.chatInput.addEventListener('keydown', () => {
        const now = Date.now();
        if (now - state.chatLastTypingSent > 2000 && state.chatWs) {
          state.chatLastTypingSent = now;
          try {
            state.chatWs.send(JSON.stringify({ type: 'typing' }));
          } catch (_e) { /* ignore */ }
        }
      });
    }

    // Emoji button
    if (dom.chatEmojiBtn) {
      dom.chatEmojiBtn.addEventListener('click', () => togglePicker('emoji'));
    }
    // GIF button
    if (dom.chatGifBtn) {
      dom.chatGifBtn.addEventListener('click', () => togglePicker('gif'));
    }
    // Attach button
    if (dom.chatAttachBtn) {
      dom.chatAttachBtn.addEventListener('click', () => {
        closeAllPickers();
        if (dom.chatFileInput) dom.chatFileInput.click();
      });
    }
    // File input change
    if (dom.chatFileInput) {
      dom.chatFileInput.addEventListener('change', handleChatFileSelect);
    }
    // Remove attachment
    if (dom.chatAttachRemove) {
      dom.chatAttachRemove.addEventListener('click', removeChatAttach);
    }
    // GIF search
    if (dom.gifSearchInput) {
      dom.gifSearchInput.addEventListener('input', () => {
        clearTimeout(gifSearchTimeout);
        gifSearchTimeout = setTimeout(() => {
          const q = dom.gifSearchInput.value.trim();
          if (q.length >= 2) {
            searchGifs(q);
          } else if (q.length === 0) {
            loadTrendingGifs();
          }
        }, 400);
      });
    }

    // Initialize emoji grid
    initEmojiPicker();
  }

  function updateChatVisibility() {
    // Show chat toggle only when a project is selected
    if (dom.chatToggle) {
      if (state.activeProjectId && state.token) {
        dom.chatToggle.style.display = '';
        // If chat panel is already open, reconnect to new project
        if (state.chatOpen) {
          const proj = state.projects.find(p => p.id === state.activeProjectId);
          const chatSubtitle = document.getElementById('chatProjectName');
          if (chatSubtitle) chatSubtitle.textContent = proj ? proj.name : '';
          connectChatWs(state.activeProjectId);
        }
      } else {
        dom.chatToggle.style.display = 'none';
        closeChat();
      }
    }
  }

  function toggleChat() {
    if (state.chatOpen) {
      closeChat();
    } else {
      openChat();
    }
  }

  function openChat() {
    if (!state.activeProjectId) return;
    state.chatOpen = true;
    if (dom.chatPanel) dom.chatPanel.classList.add('open');
    document.body.classList.add('chat-open');
    // Show project name in chat header
    const proj = state.projects.find(p => p.id === state.activeProjectId);
    const chatSubtitle = document.getElementById('chatProjectName');
    if (chatSubtitle) chatSubtitle.textContent = proj ? proj.name : '';
    // Reset unread
    state.chatUnread = 0;
    if (dom.chatUnread) dom.chatUnread.style.display = 'none';
    // Connect WebSocket if not connected
    if (!state.chatWs || state.chatWs.readyState !== WebSocket.OPEN) {
      connectChatWs(state.activeProjectId);
    }
    if (dom.chatInput) dom.chatInput.focus();
  }

  function closeChat() {
    state.chatOpen = false;
    if (dom.chatPanel) dom.chatPanel.classList.remove('open');
    document.body.classList.remove('chat-open');
  }

  function disconnectChat() {
    if (state.chatWs) {
      try { state.chatWs.close(); } catch (_e) { /* ignore */ }
      state.chatWs = null;
    }
    state.chatMessages = [];
    state.chatUsers = [];
    if (dom.chatMessages) {
      dom.chatMessages.innerHTML = '<div class="chat-empty">No messages yet. Start the conversation!</div>';
    }
    if (dom.chatPresence) dom.chatPresence.innerHTML = '';
    if (dom.chatTyping) dom.chatTyping.textContent = '';
  }

  function connectChatWs(projectId) {
    disconnectChat();
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const tokenParam = state.token ? `token=${encodeURIComponent(state.token)}` : '';
    const url = `${protocol}//${location.host}/ws/chat?${tokenParam}&project_id=${encodeURIComponent(projectId)}`;

    const ws = new WebSocket(url);
    state.chatWs = ws;

    ws.onopen = () => {
      // Connected successfully
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleChatEvent(msg);
      } catch (_e) { /* ignore parse errors */ }
    };

    ws.onerror = () => {
      if (state.chatOpen) {
        showToast('Chat connection failed. Retrying...', 'warning');
      }
    };

    ws.onclose = (event) => {
      state.chatWs = null;
      // Auto-reconnect after 3s if chat is still open
      if (state.chatOpen && state.activeProjectId && event.code !== 1000) {
        setTimeout(() => {
          if (state.chatOpen && state.activeProjectId && !state.chatWs) {
            connectChatWs(state.activeProjectId);
          }
        }, 3000);
      }
    };
  }

  function handleChatEvent(msg) {
    switch (msg.type) {
      case 'chat_history':
        state.chatMessages = msg.messages || [];
        renderChatMessages();
        break;

      case 'chat_message':
        state.chatMessages.push(msg);
        appendChatMessage(msg);
        scrollChatToBottom();
        // Unread badge if chat is closed
        if (!state.chatOpen) {
          state.chatUnread++;
          if (dom.chatUnread) {
            dom.chatUnread.textContent = state.chatUnread > 9 ? '9+' : state.chatUnread;
            dom.chatUnread.style.display = '';
          }
        }
        // Clear typing indicator for this user
        clearTypingFor(msg.user_email);
        break;

      case 'presence_update':
        state.chatUsers = msg.users || [];
        renderPresence();
        break;

      case 'typing':
        showTypingIndicator(msg.user_email);
        break;

      default:
        break;
    }
  }

  function renderChatMessages() {
    if (!dom.chatMessages) return;
    if (state.chatMessages.length === 0) {
      dom.chatMessages.innerHTML = '<div class="chat-empty">No messages yet. Start the conversation!</div>';
      return;
    }
    dom.chatMessages.innerHTML = '';
    state.chatMessages.forEach((m) => appendChatMessage(m));
    scrollChatToBottom();
  }

  function appendChatMessage(msg) {
    if (!dom.chatMessages) return;
    // Remove empty placeholder
    const empty = dom.chatMessages.querySelector('.chat-empty');
    if (empty) empty.remove();

    const isOwn = msg.user_id === state.userId;
    const div = document.createElement('div');
    div.className = `chat-msg ${isOwn ? 'own' : 'other'}`;

    let refHtml = '';
    if (msg.ref_type && msg.ref_id) {
      const label = msg.ref_type === 'run' ? 'Research run' : msg.ref_type;
      refHtml = `<div class="chat-msg-ref" title="${esc(msg.ref_id)}">${esc(label)}</div>`;
    }

    const timeStr = formatChatTime(msg.created_at);
    const senderName = (msg.user_email || '').split('@')[0];

    // Detect special content: [gif] or [img] prefixes
    let contentHtml = '';
    const content = msg.content || '';

    if (content.startsWith('[gif]')) {
      const gifUrl = content.substring(5);
      contentHtml = `<img class="chat-msg-image" src="${esc(gifUrl)}" alt="GIF" loading="lazy" />`;
    } else if (content.includes('[img]')) {
      const parts = content.split('[img]');
      const textPart = parts[0].trim();
      const imgUrl = parts[1] || '';
      if (textPart) contentHtml += `<div class="chat-msg-text">${esc(textPart)}</div>`;
      contentHtml += `<img class="chat-msg-image" src="${esc(imgUrl)}" alt="Image" loading="lazy" />`;
    } else if (content.includes('[file:')) {
      // [file:filename.pdf]dataUrl  or  text\n[file:filename.pdf]dataUrl
      const fileIdx = content.indexOf('[file:');
      const textBefore = content.substring(0, fileIdx).trim();
      const rest = content.substring(fileIdx + 6); // after "[file:"
      const closeBracket = rest.indexOf(']');
      const fileName = rest.substring(0, closeBracket);
      const dataUrl = rest.substring(closeBracket + 1);
      if (textBefore) contentHtml += `<div class="chat-msg-text">${esc(textBefore)}</div>`;
      const ext = (fileName.split('.').pop() || '').toUpperCase();
      contentHtml += `<a class="chat-file-attach" href="${esc(dataUrl)}" download="${esc(fileName)}" title="Download ${esc(fileName)}">
        <span class="chat-file-icon">\u{1F4CE}</span>
        <span class="chat-file-name">${esc(fileName)}</span>
        <span class="chat-file-ext">${esc(ext)}</span>
      </a>`;
    } else {
      contentHtml = `<div class="chat-msg-text">${esc(content)}</div>`;
    }

    div.innerHTML = `
      <div class="chat-msg-sender">${esc(senderName)}</div>
      ${refHtml}
      ${contentHtml}
      <div class="chat-msg-time">${timeStr}</div>
    `;
    dom.chatMessages.appendChild(div);
  }

  function scrollChatToBottom() {
    if (dom.chatMessages) {
      dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
    }
  }

  function formatChatTime(isoStr) {
    if (!isoStr) return '';
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (_e) {
      return '';
    }
  }

  function renderPresence() {
    if (!dom.chatPresence) return;
    dom.chatPresence.innerHTML = state.chatUsers
      .map((u) => {
        const name = (u.email || '').split('@')[0];
        return `<span class="chat-presence-dot" title="${esc(name)}"></span>`;
      })
      .join('');
  }

  function showTypingIndicator(email) {
    if (!dom.chatTyping) return;
    const name = (email || '').split('@')[0];
    dom.chatTyping.textContent = `${name} is typing...`;
    // Clear after 3 seconds
    if (state.chatTypingTimeout) clearTimeout(state.chatTypingTimeout);
    state.chatTypingTimeout = setTimeout(() => {
      if (dom.chatTyping) dom.chatTyping.textContent = '';
    }, 3000);
  }

  function clearTypingFor(_email) {
    // Clear typing indicator when a message arrives
    if (dom.chatTyping) dom.chatTyping.textContent = '';
    if (state.chatTypingTimeout) clearTimeout(state.chatTypingTimeout);
  }

  function sendChatMessage() {
    const content = (dom.chatInput ? dom.chatInput.value : '').trim();
    const hasWs = state.chatWs && state.chatWs.readyState === WebSocket.OPEN;

    // Handle file attachment — all files sent as data URL
    if (state.chatAttachFile && hasWs) {
      const file = state.chatAttachFile;
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result;
        let msgContent;
        if (file.type.startsWith('image/')) {
          msgContent = content ? `${content}\n[img]${dataUrl}` : `[img]${dataUrl}`;
        } else {
          // [file:filename.pdf]dataUrl — renders as downloadable attachment
          msgContent = content
            ? `${content}\n[file:${file.name}]${dataUrl}`
            : `[file:${file.name}]${dataUrl}`;
        }
        state.chatWs.send(JSON.stringify({ type: 'chat_message', content: msgContent }));
        removeChatAttach();
      };
      reader.readAsDataURL(file);
      if (dom.chatInput) dom.chatInput.value = '';
      closeAllPickers();
      return;
    }

    if (!content || !hasWs) return;

    state.chatWs.send(JSON.stringify({
      type: 'chat_message',
      content: content,
    }));

    if (dom.chatInput) dom.chatInput.value = '';
    closeAllPickers();
  }

  // ─── Emoji Picker ─────────────────────────────────────────────

  function initEmojiPicker() {
    if (!dom.emojiGrid) return;
    let html = '';
    EMOJI_DATA.forEach(cat => {
      html += `<div class="emoji-category-label">${cat.cat}</div>`;
      html += '<div class="emoji-category-grid">';
      cat.emojis.forEach(e => {
        html += `<button type="button" class="emoji-item" data-emoji="${e}">${e}</button>`;
      });
      html += '</div>';
    });
    dom.emojiGrid.innerHTML = html;

    dom.emojiGrid.addEventListener('click', (e) => {
      const btn = e.target.closest('.emoji-item');
      if (!btn) return;
      const emoji = btn.dataset.emoji;
      if (dom.chatInput) {
        dom.chatInput.value += emoji;
        dom.chatInput.focus();
      }
    });
  }

  // ─── GIF Picker ──────────────────────────────────────────────

  async function loadTrendingGifs() {
    try {
      const resp = await fetch('https://api.giphy.com/v1/gifs/trending?api_key=GlVGYHkr3WSBnllca54iNt0yFbjz7L65&limit=20&rating=g');
      if (!resp.ok) throw new Error('API error');
      const data = await resp.json();
      renderGifResults(data.data || []);
    } catch (_e) {
      if (dom.gifGrid) dom.gifGrid.innerHTML = '<div class="gif-loading">Trending GIFs unavailable</div>';
    }
  }

  async function searchGifs(query) {
    try {
      if (dom.gifGrid) dom.gifGrid.innerHTML = '<div class="gif-loading">Searching...</div>';
      const resp = await fetch(`https://api.giphy.com/v1/gifs/search?api_key=GlVGYHkr3WSBnllca54iNt0yFbjz7L65&q=${encodeURIComponent(query)}&limit=20&rating=g`);
      if (!resp.ok) throw new Error('API error');
      const data = await resp.json();
      renderGifResults(data.data || []);
    } catch (_e) {
      if (dom.gifGrid) dom.gifGrid.innerHTML = '<div class="gif-loading">GIF search unavailable</div>';
    }
  }

  function renderGifResults(gifs) {
    if (!dom.gifGrid) return;
    if (gifs.length === 0) {
      dom.gifGrid.innerHTML = '<div class="gif-loading">No GIFs found</div>';
      return;
    }
    dom.gifGrid.innerHTML = gifs.map(g => {
      const thumb = (g.images && g.images.fixed_height_small && g.images.fixed_height_small.url) || '';
      const full = (g.images && g.images.original && g.images.original.url) || thumb;
      return `<button type="button" class="gif-item" data-url="${esc(full)}"><img src="${esc(thumb)}" alt="${esc(g.title || '')}" loading="lazy" /></button>`;
    }).join('');

    dom.gifGrid.querySelectorAll('.gif-item').forEach(btn => {
      btn.addEventListener('click', () => {
        const url = btn.dataset.url;
        if (url && state.chatWs && state.chatWs.readyState === WebSocket.OPEN) {
          state.chatWs.send(JSON.stringify({ type: 'chat_message', content: `[gif]${url}` }));
        }
        closeAllPickers();
      });
    });
  }

  // ─── Attachment ──────────────────────────────────────────────

  function handleChatFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      showToast('File too large. Max 5 MB for chat attachments.', 'error');
      e.target.value = '';
      return;
    }

    state.chatAttachFile = file;
    closeAllPickers();

    // Show preview
    if (dom.chatAttachPreview) dom.chatAttachPreview.style.display = 'flex';
    if (dom.chatAttachName) dom.chatAttachName.textContent = file.name;

    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = () => {
        if (dom.chatAttachThumb) {
          dom.chatAttachThumb.src = reader.result;
          dom.chatAttachThumb.style.display = 'block';
        }
        if (dom.chatAttachIcon) dom.chatAttachIcon.style.display = 'none';
      };
      reader.readAsDataURL(file);
    } else {
      if (dom.chatAttachThumb) dom.chatAttachThumb.style.display = 'none';
      if (dom.chatAttachIcon) dom.chatAttachIcon.style.display = 'block';
    }

    e.target.value = '';
    if (dom.chatInput) dom.chatInput.focus();
  }

  function removeChatAttach() {
    state.chatAttachFile = null;
    if (dom.chatAttachPreview) dom.chatAttachPreview.style.display = 'none';
    if (dom.chatAttachThumb) {
      dom.chatAttachThumb.src = '';
      dom.chatAttachThumb.style.display = 'none';
    }
    if (dom.chatAttachIcon) dom.chatAttachIcon.style.display = 'none';
  }

  // ─── Picker Toggles ──────────────────────────────────────────

  function togglePicker(type) {
    const emojiOpen = dom.chatEmojiPicker && dom.chatEmojiPicker.style.display !== 'none';
    const gifOpen = dom.chatGifPicker && dom.chatGifPicker.style.display !== 'none';

    closeAllPickers();

    if (type === 'emoji' && !emojiOpen) {
      if (dom.chatEmojiPicker) dom.chatEmojiPicker.style.display = 'block';
      if (dom.chatEmojiBtn) dom.chatEmojiBtn.classList.add('active');
    } else if (type === 'gif' && !gifOpen) {
      if (dom.chatGifPicker) dom.chatGifPicker.style.display = 'block';
      if (dom.chatGifBtn) dom.chatGifBtn.classList.add('active');
      // Load trending GIFs on first open
      if (dom.gifGrid && dom.gifGrid.querySelector('.gif-loading')) {
        loadTrendingGifs();
      }
      if (dom.gifSearchInput) dom.gifSearchInput.focus();
    }
  }

  function closeAllPickers() {
    if (dom.chatEmojiPicker) dom.chatEmojiPicker.style.display = 'none';
    if (dom.chatGifPicker) dom.chatGifPicker.style.display = 'none';
    if (dom.chatEmojiBtn) dom.chatEmojiBtn.classList.remove('active');
    if (dom.chatGifBtn) dom.chatGifBtn.classList.remove('active');
  }

  // ─── Ask PDF ──────────────────────────────────────────────────

  function openAskPdf(pdfId, pdfName) {
    state.askPdfId = pdfId;
    state.askPdfName = pdfName;
    const panel = document.getElementById('ask-pdf-panel');
    const fnEl = document.getElementById('ask-pdf-filename');
    const convo = document.getElementById('ask-pdf-conversation');
    if (panel) panel.style.display = '';
    if (fnEl) fnEl.textContent = pdfName;
    if (convo) convo.innerHTML = '<div class="ask-pdf-empty">Ask any question about this document...</div>';
    const input = document.getElementById('ask-pdf-input');
    if (input) input.focus();
  }

  function closeAskPdf() {
    state.askPdfId = null;
    const panel = document.getElementById('ask-pdf-panel');
    if (panel) panel.style.display = 'none';
  }

  function bindAskPdfEvents() {
    const closeBtn = document.getElementById('ask-pdf-close');
    if (closeBtn) closeBtn.addEventListener('click', closeAskPdf);

    const form = document.getElementById('ask-pdf-form');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = document.getElementById('ask-pdf-input');
        const question = input ? input.value.trim() : '';
        if (!question || !state.askPdfId) return;

        const convo = document.getElementById('ask-pdf-conversation');
        // Remove empty placeholder
        const empty = convo ? convo.querySelector('.ask-pdf-empty') : null;
        if (empty) empty.remove();

        // Add user message
        if (convo) {
          const userDiv = document.createElement('div');
          userDiv.className = 'ask-pdf-msg user';
          userDiv.textContent = question;
          convo.appendChild(userDiv);
        }

        // Add loading indicator
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'ask-pdf-msg assistant loading';
        loadingDiv.innerHTML = '<span class="ask-pdf-dots"><span>.</span><span>.</span><span>.</span></span>';
        if (convo) convo.appendChild(loadingDiv);
        convo.scrollTop = convo.scrollHeight;

        if (input) input.value = '';

        try {
          const resp = await fetch(`/api/v1/pdfs/${state.askPdfId}/ask`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${state.token}`,
            },
            body: JSON.stringify({ question }),
          });

          loadingDiv.remove();

          if (!resp.ok) throw new Error('Failed to get answer');
          const data = await resp.json();

          // Add assistant answer
          const ansDiv = document.createElement('div');
          ansDiv.className = 'ask-pdf-msg assistant';

          let sourcesHtml = '';
          if (data.sources && data.sources.length > 0) {
            sourcesHtml = '<div class="ask-pdf-sources">' +
              data.sources.map(s =>
                `<span class="ask-pdf-source-chip" title="${esc(s.text)}">p.${s.page}</span>`
              ).join('') + '</div>';
          }

          ansDiv.innerHTML = `<div class="ask-pdf-answer">${esc(data.answer)}</div>${sourcesHtml}`;
          if (convo) convo.appendChild(ansDiv);
        } catch (_e) {
          loadingDiv.remove();
          const errDiv = document.createElement('div');
          errDiv.className = 'ask-pdf-msg assistant error';
          errDiv.textContent = 'Failed to get answer. Please try again.';
          if (convo) convo.appendChild(errDiv);
        }

        if (convo) convo.scrollTop = convo.scrollHeight;
      });
    }
  }

  // ─── Citation Graph ───────────────────────────────────────────

  function bindCitationGraphEvents() {
    const btn = document.getElementById('citation-graph-btn');
    if (btn) btn.addEventListener('click', showCitationGraph);

    const closeBtn = document.getElementById('citation-graph-close');
    if (closeBtn) closeBtn.addEventListener('click', () => {
      const container = document.getElementById('citation-graph-container');
      if (container) container.style.display = 'none';
    });
  }

  function showCitationGraph() {
    if (!state.currentResult || !state.currentResult.claims) return;

    const container = document.getElementById('citation-graph-container');
    const canvas = document.getElementById('citation-graph-canvas');
    if (!container || !canvas) return;
    container.style.display = '';

    // Build graph data
    const nodes = [];
    const edges = [];
    const sourceMap = {};

    // Add claim nodes
    state.currentResult.claims.forEach((claim, i) => {
      nodes.push({
        id: claim.id || `claim_${i}`,
        label: claim.statement.length > 50 ? claim.statement.substring(0, 50) + '...' : claim.statement,
        fullLabel: claim.statement,
        type: 'claim',
        confidence: claim.confidence || 'medium',
        x: 200 + Math.random() * 400,
        y: 100 + Math.random() * 300,
        vx: 0, vy: 0,
        radius: 12,
      });

      // Add source nodes and edges
      (claim.citations || []).forEach(cit => {
        const sid = cit.source_id || cit.doi || cit.title;
        if (!sourceMap[sid]) {
          sourceMap[sid] = {
            id: sid,
            label: (cit.title || 'Unknown').substring(0, 40) + (cit.title && cit.title.length > 40 ? '...' : ''),
            fullLabel: cit.title || 'Unknown Source',
            authors: (cit.authors || []).join(', '),
            type: 'source',
            x: 200 + Math.random() * 400,
            y: 100 + Math.random() * 300,
            vx: 0, vy: 0,
            radius: 8,
            connections: 0,
          };
          nodes.push(sourceMap[sid]);
        }
        sourceMap[sid].connections++;
        sourceMap[sid].radius = Math.min(16, 6 + sourceMap[sid].connections * 2);
        edges.push({ from: claim.id || `claim_${i}`, to: sid });
      });
    });

    // Run force simulation and render
    runForceGraph(canvas, nodes, edges);
  }

  function runForceGraph(canvas, nodes, edges) {
    const ctx = canvas.getContext('2d');
    const W = canvas.parentElement.clientWidth - 2;
    const H = 500;
    canvas.width = W;
    canvas.height = H;

    // Colors
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const colors = {
      bg: isDark ? '#0f1117' : '#ffffff',
      claimNode: '#6366f1',
      sourceNode: '#14b8a6',
      edge: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
      text: isDark ? '#e2e8f0' : '#1e293b',
      textDim: isDark ? '#64748b' : '#94a3b8',
    };

    const tooltip = document.getElementById('citation-graph-tooltip');
    let hoveredNode = null;
    let dragNode = null;
    let animFrame = null;

    function simulate() {
      // Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j].x - nodes[i].x;
          const dy = nodes[j].y - nodes[i].y;
          const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = 800 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          nodes[i].vx -= fx;
          nodes[i].vy -= fy;
          nodes[j].vx += fx;
          nodes[j].vy += fy;
        }
      }

      // Attraction along edges
      edges.forEach(e => {
        const a = nodes.find(n => n.id === e.from);
        const b = nodes.find(n => n.id === e.to);
        if (!a || !b) return;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const force = (dist - 120) * 0.005;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      });

      // Center gravity
      nodes.forEach(n => {
        n.vx += (W / 2 - n.x) * 0.001;
        n.vy += (H / 2 - n.y) * 0.001;
      });

      // Apply velocities with damping
      nodes.forEach(n => {
        if (n === dragNode) return;
        n.vx *= 0.85;
        n.vy *= 0.85;
        n.x += n.vx;
        n.y += n.vy;
        // Keep in bounds
        n.x = Math.max(n.radius + 5, Math.min(W - n.radius - 5, n.x));
        n.y = Math.max(n.radius + 5, Math.min(H - n.radius - 5, n.y));
      });
    }

    function draw() {
      ctx.clearRect(0, 0, W, H);

      // Draw edges
      ctx.strokeStyle = colors.edge;
      ctx.lineWidth = 1.5;
      edges.forEach(e => {
        const a = nodes.find(n => n.id === e.from);
        const b = nodes.find(n => n.id === e.to);
        if (!a || !b) return;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      });

      // Draw nodes
      nodes.forEach(n => {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);

        if (n.type === 'claim') {
          ctx.fillStyle = n.confidence === 'high' ? '#6366f1' : n.confidence === 'low' ? '#f43f5e' : '#a78bfa';
        } else {
          ctx.fillStyle = colors.sourceNode;
        }

        if (n === hoveredNode) {
          ctx.shadowColor = ctx.fillStyle;
          ctx.shadowBlur = 12;
        }
        ctx.fill();
        ctx.shadowBlur = 0;

        // Label
        ctx.fillStyle = colors.textDim;
        ctx.font = '9px system-ui, sans-serif';
        ctx.textAlign = 'center';
        const labelY = n.y + n.radius + 12;
        if (labelY < H - 5) {
          ctx.fillText(n.label, n.x, labelY);
        }
      });

      simulate();
      animFrame = requestAnimationFrame(draw);
    }

    // Mouse interaction
    function getNodeAt(mx, my) {
      for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        const dx = mx - n.x;
        const dy = my - n.y;
        if (dx * dx + dy * dy <= (n.radius + 4) * (n.radius + 4)) return n;
      }
      return null;
    }

    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      if (dragNode) {
        dragNode.x = mx;
        dragNode.y = my;
        dragNode.vx = 0;
        dragNode.vy = 0;
        return;
      }

      const node = getNodeAt(mx, my);
      hoveredNode = node;
      canvas.style.cursor = node ? 'pointer' : 'default';

      if (node && tooltip) {
        let html = `<strong>${esc(node.fullLabel)}</strong>`;
        if (node.authors) html += `<br><span style="color:var(--text-secondary)">${esc(node.authors)}</span>`;
        if (node.type === 'claim') html += `<br>Confidence: <span class="confidence-badge ${node.confidence}">${node.confidence}</span>`;
        tooltip.innerHTML = html;
        tooltip.style.display = '';
        tooltip.style.left = (e.clientX - canvas.parentElement.getBoundingClientRect().left + 12) + 'px';
        tooltip.style.top = (e.clientY - canvas.parentElement.getBoundingClientRect().top - 10) + 'px';
      } else if (tooltip) {
        tooltip.style.display = 'none';
      }
    });

    canvas.addEventListener('mousedown', (e) => {
      const rect = canvas.getBoundingClientRect();
      dragNode = getNodeAt(e.clientX - rect.left, e.clientY - rect.top);
    });

    canvas.addEventListener('mouseup', () => { dragNode = null; });
    canvas.addEventListener('mouseleave', () => {
      dragNode = null;
      hoveredNode = null;
      if (tooltip) tooltip.style.display = 'none';
    });

    // Start animation
    if (animFrame) cancelAnimationFrame(animFrame);
    draw();

    // Stop after 10s to save CPU
    setTimeout(() => {
      if (animFrame) cancelAnimationFrame(animFrame);
      // One final draw
      draw();
      cancelAnimationFrame(animFrame);
    }, 10000);
  }

  // ─── Data Extraction Table ────────────────────────────────────

  function bindExtractTableEvents() {
    const extractBtn = document.getElementById('extract-table-btn');
    if (extractBtn) {
      extractBtn.addEventListener('click', extractDataTable);
    }

    const closeBtn = document.getElementById('extraction-table-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        const container = document.getElementById('extraction-table-container');
        if (container) container.style.display = 'none';
      });
    }

    // Sortable columns
    document.querySelectorAll('.extraction-table th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const field = th.dataset.sort;
        sortExtractionTable(field);
      });
    });
  }

  let extractionData = [];
  let extractionSortField = null;
  let extractionSortAsc = true;

  async function extractDataTable() {
    if (!state.currentResult || !state.currentResult.claims) {
      showToast('No results to extract', 'warning');
      return;
    }

    const btn = document.getElementById('extract-table-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Extracting...'; }

    try {
      const resp = await fetch('/api/v1/extract-table', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${state.token}`,
        },
        body: JSON.stringify({ claims: state.currentResult.claims }),
      });

      if (!resp.ok) throw new Error('Extraction failed');
      const data = await resp.json();
      extractionData = data.rows || [];
      renderExtractionTable(extractionData);

      const container = document.getElementById('extraction-table-container');
      if (container) container.style.display = '';

    } catch (_e) {
      showToast('Failed to extract data table', 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Extract Table'; }
    }
  }

  function renderExtractionTable(rows) {
    const tbody = document.getElementById('extraction-table-body');
    if (!tbody) return;

    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-tertiary);">No data extracted</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(r => `
      <tr>
        <td title="${esc(r.source)}">${esc(r.source)}</td>
        <td>${esc(r.authors)}</td>
        <td>${esc(r.year)}</td>
        <td><span class="method-badge">${esc(r.method)}</span></td>
        <td>${esc(r.sample_size)}</td>
        <td class="finding-cell" title="${esc(r.key_finding)}">${esc(r.key_finding)}</td>
        <td>${esc(r.outcome)}</td>
        <td><span class="confidence-badge ${r.confidence}">${esc(r.confidence)}</span></td>
      </tr>
    `).join('');
  }

  function sortExtractionTable(field) {
    if (extractionSortField === field) {
      extractionSortAsc = !extractionSortAsc;
    } else {
      extractionSortField = field;
      extractionSortAsc = true;
    }

    extractionData.sort((a, b) => {
      const va = (a[field] || '').toLowerCase();
      const vb = (b[field] || '').toLowerCase();
      return extractionSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    });

    renderExtractionTable(extractionData);

    // Update sort indicators
    document.querySelectorAll('.extraction-table th[data-sort]').forEach(th => {
      th.classList.remove('sort-asc', 'sort-desc');
      if (th.dataset.sort === field) {
        th.classList.add(extractionSortAsc ? 'sort-asc' : 'sort-desc');
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════
  // PROVENANCE CHAIN
  // ═══════════════════════════════════════════════════════════════

  function handleProvenance(data) {
    state.provenanceData = data;

    const coveragePct = Math.round((data.coverage_score || 0) * 100);

    addTraceStep('evidence', 'Provenance chain built', `${(data.links || []).length} links, ${coveragePct}% verified coverage`);

    // The provenance button is already visible from handleCompleted
    // If provenance arrives after completed, ensure button is shown
    const provBtn = document.getElementById('provenance-btn');
    if (provBtn && dom.exportButtons.style.display !== 'none') {
      provBtn.style.display = '';
    }
  }

  function showProvenancePanel() {
    if (!state.provenanceData) {
      // Try to fetch from API if we have a run_id
      if (state.currentResult && state.currentResult.run_id) {
        fetchProvenance(state.currentResult.run_id);
      } else {
        showToast('No provenance data available yet.', 'warning');
      }
      return;
    }

    renderProvenance(state.provenanceData);
    if (dom.provenancePanel) dom.provenancePanel.style.display = '';
  }

  function hideProvenancePanel() {
    if (dom.provenancePanel) dom.provenancePanel.style.display = 'none';
  }

  async function fetchProvenance(runId) {
    try {
      const resp = await authFetch(`/api/v1/runs/${runId}/provenance`);
      if (!resp.ok) {
        showToast('Provenance data not available for this run.', 'warning');
        return;
      }
      const data = await resp.json();
      state.provenanceData = data;
      renderProvenance(data);
      if (dom.provenancePanel) dom.provenancePanel.style.display = '';
    } catch (_e) {
      showToast('Failed to load provenance data.', 'error');
    }
  }

  function renderProvenance(data) {
    if (!dom.provenanceLinks) return;

    const links = data.links || [];
    const ungrounded = data.ungrounded_claims || [];
    const coveragePct = Math.round((data.coverage_score || 0) * 100);

    // Update coverage bar
    if (dom.provenanceCoverageFill) {
      dom.provenanceCoverageFill.style.width = coveragePct + '%';
      // Color the bar based on coverage level
      if (coveragePct >= 80) {
        dom.provenanceCoverageFill.style.background = 'var(--success)';
      } else if (coveragePct >= 50) {
        dom.provenanceCoverageFill.style.background = 'var(--warning)';
      } else {
        dom.provenanceCoverageFill.style.background = 'var(--error)';
      }
    }
    if (dom.provenanceCoveragePct) {
      dom.provenanceCoveragePct.textContent = coveragePct + '%';
    }

    // Render links
    if (links.length === 0) {
      dom.provenanceLinks.innerHTML = '<div class="results-placeholder"><p>No provenance links found.</p></div>';
    } else {
      // Group links by claim_id for a cleaner display
      const grouped = {};
      const groupOrder = [];
      links.forEach((link, idx) => {
        const key = link.claim_id || ('claim-' + idx);
        if (!grouped[key]) {
          grouped[key] = { claim_text: link.claim_text, links: [] };
          groupOrder.push(key);
        }
        grouped[key].links.push(link);
      });

      let html = '';
      let claimNum = 0;
      for (const key of groupOrder) {
        claimNum++;
        const group = grouped[key];
        html += `<div class="provenance-link">`;

        // Claim
        html += `<div class="provenance-claim">`;
        html += `<div class="provenance-claim-icon">${claimNum}</div>`;
        html += `<div class="provenance-claim-text">${esc(group.claim_text)}</div>`;
        html += `</div>`;

        // For each citation link under this claim
        group.links.forEach(link => {
          const cit = link.citation || {};

          // Chain connector
          html += `<div class="provenance-chain-connector"><div class="provenance-chain-line"></div></div>`;

          // Citation
          html += `<div class="provenance-citation">`;
          const doiUrl = cit.doi ? `https://doi.org/${esc(cit.doi)}` : '';
          const paperUrl = cit.url || doiUrl;

          if (paperUrl) {
            html += `<div class="provenance-citation-title"><a href="${esc(paperUrl)}" target="_blank" rel="noopener">${esc(cit.title || 'Untitled')}</a></div>`;
          } else {
            html += `<div class="provenance-citation-title">${esc(cit.title || 'Untitled')}</div>`;
          }

          if (cit.authors && cit.authors.length > 0) {
            html += `<div class="provenance-citation-authors">${esc(cit.authors.join(', '))}</div>`;
          }

          html += `<div class="provenance-citation-meta">`;

          // DOI badge
          if (cit.doi) {
            html += `<a class="provenance-doi" href="https://doi.org/${esc(cit.doi)}" target="_blank" rel="noopener">doi:${esc(cit.doi)}</a>`;
          }

          // Tool badge
          if (link.retrieval_tool && link.retrieval_tool !== 'unknown') {
            const toolLabel = _formatToolName(link.retrieval_tool);
            html += `<span class="provenance-tool-badge">${esc(toolLabel)}</span>`;
          }

          // Verification badge
          const vs = link.verification_status || 'unverified';
          const vsLabel = vs === 'verified' ? '\u2713 Verified' : vs === 'broken' ? '\u2717 Broken' : '? Unverified';
          html += `<span class="provenance-verification ${esc(vs)}">${vsLabel}</span>`;

          html += `</div>`; // meta
          html += `</div>`; // citation

          // Evidence quote
          if (link.evidence_span && link.evidence_span.text) {
            html += `<div class="provenance-chain-connector"><div class="provenance-chain-line"></div></div>`;
            html += `<div class="provenance-evidence">`;
            html += `<div class="provenance-evidence-quote">"${esc(link.evidence_span.text)}"</div>`;
            html += `</div>`;
          }
        });

        html += `</div>`; // provenance-link
      }
      dom.provenanceLinks.innerHTML = html;
    }

    // Ungrounded claims
    if (ungrounded.length > 0) {
      if (dom.provenanceUngrounded) dom.provenanceUngrounded.style.display = '';
      if (dom.provenanceUngroundedList) {
        dom.provenanceUngroundedList.innerHTML = ungrounded.map(claim =>
          `<div class="provenance-ungrounded-item">${esc(claim)}</div>`
        ).join('');
      }
    } else {
      if (dom.provenanceUngrounded) dom.provenanceUngrounded.style.display = 'none';
    }
  }

  function _formatToolName(toolName) {
    const toolNames = {
      'semantic_scholar': 'Semantic Scholar',
      'pubmed_search': 'PubMed',
      'arxiv_search': 'ArXiv',
      'arxiv': 'ArXiv',
      'openalex_search': 'OpenAlex',
      'crossref_search': 'CrossRef',
      'web_search': 'Web Search',
      'doi_lookup': 'DOI Lookup',
      'pdf_ingest': 'PDF Ingest',
    };
    return toolNames[toolName] || toolName.replace(/_/g, ' ');
  }

  function bindProvenanceEvents() {
    // Provenance button click
    const provBtn = document.getElementById('provenance-btn');
    if (provBtn) {
      provBtn.addEventListener('click', () => {
        if (dom.provenancePanel && dom.provenancePanel.style.display !== 'none') {
          hideProvenancePanel();
        } else {
          showProvenancePanel();
        }
      });
    }

    // Close button
    if (dom.provenanceClose) {
      dom.provenanceClose.addEventListener('click', hideProvenancePanel);
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // REPRODUCIBILITY
  // ═══════════════════════════════════════════════════════════════

  function bindReproEvents() {
    if (dom.reproModalClose) {
      dom.reproModalClose.addEventListener('click', closeReproModal);
    }
    if (dom.reproOverlay) {
      dom.reproOverlay.addEventListener('click', (e) => {
        if (e.target === dom.reproOverlay) closeReproModal();
      });
    }
    if (dom.reproCopyBtn) {
      dom.reproCopyBtn.addEventListener('click', copyFingerprint);
    }
    if (dom.reproVerifyBtn) {
      dom.reproVerifyBtn.addEventListener('click', verifyFingerprint);
    }
    if (dom.reproCompareBtn) {
      dom.reproCompareBtn.addEventListener('click', compareRuns);
    }
  }

  function handleFingerprint(data) {
    state.currentFingerprint = data;

    // Store in fingerprint history
    if (data && data.run_id) {
      state.fingerprintHistory[data.run_id] = data;
    }

    // Render badge if results are already showing
    if (state.currentResult) {
      renderFingerprintBadge();
    }

    addTraceStep('info', 'Fingerprint generated', 'Hash: <code>' + esc((data.composite_hash || '').substring(0, 8)) + '...</code>');
  }

  function renderFingerprintBadge() {
    const fp = state.currentFingerprint;
    if (!fp) return;

    // Remove existing badge if any
    const existing = document.getElementById('repro-badge');
    if (existing) existing.remove();

    // Create badge and insert it in the results summary area
    const badge = document.createElement('div');
    badge.id = 'repro-badge';
    badge.className = 'repro-badge';
    badge.title = 'Reproducibility fingerprint - click for details';
    badge.innerHTML =
      '<svg class="repro-badge-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4"/>' +
      '</svg>' +
      '<code class="repro-badge-hash">' + esc(fp.composite_hash.substring(0, 8)) + '</code>' +
      '<span class="repro-badge-status repro-badge-status--unverified">unverified</span>';
    badge.addEventListener('click', openReproModal);

    // Insert after the results summary
    var summaryEl = dom.resultsSummary;
    if (summaryEl && summaryEl.parentNode) {
      summaryEl.parentNode.insertBefore(badge, summaryEl.nextSibling);
    }
  }

  function openReproModal() {
    var fp = state.currentFingerprint;
    if (!fp || !dom.reproOverlay) return;

    // Populate composite hash
    dom.reproCompositeHash.textContent = fp.composite_hash || '';

    // Populate sub-hashes
    dom.reproQueryHash.textContent = fp.query_hash || '';
    dom.reproEvidenceHash.textContent = fp.evidence_hash || '';
    dom.reproClaimsHash.textContent = fp.claims_hash || '';
    dom.reproToolCallsHash.textContent = fp.tool_calls_hash || '';

    // Populate audit trail
    renderAuditTrail(fp.tool_call_log || []);

    // Populate compare dropdown with history entries
    populateCompareDropdown();

    // Reset verification status
    dom.reproVerifyStatus.textContent = '';
    dom.reproVerifyStatus.className = 'repro-verify-status';

    // Reset comparison results
    dom.reproCompareResults.style.display = 'none';
    dom.reproCompareResults.innerHTML = '';

    dom.reproOverlay.style.display = 'flex';
  }

  function closeReproModal() {
    if (dom.reproOverlay) {
      dom.reproOverlay.style.display = 'none';
    }
  }

  function renderAuditTrail(toolCalls) {
    if (!dom.reproAuditTrail) return;

    if (!toolCalls || toolCalls.length === 0) {
      dom.reproAuditTrail.innerHTML = '<div class="repro-audit-empty">No tool calls recorded</div>';
      return;
    }

    dom.reproAuditTrail.innerHTML = toolCalls.map(function(tc, i) {
      var cached = tc.cached ? '<span class="repro-cached-badge">cached</span>' : '';
      return '<div class="repro-audit-item">' +
        '<span class="repro-audit-num">' + (i + 1) + '</span>' +
        '<div class="repro-audit-details">' +
          '<div class="repro-audit-tool">' + esc(tc.tool_name) + ' ' + cached + '</div>' +
          '<div class="repro-audit-meta">' +
            '<span>' + tc.source_count + ' source' + (tc.source_count !== 1 ? 's' : '') + '</span>' +
            '<span class="repro-audit-sep">|</span>' +
            '<span class="repro-audit-hash" title="' + esc(tc.output_hash) + '">' + esc((tc.output_hash || '').substring(0, 12)) + '...</span>' +
          '</div>' +
        '</div>' +
        '<span class="repro-audit-time">' + esc(tc.timestamp ? new Date(tc.timestamp).toLocaleTimeString() : '') + '</span>' +
      '</div>';
    }).join('');
  }

  function copyFingerprint() {
    var fp = state.currentFingerprint;
    if (!fp) return;

    var text = JSON.stringify(fp, null, 2);
    navigator.clipboard.writeText(text).then(function() {
      showToast('Fingerprint copied to clipboard', 'success');
    }).catch(function() {
      // Fallback: select the hash text
      var range = document.createRange();
      range.selectNodeContents(dom.reproCompositeHash);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      showToast('Select and copy the hash manually', 'info');
    });
  }

  function verifyFingerprint() {
    var fp = state.currentFingerprint;
    if (!fp || !fp.run_id) {
      showToast('No fingerprint to verify', 'error');
      return;
    }

    dom.reproVerifyBtn.disabled = true;
    dom.reproVerifyStatus.textContent = 'Verifying...';
    dom.reproVerifyStatus.className = 'repro-verify-status repro-verify--pending';

    var headers = { 'Content-Type': 'application/json' };
    if (state.token) headers['Authorization'] = 'Bearer ' + state.token;

    fetch('/api/v1/runs/' + fp.run_id + '/verify', {
      method: 'POST',
      headers: headers,
    })
    .then(function(resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(function(result) {
      if (result.passed) {
        dom.reproVerifyStatus.textContent = 'VERIFIED - All hashes match';
        dom.reproVerifyStatus.className = 'repro-verify-status repro-verify--passed';

        // Update badge
        var badge = document.getElementById('repro-badge');
        if (badge) {
          var statusSpan = badge.querySelector('.repro-badge-status');
          if (statusSpan) {
            statusSpan.textContent = 'verified';
            statusSpan.className = 'repro-badge-status repro-badge-status--verified';
          }
        }
      } else {
        var mismatches = result.mismatches || [];
        dom.reproVerifyStatus.textContent = 'FAILED - Mismatches: ' + mismatches.join(', ');
        dom.reproVerifyStatus.className = 'repro-verify-status repro-verify--failed';
      }
    })
    .catch(function(err) {
      dom.reproVerifyStatus.textContent = 'Verification error: ' + err.message;
      dom.reproVerifyStatus.className = 'repro-verify-status repro-verify--failed';
    })
    .finally(function() {
      dom.reproVerifyBtn.disabled = false;
    });
  }

  function populateCompareDropdown() {
    if (!dom.reproCompareSelect) return;
    var currentId = state.currentFingerprint ? state.currentFingerprint.run_id : '';

    // Build options from fingerprint history and run history
    var options = '<option value="">Select a run...</option>';

    // From fingerprint history
    Object.keys(state.fingerprintHistory).forEach(function(rid) {
      if (rid !== currentId) {
        var fpEntry = state.fingerprintHistory[rid];
        var short = (fpEntry.composite_hash || '').substring(0, 8);
        options += '<option value="' + esc(rid) + '">' + esc(short) + '... (' + esc(rid.substring(0, 8)) + ')</option>';
      }
    });

    // From run history (may have fingerprints in their data)
    state.runHistory.forEach(function(entry) {
      var entryFp = entry.data && entry.data.fingerprint;
      if (entryFp && entryFp.run_id && entryFp.run_id !== currentId && !state.fingerprintHistory[entryFp.run_id]) {
        var short = (entryFp.composite_hash || '').substring(0, 8);
        options += '<option value="' + esc(entryFp.run_id) + '">' + esc(short) + '... - ' + esc(entry.query.substring(0, 30)) + '</option>';
      }
    });

    dom.reproCompareSelect.innerHTML = options;
  }

  function compareRuns() {
    var fp = state.currentFingerprint;
    var otherRunId = dom.reproCompareSelect ? dom.reproCompareSelect.value : '';

    if (!fp || !fp.run_id || !otherRunId) {
      showToast('Select a run to compare with', 'error');
      return;
    }

    dom.reproCompareBtn.disabled = true;

    var headers = { 'Content-Type': 'application/json' };
    if (state.token) headers['Authorization'] = 'Bearer ' + state.token;

    fetch('/api/v1/runs/compare', {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ run_id_a: fp.run_id, run_id_b: otherRunId }),
    })
    .then(function(resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(function(data) {
      renderComparisonResults(data.comparison);
    })
    .catch(function(err) {
      showToast('Comparison failed: ' + err.message, 'error');
    })
    .finally(function() {
      dom.reproCompareBtn.disabled = false;
    });
  }

  function renderComparisonResults(comparison) {
    if (!dom.reproCompareResults || !comparison) return;

    var matchIcon = '<span class="repro-match">match</span>';
    var diffIcon = '<span class="repro-diff">differs</span>';

    var evidenceHtml = '';
    if (comparison.overlapping_evidence && comparison.overlapping_evidence.length > 0) {
      evidenceHtml += '<div class="repro-compare-group">' +
        '<span class="repro-compare-group-label repro-overlap-label">Overlapping Evidence (' + comparison.overlapping_evidence.length + ')</span>' +
        comparison.overlapping_evidence.slice(0, 10).map(function(e) { return '<div class="repro-compare-item repro-compare-overlap">' + esc(e) + '</div>'; }).join('') +
        (comparison.overlapping_evidence.length > 10 ? '<div class="repro-compare-more">...and ' + (comparison.overlapping_evidence.length - 10) + ' more</div>' : '') +
      '</div>';
    }
    if (comparison.unique_to_a && comparison.unique_to_a.length > 0) {
      evidenceHtml += '<div class="repro-compare-group">' +
        '<span class="repro-compare-group-label repro-unique-a-label">Unique to Run A (' + comparison.unique_to_a.length + ')</span>' +
        comparison.unique_to_a.slice(0, 5).map(function(e) { return '<div class="repro-compare-item repro-compare-unique-a">' + esc(e) + '</div>'; }).join('') +
        (comparison.unique_to_a.length > 5 ? '<div class="repro-compare-more">...and ' + (comparison.unique_to_a.length - 5) + ' more</div>' : '') +
      '</div>';
    }
    if (comparison.unique_to_b && comparison.unique_to_b.length > 0) {
      evidenceHtml += '<div class="repro-compare-group">' +
        '<span class="repro-compare-group-label repro-unique-b-label">Unique to Run B (' + comparison.unique_to_b.length + ')</span>' +
        comparison.unique_to_b.slice(0, 5).map(function(e) { return '<div class="repro-compare-item repro-compare-unique-b">' + esc(e) + '</div>'; }).join('') +
        (comparison.unique_to_b.length > 5 ? '<div class="repro-compare-more">...and ' + (comparison.unique_to_b.length - 5) + ' more</div>' : '') +
      '</div>';
    }

    var claimsHtml = '';
    if (comparison.claims_in_both && comparison.claims_in_both.length > 0) {
      claimsHtml += '<div class="repro-compare-group">' +
        '<span class="repro-compare-group-label repro-overlap-label">Shared Claims (' + comparison.claims_in_both.length + ')</span>' +
        comparison.claims_in_both.slice(0, 5).map(function(c) { return '<div class="repro-compare-item repro-compare-overlap">' + esc(c.substring(0, 100)) + (c.length > 100 ? '...' : '') + '</div>'; }).join('') +
      '</div>';
    }
    if (comparison.claims_only_a && comparison.claims_only_a.length > 0) {
      claimsHtml += '<div class="repro-compare-group">' +
        '<span class="repro-compare-group-label repro-unique-a-label">Only in Run A (' + comparison.claims_only_a.length + ')</span>' +
        comparison.claims_only_a.slice(0, 5).map(function(c) { return '<div class="repro-compare-item repro-compare-unique-a">' + esc(c.substring(0, 100)) + (c.length > 100 ? '...' : '') + '</div>'; }).join('') +
      '</div>';
    }
    if (comparison.claims_only_b && comparison.claims_only_b.length > 0) {
      claimsHtml += '<div class="repro-compare-group">' +
        '<span class="repro-compare-group-label repro-unique-b-label">Only in Run B (' + comparison.claims_only_b.length + ')</span>' +
        comparison.claims_only_b.slice(0, 5).map(function(c) { return '<div class="repro-compare-item repro-compare-unique-b">' + esc(c.substring(0, 100)) + (c.length > 100 ? '...' : '') + '</div>'; }).join('') +
      '</div>';
    }

    dom.reproCompareResults.innerHTML =
      '<div class="repro-compare-summary">' +
        '<div class="repro-compare-row"><span>Query</span> ' + (comparison.same_query ? matchIcon : diffIcon) + '</div>' +
        '<div class="repro-compare-row"><span>Evidence</span> ' + (comparison.same_evidence ? matchIcon : diffIcon) + '</div>' +
        '<div class="repro-compare-row"><span>Claims</span> ' + (comparison.same_claims ? matchIcon : diffIcon) + '</div>' +
        '<div class="repro-compare-row"><span>Tool Calls</span> ' + (comparison.same_tool_calls ? matchIcon : diffIcon) + '</div>' +
        '<div class="repro-compare-row repro-compare-row--composite"><span>Composite</span> ' + (comparison.composite_match ? matchIcon : diffIcon) + '</div>' +
      '</div>' +
      (evidenceHtml ? '<div class="repro-compare-detail-section"><h4 class="repro-compare-detail-title">Evidence Diff</h4>' + evidenceHtml + '</div>' : '') +
      (claimsHtml ? '<div class="repro-compare-detail-section"><h4 class="repro-compare-detail-title">Claims Diff</h4>' + claimsHtml + '</div>' : '');
    dom.reproCompareResults.style.display = 'block';
  }


  // ─── Statistical Synthesis ──────────────────────────────────────

  let synthesisData = null;
  let synthesisSortField = null;
  let synthesisSortAsc = true;

  function bindSynthesisEvents() {
    const synthBtn = document.getElementById('synthesize-btn');
    if (synthBtn) {
      synthBtn.addEventListener('click', runSynthesis);
    }

    const closeBtn = document.getElementById('synthesis-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        const container = document.getElementById('synthesis-container');
        if (container) container.style.display = 'none';
      });
    }

    // Sortable columns in weights table
    document.querySelectorAll('.synthesis-weights-table th[data-sort-synth]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const field = th.dataset.sortSynth;
        sortSynthesisWeights(field);
      });
    });
  }

  async function runSynthesis() {
    if (!extractionData || extractionData.length === 0) {
      showToast('No extraction data to synthesize. Extract a table first.', 'warning');
      return;
    }

    const btn = document.getElementById('synthesize-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Synthesizing...'; }

    try {
      const resp = await fetch('/api/v1/synthesize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${state.token}`,
        },
        body: JSON.stringify({ studies: extractionData }),
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || 'Synthesis failed');
      }

      synthesisData = await resp.json();

      if (synthesisData.k === 0) {
        showToast('Could not extract effect sizes from any studies. Ensure key findings include numeric results (e.g., "d = 0.5", "OR = 2.1", "p < 0.05").', 'warning');
        return;
      }

      renderSynthesisResults(synthesisData);

      const container = document.getElementById('synthesis-container');
      if (container) {
        container.style.display = '';
        container.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }

      showToast('Synthesis complete: ' + synthesisData.k + ' studies pooled (' + synthesisData.model + ' effects)', 'success');
    } catch (e) {
      showToast('Synthesis failed: ' + (e.message || 'Unknown error'), 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Synthesize'; }
    }
  }

  function renderSynthesisResults(data) {
    // Summary card
    const pooledEl = document.getElementById('synthesis-pooled-effect');
    const ciEl = document.getElementById('synthesis-pooled-ci');
    const modelEl = document.getElementById('synthesis-model');
    const kEl = document.getElementById('synthesis-k');
    const nEl = document.getElementById('synthesis-total-n');
    const pEl = document.getElementById('synthesis-p-value');

    if (pooledEl) pooledEl.textContent = data.pooled_effect.toFixed(3);
    if (ciEl) ciEl.textContent = '95% CI: [' + data.pooled_ci_lower.toFixed(3) + ', ' + data.pooled_ci_upper.toFixed(3) + ']';
    if (modelEl) {
      const modelLabel = data.model === 'random' ? 'Random Effects' :
                         data.model === 'fixed' ? 'Fixed Effects' :
                         data.model === 'single' ? 'Single Study' : data.model;
      modelEl.textContent = modelLabel;
    }
    if (kEl) kEl.textContent = data.k;
    if (nEl) nEl.textContent = data.total_n > 0 ? data.total_n.toLocaleString() : 'N/A';
    if (pEl) {
      const pStr = data.pooled_p < 0.001 ? '< 0.001' : data.pooled_p.toFixed(4);
      const sigClass = data.pooled_p < 0.05 ? 'synthesis-p-sig' : 'synthesis-p-nonsig';
      const sigLabel = data.pooled_p < 0.05 ? ' *' : '';
      pEl.innerHTML = '<span class="' + sigClass + '">' + pStr + sigLabel + '</span>';
    }

    // Heterogeneity
    const i2Badge = document.getElementById('synthesis-i2-badge');
    const i2Fill = document.getElementById('synthesis-i2-fill');
    const i2Value = document.getElementById('synthesis-i2-value');
    const qValue = document.getElementById('synthesis-q-value');
    const qPValue = document.getElementById('synthesis-q-p-value');
    const tau2Value = document.getElementById('synthesis-tau2-value');

    const i2 = data.i_squared;
    let i2Level = 'Low';
    let i2Class = 'i2-low';
    if (i2 > 75) { i2Level = 'High'; i2Class = 'i2-high'; }
    else if (i2 > 25) { i2Level = 'Moderate'; i2Class = 'i2-moderate'; }

    if (i2Badge) {
      i2Badge.textContent = 'I\u00B2 = ' + i2.toFixed(1) + '% (' + i2Level + ')';
      i2Badge.className = 'synthesis-i2-badge ' + i2Class;
    }
    if (i2Fill) {
      i2Fill.style.width = Math.min(100, i2) + '%';
      i2Fill.className = 'synthesis-i2-gauge-fill ' + i2Class;
    }
    if (i2Value) i2Value.textContent = i2.toFixed(1) + '%';
    if (qValue) qValue.textContent = data.q_statistic.toFixed(2);
    if (qPValue) qPValue.textContent = data.q_p_value < 0.001 ? '< 0.001' : data.q_p_value.toFixed(4);
    if (tau2Value) tau2Value.textContent = data.tau_squared.toFixed(4);

    // Study weights table
    renderSynthesisWeightsTable(data);

    // Forest plot
    renderForestPlot(data);
  }

  function renderSynthesisWeightsTable(data) {
    const tbody = document.getElementById('synthesis-weights-body');
    if (!tbody || !data.studies) return;

    let maxWeight = 1;
    for (let si = 0; si < data.studies.length; si++) {
      if (data.studies[si].weight > maxWeight) maxWeight = data.studies[si].weight;
    }

    tbody.innerHTML = data.studies.map(function(s) {
      const barWidth = Math.round((s.weight / maxWeight) * 100);
      return '<tr>' +
        '<td title="' + esc(s.study_label) + '">' + esc(s.study_label) + '</td>' +
        '<td>' + s.effect_size.toFixed(3) + '</td>' +
        '<td>[' + s.ci_lower.toFixed(3) + ', ' + s.ci_upper.toFixed(3) + ']</td>' +
        '<td><div class="synthesis-weight-bar-cell">' +
          '<div class="synthesis-weight-bar"><div class="synthesis-weight-bar-fill" style="width:' + barWidth + '%"></div></div>' +
          '<span>' + s.weight.toFixed(1) + '%</span>' +
        '</div></td>' +
        '<td>' + (s.n > 0 ? s.n.toLocaleString() : 'N/A') + '</td>' +
      '</tr>';
    }).join('');
  }

  function sortSynthesisWeights(field) {
    if (!synthesisData || !synthesisData.studies) return;

    if (synthesisSortField === field) {
      synthesisSortAsc = !synthesisSortAsc;
    } else {
      synthesisSortField = field;
      synthesisSortAsc = true;
    }

    const fieldMap = {
      'label': function(s) { return (s.study_label || '').toLowerCase(); },
      'effect': function(s) { return s.effect_size; },
      'ci': function(s) { return s.ci_lower; },
      'weight': function(s) { return s.weight; },
      'n': function(s) { return s.n; }
    };

    const getter = fieldMap[field] || function() { return 0; };
    synthesisData.studies.sort(function(a, b) {
      const va = getter(a);
      const vb = getter(b);
      if (typeof va === 'string') {
        return synthesisSortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      return synthesisSortAsc ? va - vb : vb - va;
    });

    renderSynthesisWeightsTable(synthesisData);

    // Update sort indicators
    document.querySelectorAll('.synthesis-weights-table th[data-sort-synth]').forEach(function(th) {
      th.classList.remove('sort-asc', 'sort-desc');
      if (th.dataset.sortSynth === field) {
        th.classList.add(synthesisSortAsc ? 'sort-asc' : 'sort-desc');
      }
    });
  }

  // ─── Forest Plot (Canvas) ──────────────────────────────────────

  function renderForestPlot(data) {
    const canvas = document.getElementById('forest-plot-canvas');
    if (!canvas || !data.forest_plot_data || data.forest_plot_data.length === 0) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    // Layout constants
    const labelWidth = 180;
    const statsWidth = 140;
    const rowHeight = 28;
    const padTop = 40, padBottom = 30, padLeft = 12, padRight = 12;
    const plotStudies = data.forest_plot_data.filter(function(d) { return d.type === 'study'; });
    const plotSummary = data.forest_plot_data.filter(function(d) { return d.type === 'summary'; })[0] || null;
    const totalRows = plotStudies.length + (plotSummary ? 2 : 0);

    // Canvas sizing
    const containerWidth = canvas.parentElement ? canvas.parentElement.clientWidth - 26 : 760;
    const W = Math.max(600, containerWidth);
    const H = padTop + totalRows * rowHeight + padBottom;

    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Clear
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, W, H);

    // Plot area bounds
    const plotLeft = padLeft + labelWidth;
    const plotRight = W - padRight - statsWidth;
    const plotWidth = plotRight - plotLeft;

    // Determine x-axis scale
    const allEffects = data.forest_plot_data;
    let minX = Infinity, maxX = -Infinity;
    for (let ai = 0; ai < allEffects.length; ai++) {
      if (allEffects[ai].ci_lower < minX) minX = allEffects[ai].ci_lower;
      if (allEffects[ai].ci_upper > maxX) maxX = allEffects[ai].ci_upper;
    }

    // Ensure null line is in range
    const nullVal = 0;
    minX = Math.min(minX, nullVal - 0.1);
    maxX = Math.max(maxX, nullVal + 0.1);

    // Add margin
    const xRange = maxX - minX;
    minX -= xRange * 0.08;
    maxX += xRange * 0.08;

    function xScale(val) {
      return plotLeft + ((val - minX) / (maxX - minX)) * plotWidth;
    }

    // --- Draw null effect line ---
    const nullX = xScale(nullVal);
    ctx.strokeStyle = '#cccccc';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(nullX, padTop - 10);
    ctx.lineTo(nullX, H - padBottom + 5);
    ctx.stroke();
    ctx.setLineDash([]);

    // --- Draw header labels ---
    ctx.fillStyle = '#999999';
    ctx.font = '600 9px "Space Mono", monospace';
    ctx.textAlign = 'left';
    ctx.fillText('STUDY', padLeft, padTop - 18);
    ctx.textAlign = 'center';
    ctx.fillText('EFFECT SIZE', (plotLeft + plotRight) / 2, padTop - 18);
    ctx.textAlign = 'left';
    ctx.fillText('ES [95% CI]', plotRight + 8, padTop - 18);
    ctx.fillText('WEIGHT', plotRight + 85, padTop - 18);

    // --- Draw x-axis ticks ---
    const axisY = H - padBottom + 5;
    const nTicks = 5;
    for (let ti = 0; ti <= nTicks; ti++) {
      const val = minX + (maxX - minX) * ti / nTicks;
      const tx = xScale(val);
      ctx.fillStyle = '#eeeeee';
      ctx.fillRect(tx, padTop - 5, 1, axisY - padTop + 10);
      ctx.fillStyle = '#999999';
      ctx.font = '400 9px "Space Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText(val.toFixed(2), tx, axisY + 12);
    }

    // Horizontal axis line
    ctx.strokeStyle = '#dddddd';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(plotLeft, axisY);
    ctx.lineTo(plotRight, axisY);
    ctx.stroke();

    // --- Draw study rows ---
    let maxWeight = 1;
    for (let mi = 0; mi < plotStudies.length; mi++) {
      if (plotStudies[mi].weight_pct > maxWeight) maxWeight = plotStudies[mi].weight_pct;
    }

    for (let i = 0; i < plotStudies.length; i++) {
      const study = plotStudies[i];
      const y = padTop + i * rowHeight + rowHeight / 2;

      // Alternating row background
      if (i % 2 === 0) {
        ctx.fillStyle = '#fafafa';
        ctx.fillRect(0, y - rowHeight / 2, W, rowHeight);
      }

      // Study label
      ctx.fillStyle = '#333333';
      ctx.font = '400 11px "Inter", sans-serif';
      ctx.textAlign = 'left';
      const label = study.label.length > 24 ? study.label.substring(0, 22) + '...' : study.label;
      ctx.fillText(label, padLeft, y + 4);

      // CI line
      const ciL = xScale(study.ci_lower);
      const ciR = xScale(study.ci_upper);
      ctx.strokeStyle = '#555555';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(Math.max(plotLeft, ciL), y);
      ctx.lineTo(Math.min(plotRight, ciR), y);
      ctx.stroke();

      // CI caps
      ctx.lineWidth = 1;
      if (ciL >= plotLeft) {
        ctx.beginPath();
        ctx.moveTo(ciL, y - 4);
        ctx.lineTo(ciL, y + 4);
        ctx.stroke();
      }
      if (ciR <= plotRight) {
        ctx.beginPath();
        ctx.moveTo(ciR, y - 4);
        ctx.lineTo(ciR, y + 4);
        ctx.stroke();
      }

      // Point estimate (square, sized by weight)
      const effectX = xScale(study.effect);
      const sqSize = Math.max(4, Math.min(12, 4 + (study.weight_pct / maxWeight) * 8));
      ctx.fillStyle = '#111111';
      ctx.fillRect(effectX - sqSize / 2, y - sqSize / 2, sqSize, sqSize);

      // Right-side stats
      ctx.fillStyle = '#555555';
      ctx.font = '400 10px "Space Mono", monospace';
      ctx.textAlign = 'left';
      const esText = study.effect.toFixed(2) + ' [' + study.ci_lower.toFixed(2) + ', ' + study.ci_upper.toFixed(2) + ']';
      ctx.fillText(esText, plotRight + 8, y + 4);
      ctx.fillText(study.weight_pct.toFixed(1) + '%', plotRight + 93, y + 4);
    }

    // --- Draw summary diamond ---
    if (plotSummary) {
      const gapRow = plotStudies.length;
      const summaryY = padTop + (gapRow + 1) * rowHeight + rowHeight / 2;

      // Separator line
      ctx.strokeStyle = '#dddddd';
      ctx.lineWidth = 1;
      const sepY = padTop + gapRow * rowHeight + rowHeight / 2;
      ctx.beginPath();
      ctx.moveTo(padLeft, sepY);
      ctx.lineTo(W - padRight, sepY);
      ctx.stroke();

      // Summary label
      ctx.fillStyle = '#111111';
      ctx.font = '700 11px "Inter", sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(plotSummary.label, padLeft, summaryY + 4);

      // Diamond
      const diamondCx = xScale(plotSummary.effect);
      const diamondL = xScale(plotSummary.ci_lower);
      const diamondR = xScale(plotSummary.ci_upper);
      const diamondH = 10;

      ctx.fillStyle = '#111111';
      ctx.beginPath();
      ctx.moveTo(diamondCx, summaryY - diamondH);
      ctx.lineTo(Math.min(plotRight, diamondR), summaryY);
      ctx.lineTo(diamondCx, summaryY + diamondH);
      ctx.lineTo(Math.max(plotLeft, diamondL), summaryY);
      ctx.closePath();
      ctx.fill();

      // Summary stats on right
      ctx.fillStyle = '#111111';
      ctx.font = '700 10px "Space Mono", monospace';
      ctx.textAlign = 'left';
      const summaryText = plotSummary.effect.toFixed(2) + ' [' + plotSummary.ci_lower.toFixed(2) + ', ' + plotSummary.ci_upper.toFixed(2) + ']';
      ctx.fillText(summaryText, plotRight + 8, summaryY + 4);
    }

    // --- Null effect label ---
    ctx.fillStyle = '#bbbbbb';
    ctx.font = '400 9px "Space Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText('null', nullX, padTop - 6);
  }

  // ═══════════════════════════════════════════════════════════════
  // IMPORT LIBRARY (.bib / .ris)
  // ═══════════════════════════════════════════════════════════════

  function bindImportLibraryEvents() {
    if (dom.importLibraryBtn) {
      dom.importLibraryBtn.addEventListener('click', () => {
        if (dom.bibFileInput) dom.bibFileInput.click();
      });
    }

    if (dom.bibFileInput) {
      dom.bibFileInput.addEventListener('change', async (e) => {
        if (e.target.files.length === 0) return;
        const file = e.target.files[0];
        e.target.value = '';
        await importBibliography(file);
      });
    }
  }

  async function importBibliography(file) {
    if (!state.token) {
      showAuthModal();
      showToast('Please sign in to import.', 'warning');
      return;
    }

    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'bib' && ext !== 'ris') {
      showToast('Unsupported file type. Please use .bib or .ris files.', 'warning');
      return;
    }

    dom.importLibraryBtn.disabled = true;
    dom.importLibraryBtn.innerHTML = '<span class="spinner"></span> Importing...';

    try {
      const formData = new FormData();
      formData.append('file', file);

      let url = '/api/v1/import/bibliography';
      if (state.currentReviewId) {
        url += '?review_id=' + encodeURIComponent(state.currentReviewId);
      }

      const resp = await authFetch(url, {
        method: 'POST',
        body: formData,
      });

      const data = await resp.json();

      if (resp.ok) {
        const imported = data.imported || data.papers_imported || 0;
        const duplicates = data.duplicates_skipped || data.duplicates || 0;
        const format = data.format_detected || ext.toUpperCase();

        // Show result inline
        let resultEl = document.getElementById('import-result');
        if (!resultEl) {
          resultEl = document.createElement('div');
          resultEl.id = 'import-result';
          resultEl.className = 'import-result';
          dom.importLibraryBtn.parentElement.appendChild(resultEl);
        }
        resultEl.innerHTML =
          '<span class="import-result-stat">' + imported + '</span> papers imported, ' +
          '<span class="import-result-stat">' + duplicates + '</span> duplicates skipped. ' +
          'Format: <span class="import-result-stat">' + esc(format) + '</span>';

        showToast('Bibliography imported: ' + imported + ' papers.', 'success');
      } else {
        showToast(data.detail || 'Import failed.', 'error');
      }
    } catch (err) {
      showToast('Failed to import bibliography.', 'error');
    } finally {
      dom.importLibraryBtn.disabled = false;
      dom.importLibraryBtn.innerHTML =
        '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 1v10M4 7l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12v2a1 1 0 001 1h10a1 1 0 001-1v-2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg> Import Library (.bib / .ris)';
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // PRISMA FLOW DIAGRAM DOWNLOAD
  // ═══════════════════════════════════════════════════════════════

  function bindPrismaDownloadEvents() {
    if (dom.prismaDownloadBtn) {
      dom.prismaDownloadBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const menu = dom.prismaDownloadMenu;
        if (menu) {
          menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
        }
      });
    }

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
      if (dom.prismaDownloadMenu && !e.target.closest('.prisma-download-btn') && !e.target.closest('#prisma-download-menu')) {
        dom.prismaDownloadMenu.style.display = 'none';
      }
    });

    // Dropdown items
    if (dom.prismaDownloadMenu) {
      dom.prismaDownloadMenu.addEventListener('click', (e) => {
        const item = e.target.closest('[data-prisma-format]');
        if (!item) return;
        const format = item.dataset.prismaFormat;
        dom.prismaDownloadMenu.style.display = 'none';

        if (format === 'svg') downloadPrismaDiagram('svg');
        else if (format === 'png') downloadPrismaDiagram('png');
        else if (format === 'preview') previewPrismaDiagram();
      });
    }

    // Preview modal close
    if (dom.prismaPreviewClose) {
      dom.prismaPreviewClose.addEventListener('click', () => {
        if (dom.prismaPreviewOverlay) dom.prismaPreviewOverlay.style.display = 'none';
      });
    }
    if (dom.prismaPreviewOverlay) {
      dom.prismaPreviewOverlay.addEventListener('click', (e) => {
        if (e.target === dom.prismaPreviewOverlay) dom.prismaPreviewOverlay.style.display = 'none';
      });
    }
  }

  async function downloadPrismaDiagram(format) {
    if (!state.currentReviewId) {
      showToast('No active review.', 'warning');
      return;
    }

    try {
      const url = '/api/v1/reviews/' + encodeURIComponent(state.currentReviewId) + '/prisma/' + format;
      const resp = await authFetch(url);

      if (resp.status === 501) {
        showToast('PNG export requires cairosvg to be installed on the server.', 'warning');
        return;
      }

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        showToast(errData.detail || 'Failed to download PRISMA diagram.', 'error');
        return;
      }

      const blob = await resp.blob();
      const downloadUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = 'prisma_flow.' + format;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(downloadUrl);
      showToast('PRISMA diagram downloaded as ' + format.toUpperCase() + '.', 'success');
    } catch (err) {
      showToast('Failed to download PRISMA diagram.', 'error');
    }
  }

  async function previewPrismaDiagram() {
    if (!state.currentReviewId) {
      showToast('No active review.', 'warning');
      return;
    }

    if (dom.prismaPreviewOverlay) dom.prismaPreviewOverlay.style.display = 'flex';
    if (dom.prismaPreviewContent) {
      dom.prismaPreviewContent.innerHTML = '<div class="results-placeholder"><span class="spinner"></span><p>Loading diagram...</p></div>';
    }

    try {
      const url = '/api/v1/reviews/' + encodeURIComponent(state.currentReviewId) + '/prisma/svg';
      const resp = await authFetch(url);

      if (!resp.ok) {
        dom.prismaPreviewContent.innerHTML = '<div class="results-placeholder"><p>Failed to load PRISMA diagram.</p></div>';
        return;
      }

      const svgText = await resp.text();
      dom.prismaPreviewContent.innerHTML = svgText;
    } catch (err) {
      if (dom.prismaPreviewContent) {
        dom.prismaPreviewContent.innerHTML = '<div class="results-placeholder"><p>Error loading diagram.</p></div>';
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // CSL-JSON & ZOTERO EXPORT
  // ═══════════════════════════════════════════════════════════════

  async function exportCSLJSON() {
    if (!state.currentResult || !state.currentResult.claims) {
      showToast('No results to export.', 'warning');
      return;
    }

    try {
      const resp = await authFetch('/api/v1/export/csl-json', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claims: state.currentResult.claims }),
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        showToast(errData.detail || 'CSL-JSON export failed.', 'error');
        return;
      }

      const blob = await resp.blob();
      const downloadUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = 'evidentia_references.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(downloadUrl);
      showToast('Exported citations as CSL-JSON.', 'success');
    } catch (err) {
      showToast('CSL-JSON export failed.', 'error');
    }
  }

  function bindZoteroExportEvents() {
    if (dom.zoteroExportBtn) {
      dom.zoteroExportBtn.addEventListener('click', () => {
        if (!state.currentResult || !state.currentResult.claims) {
          showToast('No results to export.', 'warning');
          return;
        }
        if (dom.zoteroExportOverlay) dom.zoteroExportOverlay.style.display = 'flex';
      });
    }

    if (dom.zoteroExportClose) {
      dom.zoteroExportClose.addEventListener('click', () => {
        if (dom.zoteroExportOverlay) dom.zoteroExportOverlay.style.display = 'none';
      });
    }
    if (dom.zoteroExportOverlay) {
      dom.zoteroExportOverlay.addEventListener('click', (e) => {
        if (e.target === dom.zoteroExportOverlay) dom.zoteroExportOverlay.style.display = 'none';
      });
    }

    if (dom.zoteroExportForm) {
      dom.zoteroExportForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await runZoteroExport();
      });
    }
  }

  async function runZoteroExport() {
    const apiKey = document.getElementById('zotero-api-key').value.trim();
    const userId = document.getElementById('zotero-user-id').value.trim();

    if (!apiKey || !userId) {
      if (dom.zoteroExportError) {
        dom.zoteroExportError.textContent = 'Both API key and User ID are required.';
        dom.zoteroExportError.style.display = 'block';
      }
      return;
    }

    if (dom.zoteroExportError) dom.zoteroExportError.style.display = 'none';
    if (dom.zoteroExportProgress) dom.zoteroExportProgress.style.display = 'flex';
    if (dom.zoteroExportSubmit) dom.zoteroExportSubmit.disabled = true;

    try {
      const resp = await authFetch('/api/v1/export/zotero', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          claims: state.currentResult.claims,
          zotero_api_key: apiKey,
          zotero_user_id: userId,
        }),
      });

      const data = await resp.json();

      if (resp.ok) {
        const created = data.items_created || data.count || 0;
        if (dom.zoteroExportStatus) dom.zoteroExportStatus.textContent = 'Done! ' + created + ' items created in Zotero.';
        showToast('Exported ' + created + ' items to Zotero.', 'success');
        setTimeout(() => {
          if (dom.zoteroExportOverlay) dom.zoteroExportOverlay.style.display = 'none';
          if (dom.zoteroExportProgress) dom.zoteroExportProgress.style.display = 'none';
        }, 2000);
      } else {
        if (dom.zoteroExportError) {
          dom.zoteroExportError.textContent = data.detail || 'Zotero export failed.';
          dom.zoteroExportError.style.display = 'block';
        }
        if (dom.zoteroExportProgress) dom.zoteroExportProgress.style.display = 'none';
      }
    } catch (err) {
      if (dom.zoteroExportError) {
        dom.zoteroExportError.textContent = 'Network error during Zotero export.';
        dom.zoteroExportError.style.display = 'block';
      }
      if (dom.zoteroExportProgress) dom.zoteroExportProgress.style.display = 'none';
    } finally {
      if (dom.zoteroExportSubmit) dom.zoteroExportSubmit.disabled = false;
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // VALIDATION DASHBOARD
  // ═══════════════════════════════════════════════════════════════

  function bindValidationEvents() {
    if (dom.validateReviewBtn) {
      dom.validateReviewBtn.addEventListener('click', () => {
        if (!state.currentReviewId) {
          showToast('No active review to validate.', 'warning');
          return;
        }
        // Reset modal state
        if (dom.validationConfig) dom.validationConfig.style.display = 'block';
        if (dom.validationResults) dom.validationResults.style.display = 'none';
        if (dom.validationError) dom.validationError.style.display = 'none';
        if (dom.validationOverlay) dom.validationOverlay.style.display = 'flex';
      });
    }

    if (dom.validationClose) {
      dom.validationClose.addEventListener('click', () => {
        if (dom.validationOverlay) dom.validationOverlay.style.display = 'none';
      });
    }
    if (dom.validationOverlay) {
      dom.validationOverlay.addEventListener('click', (e) => {
        if (e.target === dom.validationOverlay) dom.validationOverlay.style.display = 'none';
      });
    }

    // Toggle custom upload visibility
    $$('input[name="gold-standard"]').forEach(radio => {
      radio.addEventListener('change', () => {
        if (dom.validationCustomUpload) {
          dom.validationCustomUpload.style.display = radio.value === 'custom' && radio.checked ? 'block' : 'none';
        }
      });
    });

    // Custom BibTeX file
    if (dom.validationBibInput) {
      dom.validationBibInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
          const reader = new FileReader();
          reader.onload = (ev) => {
            state.customGoldBib = ev.target.result;
          };
          reader.readAsText(e.target.files[0]);
        }
      });
    }

    if (dom.validationRunBtn) {
      dom.validationRunBtn.addEventListener('click', runValidation);
    }
  }

  async function runValidation() {
    if (!state.currentReviewId) {
      showToast('No active review.', 'warning');
      return;
    }

    const gsType = document.querySelector('input[name="gold-standard"]:checked')?.value || 'sample';

    if (gsType === 'custom' && !state.customGoldBib) {
      if (dom.validationError) {
        dom.validationError.textContent = 'Please upload a BibTeX file for the custom gold standard.';
        dom.validationError.style.display = 'block';
      }
      return;
    }

    if (dom.validationError) dom.validationError.style.display = 'none';
    dom.validationRunBtn.disabled = true;
    dom.validationRunBtn.textContent = 'Validating...';

    try {
      const body = {};
      if (gsType === 'sample') {
        body.gold_standard = 'sample';
      } else {
        body.gold_standard = 'custom';
        body.custom_gold = state.customGoldBib;
      }

      const resp = await authFetch('/api/v1/validate/review/' + encodeURIComponent(state.currentReviewId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await resp.json();

      if (resp.ok) {
        displayValidationResults(data);
        state.reviewValidated = true;
        updateReproducibleBadge();
        showToast('Validation complete.', 'success');
      } else {
        if (dom.validationError) {
          dom.validationError.textContent = data.detail || 'Validation failed.';
          dom.validationError.style.display = 'block';
        }
      }
    } catch (err) {
      if (dom.validationError) {
        dom.validationError.textContent = 'Network error during validation.';
        dom.validationError.style.display = 'block';
      }
    } finally {
      dom.validationRunBtn.disabled = false;
      dom.validationRunBtn.textContent = 'Run Validation';
    }
  }

  function displayValidationResults(data) {
    // Show results, hide config
    if (dom.validationResults) dom.validationResults.style.display = 'block';

    // Confusion matrix
    const cm = data.confusion_matrix || data;
    const tp = cm.tp || cm.true_positives || 0;
    const fp = cm.fp || cm.false_positives || 0;
    const fn = cm.fn || cm.false_negatives || 0;
    const tn = cm.tn || cm.true_negatives || 0;

    const tpEl = document.getElementById('val-tp');
    const fpEl = document.getElementById('val-fp');
    const fnEl = document.getElementById('val-fn');
    const tnEl = document.getElementById('val-tn');
    if (tpEl) tpEl.textContent = tp;
    if (fpEl) fpEl.textContent = fp;
    if (fnEl) fnEl.textContent = fn;
    if (tnEl) tnEl.textContent = tn;

    // Metrics
    const metrics = data.metrics || data;
    const metricKeys = ['sensitivity', 'specificity', 'precision', 'f1', 'accuracy'];
    const metricAliases = {
      sensitivity: metrics.sensitivity || metrics.recall || 0,
      specificity: metrics.specificity || 0,
      precision: metrics.precision || 0,
      f1: metrics.f1 || metrics.f1_score || 0,
      accuracy: metrics.accuracy || 0,
    };

    metricKeys.forEach(key => {
      const el = document.getElementById('metric-' + key);
      if (!el) return;
      const val = metricAliases[key];
      const valEl = el.querySelector('.metric-value');
      if (valEl) valEl.textContent = typeof val === 'number' ? val.toFixed(3) : '--';

      // Color coding
      el.className = 'metric-card';
      if (typeof val === 'number') {
        if (val > 0.8) el.classList.add('metric-card--green');
        else if (val > 0.5) el.classList.add('metric-card--yellow');
        else el.classList.add('metric-card--red');
      }
    });

    // Paper lists
    const matched = data.matched || data.true_positive_papers || [];
    const missed = data.missed || data.false_negative_papers || [];
    const extra = data.extra || data.false_positive_papers || [];

    renderValidationPaperList('val-matched-list', matched, 'matched');
    renderValidationPaperList('val-missed-list', missed, 'missed');
    renderValidationPaperList('val-extra-list', extra, 'extra');
  }

  function renderValidationPaperList(containerId, papers, type) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!papers || papers.length === 0) {
      container.innerHTML = '<div class="validation-paper-item">None</div>';
      return;
    }

    container.innerHTML = papers.map(p => {
      const title = typeof p === 'string' ? p : (p.title || p.name || 'Untitled');
      return '<div class="validation-paper-item validation-paper-item--' + esc(type) + '">' + esc(title) + '</div>';
    }).join('');
  }

  // ═══════════════════════════════════════════════════════════════
  // REPRODUCIBLE & VALIDATED BADGE
  // ═══════════════════════════════════════════════════════════════

  function updateReproducibleBadge() {
    if (!dom.reproducibleBadge) return;

    // Show badge when review is complete + validated + has fingerprint/hash
    const hasReviewComplete = dom.reviewWorkspace && dom.reviewWorkspace.style.display !== 'none';
    const hasFingerprint = dom.reviewRunHash && dom.reviewRunHash.style.display !== 'none' && dom.reviewRunHash.textContent;
    const hasValidation = state.reviewValidated;

    if (hasReviewComplete && hasFingerprint && hasValidation) {
      dom.reproducibleBadge.style.display = 'inline-flex';
    } else {
      dom.reproducibleBadge.style.display = 'none';
    }
  }


  // ═══════════════════════════════════════════════════════════════
  // WRITING WORKSPACE
  // ═══════════════════════════════════════════════════════════════

  function bindWritingEvents() {
    if (dom.newDocBtn) dom.newDocBtn.addEventListener('click', showTemplatePicker);
    if (dom.templatePickerClose) dom.templatePickerClose.addEventListener('click', hideTemplatePicker);
    if (dom.writingConvertBtn) dom.writingConvertBtn.addEventListener('click', convertToLatex);
    if (dom.writingExportBtn) dom.writingExportBtn.addEventListener('click', exportDocument);
    if (dom.writingSaveBtn) dom.writingSaveBtn.addEventListener('click', saveDocument);
    if (dom.writingCopyLatex) dom.writingCopyLatex.addEventListener('click', copyLatex);

    // Mode pills
    if (dom.writingModePlain) {
      dom.writingModePlain.addEventListener('click', () => toggleWritingMode('plain'));
    }
    if (dom.writingModeLatex) {
      dom.writingModeLatex.addEventListener('click', () => toggleWritingMode('latex'));
    }

    // Layout toggle
    if (dom.writingLayoutSplit) {
      dom.writingLayoutSplit.addEventListener('click', () => toggleWritingLayout('split'));
    }
    if (dom.writingLayoutFull) {
      dom.writingLayoutFull.addEventListener('click', () => toggleWritingLayout('full'));
    }

    // Auto-convert toggle
    if (dom.writingAutoConvert) {
      dom.writingAutoConvert.addEventListener('change', (e) => {
        state.writingAutoConvert = e.target.checked;
      });
    }

    // Textarea input — word count, auto-save, auto-convert
    if (dom.writingInput) {
      dom.writingInput.addEventListener('input', () => {
        updateWordCount();
        // Auto-save
        state.writingDirty = true;
        if (dom.writingStatus) dom.writingStatus.textContent = 'Unsaved changes';
        clearTimeout(state.writingAutoSaveTimer);
        if (state.writingDocId) {
          state.writingAutoSaveTimer = setTimeout(() => saveDocument(), 3000);
        }
        // Auto-convert
        if (state.writingAutoConvert && state.writingMode === 'plain') {
          clearTimeout(state.writingConvertTimer);
          state.writingConvertTimer = setTimeout(() => convertToLatex(), 3000);
        }
      });
    }

    // Title change triggers dirty
    if (dom.writingTitle) {
      dom.writingTitle.addEventListener('input', () => {
        state.writingDirty = true;
        if (dom.writingStatus) dom.writingStatus.textContent = 'Unsaved changes';
        clearTimeout(state.writingAutoSaveTimer);
        if (state.writingDocId) {
          state.writingAutoSaveTimer = setTimeout(() => saveDocument(), 3000);
        }
      });
    }
  }

  async function loadDocuments() {
    if (!state.token) return;
    try {
      const resp = await authFetch('/api/v1/writing/documents');
      if (!resp.ok) return;
      state.documents = await resp.json();
      renderDocumentList();
      renderSidebarDocuments();
    } catch (e) {
      // silent fallback
    }
  }

  function renderDocumentList() {
    if (!dom.writingDocList) return;
    if (state.documents.length === 0) {
      dom.writingDocList.innerHTML = '<div class="writing-doc-empty">No documents yet. Create one to get started.</div>';
      return;
    }
    dom.writingDocList.innerHTML = state.documents.map((doc) => {
      const date = new Date(doc.updated_at).toLocaleDateString();
      return `<div class="writing-doc-item" data-doc-id="${doc.id}">
        <div class="writing-doc-item-title">${escapeHtml(doc.title)}</div>
        <div class="writing-doc-item-meta">${doc.mode === 'latex' ? 'LaTeX' : 'Plain English'} &middot; ${date}</div>
        <button class="btn btn-ghost btn-xs writing-doc-delete" data-doc-id="${doc.id}" title="Delete">&times;</button>
      </div>`;
    }).join('');

    // Bind click events
    dom.writingDocList.querySelectorAll('.writing-doc-item').forEach((item) => {
      item.addEventListener('click', (e) => {
        if (e.target.closest('.writing-doc-delete')) return;
        openDocument(item.dataset.docId);
      });
    });
    dom.writingDocList.querySelectorAll('.writing-doc-delete').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteDocument(btn.dataset.docId);
      });
    });
  }

  function renderSidebarDocuments() {
    if (!dom.documentList) return;
    if (state.documents.length === 0) {
      dom.documentList.innerHTML = '<li class="pdf-empty">No documents</li>';
      return;
    }
    dom.documentList.innerHTML = state.documents.map((doc) =>
      `<li class="sidebar-doc-item" data-doc-id="${doc.id}">${escapeHtml(doc.title)}</li>`
    ).join('');
    dom.documentList.querySelectorAll('.sidebar-doc-item').forEach((item) => {
      item.addEventListener('click', () => openDocument(item.dataset.docId));
    });
  }

  async function showTemplatePicker() {
    if (!state.token) { showAuthModal(); return; }
    if (!dom.templatePicker || !dom.templateGrid) return;

    // Fetch templates
    try {
      const resp = await authFetch('/api/v1/writing/templates');
      if (!resp.ok) {
        // Fallback — just create a blank doc
        createDocument(null);
        return;
      }
      const templates = await resp.json();

      // Group by category
      const groups = {};
      templates.forEach((t) => {
        if (!groups[t.category]) groups[t.category] = [];
        groups[t.category].push(t);
      });

      let html = '';
      for (const [category, tmpls] of Object.entries(groups)) {
        html += `<div class="template-category-label">${escapeHtml(category)}</div>`;
        html += '<div class="template-category-grid">';
        tmpls.forEach((t) => {
          html += `<div class="template-card" data-template-id="${t.id}">
            <div class="template-card-name">${escapeHtml(t.name)}</div>
            <div class="template-card-desc">${escapeHtml(t.description)}</div>
          </div>`;
        });
        html += '</div>';
      }

      // Add "Blank Document" at the start
      html = `<div class="template-category-grid">
        <div class="template-card template-card--blank" data-template-id="">
          <div class="template-card-name">Blank Document</div>
          <div class="template-card-desc">Start from scratch with no template</div>
        </div>
      </div>` + html;

      dom.templateGrid.innerHTML = html;

      // Bind click events on cards
      dom.templateGrid.querySelectorAll('.template-card').forEach((card) => {
        card.addEventListener('click', () => {
          const templateId = card.dataset.templateId || null;
          hideTemplatePicker();
          createDocument(templateId);
        });
      });

      // Show the picker, hide doc list
      if (dom.writingDocList) dom.writingDocList.style.display = 'none';
      dom.templatePicker.style.display = 'block';
    } catch (e) {
      createDocument(null);
    }
  }

  function hideTemplatePicker() {
    if (dom.templatePicker) dom.templatePicker.style.display = 'none';
    if (dom.writingDocList) dom.writingDocList.style.display = '';
  }

  async function createDocument(templateId) {
    if (!state.token) { showAuthModal(); return; }
    try {
      const body = { title: 'Untitled' };
      if (templateId) body.template_id = templateId;

      const resp = await authFetch('/api/v1/writing/documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) { showToast('Failed to create document.', 'error'); return; }
      const doc = await resp.json();
      state.documents.unshift(doc);
      renderDocumentList();
      renderSidebarDocuments();
      openDocument(doc.id);
    } catch (e) {
      showToast('Failed to create document.', 'error');
    }
  }

  async function openDocument(docId) {
    if (!state.token) return;
    try {
      const resp = await authFetch('/api/v1/writing/documents/' + encodeURIComponent(docId));
      if (!resp.ok) { showToast('Document not found.', 'error'); return; }
      const doc = await resp.json();
      state.writingDocId = doc.id;
      state.writingMode = doc.mode || 'plain';
      state.writingDirty = false;

      // Populate editor
      if (dom.writingTitle) dom.writingTitle.value = doc.title;
      if (dom.writingInput) {
        dom.writingInput.value = state.writingMode === 'plain' ? doc.plain_content : doc.latex_content;
      }
      if (dom.writingLatexOutput) {
        dom.writingLatexOutput.querySelector('code').textContent = doc.latex_content || '';
      }

      // Update UI
      toggleWritingMode(state.writingMode);
      updateWordCount();
      if (dom.writingStatus) dom.writingStatus.textContent = 'Ready';

      // Show workspace, hide landing with animation
      const landing = $('#landing');
      if (landing) landing.style.display = 'none';
      if (dom.writingWorkspace) {
        dom.writingWorkspace.style.display = 'flex';
        dom.writingWorkspace.classList.add('view-enter');
        dom.writingWorkspace.addEventListener('animationend', function onDone() {
          dom.writingWorkspace.removeEventListener('animationend', onDone);
          dom.writingWorkspace.classList.remove('view-enter');
        });
      }
      // Hide other workspaces
      const ws = $('#workspace');
      if (ws) ws.style.display = 'none';
      const rw = $('#review-workspace');
      if (rw) rw.style.display = 'none';
    } catch (e) {
      showToast('Failed to open document.', 'error');
    }
  }

  async function saveDocument() {
    if (!state.writingDocId || !state.token) return;
    const body = {
      title: dom.writingTitle ? dom.writingTitle.value : 'Untitled',
      mode: state.writingMode,
    };
    if (state.writingMode === 'plain') {
      body.plain_content = dom.writingInput ? dom.writingInput.value : '';
    } else {
      body.latex_content = dom.writingInput ? dom.writingInput.value : '';
    }

    try {
      if (dom.writingStatus) dom.writingStatus.textContent = 'Saving...';
      const resp = await authFetch('/api/v1/writing/documents/' + encodeURIComponent(state.writingDocId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (resp.ok) {
        state.writingDirty = false;
        if (dom.writingStatus) dom.writingStatus.textContent = 'Saved';
        const now = new Date().toLocaleTimeString();
        if (dom.writingAutosaveStatus) dom.writingAutosaveStatus.textContent = 'Last saved ' + now;
      } else {
        if (dom.writingStatus) dom.writingStatus.textContent = 'Save failed';
        showToast('Failed to save document.', 'error');
      }
    } catch (e) {
      if (dom.writingStatus) dom.writingStatus.textContent = 'Save failed';
    }
  }

  async function convertToLatex() {
    const content = dom.writingInput ? dom.writingInput.value.trim() : '';
    if (!content) { showToast('Nothing to convert.', 'warning'); return; }
    if (!state.token) { showAuthModal(); return; }

    try {
      if (dom.writingStatus) dom.writingStatus.textContent = 'Converting...';
      if (dom.writingConvertBtn) dom.writingConvertBtn.disabled = true;

      const resp = await authFetch('/api/v1/writing/convert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: content, document_class: 'article' }),
      });

      if (!resp.ok) {
        showToast('Conversion failed.', 'error');
        if (dom.writingStatus) dom.writingStatus.textContent = 'Conversion failed';
        return;
      }

      const data = await resp.json();
      if (dom.writingLatexOutput) {
        dom.writingLatexOutput.querySelector('code').textContent = data.latex;
      }
      if (dom.writingStatus) dom.writingStatus.textContent = 'Converted (' + data.tokens_used + ' tokens)';

      // Also save the latex_content to DB
      if (state.writingDocId) {
        await authFetch('/api/v1/writing/documents/' + encodeURIComponent(state.writingDocId), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ latex_content: data.latex }),
        });
      }
    } catch (e) {
      showToast('Conversion failed.', 'error');
      if (dom.writingStatus) dom.writingStatus.textContent = 'Error';
    } finally {
      if (dom.writingConvertBtn) dom.writingConvertBtn.disabled = false;
    }
  }

  async function exportDocument() {
    if (!state.writingDocId || !state.token) return;
    try {
      const resp = await authFetch('/api/v1/writing/documents/' + encodeURIComponent(state.writingDocId) + '/export');
      if (!resp.ok) { showToast('Export failed.', 'error'); return; }
      const blob = await resp.blob();
      const cd = resp.headers.get('Content-Disposition') || '';
      const match = cd.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : 'document.tex';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('Exported ' + filename, 'success');
    } catch (e) {
      showToast('Export failed.', 'error');
    }
  }

  function copyLatex() {
    const code = dom.writingLatexOutput ? dom.writingLatexOutput.querySelector('code').textContent : '';
    if (!code) { showToast('No LaTeX to copy.', 'warning'); return; }
    navigator.clipboard.writeText(code).then(() => {
      showToast('LaTeX copied to clipboard.', 'success');
    }).catch(() => {
      showToast('Failed to copy.', 'error');
    });
  }

  function toggleWritingMode(mode) {
    state.writingMode = mode;
    if (dom.writingModePlain) dom.writingModePlain.classList.toggle('mode-pill--active', mode === 'plain');
    if (dom.writingModeLatex) dom.writingModeLatex.classList.toggle('mode-pill--active', mode === 'latex');
    if (dom.writingEditorLabel) dom.writingEditorLabel.textContent = mode === 'plain' ? 'Plain English' : 'LaTeX';
    if (dom.writingInput) {
      dom.writingInput.classList.toggle('latex-mode', mode === 'latex');
      dom.writingInput.placeholder = mode === 'plain'
        ? 'Start writing your research paper...'
        : '\\section{Introduction}\nStart writing LaTeX...';
    }
    // In LaTeX mode, hide the convert button and auto-convert
    if (dom.writingConvertBtn) dom.writingConvertBtn.style.display = mode === 'plain' ? '' : 'none';
    const acLabel = dom.writingAutoConvert ? dom.writingAutoConvert.closest('.auto-convert-toggle') : null;
    if (acLabel) acLabel.style.display = mode === 'plain' ? '' : 'none';
  }

  function toggleWritingLayout(layout) {
    state.writingLayout = layout;
    if (dom.writingEditor) {
      dom.writingEditor.classList.toggle('writing-editor--split', layout === 'split');
      dom.writingEditor.classList.toggle('writing-editor--full', layout === 'full');
    }
    if (dom.writingLayoutSplit) dom.writingLayoutSplit.classList.toggle('layout-btn--active', layout === 'split');
    if (dom.writingLayoutFull) dom.writingLayoutFull.classList.toggle('layout-btn--active', layout === 'full');
  }

  function updateWordCount() {
    if (!dom.writingInput || !dom.writingWordCount) return;
    const text = dom.writingInput.value.trim();
    const count = text ? text.split(/\s+/).length : 0;
    dom.writingWordCount.textContent = count + ' word' + (count !== 1 ? 's' : '');
  }

  async function deleteDocument(docId) {
    if (!confirm('Delete this document?')) return;
    try {
      const resp = await authFetch('/api/v1/writing/documents/' + encodeURIComponent(docId), {
        method: 'DELETE',
      });
      if (resp.ok) {
        state.documents = state.documents.filter((d) => d.id !== docId);
        renderDocumentList();
        renderSidebarDocuments();
        // If we deleted the currently open document, go back to landing
        if (state.writingDocId === docId) {
          state.writingDocId = null;
          if (dom.writingWorkspace) dom.writingWorkspace.style.display = 'none';
          const landing = $('#landing');
          if (landing) landing.style.display = '';
        }
        showToast('Document deleted.', 'success');
      }
    } catch (e) {
      showToast('Failed to delete document.', 'error');
    }
  }

  // Helper for HTML escaping
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ═══════════════════════════════════════════════════════════════
  // DARK MODE
  // ═══════════════════════════════════════════════════════════════

  function bindDarkModeEvents() {
    // Restore saved preference
    const saved = localStorage.getItem('evidentia_theme');
    if (saved === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
      updateDarkModeIcon(true);
    }

    if (dom.darkModeToggle) {
      dom.darkModeToggle.addEventListener('click', toggleDarkMode);
    }
  }

  function toggleDarkMode() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem('evidentia_theme', 'light');
      updateDarkModeIcon(false);
    } else {
      document.documentElement.setAttribute('data-theme', 'dark');
      localStorage.setItem('evidentia_theme', 'dark');
      updateDarkModeIcon(true);
    }
  }

  function updateDarkModeIcon(isDark) {
    if (!dom.darkModeIcon) return;
    if (isDark) {
      // Sun icon for "switch to light"
      dom.darkModeIcon.innerHTML = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
    } else {
      // Moon icon for "switch to dark"
      dom.darkModeIcon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
    }
  }


  // ─── Boot ──────────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
