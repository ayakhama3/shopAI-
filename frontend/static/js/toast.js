/*
  ShopAI - Toast notifications.
  Role: afficher des retours courts et professionnels en bas a droite.
*/

(function () {
  'use strict';

  const COLORS = {
    success: '#16a34a',
    error: '#dc2626',
    warning: '#d97706',
    info: '#2563eb',
  };

  function ensureContainer() {
    let container = document.getElementById('shopai-toast-container');
    if (container) return container;

    container = document.createElement('div');
    container.id = 'shopai-toast-container';
    container.setAttribute('aria-live', 'polite');
    container.style.cssText = [
      'position:fixed',
      'right:24px',
      'bottom:24px',
      'z-index:99999',
      'display:flex',
      'flex-direction:column',
      'gap:10px',
      'pointer-events:none',
      'max-width:min(360px,calc(100vw - 32px))',
    ].join(';');
    document.body.appendChild(container);
    return container;
  }

  function show(message, type = 'info', delay = 2800) {
    const container = ensureContainer();
    const toast = document.createElement('div');
    const color = COLORS[type] || COLORS.info;

    toast.textContent = message;
    toast.style.cssText = [
      'pointer-events:auto',
      'background:rgba(17,24,39,0.96)',
      'color:#fff',
      `border-left:5px solid ${color}`,
      'border-radius:8px',
      'box-shadow:0 18px 42px rgba(15,23,42,0.25)',
      'font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
      'font-size:14px',
      'line-height:1.4',
      'padding:12px 14px',
      'transform:translateY(8px)',
      'opacity:0',
      'transition:opacity 180ms ease, transform 180ms ease',
    ].join(';');

    container.appendChild(toast);
    requestAnimationFrame(() => {
      toast.style.opacity = '1';
      toast.style.transform = 'translateY(0)';
    });

    window.setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      window.setTimeout(() => toast.remove(), 200);
    }, delay);
  }

  window.ShopAIToast = { show };
  window.showToast = show;
})();
