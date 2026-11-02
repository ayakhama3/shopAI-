// historique.js — logique dynamique de la page Historique des Commandes
// ShopAI

(function () {
  // ---------------------------------------------------------------------
  // CONFIG
  // ---------------------------------------------------------------------
  const ENDPOINTS = {
    list: (params) => `/api/orders?${params.toString()}`,
    invoice: (orderId) => `/api/invoices/${orderId}/download`,
    reorder: (orderId) => `/api/orders/${orderId}/reorder`,
  };

  const STATUS_MAP = {
    created: {
      label: "Créée",
      badgeClass: "bg-surface-container-high text-on-surface-variant",
      icon: "receipt_long",
    },
    paid: {
      label: "Payée",
      badgeClass: "bg-secondary-container text-on-secondary-container",
      icon: "payments",
    },
    shipped: {
      label: "Expédiée",
      badgeClass: "bg-primary-fixed text-on-primary-fixed",
      icon: "local_shipping",
    },
    delivered: {
      label: "Livrée",
      badgeClass: "bg-[#15803d]/10 text-[#15803d]",
      icon: "check_circle",
    },
    cancelled: {
      label: "Annulée",
      badgeClass: "bg-error-container text-error",
      icon: "cancel",
    },
  };

  // Statuts considérés comme "à venir" / en cours (toujours affichés)
  const UPCOMING_STATUSES = ["created", "paid", "shipped"];
  // Nombre de commandes terminées (livrées/annulées) à conserver
  const RECENT_COMPLETED_LIMIT = 3;
  // Sécurité : nombre max de pages qu'on va parcourir côté API pour
  // reconstituer l'historique complet avant de filtrer
  const MAX_PAGES_TO_FETCH = 10;

  const state = {
    period: "",
    status: "",
    loading: false,
  };

  let els = {};

  // ---------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------
  function authHeaders() {
    const token =
      window.ShopAIAuth && typeof window.ShopAIAuth.getToken === "function"
        ? window.ShopAIAuth.getToken()
        : null;
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function showToast(message, type) {
    if (window.ShopAIToast && typeof window.ShopAIToast.show === "function") {
      window.ShopAIToast.show(message, type);
    } else {
      console.log(`[${type || "info"}] ${message}`);
    }
  }

  function formatPrice(value) {
    const num = Number(value);
    if (Number.isNaN(num)) return value;
    return `${num.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} DH`;
  }

  // ---------------------------------------------------------------------
  // Rendu d'une carte de commande
  // ---------------------------------------------------------------------
  function renderOrderCard(order) {
    const statusInfo = STATUS_MAP[order.status] || {
      label: order.status || "—",
      badgeClass: "bg-surface-container-high text-on-surface-variant",
      icon: "info",
    };

    const items = Array.isArray(order.items) ? order.items : [];
    const firstItems = items.slice(0, 2);
    const remainingCount = Math.max(items.length - firstItems.length, 0);

    const thumbsHtml = firstItems
      .map(
        (item) => `
        <img alt="${item.name || "Article"}" class="h-20 w-20 rounded-lg border-4 border-surface-container-lowest object-cover bg-surface-container" src="${item.image || "https://via.placeholder.com/80?text=Article"}"/>
      `
      )
      .join("");

    const itemsLabel = items.length
      ? items.slice(0, 1).map((i) => i.name).join(", ")
      : "Commande";

    const remainingLabel = remainingCount > 0
      ? `<p class="font-label-sm text-on-surface-variant">+ ${remainingCount} autre(s) article(s)</p>`
      : "";

    let actionsHtml = "";
    if (order.status === "delivered") {
      actionsHtml = `
        <button data-action="invoice" class="flex items-center gap-2 px-4 py-2 rounded-lg border border-outline-variant font-label-sm text-primary hover:bg-surface-container-low transition-colors">
          <span class="material-symbols-outlined text-[20px]">description</span>
          Facture PDF
        </button>
        <button data-action="details" class="flex items-center gap-2 px-4 py-2 rounded-lg border border-outline-variant font-label-sm text-primary hover:bg-surface-container-low transition-colors">
          <span class="material-symbols-outlined text-[20px]">visibility</span>
          Détails
        </button>
      `;
    } else if (order.status === "shipped" || order.status === "paid") {
      actionsHtml = `
        <button data-action="track" class="flex items-center gap-2 px-4 py-2 rounded-lg border border-outline-variant font-label-sm text-primary hover:bg-surface-container-low transition-colors">
          <span class="material-symbols-outlined text-[20px]">visibility</span>
          Suivre le colis
        </button>
        <button data-action="details" class="flex items-center gap-2 px-4 py-2 rounded-lg border border-outline-variant font-label-sm text-primary hover:bg-surface-container-low transition-colors">
          <span class="material-symbols-outlined text-[20px]">info</span>
          Détails
        </button>
      `;
    } else {
      actionsHtml = `
        <button data-action="details" class="flex items-center gap-2 px-4 py-2 rounded-lg border border-outline-variant font-label-sm text-primary hover:bg-surface-container-low transition-colors">
          <span class="material-symbols-outlined text-[20px]">visibility</span>
          Détails
        </button>
      `;
    }

    const dimmedClass = order.status === "cancelled" ? "opacity-75 grayscale-[0.5]" : "";

    return `
      <article data-order-id="${order.id}" class="bg-surface-container-lowest rounded-xl order-card-shadow border border-outline-variant/20 overflow-hidden ${dimmedClass}">
        <div class="p-6 border-b border-outline-variant/10 flex flex-wrap items-center justify-between gap-4">
          <div class="flex items-center gap-6">
            <div>
              <p class="font-label-sm text-on-surface-variant">COMMANDE</p>
              <p class="font-bold text-on-surface">#${order.reference || order.id}</p>
            </div>
            <div>
              <p class="font-label-sm text-on-surface-variant">DATE</p>
              <p class="font-bold text-on-surface">${order.date || "—"}</p>
            </div>
            <div>
              <p class="font-label-sm text-on-surface-variant">TOTAL</p>
              <p class="font-price-display text-price-display text-primary">${formatPrice(order.total)}</p>
            </div>
          </div>
          <span class="px-4 py-1.5 rounded-full font-label-sm font-bold ${statusInfo.badgeClass} flex items-center gap-1.5">
            <span class="material-symbols-outlined text-[18px]">${statusInfo.icon}</span>
            ${statusInfo.label}
          </span>
        </div>
        <div class="p-6 flex flex-col md:flex-row gap-8 items-center">
          <div class="flex -space-x-3 overflow-hidden flex-shrink-0">
            ${thumbsHtml}
          </div>
          <div class="flex-grow text-center md:text-left">
            <p class="font-body-md text-on-surface font-semibold">${itemsLabel}</p>
            ${remainingLabel}
          </div>
          <div class="flex flex-wrap gap-3 justify-center">
            ${actionsHtml}
          </div>
        </div>
      </article>
    `;
  }

  // ---------------------------------------------------------------------
  // Récupération de TOUTES les commandes (toutes pages confondues),
  // puis filtrage : commandes "à venir" + 3 dernières terminées
  // ---------------------------------------------------------------------
  async function fetchAllOrdersAcrossPages(period, status) {
    let allOrders = [];
    let page = 1;

    while (page <= MAX_PAGES_TO_FETCH) {
      const params = new URLSearchParams();
      params.set("page", String(page));
      if (period) params.set("period", period);
      if (status) params.set("status", status);

      const res = await fetch(ENDPOINTS.list(params), { headers: authHeaders() });

      if (res.status === 401) {
        window.location.href = "/login";
        return allOrders;
      }
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || `Erreur ${res.status}`);
      }

      const data = await res.json();
      const orders = data.orders || [];
      allOrders = allOrders.concat(orders);

      const hasMore = data.has_more || (orders.length > 0 && page < data.pages);
      if (!hasMore || orders.length === 0) break;
      page += 1;
    }

    return allOrders;
  }

  function filterToRecentAndUpcoming(allOrders) {
    // On suppose que l'API renvoie les commandes triées du plus récent au plus ancien.
    const upcoming = allOrders.filter((o) => UPCOMING_STATUSES.includes(o.status));
    const completed = allOrders.filter((o) => !UPCOMING_STATUSES.includes(o.status));
    const recentCompleted = completed.slice(0, RECENT_COMPLETED_LIMIT);
    return [...upcoming, ...recentCompleted];
  }

  async function fetchOrders() {
    if (state.loading) return;
    state.loading = true;

    els.ordersList.innerHTML = "";
    els.ordersLoading.classList.remove("hidden");
    els.ordersEmpty.classList.add("hidden");
    els.paginationContainer.classList.add("hidden"); // plus de pagination, liste plafonnée

    try {
      const allOrders = await fetchAllOrdersAcrossPages(state.period, state.status);
      const toDisplay = filterToRecentAndUpcoming(allOrders);

      if (toDisplay.length === 0) {
        els.ordersEmpty.classList.remove("hidden");
      } else {
        toDisplay.forEach((order) => {
          els.ordersList.insertAdjacentHTML("beforeend", renderOrderCard(order));
        });
      }
    } catch (err) {
      console.error(err);
      showToast(err.message || "Erreur lors du chargement des commandes.", "error");
      els.ordersEmpty.classList.remove("hidden");
      els.ordersEmpty.innerHTML = `
        <div class="text-center py-10">
          <span class="material-symbols-outlined text-4xl text-error mb-2">error</span>
          <p class="text-on-surface-variant">${err.message || "Erreur de chargement"}</p>
          <button onclick="location.reload()" class="mt-4 bg-primary text-on-primary px-6 py-2 rounded-lg font-bold">Réessayer</button>
        </div>
      `;
    } finally {
      els.ordersLoading.classList.add("hidden");
      state.loading = false;
    }
  }

  // ---------------------------------------------------------------------
  // Actions sur une commande
  // ---------------------------------------------------------------------
  function goToOrderDetails(orderId) {
    sessionStorage.setItem("shopai_last_order_id", orderId);
    window.location.href = "/suivi_1";
  }

  async function downloadInvoice(orderId, btn) {
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="material-symbols-outlined text-[20px] animate-spin">progress_activity</span> Facture...`;
    try {
      window.open(ENDPOINTS.invoice(orderId), "_blank");
    } catch (err) {
      console.error(err);
      showToast("Impossible d'ouvrir la facture.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }

  function handleListClick(e) {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const article = btn.closest("[data-order-id]");
    if (!article) return;
    const orderId = article.dataset.orderId;
    const action = btn.dataset.action;

    switch (action) {
      case "details":
      case "track":
        goToOrderDetails(orderId);
        break;
      case "invoice":
        downloadInvoice(orderId, btn);
        break;
      default:
        break;
    }
  }

  // ---------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------
  function init() {
    els = {
      ordersList: document.getElementById("orders-list"),
      ordersLoading: document.getElementById("orders-loading"),
      ordersEmpty: document.getElementById("orders-empty"),
      paginationContainer: document.getElementById("pagination-container"),
      applyFiltersBtn: document.getElementById("apply-filters-btn"),
      filterPeriod: document.getElementById("filter-period"),
      filterStatus: document.getElementById("filter-status"),
    };

    if (!els.ordersList) return;

    els.applyFiltersBtn?.addEventListener("click", () => {
      state.period = els.filterPeriod.value;
      state.status = els.filterStatus.value;
      fetchOrders();
    });

    els.ordersList.addEventListener("click", handleListClick);

    fetchOrders();
  }

  document.addEventListener("DOMContentLoaded", init);
})();