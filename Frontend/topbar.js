(function () {
  const root = document.getElementById('topbar-root');

  if (!root) {
    return;
  }

  const titleText = root.dataset.title || 'Dashboard';
  const subtitleText = root.dataset.subtitle || '';
  const notificationCount = Number(root.dataset.notifications || 3);

  // ========== RÉCUPÉRATION DE LA SESSION UTILISATEUR ==========
  function getSessionUser() {
    try {
      if (window.NetGuardAuth && typeof window.NetGuardAuth.getSession === 'function') {
        const s = window.NetGuardAuth.getSession();
        if (s) {
          // Enrichir avec email depuis localStorage si absent dans la session
          if (!s.email) s.email = localStorage.getItem('userEmail') || '';
          return s;
        }
      }
      const raw = localStorage.getItem('netguardSession');
      if (raw) {
        const s = JSON.parse(raw);
        if (!s.email) s.email = localStorage.getItem('userEmail') || '';
        return s;
      }
    } catch (e) {
      console.warn('Impossible de lire la session :', e);
    }
    return null;
  }

  const ROLE_LABELS = {
    'admin':          'Administrateur Système',
    'network_admin':  'Administrateur Réseau',
    'security_admin': 'Analyste Sécurité (SOC)',
    'auditor':        'Auditeur Externe',
    'ADMIN':          'Administrateur Système',
    'NETWORK_ADMIN':  'Administrateur Réseau',
    'SECURITY_ADMIN': 'Analyste Sécurité (SOC)',
    'AUDITOR':        'Auditeur Externe',
  };

  function getRoleLabel(role) {
    if (!role) return 'Inconnu';
    return ROLE_LABELS[role] || role;
  }

  function getRoleColor(role) {
    const r = (role || '').toLowerCase();
    if (r.includes('network'))  return '#0ea5e9';
    if (r.includes('security')) return '#f59e0b';
    if (r.includes('audit'))    return '#22c55e';
    if (r.includes('admin'))    return '#6366f1';
    return '#64748b';
  }

  function getInitials(username) {
    if (username) return username.slice(0, 2).toUpperCase();
    return '??';
  }

  root.innerHTML = `
    <header class="topbar">
      <div class="topbar-section">
        <div class="topbar-title" id="topbar-title"></div>
        <div class="topbar-subtitle" id="topbar-subtitle"></div>
      </div>

      <div class="topbar-actions">
        <div class="topbar-search-wrapper">
          <label class="topbar-search" for="topbar-search-input">
            <span class="sr-only">Rechercher</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input id="topbar-search-input" class="search-input" type="search" placeholder="Rechercher..." autocomplete="off" aria-controls="topbar-search-results" aria-expanded="false" />
          </label>
          <div id="topbar-search-results" class="topbar-search-results" role="listbox" hidden></div>
        </div>

        <button type="button" id="topbar-detection-toggle" class="detection-btn detection-btn--start" aria-label="Lancer la detection" data-active="false">
          <svg id="topbar-detection-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M8 5v14l11-7z"></path>
          </svg>
          <span id="topbar-detection-label">Start detection</span>
        </button>

        <div class="notif-wrapper">
          <button type="button" id="topbar-notif-button" class="icon-button" aria-label="Notifications">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M15 17h5l-1.405-1.405A2.032 2.032 0 0 1 18 14.158V11a6 6 0 0 0-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 1 1-6 0v-1m6 0H9" />
            </svg>
          </button>
          <span id="topbar-notif-count" class="notif-count"></span>

          <!-- Dropdown alertes -->
          <div id="topbar-alerts-dropdown" class="alerts-dropdown" hidden>
            <div class="alerts-dropdown-header">
              <span class="alerts-dropdown-title">Alertes récentes</span>
              <div style="display:flex;align-items:center;gap:6px;">
                <button type="button" id="topbar-notif-config-btn" class="alerts-config-btn" title="Configurer les notifications">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                  </svg>
                  Configurer
                </button>
                <a href="alerts.html" class="alerts-dropdown-viewall">Voir tout</a>
              </div>
            </div>
            <div id="topbar-alerts-list" class="alerts-dropdown-list">
              <div class="alerts-dropdown-empty">Aucune alerte</div>
            </div>
          </div>

          <!-- Modal configuration notifications -->
          <div id="topbar-notif-config-modal" class="notif-config-overlay" hidden>
            <div class="notif-config-card">
              <div class="notif-config-header">
                <div class="notif-config-header-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20">
                    <path d="M15 17h5l-1.405-1.405A2.032 2.032 0 0 1 18 14.158V11a6 6 0 0 0-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 1 1-6 0v-1m6 0H9"/>
                  </svg>
                </div>
                <div>
                  <h3 class="notif-config-title">Configuration des notifications</h3>
                  <p class="notif-config-subtitle">Paramètres du service de notification IDS</p>
                </div>
                <button type="button" id="notif-config-close" class="notif-config-close-btn" aria-label="Fermer">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="16" height="16">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </button>
              </div>

              <div class="notif-config-body">

                <!-- Section : Installation -->
                <div class="notif-config-section">
                  <div class="notif-config-section-label">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    Installation du notifier
                  </div>
                  <p class="notif-config-hint">Installe le service de notification IDS en arrière-plan et le configure pour démarrer automatiquement.</p>
                  <button type="button" class="notif-config-action-btn notif-config-action-btn--primary" id="notif-run-install">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    Installer le notifier
                  </button>
                </div>



              </div>

              <div class="notif-config-footer">
                <div class="notif-config-info">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  Les actions s'exécutent en arrière-plan sur le serveur Windows.
                </div>
                <button type="button" id="notif-config-close-btn" class="notif-config-btn-close">Fermer</button>
              </div>
            </div>
          </div>
        </div>

        <button type="button" id="topbar-theme-toggle" class="icon-button theme-toggle" aria-label="Changer le theme">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"></path>
          </svg>
        </button>

        <div class="user-dropdown">
          <button type="button" id="topbar-user-button" class="icon-button user-avatar-btn" aria-label="Compte utilisateur">
            <span id="topbar-user-initials" class="user-initials-badge">?</span>
          </button>
          <div id="topbar-user-menu" class="user-menu" hidden>
            <div id="topbar-menu-user-info" class="user-menu-info">
              <div id="topbar-menu-avatar" class="user-menu-avatar">?</div>
              <div class="user-menu-details">
                <span id="topbar-menu-username" class="user-menu-name">Chargement...</span>
                <span id="topbar-menu-role" class="user-menu-role">...</span>
              </div>
            </div>
            <div class="user-menu-divider"></div>
            <button type="button" class="user-menu-item" id="topbar-menu-profile">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              Mon profil
            </button>
            <button type="button" class="user-menu-item user-menu-item--danger" id="topbar-menu-logout">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
              Déconnexion
            </button>
          </div>
        </div>
      </div>
    </header>

    <div id="topbar-detection-toast" class="detection-toast" role="status" aria-live="polite" hidden></div>

    <!-- ===================== MODAL PROFIL ===================== -->
    <div id="topbar-profile-modal" class="ng-profile-overlay" role="dialog" aria-modal="true" aria-labelledby="ng-profile-title">
      <div class="ng-profile-card">

        <button type="button" id="profile-modal-close" class="ng-profile-close" aria-label="Fermer">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>

        <div class="ng-profile-header">
          <div class="ng-profile-header-bg" id="ng-header-bg"></div>
          <div class="ng-profile-avatar-wrap">
            <div class="ng-profile-avatar" id="ng-profile-avatar">??</div>
            <div class="ng-profile-status-dot" title="En ligne"></div>
          </div>
          <div class="ng-profile-header-info">
            <h2 class="ng-profile-name" id="ng-profile-title">Chargement…</h2>
            <span class="ng-profile-badge" id="ng-profile-badge">…</span>
          </div>
        </div>

        <div class="ng-profile-body">

          <div class="ng-info-row">
            <div class="ng-info-icon">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
            <div class="ng-info-content">
              <span class="ng-info-label">Nom d'utilisateur</span>
              <span class="ng-info-value" id="ng-profile-username">—</span>
            </div>
          </div>

          <div class="ng-info-row">
            <div class="ng-info-icon">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                <polyline points="22,6 12,13 2,6"/>
              </svg>
            </div>
            <div class="ng-info-content">
              <span class="ng-info-label">Adresse e-mail</span>
              <span class="ng-info-value" id="ng-profile-email">—</span>
            </div>
          </div>

          <div class="ng-info-row">
            <div class="ng-info-icon">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </div>
            <div class="ng-info-content">
              <span class="ng-info-label">Rôle et permissions</span>
              <span class="ng-info-value" id="ng-profile-role">—</span>
            </div>
          </div>

          <div class="ng-info-row">
            <div class="ng-info-icon">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
            </div>
            <div class="ng-info-content">
              <span class="ng-info-label">Session démarrée</span>
              <span class="ng-info-value" id="ng-profile-session">—</span>
            </div>
          </div>

        </div>

        <div class="ng-profile-footer">
          <button type="button" id="profile-modal-logout" class="ng-btn-logout">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Déconnexion
          </button>
          <button type="button" id="profile-modal-close-btn" class="ng-btn-close">Fermer</button>
        </div>

      </div>
    </div>
  `;

  const titleEl      = document.getElementById('topbar-title');
  const subtitleEl   = document.getElementById('topbar-subtitle');
  const countEl      = document.getElementById('topbar-notif-count');
  const themeToggle  = document.getElementById('topbar-theme-toggle');
  const userButton   = document.getElementById('topbar-user-button');
  const userMenu     = document.getElementById('topbar-user-menu');
  const logoutBtn    = document.getElementById('topbar-menu-logout');
  const profileBtn   = document.getElementById('topbar-menu-profile');
  const profileModal = document.getElementById('topbar-profile-modal');
  const searchInput  = document.getElementById('topbar-search-input');
  const searchResults = document.getElementById('topbar-search-results');
  const detectionToggleBtn = document.getElementById('topbar-detection-toggle');
  const detectionToast     = document.getElementById('topbar-detection-toast');

  // ========== AVATAR + DROPDOWN ==========
  function initUserAvatar() {
    var user      = getSessionUser();
    var initials  = getInitials(user ? user.username : null);
    var roleColor = getRoleColor(user ? user.role : null);

    var initialsEl = document.getElementById('topbar-user-initials');
    if (initialsEl) {
      initialsEl.textContent = initials;
      initialsEl.style.background = 'linear-gradient(135deg, ' + roleColor + ', ' + roleColor + 'cc)';
    }

    var menuUsernameEl = document.getElementById('topbar-menu-username');
    var menuRoleEl     = document.getElementById('topbar-menu-role');
    var menuAvatarEl   = document.getElementById('topbar-menu-avatar');
    if (menuUsernameEl) menuUsernameEl.textContent = (user && user.username) || 'Utilisateur';
    if (menuRoleEl)     menuRoleEl.textContent     = getRoleLabel(user ? user.role : null);
    if (menuAvatarEl) {
      menuAvatarEl.textContent = initials;
      menuAvatarEl.style.background = 'linear-gradient(135deg, ' + roleColor + ', ' + roleColor + 'cc)';
    }
  }

  // ========== REMPLIR LE MODAL PROFIL ==========
  function fillProfileModal() {
    var user      = getSessionUser();
    var initials  = getInitials(user ? user.username : null);
    var roleColor = getRoleColor(user ? user.role : null);

    // Fond coloré de l'en-tête
    var headerBg = document.getElementById('ng-header-bg');
    if (headerBg) {
      headerBg.style.background = 'linear-gradient(135deg, ' + roleColor + '28 0%, ' + roleColor + '08 100%)';
    }

    // Avatar avec initiales et ombre colorée
    var avatar = document.getElementById('ng-profile-avatar');
    if (avatar) {
      avatar.textContent     = initials;
      avatar.style.background  = 'linear-gradient(135deg, ' + roleColor + ' 0%, ' + roleColor + 'bb 100%)';
      avatar.style.boxShadow   = '0 8px 28px ' + roleColor + '55';
    }

    // Nom = username depuis la BDD
    var nameEl = document.getElementById('ng-profile-title');
    if (nameEl) nameEl.textContent = (user && user.username) || 'Utilisateur';

    // Badge rôle coloré
    var badgeEl = document.getElementById('ng-profile-badge');
    if (badgeEl) {
      badgeEl.textContent       = getRoleLabel(user ? user.role : null);
      badgeEl.style.background  = roleColor + '18';
      badgeEl.style.color       = roleColor;
      badgeEl.style.borderColor = roleColor + '50';
    }

    // Champs détaillés — toutes les données viennent de la session (BDD via /login)
    var usernameEl = document.getElementById('ng-profile-username');
    var emailEl    = document.getElementById('ng-profile-email');
    var roleEl     = document.getElementById('ng-profile-role');
    var sessionEl  = document.getElementById('ng-profile-session');

    if (usernameEl) usernameEl.textContent = (user && user.username) || '—';
    if (emailEl)    emailEl.textContent    = (user && user.email)    || 'Non renseigné';
    if (roleEl)     roleEl.textContent     = getRoleLabel(user ? user.role : null);

    if (sessionEl) {
      var loginTime = localStorage.getItem('netguard_login_time');
      if (!loginTime) {
        loginTime = Date.now().toString();
        localStorage.setItem('netguard_login_time', loginTime);
      }
      var d = new Date(Number(loginTime));
      sessionEl.textContent = d.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
    }
  }

  function openProfileModal() {
    fillProfileModal();
    profileModal.classList.add('ng-profile-overlay--visible');
    closeUserMenu();
    setTimeout(function() {
      var closeBtn = document.getElementById('profile-modal-close');
      if (closeBtn) closeBtn.focus();
    }, 120);
  }

  function closeProfileModal() {
    profileModal.classList.remove('ng-profile-overlay--visible');
  }

  function doLogout() {
    if (window.NetGuardAuth && typeof window.NetGuardAuth.clearSession === 'function') {
      window.NetGuardAuth.clearSession();
    }
    localStorage.removeItem('netguard_login_time');
    window.location.href = 'login.html';
  }

  function updateNotificationCount(count) {
    var value = Number(count) || 0;
    countEl.textContent = value > 99 ? '99+' : value;
    countEl.style.display = value > 0 ? 'flex' : 'none';
  }

  function showDetectionToast(message, isError) {
    if (!detectionToast) return;
    detectionToast.textContent = message;
    detectionToast.classList.toggle('detection-toast--error', !!isError);
    detectionToast.hidden = false;
    clearTimeout(showDetectionToast.timer);
    showDetectionToast.timer = setTimeout(function () {
      detectionToast.hidden = true;
    }, 3500);
  }

  async function callDetection(endpoint, button, loadingText) {
    var originalHTML = button ? button.innerHTML : '';
    try {
      if (button) {
        button.disabled = true;
        var labelEl = button.querySelector('#topbar-detection-label') || button.querySelector('span');
        if (labelEl) labelEl.textContent = loadingText;
      }

      var res = await fetch('http://localhost:5000' + endpoint, { method: 'POST' });
      var data = await res.json().catch(function () { return {}; });
      if (!res.ok) throw new Error(data.message || data.error || 'Erreur serveur');

      showDetectionToast(data.message || 'Action effectuée avec succès', false);
    } catch (e) {
      showDetectionToast(e.message || 'Impossible de contacter le serveur', true);
      // Restaurer le HTML original en cas d'erreur
      if (button) button.innerHTML = originalHTML;
      throw e; // Re-throw pour que le .then() du toggle ne soit pas appelé
    } finally {
      if (button) button.disabled = false;
    }
  }

  function setTheme(isDark) {
    document.documentElement.classList.toggle('dark-mode', isDark);
    document.body.classList.toggle('dark-mode', isDark);
    document.documentElement.classList.toggle('dark', isDark);
    document.body.classList.toggle('dark', isDark);

    if (themeToggle) {
      themeToggle.classList.toggle('toggle-active', isDark);
      themeToggle.setAttribute('aria-pressed', String(isDark));
      var svg = themeToggle.querySelector('svg');
      if (svg) {
        svg.innerHTML = isDark
          ? '<path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>'
          : '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"></path>';
      }
    }
    localStorage.setItem('netguard-theme', isDark ? 'dark' : 'light');
    window.dispatchEvent(new CustomEvent('themeChanged', { detail: { isDark: isDark } }));
  }

  function toggleTheme() {
    var isDark = document.documentElement.classList.contains('dark-mode') || document.body.classList.contains('dark-mode');
    setTheme(!isDark);
  }

  function initTheme() {
    var savedTheme = localStorage.getItem('netguard-theme');
    var shouldBeDark = savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches);
    setTheme(shouldBeDark);
  }

  function closeUserMenu() { userMenu.hidden = true; }
  function toggleUserMenu() { userMenu.hidden = !userMenu.hidden; }

  // ========== RECHERCHE GLOBALE ==========
  const SEARCH_ITEMS = [
    { id: 'dashboard', label: 'Dashboard', href: 'dashboard.html', keywords: ['accueil', 'home', 'overview', 'tableau de bord', 'reseau', 'réseau'] },
    { id: 'vlan', label: 'VLAN', href: 'vlan.html', keywords: ['vlans', 'reseau vlan', 'réseau vlan', 'quarantine', 'isolation'] },
    { id: 'interfaces', label: 'Interfaces', href: 'interfaces.html', keywords: ['interface', 'ports', 'port', 'switchport', 'up', 'down', 'port security'] },
    { id: 'alerts', label: 'Alerts', href: 'alerts.html', keywords: ['alertes', 'alerte', 'snort', 'critique', 'securite', 'sécurité'] },
    { id: 'traffic', label: 'Traffic', href: 'traffic.html', keywords: ['trafic', 'network traffic', 'monitoring', 'bande passante'] },
    { id: 'configuration', label: 'Configuration', href: 'Configuration.html', keywords: ['config', 'regles', 'règles', 'rules', 'automation'] },
    { id: 'users', label: 'Users', href: 'users.html', keywords: ['utilisateurs', 'user', 'roles', 'rôles', 'compte'] },
    { id: 'equipements', label: 'Equipements', href: 'equipements.html', keywords: ['equipement', 'équipement', 'switch', 'routeur', 'router'] },
    { id: 'logs', label: 'Logs', href: 'logs.html', keywords: ['journal', 'audit', 'activites', 'activités', 'historique'] }
  ];

  let searchMatches = [];
  let activeSearchIndex = -1;

  function normalizeSearchText(value) {
    return String(value || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }

  function canOpenSearchItem(item) {
    if (!window.NetGuardAuth || typeof window.NetGuardAuth.canAccessPage !== 'function') {
      return true;
    }
    return window.NetGuardAuth.canAccessPage(item.id);
  }

  function getSearchableText(item) {
    return normalizeSearchText([item.label, item.id].concat(item.keywords || []).join(' '));
  }

  function closeSearchResults() {
    searchMatches = [];
    activeSearchIndex = -1;
    if (searchResults) {
      searchResults.hidden = true;
      searchResults.innerHTML = '';
    }
    if (searchInput) {
      searchInput.setAttribute('aria-expanded', 'false');
      searchInput.removeAttribute('aria-activedescendant');
    }
  }

  function openSearchItem(item) {
    if (!item || !canOpenSearchItem(item)) return;
    window.location.href = item.href;
  }

  function setActiveSearchIndex(index) {
    activeSearchIndex = index;
    var options = searchResults ? searchResults.querySelectorAll('.topbar-search-result') : [];
    options.forEach(function(option, optionIndex) {
      var isActive = optionIndex === activeSearchIndex;
      option.classList.toggle('active', isActive);
      option.setAttribute('aria-selected', String(isActive));
      if (isActive && searchInput) {
        searchInput.setAttribute('aria-activedescendant', option.id);
      }
    });
  }

  function renderSearchResults(query) {
    if (!searchInput || !searchResults) return;

    var normalizedQuery = normalizeSearchText(query).trim();
    if (!normalizedQuery) {
      closeSearchResults();
      return;
    }

    searchMatches = SEARCH_ITEMS
      .filter(canOpenSearchItem)
      .filter(function(item) {
        return getSearchableText(item).includes(normalizedQuery);
      })
      .slice(0, 6);

    if (searchMatches.length === 0) {
      searchResults.innerHTML = '<div class="topbar-search-empty">Aucun resultat</div>';
      searchResults.hidden = false;
      searchInput.setAttribute('aria-expanded', 'true');
      activeSearchIndex = -1;
      return;
    }

    searchResults.innerHTML = searchMatches.map(function(item, index) {
      return '<button type="button" id="topbar-search-option-' + index + '" class="topbar-search-result" role="option" aria-selected="false" data-index="' + index + '">' +
        '<span class="topbar-search-result-title">' + item.label + '</span>' +
        '<span class="topbar-search-result-path">' + item.href + '</span>' +
      '</button>';
    }).join('');

    searchResults.hidden = false;
    searchInput.setAttribute('aria-expanded', 'true');
    setActiveSearchIndex(0);
  }

  function initGlobalSearch() {
    if (!searchInput || !searchResults) return;

    searchInput.addEventListener('input', function() {
      renderSearchResults(searchInput.value);
    });

    searchInput.addEventListener('focus', function() {
      renderSearchResults(searchInput.value);
    });

    searchInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        openSearchItem(searchMatches[activeSearchIndex] || searchMatches[0]);
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (searchMatches.length) setActiveSearchIndex((activeSearchIndex + 1) % searchMatches.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (searchMatches.length) setActiveSearchIndex((activeSearchIndex - 1 + searchMatches.length) % searchMatches.length);
      } else if (e.key === 'Escape') {
        closeSearchResults();
      }
    });

    searchResults.addEventListener('mousedown', function(e) {
      var result = e.target.closest('.topbar-search-result');
      if (!result) return;
      e.preventDefault();
      openSearchItem(searchMatches[Number(result.dataset.index)]);
    });
  }

  // ========== INIT ==========
  titleEl.textContent    = titleText;
  subtitleEl.textContent = subtitleText;
  subtitleEl.style.display = subtitleText ? 'block' : 'none';
  updateNotificationCount(notificationCount);
  initTheme();
  initUserAvatar();
  initGlobalSearch();

  // ========== ÉVÉNEMENTS ==========
  window.addEventListener('storage', function (e) {
    if (e.key === 'netguard-theme') setTheme(e.newValue === 'dark');
  });

  if (themeToggle) themeToggle.addEventListener('click', toggleTheme);
  if (detectionToggleBtn) {
    detectionToggleBtn.addEventListener('click', function () {
      var isActive = detectionToggleBtn.dataset.active === 'true';
      if (!isActive) {
        // Passer en mode "actif" → appeler start, switcher vers Stop
        callDetection('/start-detection', detectionToggleBtn, 'Lancement...').then(function () {
          detectionToggleBtn.dataset.active = 'true';
          detectionToggleBtn.classList.remove('detection-btn--start');
          detectionToggleBtn.classList.add('detection-btn--stop');
          detectionToggleBtn.setAttribute('aria-label', 'Arrêter la détection');
          document.getElementById('topbar-detection-label').textContent = 'Stop detection';
          document.getElementById('topbar-detection-icon').innerHTML =
            '<rect x="7" y="7" width="10" height="10" rx="1.5"></rect>';
          document.getElementById('topbar-detection-icon').setAttribute('fill', 'none');
          document.getElementById('topbar-detection-icon').setAttribute('stroke', 'currentColor');
          document.getElementById('topbar-detection-icon').setAttribute('stroke-width', '2.4');
          document.getElementById('topbar-detection-icon').setAttribute('stroke-linecap', 'round');
          document.getElementById('topbar-detection-icon').setAttribute('stroke-linejoin', 'round');
        });
      } else {
        // Passer en mode "inactif" → appeler stop, switcher vers Start
        callDetection('/stop-detection', detectionToggleBtn, 'Arrêt...').then(function () {
          detectionToggleBtn.dataset.active = 'false';
          detectionToggleBtn.classList.remove('detection-btn--stop');
          detectionToggleBtn.classList.add('detection-btn--start');
          detectionToggleBtn.setAttribute('aria-label', 'Lancer la détection');
          document.getElementById('topbar-detection-label').textContent = 'Start detection';
          var icon = document.getElementById('topbar-detection-icon');
          icon.setAttribute('fill', 'currentColor');
          icon.removeAttribute('stroke');
          icon.removeAttribute('stroke-width');
          icon.removeAttribute('stroke-linecap');
          icon.removeAttribute('stroke-linejoin');
          icon.innerHTML = '<path d="M8 5v14l11-7z"></path>';
        });
      }
    });
  }

  userButton.addEventListener('click', function (e) {
    e.stopPropagation();
    toggleUserMenu();
  });

  profileBtn.addEventListener('click', openProfileModal);
  logoutBtn.addEventListener('click', doLogout);

  document.getElementById('profile-modal-logout').addEventListener('click', doLogout);
  document.getElementById('profile-modal-close').addEventListener('click', closeProfileModal);
  document.getElementById('profile-modal-close-btn').addEventListener('click', closeProfileModal);

  profileModal.addEventListener('click', function (e) {
    if (e.target === profileModal) closeProfileModal();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeProfileModal(); closeUserMenu(); }
  });

  document.addEventListener('click', function (e) {
    if (userMenu && !userMenu.contains(e.target) && e.target !== userButton) closeUserMenu();
    if (searchResults && searchInput && !searchResults.contains(e.target) && e.target !== searchInput && !e.target.closest('.topbar-search')) closeSearchResults();
  });

  // ========== MODAL CONFIGURATION NOTIFICATIONS ==========
  var _notifConfigModal  = document.getElementById('topbar-notif-config-modal');
  var _notifConfigOpenBtn = document.getElementById('topbar-notif-config-btn');
  var _notifConfigCloseBtn = document.getElementById('notif-config-close');
  var _notifConfigCloseBtnFooter = document.getElementById('notif-config-close-btn');

  function _openNotifConfig() {
    if (_notifConfigModal) _notifConfigModal.hidden = false;
    if (typeof _closeAlertsDropdown === 'function') _closeAlertsDropdown();
  }
  function _closeNotifConfig() {
    if (_notifConfigModal) _notifConfigModal.hidden = true;
  }

  if (_notifConfigOpenBtn)        _notifConfigOpenBtn.addEventListener('click', function(e) { e.stopPropagation(); _openNotifConfig(); });
  if (_notifConfigCloseBtn)       _notifConfigCloseBtn.addEventListener('click', _closeNotifConfig);
  if (_notifConfigCloseBtnFooter) _notifConfigCloseBtnFooter.addEventListener('click', _closeNotifConfig);

  if (_notifConfigModal) {
    _notifConfigModal.addEventListener('click', function(e) {
      if (e.target === _notifConfigModal) _closeNotifConfig();
    });
  }

var _installBtn = document.getElementById('notif-run-install');
  if (_installBtn) {
    _installBtn.addEventListener('click', function() { _launchPBat('1', null, _installBtn, 'Installer le notifier', 'Installation lancée ✅'); });
  }

function _launchPBat(option, params, btn, originalLabel, successLabel) {
    var body = { option: option };
    if (params) body.params = params;

    // État chargement
    if (btn) {
      btn.disabled = true;
      btn.style.opacity = '0.7';
      btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14" style="animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> En cours…';
    }

    fetch('http://localhost:5000/api/run-pbat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d && d.success) {
        showDetectionToast(successLabel || 'Opération réussie ✅', false);
        _closeNotifConfig();
      } else {
        showDetectionToast((d && d.message) || 'Erreur lors du lancement du service', true);
      }
    })
    .catch(function() {
      showDetectionToast('Impossible de contacter Flask — vérifiez que le serveur tourne sur localhost:5000', true);
    })
    .finally(function() {
      if (btn) {
        btn.disabled = false;
        btn.style.opacity = '';
        // Restaurer le label d'origine avec son icône
        btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> ' + (originalLabel || 'Installer le notifier');
      }
    });
  }

  // ========== ALERTES TEMPS RÉEL ==========
  var _lastAlertCount = null;
  var _alertsDropdown = document.getElementById('topbar-alerts-dropdown');
  var _alertsList     = document.getElementById('topbar-alerts-list');
  var _notifButton    = document.getElementById('topbar-notif-button');

  function _severityColor(severity) {
    var s = (severity || '').toLowerCase();
    if (s === 'critique' || s === 'critical' || s === 'high' || s === '1') return '#ef4444';
    if (s === 'moyen'    || s === 'medium'   || s === 'moderate' || s === '2') return '#f59e0b';
    return '#22c55e';
  }

  function _severityLabel(severity) {
    var s = (severity || '').toLowerCase();
    if (s === 'critique' || s === 'critical' || s === 'high' || s === '1') return 'Critique';
    if (s === 'moyen'    || s === 'medium'   || s === 'moderate' || s === '2') return 'Moyen';
    return 'Faible';
  }

  function _renderAlertsList(alerts) {
    if (!_alertsList) return;
    if (!alerts || alerts.length === 0) {
      _alertsList.innerHTML = '<div class="alerts-dropdown-empty">Aucune alerte récente</div>';
      return;
    }
    _alertsList.innerHTML = alerts.slice(0, 8).map(function(a) {
      var color = _severityColor(a.severity || a.priority || a.gravite || '');
      var label = _severityLabel(a.severity || a.priority || a.gravite || '');
      var msg   = a.message || a.msg || a.classification || a.description || 'Alerte détectée';
      var src   = a.src_ip  || a.source_ip || a.source || '';
      var ts    = a.timestamp || a.date || a.created_at || '';
      var time  = '';
      if (ts) {
        try {
          var d = new Date(ts);
          time = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
        } catch(e) { time = ts; }
      }
      return '<div class="alerts-dropdown-item">' +
        '<span class="alert-dot" style="background:' + color + '"></span>' +
        '<div class="alert-item-body">' +
          '<span class="alert-item-msg">' + msg + '</span>' +
          '<span class="alert-item-meta">' +
            '<span class="alert-item-badge" style="color:' + color + ';border-color:' + color + '40;background:' + color + '12">' + label + '</span>' +
            (src  ? '<span class="alert-item-ip">'   + src  + '</span>' : '') +
            (time ? '<span class="alert-item-time">'  + time + '</span>' : '') +
          '</span>' +
        '</div>' +
      '</div>';
    }).join('');
  }

  function _toggleAlertsDropdown(e) {
    e.stopPropagation();
    if (!_alertsDropdown) return;
    var isHidden = _alertsDropdown.hidden;
    _alertsDropdown.hidden = !isHidden;
    if (!isHidden) return;
    // Marquer comme lu : reset badge
    updateNotificationCount(0);
    _lastAlertCount = null; // sera recalculé au prochain poll
  }

  function _closeAlertsDropdown() {
    if (_alertsDropdown) _alertsDropdown.hidden = true;
  }

  if (_notifButton) {
    _notifButton.addEventListener('click', _toggleAlertsDropdown);
  }

  document.addEventListener('click', function(e) {
    if (_alertsDropdown && !_alertsDropdown.hidden) {
      if (!_alertsDropdown.contains(e.target) && e.target !== _notifButton) {
        _closeAlertsDropdown();
      }
    }
  });

  // Poll API alertes toutes les 5 secondes
  async function _pollAlerts() {
    try {
      var token = localStorage.getItem('jwtToken');
      var headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = 'Bearer ' + token;

      // Récupérer les alertes récentes
      var res = await fetch('http://localhost:5000/api/alerts?limit=8&sort=desc', { headers: headers });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();

      var alerts = data.alerts || data.data || data.results || [];
      _renderAlertsList(alerts);

      // Récupérer le total pour le badge
      var statsRes = await fetch('http://localhost:5000/api/stats', { headers: headers });
      var statsData = await statsRes.json();
      if (statsData.success || statsData.stats) {
        var total = parseInt((statsData.stats || statsData).total) || 0;
        if (_lastAlertCount === null) {
          _lastAlertCount = total;
        }
        var newCount = Math.max(0, total - _lastAlertCount);
        // Si dropdown ouvert, ne pas changer le badge
        if (_alertsDropdown && _alertsDropdown.hidden) {
          updateNotificationCount(newCount);
        }
      }
    } catch(e) {
      // Silencieux — API peut être indisponible
    }
  }

  _pollAlerts();
  setInterval(_pollAlerts, 5000);

  // API publique : permet à alerts.html de réinitialiser le badge topbar
  window.resetTopbarAlertBadge = function() {
    fetch('http://localhost:5000/api/stats').then(function(r) { return r.json(); }).then(function(d) {
      if (d.success || d.stats) _lastAlertCount = parseInt((d.stats || d).total) || 0;
    }).catch(function(){});
    updateNotificationCount(0);
  };

  // ========== API PUBLIQUE ==========
  window.setPageTitle = function (title, subtitle) {
    titleEl.textContent    = title || 'Dashboard';
    subtitleEl.textContent = subtitle || '';
    subtitleEl.style.display = subtitle ? 'block' : 'none';
  };
  window.setNotificationCount = function (count) { updateNotificationCount(count); };
  window.toggleTheme  = toggleTheme;
  window.setTheme     = setTheme;
  window.openProfileModal = openProfileModal;
})();