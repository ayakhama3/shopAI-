/*
  ShopAI - Authentification frontend.
  Role: dialoguer avec Flask/JWT, gerer la session navigateur et proteger les pages.
*/

(function () {
  'use strict';

  const SESSION_KEY = 'shopai_session';
  const TOKEN_KEY = 'shopai_token';
  const PUBLIC_PATHS = ['/login', '/inscription', '/otp'];
  const ADMIN_PATHS = [
    '/dashboard',
    '/dashboard_2',
    '/dashboard_stats',
    '/admin_catalogue',
    '/admin_add_product',
    '/admin_commandes',
    '/admin_fidelite',
    '/admin_messagerie',
    '/admin_parametres',
    '/admin_portefeuille',
  ];

  function showToast(message, type) {
    if (window.ShopAIToast && typeof window.ShopAIToast.show === 'function') {
      window.ShopAIToast.show(message, type);
      return;
    }
    if (typeof window.showToast === 'function' && window.showToast !== showToast) {
      window.showToast(message, type);
      return;
    }
    console[type === 'error' ? 'error' : 'log'](message);
  }

  function getStoredValue(key) {
    return sessionStorage.getItem(key) || localStorage.getItem(key);
  }

  function removeStoredValue(key) {
    sessionStorage.removeItem(key);
    localStorage.removeItem(key);
  }

  function getToken() {
    return getStoredValue(TOKEN_KEY);
  }

  function decodeJwtPayload(token) {
    try {
      const payload = token.split('.')[1];
      const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
      return JSON.parse(decodeURIComponent(escape(atob(normalized))));
    } catch (error) {
      return null;
    }
  }

  function isTokenExpired(token) {
    const payload = decodeJwtPayload(token);
    if (!payload || !payload.exp) return false;
    return Date.now() >= payload.exp * 1000;
  }

  function clearSession() {
    removeStoredValue(SESSION_KEY);
    removeStoredValue(TOKEN_KEY);
  }

  function saveSession(sessionData, token, remember) {
    const storage = remember ? localStorage : sessionStorage;
    storage.setItem(SESSION_KEY, JSON.stringify(sessionData));
    if (token) storage.setItem(TOKEN_KEY, token);

    const other = remember ? sessionStorage : localStorage;
    other.removeItem(SESSION_KEY);
    other.removeItem(TOKEN_KEY);
  }

  function getUser() {
    try {
      const raw = getStoredValue(SESSION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      console.error('[ShopAI][auth] getUser', error);
      return null;
    }
  }

  async function login(email, password) {
    const normalizedEmail = (email || '').trim().toLowerCase();
    if (!normalizedEmail || !password) {
      showToast('Veuillez remplir tous les champs.', 'error');
      return false;
    }

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: normalizedEmail, password }),
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        showToast(data.error || 'Email ou mot de passe incorrect.', 'error');
        return false;
      }

      const user = data.user || {};
      const sessionData = {
        id: user.id || null,
        name: user.username || user.name || normalizedEmail.split('@')[0],
        username: user.username || normalizedEmail.split('@')[0],
        email: user.email || normalizedEmail,
        role: user.role || 'user',
        preferences: Array.isArray(user.preferences) ? user.preferences : [],
        onboardingCompleted: Boolean(user.onboarding_completed),
        avatar: (user.username || normalizedEmail).charAt(0).toUpperCase(),
      };

      const remember = Boolean(document.getElementById('remember')?.checked);
      saveSession(sessionData, data.token, remember);

      // AJOUT : signaler au panier qu'un login vient de se produire pour sync
      sessionStorage.setItem('just_logged_in', 'true');

      showToast('Connexion reussie. Redirection...', 'success');
      window.setTimeout(() => {
        if (sessionData.role === 'admin') {
          window.location.href = '/dashboard';
        } else {
          window.location.href = sessionData.onboardingCompleted ? '/' : '/onboarding';
        }
      }, 450);
      return true;
    } catch (error) {
      console.error('[ShopAI][auth] login', error);
      showToast('Erreur reseau pendant la connexion.', 'error');
      return false;
    }
  }

  async function logout() {
    const token = getToken();
    try {
      if (token) {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        }).catch(() => null);
      }
    } finally {
      clearSession();
      showToast('Deconnexion reussie.', 'info');
      window.setTimeout(() => {
        window.location.href = '/login';
      }, 350);
    }
  }

  function isPublicPage(pathname) {
    return PUBLIC_PATHS.includes(pathname);
  }

  function isAdminPage(pathname) {
    return ADMIN_PATHS.includes(pathname);
  }

  function redirectToLogin() {
    clearSession();
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
  }

  function checkAuth() {
    const token = getToken();
    const user = getUser();
    if (!user || (token && isTokenExpired(token))) {
      redirectToLogin();
      return false;
    }
    return true;
  }

  function checkRole(requiredRole) {
    if (!checkAuth()) return false;
    const user = getUser();
    if (requiredRole === 'admin' && user.role !== 'admin') {
      showToast('Acces reserve aux administrateurs.', 'error');
      window.setTimeout(() => {
        window.location.href = '/';
      }, 600);
      return false;
    }
    if (requiredRole === 'user' && user.role === 'admin') {
      window.location.href = '/dashboard';
      return false;
    }
    return true;
  }

  function protectCurrentPage() {
    const pathname = window.location.pathname;
    if (isPublicPage(pathname)) return true;
    return checkRole(isAdminPage(pathname) ? 'admin' : 'user');
  }

  window.ShopAIAuth = {
    login,
    logout,
    checkAuth,
    checkRole,
    protectCurrentPage,
    getUser,
    getToken,
    clearSession,
    toast: showToast,
  };

  window.login = login;
  window.logout = logout;
  window.checkAuth = checkAuth;
  window.checkRole = checkRole;
  window.getUser = getUser;

  document.addEventListener('DOMContentLoaded', protectCurrentPage);
})();