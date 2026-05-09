(function () {
  const host = document.getElementById('sidebar-root');

  if (!host || !window.NetGuardAuth) {
    return;
  }

  const currentPage = host.dataset.page || '';

  if (!window.NetGuardAuth.requirePageAccess(currentPage)) {
    return;
  }

  const session = window.NetGuardAuth.getSession();

  const links = [
    { id: 'dashboard', label: 'Dashboard', href: 'dashboard.html', icon: 'monitor' },
    { id: 'vlan', label: 'VLAN', href: 'vlan.html', icon: 'vlan' },
    { id: 'interfaces', label: 'Interfaces', href: 'interfaces.html', icon: 'ports' },
    { id: 'alerts', label: 'Alerts', href: 'alerts.html', icon: 'alert' },
    { id: 'traffic', label: 'Traffic', href: 'traffic.html', icon: 'traffic' },
    { id: 'configuration', label: 'Configuration', href: 'Configuration.html', icon: 'config' },
    { id: 'users', label: 'Users', href: 'users.html', icon: 'users' },
    { id: 'equipements', label: 'Équipements', href: 'equipements.html', icon: 'switch' },
    { id: 'logs', label: 'Logs', href: 'logs.html', icon: 'logs' }
  ].filter((link) => window.NetGuardAuth.canAccessPage(link.id));

  const icons = {
    vlan: '<path d="M21 5H3a1 1 0 0 0-1 1v3a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1zM21 13H3a1 1 0 0 0-1 1v3a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1z"></path>',
    ports: '<circle cx="12" cy="12" r="3"></circle><path d="M2 12h3M19 12h3M12 2v3M12 19v3"></path>',
    alert: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line>',
    monitor: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>',
    traffic: '<path d="M3 12h4l2-6 4 12 2-6h6"></path>',
    config: '<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"></path><path d="M18.37 7.29l1.65-1.65a1 1 0 0 0 0-1.41l-1.25-1.25a1 1 0 0 0-1.41 0L15.71 4.63a7.09 7.09 0 0 0-7.42 0L6.64 2.98a1 1 0 0 0-1.41 0L3.98 4.23a1 1 0 0 0 0 1.41L5.63 7.29a7.09 7.09 0 0 0 0 7.42L3.98 16.36a1 1 0 0 0 0 1.41l1.25 1.25a1 1 0 0 0 1.41 0l1.65-1.65a7.09 7.09 0 0 0 7.42 0l1.65 1.65a1 1 0 0 0 1.41 0l1.25-1.25a1 1 0 0 0 0-1.41l-1.65-1.65a7.09 7.09 0 0 0 0-7.42z"></path>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><path d="M20 8v6"></path><path d="M23 11h-6"></path>',
    logs: '<path d="M9 3h6"></path><path d="M10 7h4"></path><rect x="4" y="3" width="16" height="18" rx="2"></rect><path d="M8 12h8"></path><path d="M8 16h8"></path>',
    switch: '<rect x="2" y="4" width="20" height="6" rx="1" ry="1"></rect><rect x="2" y="14" width="20" height="6" rx="1" ry="1"></rect><line x1="6" y1="7" x2="6.01" y2="7"></line><line x1="6" y1="17" x2="6.01" y2="17"></line>'
  };

  const renderIcon = (type) =>
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    icons[type] +
    '</svg>';

  host.innerHTML = `
    <aside class="app-sidebar">
      <a class="sidebar-logo" href="${window.NetGuardAuth.getDefaultPage(session?.role)}" aria-label="Go to home">
        ${renderIcon('vlan')}
      </a>
      <nav class="sidebar-nav" aria-label="Main navigation">
        ${links.map(
          (link) => `
            <a class="sidebar-link ${link.id === currentPage ? 'active' : ''}" href="${link.href}">
              ${renderIcon(link.icon)}
              <span>${link.label}</span>
            </a>
          `
        ).join('')}
      </nav>
    </aside>
  `;
})();
