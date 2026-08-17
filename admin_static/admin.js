const API_BASE = "";
let cachedOrders = [];

// ==================== AVTOMATIK TAKLIF (SHAHARLAR) ====================
function setupFlightAutocomplete(inputId, hiddenId, boxId) {
  const input = document.getElementById(inputId);
  const hidden = document.getElementById(hiddenId);
  const box = document.getElementById(boxId);
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
  document.getElementById("login-screen").classList.remove("hidden");
  document.getElementById("panel").classList.add("hidden");
}

function showPanel() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("panel").classList.remove("hidden");
  loadOrders();
  loadFlights();
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
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
    document.getElementById("login-error").classList.add("hidden");
    showPanel();
  } catch (err) {
    document.getElementById("login-error").classList.remove("hidden");
  }
});

document.getElementById("logout-btn").addEventListener("click", () => {
  clearPassword();
  showLogin();
});

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
    document.getElementById(`tab-${tab.dataset.tab}`).classList.remove("hidden");
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
  const status = document.getElementById("status-filter").value;
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

  document.getElementById("stat-total-orders").innerText = total;
  document.getElementById("stat-pending-orders").innerText = pending;
  document.getElementById("stat-confirmed-orders").innerText = confirmed;
  document.getElementById("stat-revenue").innerText = `$${revenue.toLocaleString()}`;
}

function filterOrdersLocally() {
  const query = document.getElementById("orders-search").value.toLowerCase().trim();
  if (!query) {
    renderOrders(cachedOrders);
    return;
  }
  const filtered = cachedOrders.filter(order => {
    const passport = (order.passports && order.passports[0]) || order.passports || {};
    const fullName = `${passport.first_name || ""} ${passport.last_name || ""}`.toLowerCase();
    const pNum = (passport.passport_number || "").toLowerCase();
    const orderId = String(order.id);
    return fullName.includes(query) || pNum.includes(query) || orderId.includes(query);
  });
  renderOrders(filtered);
}

function renderOrders(orders) {
  const list = document.getElementById("orders-list");
  const empty = document.getElementById("orders-empty");
  list.innerHTML = "";

  if (!orders.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  orders.forEach(order => {
    const passport = (order.passports && order.passports[0]) || order.passports || {};
    const statusClass = order.status === "confirmed" ? "confirmed" : order.status === "rejected" ? "rejected" : "";
    const card = document.createElement("div");
    card.className = `order-card ${statusClass}`;
    
    card.innerHTML = `
      <div class="order-top">
        <div class="order-id">#${order.id} — ✈️ ${order.origin.toUpperCase()} ➔ ${order.destination.toUpperCase()}</div>
        <div class="order-status-badge ${statusClass}">${STATUS_LABELS[order.status] || order.status}</div>
      </div>
      
      <div class="order-details-grid">
        <div class="order-detail-item">
          <span>YO'LOVCHI F.I.SH</span>
          <strong>${passport.first_name || "-"} ${passport.last_name || ""}</strong>
        </div>
        <div class="order-detail-item">
          <span>PASPORT RAQAMI</span>
          <strong>${passport.passport_number || "-"}</strong>
        </div>
        <div class="order-detail-item">
          <span>UCHISH SANASI</span>
          <strong>${order.depart_date} (${order.passengers || 1} yo'lovchi)</strong>
        </div>
        <div class="order-detail-item">
          <span>SUMMA (TO'LOV)</span>
          <strong style="color: var(--primary); font-size: 15px;">$${order.price}</strong>
        </div>
      </div>

      <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">
        👤 Telegram: <code>${order.telegram_user_id}</code> ${order.username ? "(@" + order.username + ")" : ""}
      </div>

      ${order.payment_screenshot_url ? `
        <div style="margin-top: 8px; margin-bottom: 8px;">
          <span style="font-size: 11px; font-weight: 700; color: var(--text-muted); display: block; margin-bottom: 4px;">TO'LOV CHEKI (BOSING):</span>
          <img class="order-photo-thumb" src="${order.payment_screenshot_url}" alt="To'lov cheki" onclick="openImgModal('${order.payment_screenshot_url}')">
        </div>
      ` : ""}

      ${order.status === "new" || order.status === "awaiting_confirmation" ? `
        <div class="order-actions">
          <button class="order-btn confirm" data-id="${order.id}" data-action="confirm">✅ Tasdiqlash & PDF Chipta Yuborish</button>
          <button class="order-btn reject" data-id="${order.id}" data-action="reject">❌ Rad Etish</button>
        </div>` : ""}
    `;
    list.appendChild(card);
  });

  list.querySelectorAll("[data-action='confirm']").forEach(btn => {
    btn.addEventListener("click", () => confirmOrder(btn.dataset.id));
  });
  list.querySelectorAll("[data-action='reject']").forEach(btn => {
    btn.addEventListener("click", () => rejectOrder(btn.dataset.id));
  });
}

async function confirmOrder(id) {
  if (!confirm(`#${id} raqamli buyurtmani tasdiqlaysizmi?\n\nMijozga avtomatik ravishda chiroyli PDF elektron chipta yuboriladi.`)) return;
  try {
    await apiFetch(`/api/admin/orders/${id}/confirm`, { method: "POST" });
    alert(`Buyurtma #${id} muvaffaqiyatli tasdiqlandi!`);
    loadOrders();
  } catch (e) {
    alert("Xatolik: " + e.message);
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

document.getElementById("refresh-orders").addEventListener("click", loadOrders);
document.getElementById("status-filter").addEventListener("change", loadOrders);

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
  list.innerHTML = "";
  if (!flights.length) {
    list.innerHTML = `<div class="a-empty"><div class="empty-icon">✈️</div>Hali chiptalar qo'shilmagan.</div>`;
    return;
  }
  flights.forEach(f => {
    const card = document.createElement("div");
    card.className = "flight-item-card";
    card.innerHTML = `
      <div>
        <div class="flight-route-title">✈️ ${f.origin.toUpperCase()} ➔ ${f.destination.toUpperCase()}</div>
        <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">
          📅 ${f.depart_date} ${f.departure_time || ""} | 🛫 ${f.airline || ""} (${f.flight_number || "-"}) | 💺 O'rindiqlar: <strong>${f.seats_available ?? "Ko'p"}</strong>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 14px;">
        <div style="font-size: 20px; font-weight: 800; color: var(--primary);">$${f.price}</div>
        <button class="flight-del-btn" data-id="${f.id}">🗑 O'chirish</button>
      </div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll(".flight-del-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm("Ushbu chiptani o'chirmoqchimisiz?")) return;
      await apiFetch(`/api/admin/flights/${btn.dataset.id}`, { method: "DELETE" });
      loadFlights();
    });
  });
}

document.getElementById("btn-add-flight").addEventListener("click", async () => {
  const originCode = document.getElementById("f_origin_code").value || document.getElementById("f_origin").value;
  const destinationCode = document.getElementById("f_destination_code").value || document.getElementById("f_destination").value;

  if (!originCode || !destinationCode) {
    alert("Iltimos, jo'nash va borish shahar/aeroportini kiriting.");
    return;
  }

  const payload = {
    origin: originCode.trim(),
    destination: destinationCode.trim(),
    depart_date: document.getElementById("f_depart_date").value,
    departure_time: document.getElementById("f_departure_time").value || null,
    price: parseFloat(document.getElementById("f_price").value),
    seats_available: document.getElementById("f_seats").value ? parseInt(document.getElementById("f_seats").value) : null,
    airline: document.getElementById("f_airline").value || "Umra Chipta",
    flight_number: document.getElementById("f_flight_number").value || null,
  };

  if (!payload.depart_date || !payload.price) {
    alert("Iltimos, sana va narxni to'ldiring.");
    return;
  }

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
    document.getElementById("f_price").value = "";
    document.getElementById("f_seats").value = "";
    document.getElementById("f_flight_number").value = "";
    loadFlights();
  } catch (e) {
    alert("Xatolik: " + e.message);
  }
});

// ==================== IMAGE MODAL ====================
function openImgModal(src) {
  document.getElementById("modalPreviewImg").src = src;
  document.getElementById("imgModal").classList.remove("hidden");
}
function closeImgModal() {
  document.getElementById("imgModal").classList.add("hidden");
}
