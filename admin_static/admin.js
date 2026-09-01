const API_BASE = "";
let cachedOrders = [];
let cbuRate = 12850;
let pendingDelete = { type: null, id: null };

// ==================== XSS HIMOYASI ====================
function escapeHtml(value) {
  // XSS himoyasi: barcha maxsus belgilarni HTML entity ga aylantirish
  if (value === null || value === undefined) return "";
  const str = String(value);
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/`/g, "&#96;");
}

function escapeAttr(value) {
  // HTML atribut ichida ishlatish uchun qo'shimcha himoya
  return escapeHtml(value).replace(/\n/g, "&#10;").replace(/\r/g, "&#13;");
}

// ==================== AVTOMATIK TAKLIF (SHAHARLAR) ====================
function setupFlightAutocomplete(inputId, hiddenId, boxId) {
  const input = document.getElementById(inputId);
  const hidden = document.getElementById(hiddenId);
  const box = document.getElementById(boxId);
  if (!input || !hidden || !box) return;
  let debounceTimer = null;

  input.addEventListener("input", () => {
    hidden.value = "";
    const term = input.value.trim();
    clearTimeout(debounceTimer);
    if (term.length < 2) {
      box.classList.add("hidden");
      box.innerHTML = "";
      return;
    }
    debounceTimer = setTimeout(async () => {
      try {
        const url = `https://autocomplete.travelpayouts.com/places2?term=${encodeURIComponent(term)}&locale=uz&types[]=city&types[]=airport`;
        const res = await fetch(url);
        const items = await res.json();
        if (!items || !items.length) {
          box.classList.add("hidden");
          box.innerHTML = "";
          return;
        }
        box.innerHTML = "";
        items.slice(0, 8).forEach(item => {
          const label = item.name + (item.country_name ? `, ${item.country_name}` : "");
          const el = document.createElement("div");
          el.className = "a-suggestion-item";
          el.innerHTML = `<span class="a-suggestion-code">${item.code}</span>${label}`;
          el.addEventListener("mousedown", () => {
            input.value = label;
            hidden.value = item.code;
            box.classList.add("hidden");
          });
          box.appendChild(el);
        });
        box.classList.remove("hidden");
      } catch (e) {
        console.error("Autocomplete xatosi:", e);
      }
    }, 300);
  });

  input.addEventListener("blur", () => {
    setTimeout(() => box.classList.add("hidden"), 200);
  });
}

setupFlightAutocomplete("f_origin", "f_origin_code", "f_origin_suggestions");
setupFlightAutocomplete("f_destination", "f_destination_code", "f_destination_suggestions");

// ==================== LOGIN VA AVTORIZATSIYA ====================
function getPassword() {
  return localStorage.getItem("admin_password") || "";
}
function setPassword(pw) {
  localStorage.setItem("admin_password", pw);
}
function clearPassword() {
  localStorage.removeItem("admin_password");
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Password": getPassword(),
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    clearPassword();
    showLogin();
    throw new Error("Parol xato yoki seans tugagan");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Xatolik yuz berdi");
  }
  return res.json();
}

function showLogin() {
  const loginScreen = document.getElementById("login-screen");
  const panel = document.getElementById("panel");
  if (loginScreen) loginScreen.classList.remove("hidden");
  if (panel) panel.classList.add("hidden");
}

function showPanel() {
  const loginScreen = document.getElementById("login-screen");
  const panel = document.getElementById("panel");
  if (loginScreen) loginScreen.classList.add("hidden");
  if (panel) panel.classList.remove("hidden");
  loadOrders();
  loadFlights();
}

const loginForm = document.getElementById("login-form");
if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const pw = document.getElementById("login-password").value;
    try {
      const res = await fetch(`${API_BASE}/api/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: pw }),
      });
      if (!res.ok) throw new Error("Noto'g'ri parol");
      setPassword(pw);
      const errEl = document.getElementById("login-error");
      if (errEl) errEl.classList.add("hidden");
      showPanel();
    } catch (err) {
      const errEl = document.getElementById("login-error");
      if (errEl) errEl.classList.remove("hidden");
    }
  });
}

const logoutBtn = document.getElementById("logout-btn");
if (logoutBtn) {
  logoutBtn.addEventListener("click", () => {
    clearPassword();
    showLogin();
  });
}

// Sahifa yuklanganda tekshirish
(async function initAuth() {
  if (!getPassword()) { showLogin(); return; }
  try {
    await apiFetch("/api/admin/orders");
    showPanel();
  } catch {
    showLogin();
  }
})();

// ==================== TABS ====================
document.querySelectorAll(".a-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".a-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".a-tab-content").forEach(c => c.classList.add("hidden"));
    tab.classList.add("active");
    const target = document.getElementById(`tab-${tab.dataset.tab}`);
    if (target) target.classList.remove("hidden");

    if (tab.dataset.tab === "orders") {
      loadOrders();
    } else if (tab.dataset.tab === "all-flights") {
      loadFlights();
    } else if (tab.dataset.tab === "visa-applications") {
      loadVisaApplicationsAdmin();
    } else if (tab.dataset.tab === "price-alerts") {
      loadPriceAlertsAdmin();
    }
  });
});

// ==================== BUYURTMALAR VA STATISTIKA ====================
const STATUS_LABELS = {
  new: "🆕 Yangi",
  awaiting_confirmation: "⏳ Tasdiq kutilmoqda",
  confirmed: "✅ Tasdiqlangan",
  rejected: "❌ Rad etilgan",
};

async function loadOrders() {
  const statusFilter = document.getElementById("status-filter");
  const status = statusFilter ? statusFilter.value : "";
  const qs = status ? `?status=${status}` : "";
  try {
    const data = await apiFetch(`/api/admin/orders${qs}`);
    cachedOrders = data.orders || [];
    updateDashboardStats(cachedOrders);
    renderOrders(cachedOrders);
  } catch (e) {
    console.error("Buyurtmalarni yuklashda xato:", e);
  }
}

function updateDashboardStats(orders) {
  const total = orders.length;
  const pending = orders.filter(o => o.status === "new" || o.status === "awaiting_confirmation").length;
  const confirmed = orders.filter(o => o.status === "confirmed").length;
  const revenue = orders
    .filter(o => o.status === "confirmed")
    .reduce((sum, o) => sum + (parseFloat(o.price) || 0), 0);

  const statTotal = document.getElementById("stat-total-orders");
  const statPending = document.getElementById("stat-pending-orders");
  const statConfirmed = document.getElementById("stat-confirmed-orders");
  const statRevenue = document.getElementById("stat-revenue");

  if (statTotal) statTotal.innerText = total;
  if (statPending) statPending.innerText = pending;
  if (statConfirmed) statConfirmed.innerText = confirmed;
  if (statRevenue) statRevenue.innerText = `$${revenue.toLocaleString()}`;
  const statRevenueUzs = document.getElementById("stat-revenue-uzs");
  if (statRevenueUzs) {
    const uzs = Math.round(revenue * cbuRate);
    statRevenueUzs.innerText = `${uzs.toLocaleString("uz-UZ").replace(/,/g, " ")} so'm`;
  }
}

function filterOrdersLocally() {
  const searchInput = document.getElementById("orders-search");
  const query = searchInput ? searchInput.value.toLowerCase().trim() : "";
  if (!query) {
    renderOrders(cachedOrders);
    return;
  }
  const filtered = cachedOrders.filter(order => {
    const p_raw = order.passports;
    const passport = (Array.isArray(p_raw) && p_raw[0]) ? p_raw[0] : (p_raw && typeof p_raw === "object" ? p_raw : {});
    const fullName = `${passport.first_name || ""} ${passport.last_name || ""}`.toLowerCase();
    const pNum = (passport.passport_number || "").toLowerCase();
    const orderId = String(order.id || "");
    const route = `${order.origin || ""} ${order.destination || ""}`.toLowerCase();
    return fullName.includes(query) || pNum.includes(query) || orderId.includes(query) || route.includes(query);
  });
  renderOrders(filtered);
}

function renderOrders(orders) {
  const list = document.getElementById("orders-list");
  const empty = document.getElementById("orders-empty");
  if (!list) return;
  list.innerHTML = "";

  if (!orders || !orders.length) {
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");

  orders.forEach(order => {
    const p_raw = order.passports;
    const passport = (Array.isArray(p_raw) && p_raw[0]) ? p_raw[0] : (p_raw && typeof p_raw === "object" ? p_raw : {});
    const statusClass = order.status === "confirmed" ? "confirmed" : order.status === "rejected" ? "rejected" : "";
    const origin = escapeHtml((order.origin || "-").toUpperCase());
    const destination = escapeHtml((order.destination || "-").toUpperCase());
    const card = document.createElement("div");
    card.className = `order-card ${statusClass}`;
    
    // XSS himoyasi: barcha ma'lumotlarni escape qilish
    const orderId = escapeHtml(String(order.id || ""));
    const firstName = escapeHtml(passport.first_name || "-");
    const lastName = escapeHtml(passport.last_name || "");
    const passportNum = escapeHtml(passport.passport_number || "-");
    const departDate = escapeHtml(order.depart_date || "-");
    const passengers = escapeHtml(String(order.passengers || 1));
    const price = escapeHtml(String(order.price ?? "-"));
    const telegramId = escapeHtml(String(order.telegram_user_id || "-"));
    const username = escapeHtml(order.username || "");
    const birthYear = escapeHtml(passport.birth_year || "");
    const paymentUrl = escapeAttr(order.payment_screenshot_url || "");
    const orderStatus = escapeHtml(order.status || "new");
    
    card.innerHTML = `
      <div class="order-top">
        <div class="order-id">#${orderId} — ✈️ ${origin} ➔ ${destination}</div>
        <div class="order-status-badge ${statusClass}">${STATUS_LABELS[orderStatus] || orderStatus || "Noma'lum"}</div>
      </div>
      
      <div class="order-details-grid">
        <div class="order-detail-item">
          <span>YO'LOVCHI F.I.SH</span>
          <strong>${firstName} ${lastName}</strong>
        </div>
        <div class="order-detail-item">
          <span>PASPORT RAQAMI</span>
          <strong>${passportNum}</strong>
        </div>
        <div class="order-detail-item">
          <span>UCHISH SANASI</span>
          <strong>${departDate} (${passengers} yo'lovchi)</strong>
        </div>
        <div class="order-detail-item">
          <span>SUMMA (TO'LOV)</span>
          <strong style="color: var(--primary); font-size: 15px;">$${price}</strong>
        </div>
      </div>

      <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px; display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
        <span>👤 Telegram: <code>${telegramId}</code> ${username ? "(@" + username + ")" : ""}</span>
        ${birthYear ? `<span style="background:#F1F5F9; padding:2px 8px; border-radius:8px;">🎂 ${birthYear}</span>` : ""}
      </div>

      ${paymentUrl ? `
        <div style="margin-top: 8px; margin-bottom: 8px;">
          <span style="font-size: 10.5px; font-weight: 800; color: var(--text-muted); display: block; margin-bottom: 6px; letter-spacing:0.5px;">TO'LOV CHEKI (BOSING):</span>
          <img class="order-photo-thumb" src="${paymentUrl}" alt="To'lov cheki" onclick="openImgModal('${paymentUrl}')">
        </div>
      ` : `<div style="font-size:11px; color:#94A3B8; margin:6px 0;">💳 To'lov cheki hali yuklanmagan</div>`}

      <div class="order-actions">
        ${orderStatus === "new" || orderStatus === "awaiting_confirmation" ? `
          <button class="order-btn confirm" data-id="${orderId}" data-action="confirm">✅ Tasdiqlash & PDF Yuborish</button>
          <button class="order-btn reject" data-id="${orderId}" data-action="reject">❌ Rad Etish</button>
        ` : `
          <span style="font-size:11px; color:var(--text-muted); padding:8px 0;">☑️ ${STATUS_LABELS[orderStatus] || orderStatus}</span>
        `}
        <button class="order-btn delete" data-id="${orderId}" data-action="delete-order" title="Buyurtmani o'chirish">🗑 O'chirish</button>
      </div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll("[data-action='confirm']").forEach(btn => {
    btn.addEventListener("click", () => confirmOrder(btn.dataset.id));
  });
  list.querySelectorAll("[data-action='reject']").forEach(btn => {
    btn.addEventListener("click", () => rejectOrder(btn.dataset.id));
  });
  list.querySelectorAll("[data-action='delete-order']").forEach(btn => {
    btn.addEventListener("click", () => openDeleteModal("order", btn.dataset.id));
  });
}

async function confirmOrder(id) {
  if (!confirm(`#${id} raqamli buyurtmani tasdiqlaysizmi?\n\nMijozga avtomatik ravishda chiroyli PDF elektron chipta yuboriladi.`)) return;
  try {
    await apiFetch(`/api/admin/orders/${id}/confirm`, { method: "POST" });
    alert(`✅ Buyurtma #${id} muvaffaqiyatli tasdiqlandi!`);
    loadOrders();
  } catch (e) {
    alert("❌ Xatolik: " + e.message);
  }
}

async function rejectOrder(id) {
  const reason = prompt("Rad etish sababini kiriting:", "To'lov tasdiqlanmadi");
  if (reason === null) return;
  try {
    await apiFetch(`/api/admin/orders/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
    alert(`Buyurtma #${id} rad etildi.`);
    loadOrders();
  } catch (e) {
    alert("Xatolik: " + e.message);
  }
}

// ==================== OXIRGI O'CHIRISH TUGMASI LOGIKASI ====================
function openDeleteModal(type, id) {
  pendingDelete = { type, id };
  const modal = document.getElementById("deleteConfirmModal");
  const title = document.getElementById("delete-modal-title");
  const desc = document.getElementById("delete-modal-desc");
  if (type === "order") {
    if (title) title.innerText = `Buyurtma #${id} o'chirilsinmi?`;
    if (desc) desc.innerText = "Buyurtma va pasport ma'lumotlari butunlay o'chiriladi. Bu amalni ortga qaytarib bo'lmaydi!";
  } else if (type === "flight") {
    if (title) title.innerText = `Chipta #${id} o'chirilsinmi?`;
    if (desc) desc.innerText = "Tanlangan aviachipta butunlay o'chiriladi.";
  } else if (type === "visa") {
    if (title) title.innerText = `Viza arizasi #${id} o'chirilsinmi?`;
    if (desc) desc.innerText = "Ariza va undagi shaxsiy ma'lumotlar butunlay o'chiriladi.";
  } else if (type === "price-alert") {
    if (title) title.innerText = `Narx obunasi #${id} o'chirilsinmi?`;
    if (desc) desc.innerText = "Tanlangan narx obunasi butunlay o'chiriladi.";
  }
  if (modal) modal.classList.remove("hidden");
}

function closeDeleteModal() {
  const modal = document.getElementById("deleteConfirmModal");
  if (modal) modal.classList.add("hidden");
  pendingDelete = { type: null, id: null };
}

const deleteConfirmBtn = document.getElementById("delete-confirm-btn");
if (deleteConfirmBtn) {
  deleteConfirmBtn.addEventListener("click", async () => {
    const { type, id } = pendingDelete;
    if (!id) { closeDeleteModal(); return; }
    try {
      if (type === "order") {
        await apiFetch(`/api/admin/orders/${id}`, { method: "DELETE" });
        loadOrders();
      } else if (type === "flight") {
        await apiFetch(`/api/admin/flights/${id}`, { method: "DELETE" });
        loadFlights();
      } else if (type === "visa") {
        await apiFetch(`/api/admin/visa-applications/${id}`, { method: "DELETE" });
        loadVisaApplicationsAdmin();
      } else if (type === "price-alert") {
        await apiFetch(`/api/admin/price-alerts/${id}`, { method: "DELETE" });
        loadPriceAlertsAdmin();
      }
      closeDeleteModal();
    } catch (e) {
      alert("O'chirishda xatolik: " + e.message);
    }
  });
}

const refreshOrdersBtn = document.getElementById("refresh-orders");
if (refreshOrdersBtn) refreshOrdersBtn.addEventListener("click", loadOrders);

const statusFilterEl = document.getElementById("status-filter");
if (statusFilterEl) statusFilterEl.addEventListener("change", loadOrders);

// ==================== EXCEL / CSV EKSPORT ====================
async function exportOrders(format, btn, defaultLabel) {
  const statusFilter = document.getElementById("status-filter");
  const status = statusFilter ? statusFilter.value : "";
  const params = new URLSearchParams({ format });
  if (status) params.set("status", status);

  if (btn) { btn.innerText = "⏳ Yuklanmoqda..."; btn.disabled = true; }
  try {
    const res = await fetch(`${API_BASE}/api/admin/orders/export?${params.toString()}`, {
      headers: { "X-Admin-Password": getPassword() }
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Xatolik" }));
      throw new Error(err.detail || "Export xatosi");
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    const disposition = res.headers.get("Content-Disposition") || "";
    let filename = `buyurtmalar_${new Date().toISOString().slice(0, 10)}.${format}`;
    const match = disposition.match(/filename=([^;]+)/);
    if (match) filename = match[1].replace(/"/g, "").trim();
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (e) {
    alert("Eksport xatosi: " + e.message);
  } finally {
    if (btn) { btn.innerText = defaultLabel; btn.disabled = false; }
  }
}

const exportExcelBtn = document.getElementById("export-excel-btn");
if (exportExcelBtn) {
  exportExcelBtn.addEventListener("click", () =>
    exportOrders("xlsx", exportExcelBtn, "📊 Excel Yuklab Olish"));
}

const exportCsvBtn = document.getElementById("export-csv-btn");
if (exportCsvBtn) {
  exportCsvBtn.addEventListener("click", () =>
    exportOrders("csv", exportCsvBtn, "📄 CSV"));
}

// ==================== QO'LDA CHIPTA QO'SHISH VA RO'YXAT ====================
async function loadFlights() {
  try {
    const data = await apiFetch("/api/admin/flights");
    renderFlights(data.flights || []);
  } catch (e) {
    console.error("Chiptalarni olishda xato:", e);
  }
}

function renderFlights(flights) {
  const list = document.getElementById("flights-list");
  if (!list) return;
  list.innerHTML = "";
  if (!flights || !flights.length) {
    list.innerHTML = `<div class="a-empty"><div class="empty-icon">✈️</div><p style="margin-top:8px;">Hali chiptalar qo'shilmagan.</p><p class="a-text">Yuqoridagi forma orqali yangi chipta qo'shing — u Mini Appda eng yuqori o'rinda chiqadi.</p></div>`;
    return;
  }
  flights.forEach(f => {
    // XSS himoyasi: barcha ma'lumotlarni escape qilish
    const origin = escapeHtml((f.origin || "-").toUpperCase());
    const destination = escapeHtml((f.destination || "-").toUpperCase());
    const departDate = escapeHtml(f.depart_date || "");
    const departTime = escapeHtml(f.departure_time || "");
    const airline = escapeHtml(f.airline || "");
    const flightNum = escapeHtml(f.flight_number || "-");
    const seats = escapeHtml(String(f.seats_available ?? "Ko'p"));
    const transfers = escapeHtml(String(f.transfers ?? 0));
    const isActive = f.is_active ? "✅ Faol" : "⏸ Nofaol";
    const price = escapeHtml(String(f.price ?? 0));
    const flightId = escapeHtml(String(f.id || ""));
    
    const card = document.createElement("div");
    card.className = "flight-item-card";
    card.innerHTML = `
      <div>
        <div class="flight-route-title">✈️ ${origin} ➔ ${destination}</div>
        <div style="font-size: 13px; color: var(--text-muted); margin-top: 6px; line-height:1.4;">
          📅 ${departDate} ${departTime} | 🛫 ${airline} (${flightNum})<br>
          💺 O'rindiqlar: <strong>${seats}</strong> | 🔄 ${transfers} tranzit | ${isActive}
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 14px;">
        <div style="text-align:right;">
          <div style="font-size: 20px; font-weight: 800; color: var(--primary);">$${price}</div>
          <div style="font-size:10px; color:var(--text-muted);">USD</div>
        </div>
        <button class="flight-del-btn" data-id="${flightId}">🗑 O'chirish</button>
      </div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll(".flight-del-btn").forEach(btn => {
    btn.addEventListener("click", () => openDeleteModal("flight", btn.dataset.id));
  });
}

const addFlightBtn = document.getElementById("btn-add-flight");
if (addFlightBtn) {
  addFlightBtn.addEventListener("click", async () => {
    const originCode = document.getElementById("f_origin_code").value || document.getElementById("f_origin").value;
    const destinationCode = document.getElementById("f_destination_code").value || document.getElementById("f_destination").value;

    if (!originCode || !destinationCode) {
      alert("Iltimos, jo'nash va borish shahar/aeroportini kiriting.");
      return;
    }

    const departDate = document.getElementById("f_depart_date").value;
    const priceVal = parseFloat(document.getElementById("f_price").value);

    if (!departDate || isNaN(priceVal) || priceVal < 0) {
      alert("Iltimos, to'g'ri sana va narxni kiriting.");
      return;
    }

    const payload = {
      origin: originCode.trim(),
      destination: destinationCode.trim(),
      depart_date: departDate,
      departure_time: document.getElementById("f_departure_time").value || null,
      price: priceVal,
      seats_available: document.getElementById("f_seats").value ? parseInt(document.getElementById("f_seats").value) : null,
      airline: document.getElementById("f_airline").value || "Saudiya Biletlar",
      flight_number: document.getElementById("f_flight_number").value || null,
    };

    addFlightBtn.innerText = "⏳ Saqlanmoqda...";
    addFlightBtn.disabled = true;
    try {
      await apiFetch("/api/admin/flights", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      alert("✅ Chipta muvaffaqiyatli qo'shildi!");
      document.getElementById("f_origin").value = "";
      document.getElementById("f_destination").value = "";
      document.getElementById("f_origin_code").value = "";
      document.getElementById("f_destination_code").value = "";
      document.getElementById("f_depart_date").value = "";
      document.getElementById("f_departure_time").value = "";
      document.getElementById("f_price").value = "";
      document.getElementById("f_seats").value = "";
      document.getElementById("f_airline").value = "";
      document.getElementById("f_flight_number").value = "";
      loadFlights();
    } catch (e) {
      alert("Xatolik: " + e.message);
    } finally {
      addFlightBtn.innerText = "💾 Chiptani Saqlash va E'lon Qilish";
      addFlightBtn.disabled = false;
    }
  });
}

// ==================== VIZA ARIZALARI ====================
const VISA_STATUS_LABELS = {
  new: "🆕 Yangi",
  processing: "⏳ Ko'rib chiqilmoqda",
  approved: "✅ Tasdiqlangan",
  rejected: "❌ Rad etilgan",
};
const VISA_TYPE_LABELS = {
  tourist_multi: "1 yillik Multi Turistik Viza",
  umrah_nusuk: "Rasmiy Umra Vizasi (Nusuk)",
};

async function loadVisaApplicationsAdmin() {
  const list = document.getElementById("visa-admin-list");
  if (!list) return;
  const status = document.getElementById("visa-status-filter")?.value || "";
  list.innerHTML = '<div class="a-empty">⏳ Viza arizalari yuklanmoqda...</div>';
  try {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    const data = await apiFetch(`/api/admin/visa-applications${qs}`);
    renderVisaApplicationsAdmin(data.applications || []);
  } catch (e) {
    list.innerHTML = `<div class="a-empty error">${escapeHtml(e.message)}</div>`;
  }
}

function renderVisaApplicationsAdmin(applications) {
  const list = document.getElementById("visa-admin-list");
  if (!list) return;
  if (!applications.length) {
    list.innerHTML = '<div class="a-empty"><div class="empty-icon">📑</div><p>Viza arizalari topilmadi.</p></div>';
    return;
  }
  list.innerHTML = "";
  applications.forEach(a => {
    const card = document.createElement("article");
    card.className = `admin-feature-card visa-${escapeHtml(a.status || "new")}`;
    card.innerHTML = `
      <div class="admin-feature-top">
        <div>
          <span class="admin-feature-id">VIZA ARIZASI #${Number(a.id) || "-"}</span>
          <h3>${escapeHtml(a.first_name)} ${escapeHtml(a.last_name)}</h3>
          <p>${escapeHtml(VISA_TYPE_LABELS[a.visa_type] || a.visa_type)}</p>
        </div>
        <span class="admin-status-pill ${escapeHtml(a.status || "new")}">${escapeHtml(VISA_STATUS_LABELS[a.status] || a.status)}</span>
      </div>
      <div class="admin-feature-grid">
        <div><span>PASPORT</span><strong>${escapeHtml(a.passport_number)}</strong></div>
        <div><span>TELEFON</span><strong>${escapeHtml(a.phone)}</strong></div>
        <div><span>TUG'ILGAN SANA</span><strong>${escapeHtml(a.birth_date)}</strong></div>
        <div><span>SAFAR SANASI</span><strong>${escapeHtml(a.travel_date || "Belgilanmagan")}</strong></div>
        <div><span>TELEGRAM</span><strong>${escapeHtml(a.telegram_user_id)} ${a.username ? `(@${escapeHtml(a.username)})` : ""}</strong></div>
        <div><span>YARATILGAN</span><strong>${escapeHtml(String(a.created_at || "").slice(0, 16).replace("T", " "))}</strong></div>
      </div>
      ${a.notes ? `<p class="admin-feature-note"><b>Mijoz izohi:</b> ${escapeHtml(a.notes)}</p>` : ""}
      ${a.admin_note ? `<p class="admin-feature-note admin"><b>Admin izohi:</b> ${escapeHtml(a.admin_note)}</p>` : ""}
      <div class="admin-feature-actions">
        <select class="a-select visa-status-select" data-visa-id="${Number(a.id)}">
          ${Object.entries(VISA_STATUS_LABELS).map(([key,label]) => `<option value="${key}" ${a.status===key?"selected":""}>${label}</option>`).join("")}
        </select>
        <button class="order-btn confirm visa-save-btn" data-visa-id="${Number(a.id)}">💾 Holatni saqlash</button>
        <button class="order-btn delete visa-delete-btn" data-visa-id="${Number(a.id)}">🗑 O'chirish</button>
      </div>
    `;
    list.appendChild(card);
  });
  list.querySelectorAll(".visa-save-btn").forEach(btn => btn.addEventListener("click", () => updateVisaApplicationAdmin(Number(btn.dataset.visaId))));
  list.querySelectorAll(".visa-delete-btn").forEach(btn => btn.addEventListener("click", () => openDeleteModal("visa", btn.dataset.visaId)));
}

async function updateVisaApplicationAdmin(id) {
  const select = document.querySelector(`.visa-status-select[data-visa-id="${id}"]`);
  const status = select?.value || "new";
  const adminNote = prompt("Mijozga yuboriladigan izoh (ixtiyoriy):", "") ?? null;
  if (adminNote === null) return;
  try {
    await apiFetch(`/api/admin/visa-applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status, admin_note: adminNote || null }),
    });
    alert(`✅ Viza arizasi #${id} yangilandi va mijozga xabar yuborildi.`);
    loadVisaApplicationsAdmin();
  } catch (e) { alert("Xatolik: " + e.message); }
}

document.getElementById("refresh-visa-btn")?.addEventListener("click", loadVisaApplicationsAdmin);
document.getElementById("visa-status-filter")?.addEventListener("change", loadVisaApplicationsAdmin);

// ==================== NARX OBUNALARI ====================
async function loadPriceAlertsAdmin() {
  const list = document.getElementById("price-alerts-admin-list");
  if (!list) return;
  const activeOnly = document.getElementById("price-alert-filter")?.value === "true";
  list.innerHTML = '<div class="a-empty">⏳ Narx obunalari yuklanmoqda...</div>';
  try {
    const data = await apiFetch(`/api/admin/price-alerts?active_only=${activeOnly}`);
    renderPriceAlertsAdmin(data.alerts || []);
  } catch (e) {
    list.innerHTML = `<div class="a-empty error">${escapeHtml(e.message)}</div>`;
  }
}

function renderPriceAlertsAdmin(alerts) {
  const list = document.getElementById("price-alerts-admin-list");
  if (!list) return;
  if (!alerts.length) {
    list.innerHTML = '<div class="a-empty"><div class="empty-icon">🔔</div><p>Narx obunalari topilmadi.</p></div>';
    return;
  }
  list.innerHTML = alerts.map(a => `
    <article class="admin-feature-card alert-${a.is_active ? "active" : "inactive"}">
      <div class="admin-feature-top">
        <div>
          <span class="admin-feature-id">NARX OBUNASI #${Number(a.id)||"-"}</span>
          <h3>✈️ ${escapeHtml(a.origin)} ➔ ${escapeHtml(a.destination)}</h3>
          <p>${escapeHtml(a.date_from)} — ${escapeHtml(a.date_to)}</p>
        </div>
        <span class="admin-status-pill ${a.is_active ? "approved" : "rejected"}">${a.is_active ? "🔔 Faol" : (a.last_notified_at ? "✅ Xabar yuborilgan" : "⏹ Nofaol")}</span>
      </div>
      <div class="admin-feature-grid">
        <div><span>MAQSADLI NARX</span><strong>$${Number(a.target_price).toLocaleString()}</strong></div>
        <div><span>OXIRGI NARX</span><strong>${a.last_price == null ? "Tekshirilmagan" : `$${Number(a.last_price).toLocaleString()}`}</strong></div>
        <div><span>TELEGRAM</span><strong>${escapeHtml(a.telegram_user_id)} ${a.username ? `(@${escapeHtml(a.username)})` : ""}</strong></div>
        <div><span>OXIRGI TEKSHIRUV</span><strong>${escapeHtml(String(a.last_checked_at || "").slice(0,16).replace("T"," ") || "-")}</strong></div>
      </div>
      <div class="admin-feature-actions">
        <button class="order-btn delete price-alert-delete-btn" data-alert-id="${Number(a.id)}">🗑 O'chirish</button>
      </div>
    </article>
  `).join("");
  list.querySelectorAll(".price-alert-delete-btn").forEach(btn => btn.addEventListener("click", () => openDeleteModal("price-alert", btn.dataset.alertId)));
}

document.getElementById("refresh-price-alerts-btn")?.addEventListener("click", loadPriceAlertsAdmin);
document.getElementById("price-alert-filter")?.addEventListener("change", loadPriceAlertsAdmin);


// ==================== IMAGE MODAL ====================
function openImgModal(src) {
  const modalImg = document.getElementById("modalPreviewImg");
  const modal = document.getElementById("imgModal");
  if (modalImg) modalImg.src = src;
  if (modal) modal.classList.remove("hidden");
}
function closeImgModal() {
  const modal = document.getElementById("imgModal");
  if (modal) modal.classList.add("hidden");
}

// Close modals on Escape
document.addEventListener("keydown", (e)=>{
  if(e.key==="Escape"){ closeImgModal(); closeDeleteModal(); }
});

// ==================== MARKAZIY BANK (CBU) JONLI KURSI ====================
async function loadCbuRate() {
  const valueEl = document.getElementById("cbu-rate-value");
  const dateEl = document.getElementById("cbu-rate-date");
  try {
    const res = await fetch(`${API_BASE}/api/cbu-rate`);
    if (!res.ok) throw new Error("Kurs olinmadi");
    const data = await res.json();
    const rate = parseFloat(data.rate);
    if (rate && !isNaN(rate)) {
      cbuRate = rate;
      if (valueEl) valueEl.innerText = `1$ = ${Math.round(rate).toLocaleString("uz-UZ").replace(/,/g, " ")} so'm`;
      if (dateEl) {
        const diff = parseFloat(data.diff);
        const diffTxt = !isNaN(diff) && diff !== 0
          ? (diff > 0 ? ` ▲ +${diff}` : ` ▼ ${diff}`)
          : "";
        dateEl.innerText = `${data.date || ""}${diffTxt}`;
        dateEl.className = "a-rate-date" + (!isNaN(diff) ? (diff > 0 ? " up" : (diff < 0 ? " down" : "")) : "");
      }
      if (cachedOrders.length) updateDashboardStats(cachedOrders);
    }
  } catch (e) {
    if (valueEl) valueEl.innerText = "Kurs mavjud emas";
    console.warn("CBU kursini olishda xato:", e);
  }
}
loadCbuRate();
setInterval(loadCbuRate, 30 * 60 * 1000); // har 30 daqiqada yangilanadi

// ==================== RAD ETILGANLARNI TOZALASH ====================
const clearRejectedBtn = document.getElementById("clear-rejected-btn");
if (clearRejectedBtn) {
  clearRejectedBtn.addEventListener("click", async () => {
    const rejectedCount = cachedOrders.filter(o => o.status === "rejected").length;
    const question = rejectedCount
      ? `Rad etilgan ${rejectedCount} ta buyurtma butunlay o'chiriladi. Davom etamizmi?`
      : "Barcha rad etilgan buyurtmalar o'chiriladi. Davom etamizmi?";
    if (!confirm(question)) return;

    const oldText = clearRejectedBtn.innerText;
    clearRejectedBtn.innerText = "⏳ Tozalanmoqda...";
    clearRejectedBtn.disabled = true;
    try {
      const data = await apiFetch("/api/admin/orders/clear-rejected", { method: "POST" });
      alert(`🗑 ${data.deleted || 0} ta rad etilgan buyurtma o'chirildi.`);
      loadOrders();
    } catch (e) {
      alert("Tozalashda xatolik: " + e.message);
    } finally {
      clearRejectedBtn.innerText = oldText;
      clearRejectedBtn.disabled = false;
    }
  });
}

// ==================== BARCHA BUYURTMALARNI O'CHIRISH ====================
const deleteAllOrdersBtn = document.getElementById("delete-all-orders-btn");
if (deleteAllOrdersBtn) {
  deleteAllOrdersBtn.addEventListener("click", async () => {
    const totalCount = cachedOrders.length;
    if (totalCount === 0) {
      alert("O'chirish uchun buyurtmalar yo'q.");
      return;
    }
    
    // Ikki marta tasdiqlash - xavfsizlik uchun
    const firstConfirm = confirm(
      `⚠️ DIQQAT: ${totalCount} ta buyurtma O'CHIRILADI!\n\n` +
      `Bu amali ortga qaytarib BO'LMAYDI!\n\n` +
      `Davom etishni xohlaysizmi?`
    );
    if (!firstConfirm) return;
    
    const secondConfirm = confirm(
      `🚨 YAKUNIY TASDIQLASH:\n\n` +
      `${totalCount} ta buyurtma to'liq o'chiriladi.\n\n` +
      `Ha, men barchasini o'chirishni tasdiqlayman.`
    );
    if (!secondConfirm) return;
    
    const oldText = deleteAllOrdersBtn.innerText;
    deleteAllOrdersBtn.innerText = "⏳ Barchasi o'chirilmoqda...";
    deleteAllOrdersBtn.disabled = true;
    
    try {
      const data = await apiFetch("/api/admin/orders", { method: "DELETE" });
      alert(`🗑 ${data.deleted || 0} ta buyurtma muvaffaqiyatli o'chirildi.`);
      cachedOrders = [];
      loadOrders();
    } catch (e) {
      alert("O'chirishda xatolik: " + e.message);
    } finally {
      deleteAllOrdersBtn.innerText = oldText;
      deleteAllOrdersBtn.disabled = false;
    }
  });
}
