/**
 * ╔══════════════════════════════════════════════════════════════════════╗
 * ║              NetGuard — Système d'Audit Centralisé                  ║
 * ║  Enregistre toutes les actions utilisateur + visites de pages       ║
 * ║  Stockage : localStorage  →  clé "netguard_audit_logs"             ║
 * ╚══════════════════════════════════════════════════════════════════════╝
 */
(function () {
  'use strict';

  const LS_KEY   = 'netguard_audit_logs';
  const MAX_LOGS = 2000;

  /* ── Récupérer la session courante ──────────────────────────────────── */
  function getSession() {
    try {
      if (window.NetGuardAuth && window.NetGuardAuth.getSession) {
        return window.NetGuardAuth.getSession();
      }
    } catch (_) {}
    /* Fallback : lire directement le localStorage d'auth */
    try {
      const raw = localStorage.getItem('netguard_session');
      if (raw) return JSON.parse(raw);
    } catch (_) {}
    return null;
  }

  /* ── Persister une entrée ────────────────────────────────────────────── */
  function persist(entry) {
    try {
      const logs = JSON.parse(localStorage.getItem(LS_KEY) || '[]');
      logs.unshift(entry);
      if (logs.length > MAX_LOGS) logs.length = MAX_LOGS;
      localStorage.setItem(LS_KEY, JSON.stringify(logs));
      window.dispatchEvent(new Event('netguard:audit'));
    } catch (e) {
      console.warn('[NetGuardAudit] Erreur persist:', e);
    }
  }

  /* ══════════════════════════════════════════════════════════════════════
     API PRINCIPALE — window.NetGuardAudit.log(opts)
     opts : {
       action   : string  (obligatoire)
       target   : string
       severity : 'Info' | 'Low' | 'Medium' | 'High' | 'Critical'
       success  : bool
     }
  ══════════════════════════════════════════════════════════════════════ */
  function log(opts) {
    const session = getSession();
    const entry = {
      id:        `log-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      timestamp: new Date().toISOString(),
      actor:     session ? (session.username || session.name || 'inconnu') : 'inconnu',
      role:      session ? (session.role || '') : '',
      action:    opts.action   || '—',
      target:    opts.target   || '—',
      severity:  opts.severity || 'Info',
      result:    opts.success === false ? 'failure' : 'success',
    };
    persist(entry);
    return entry;
  }

  /* ══════════════════════════════════════════════════════════════════════
     HELPERS SÉMANTIQUES — appelés depuis chaque page HTML
  ══════════════════════════════════════════════════════════════════════ */

  /* ── Visite de page ─────────────────────────────────────────────────── */
  function pageVisited(pageName) {
    log({ action: `Consultation page`, target: pageName, severity: 'Info', success: true });
  }

  /* ── Authentification ───────────────────────────────────────────────── */
  function loginSuccess(username) {
    log({ action: 'Connexion réussie', target: username, severity: 'Info', success: true });
  }
  function loginFailed(username) {
    log({ action: 'Échec de connexion', target: username || 'inconnu', severity: 'High', success: false });
  }
  function logout(username) {
    log({ action: 'Déconnexion', target: username || '—', severity: 'Info', success: true });
  }

  /* ── Utilisateurs ───────────────────────────────────────────────────── */
  function userCreated(opts) {
    log({ action: 'Création utilisateur', target: `${opts.username} (${opts.role || '?'})`, severity: 'Medium', success: true });
  }
  function userDeleted(opts) {
    log({ action: 'Suppression utilisateur', target: opts.username, severity: 'High', success: true });
  }
  function userUpdated(opts) {
    log({ action: 'Modification utilisateur', target: opts.username, severity: 'Medium', success: true });
  }

  /* ── Règles Snort ───────────────────────────────────────────────────── */
  function ruleCreated(opts) {
    log({ action: 'Création règle Snort', target: `SID ${opts.sid || '?'} — ${opts.name || ''}`, severity: 'High', success: true });
  }
  function ruleModified(opts) {
    log({ action: 'Modification règle Snort', target: `SID ${opts.sid || '?'} — ${opts.name || ''}`, severity: 'High', success: true });
  }
  function ruleDeleted(opts) {
    log({ action: 'Suppression règle Snort', target: `SID ${opts.sid || '?'}`, severity: 'High', success: true });
  }
  function rulesReset() {
    log({ action: 'Reset règles Snort (restore usine)', target: 'Toutes les règles', severity: 'Critical', success: true });
  }
  function rulesImported(opts) {
    log({ action: 'Import règles Snort', target: opts.filename || 'fichier inconnu', severity: 'High', success: true });
  }
  function rulesExported() {
    log({ action: 'Export règles Snort', target: 'Export .rules', severity: 'Info', success: true });
  }

  /* ── VLAN ───────────────────────────────────────────────────────────── */
  function vlanCreated(opts) {
    log({ action: 'Création VLAN', target: `VLAN ${opts.id} "${opts.name || ''}" sur ${opts.switchName || '?'}`, severity: 'High', success: true });
  }
  function vlanDeleted(opts) {
    log({ action: 'Suppression VLAN', target: `VLAN ${opts.id}`, severity: 'High', success: true });
  }

  /* ── Interfaces / Ports ─────────────────────────────────────────────── */
  function interfaceDeployed(opts) {
    log({
      action: 'Déploiement interface',
      target: `${opts.name} — mode ${opts.mode || '?'}, VLAN ${opts.vlan || '?'}`,
      severity: 'High',
      success: true,
    });
  }
  function interfaceDeleted(opts) {
    log({ action: 'Suppression interface', target: opts.name, severity: 'High', success: true });
  }

  /* ── Switch / Équipements ───────────────────────────────────────────── */
  function switchCreated(opts) {
    log({ action: 'Création switch', target: `${opts.name || '?'} (${opts.ip || '?'})`, severity: 'High', success: true });
  }
  function switchDeleted(opts) {
    log({ action: 'Suppression switch', target: `${opts.name || opts.id || '?'}`, severity: 'High', success: true });
  }
  function switchUpdated(opts) {
    log({ action: 'Modification switch', target: `${opts.name || opts.id || '?'}`, severity: 'Medium', success: true });
  }

  /* ── TFTP ───────────────────────────────────────────────────────────── */
  function tftpBackup(opts) {
    log({
      action: 'Sauvegarde TFTP',
      target: `${opts.filename || '?'} → ${opts.server || '?'} (${opts.configType || 'running'})`,
      severity: 'Medium',
      success: opts.success !== false,
    });
  }
  function tftpRestore(opts) {
    log({
      action: 'Restauration TFTP',
      target: `${opts.filename || '?'} depuis ${opts.server || '?'} (${opts.configType || 'running'})`,
      severity: 'High',
      success: opts.success !== false,
    });
  }

  /* ── Port Mirroring ─────────────────────────────────────────────────── */
  function portMirroringCreated(opts) {
    log({
      action: 'Configuration Port Mirroring (SPAN)',
      target: `Session ${opts.sessionId || '?'} — VLAN ${opts.sourceVlan || '?'} → ${opts.destination || '?'}`,
      severity: 'High',
      success: true,
    });
  }
  function portMirroringDeleted(opts) {
    log({
      action: 'Suppression Port Mirroring (SPAN)',
      target: `Session ${opts.sessionId || '?'}`,
      severity: 'High',
      success: true,
    });
  }

  /* ── Logs ───────────────────────────────────────────────────────────── */
  function logsExported() {
    log({ action: 'Export logs audit (CSV)', target: 'Journal d\'audit', severity: 'Info', success: true });
  }

  /* ── Utilitaires ────────────────────────────────────────────────────── */
  function clear() {
    try { localStorage.removeItem(LS_KEY); } catch (_) {}
  }

  /* ══════════════════════════════════════════════════════════════════════
     DÉTECTION AUTOMATIQUE DE PAGE au chargement du DOM
     Lit window.location.pathname et enregistre la visite.
  ══════════════════════════════════════════════════════════════════════ */
  const PAGE_NAMES = {
    'dashboard.html':    'Tableau de bord',
    'alerts.html':       'Alertes de sécurité',
    'traffic.html':      'Analyse de trafic',
    'vlan.html':         'Gestion VLAN',
    'interfaces.html':   'Interfaces réseau',
    'Configuration.html':'Configuration / Règles Snort',
    'equipements.html':  'Équipements réseau',
    'users.html':        'Gestion des utilisateurs',
    'logs.html':         'Journal d\'audit',
    'login.html':        'Page de connexion',
  };

  function autoTrackPageVisit() {
    try {
      const path     = window.location.pathname;
      const filename = path.split('/').pop() || 'index.html';
      const name     = PAGE_NAMES[filename] || filename;
      /* Ne pas logguer la page de login — la connexion est loggée séparément */
      if (filename !== 'login.html') {
        pageVisited(name);
      }
    } catch (_) {}
  }

  /* Lancer après le chargement complet du DOM */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoTrackPageVisit);
  } else {
    autoTrackPageVisit();
  }

  /* ══════════════════════════════════════════════════════════════════════
     EXPORT GLOBAL
  ══════════════════════════════════════════════════════════════════════ */
  window.NetGuardAudit = {
    log,
    /* Auth */
    loginSuccess,
    loginFailed,
    logout,
    /* Utilisateurs */
    userCreated,
    userDeleted,
    userUpdated,
    /* Règles */
    ruleCreated,
    ruleModified,
    ruleDeleted,
    rulesReset,
    rulesImported,
    rulesExported,
    /* VLAN */
    vlanCreated,
    vlanDeleted,
    /* Interfaces */
    interfaceDeployed,
    interfaceDeleted,
    /* Switches */
    switchCreated,
    switchDeleted,
    switchUpdated,
    /* TFTP */
    tftpBackup,
    tftpRestore,
    /* Port Mirroring */
    portMirroringCreated,
    portMirroringDeleted,
    /* Logs page */
    logsExported,
    pageVisited,
    /* Admin */
    clear,
  };

  console.info('[NetGuardAudit] ✅ Système d\'audit chargé.');
})();