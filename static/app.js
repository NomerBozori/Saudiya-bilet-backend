// ==================== SOZLAMALAR — v11 Premium Dizayn ====================
const API_BASE_URL = "";
const ADMIN_TG_USERNAME = "nuriddinovdfg";
let UZS_RATE = 12850; // Markaziy Bank (CBU) kursi bilan avtomatik yangilanadi
const APP_VERSION = "v13";

let currentCurrency = "USD";
let lastFlightResults = [];
let lastCalendarDays = [];
let calendarCheapestDate = null;
let calendarLoading = false;

const tg = window.Telegram?.WebApp || {
  ready: () => {}, expand: () => {}, showAlert: (msg) => alert(msg),
  themeParams: {}, initDataUnsafe: { user: { id: 0, username: "web_user" } },
  MainButton: { showProgress: () => {}, hideProgress: () => {} }
};
tg.ready(); tg.expand();
const user = tg.initDataUnsafe?.user || { id: 0, username: "web_user" };

const state = {
  selectedFlight: null,
  origin: "TAS",
  destination: "JED",
  departDate: null,
  passengers: 1,
  passport: null,
  paymentFile: null,
  lastOrderId: null,
};

// ==================== VALYUTA ====================
document.querySelectorAll(".tg-curr-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tg-curr-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentCurrency = btn.dataset.curr;
    if (lastFlightResults.length) renderResults(lastFlightResults);
    if (lastCalendarDays.length) renderPriceCalendar(lastCalendarDays);
    if (typeof lastDeals !== "undefined" && lastDeals.length) renderDeals(lastDeals);
  });
});

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[ch]);
}

async function apiJson(url, options={}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");
  return data;
}

function telegramHeaders(extra={}) {
  return {"X-Telegram-Init-Data": tg.initData || "", ...extra};
}

function formatPrice(usdPrice) {
  const price = Number(usdPrice) || 0;
  if (currentCurrency === "UZS") {
    const uzs = Math.round(price * UZS_RATE);
    return `${uzs.toLocaleString("uz-UZ").replace(/,/g, " ")} UZS`;
  }
  return `$${price}`;
}

// ==================== MARKAZIY BANK (CBU) JONLI KURSI ====================
async function loadCbuRate(){
  try{
    const res = await fetch(`${API_BASE_URL}/api/cbu-rate`);
    if(!res.ok) return;
    const data = await res.json();
    const rate = parseFloat(data.rate);
    if(!rate || isNaN(rate)) return;
    UZS_RATE = rate;
    const calcRate = document.getElementById("calc_rate");
    if(calcRate && !calcRate.dataset.touched) calcRate.value = Math.round(rate);
    if(typeof calculateCustomFare === "function") calculateCustomFare();
    if(lastFlightResults.length) renderResults(lastFlightResults);
    if(lastCalendarDays.length) renderPriceCalendar(lastCalendarDays);
    if(typeof lastDeals !== "undefined" && lastDeals.length) renderDeals(lastDeals);
  }catch(e){ console.warn("CBU kursini olishda xatolik:", e); }
}
loadCbuRate();
document.getElementById("calc_rate")?.addEventListener("input", (e)=>{ e.target.dataset.touched = "1"; });

// ==================== KALKULYATOR ====================
window.calculateCustomFare = function() {
  const price = parseFloat(document.getElementById("calc_price")?.value || "0");
  const rate = parseFloat(document.getElementById("calc_rate")?.value || "12850");
  const passengers = parseInt(document.getElementById("calc_passengers")?.value || "1", 10);
  const safePrice = isNaN(price) || price < 0 ? 0 : price;
  const safePassengers = isNaN(passengers) || passengers < 1 ? 1 : passengers;
  const safeRate = isNaN(rate) || rate < 0 ? 12850 : rate;
  const totalUsd = Math.round(safePrice * safePassengers);
  const totalUzs = Math.round(totalUsd * safeRate);
  const resUsdEl = document.getElementById("calc-res-usd");
  const resUzsEl = document.getElementById("calc-res-uzs");
  if (resUsdEl) resUsdEl.innerText = `$${totalUsd.toLocaleString()}`;
  if (resUzsEl) resUzsEl.innerText = `${totalUzs.toLocaleString("uz-UZ").replace(/,/g, " ")} UZS`;
};

// ==================== TABS ====================
document.querySelectorAll(".tg-tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tg-tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    const targetPane = document.getElementById(btn.dataset.tab);
    if (targetPane) {
      targetPane.classList.add("active");
      if (btn.dataset.tab === "tab-orders") loadUserOrders();
      if (btn.dataset.tab === "tab-calc") calculateCustomFare();
      if (btn.dataset.tab === "tab-visa") loadVisaApplications();
      if (btn.dataset.tab === "tab-search") loadPriceAlerts();
    }
  });
});
const initialTab=new URLSearchParams(window.location.search).get("tab");
if(initialTab==="visa") document.querySelector('[data-tab="tab-visa"]')?.click();

window.setRoute = function(fromCode, fromName, toCode, toName) {
  const originEl = document.getElementById("origin");
  const originCodeEl = document.getElementById("origin_code");
  const destEl = document.getElementById("destination");
  const destCodeEl = document.getElementById("destination_code");
  if (originEl) originEl.value = `${fromName} (${fromCode})`;
  if (originCodeEl) originCodeEl.value = fromCode;
  if (destEl) destEl.value = `${toName} (${toCode})`;
  if (destCodeEl) destCodeEl.value = toCode;
  // subtle animation
  if (originEl) { originEl.animate([{transform:'scale(1.02)'},{transform:'scale(1)'}], {duration:240}); }
  window.schedulePriceCalendar?.(120);
  syncPriceAlertRoute();
};

function showScreen(id) {
  document.querySelectorAll("#tab-search .tg-screen").forEach(s => s.classList.add("hidden"));
  const screen = document.getElementById(id);
  if (screen) {
    screen.classList.remove("hidden");
    screen.animate?.([{opacity:0, transform:'translateY(8px)'},{opacity:1, transform:'none'}], {duration:220, easing:'ease-out'});
  }
}
document.querySelectorAll("[data-back]").forEach(btn => {
  btn.addEventListener("click", () => showScreen(btn.dataset.back));
});

// ==================== AUTOCOMPLETE ====================
function setupAutocomplete(inputId, hiddenId, boxId) {
  const input = document.getElementById(inputId);
  const hidden = document.getElementById(hiddenId);
  const box = document.getElementById(boxId);
  if (!input || !hidden || !box) return;
  let debounceTimer = null;
  input.addEventListener("input", () => {
    hidden.value = "";
    const term = input.value.trim();
    clearTimeout(debounceTimer);
    if (term.length < 2) { box.classList.add("hidden"); box.innerHTML=""; return; }
    debounceTimer = setTimeout(() => fetchSuggestions(term, box, input, hidden), 300);
  });
  input.addEventListener("blur", () => { setTimeout(()=>box.classList.add("hidden"),200); });
}
async function fetchSuggestions(term, box, input, hidden) {
  try {
    const url = `https://autocomplete.travelpayouts.com/places2?term=${encodeURIComponent(term)}&locale=uz&types[]=city&types[]=airport`;
    const res = await fetch(url);
    const items = await res.json();
    if (!items || !items.length) { box.classList.add("hidden"); box.innerHTML=""; return; }
    box.innerHTML = "";
    items.slice(0,8).forEach(item => {
      const label = item.name + (item.country_name ? `, ${item.country_name}` : "");
      const el = document.createElement("div");
      el.className = "tg-suggestion-item";
      el.innerHTML = `<span class="tg-suggestion-code">${item.code}</span>${label}`;
      el.addEventListener("mousedown", () => {
        input.value = `${item.name} (${item.code})`;
        hidden.value = item.code;
        box.classList.add("hidden");
        window.schedulePriceCalendar?.(150);
        syncPriceAlertRoute();
      });
      box.appendChild(el);
    });
    box.classList.remove("hidden");
  } catch(e){ console.error("Autocomplete xatosi:", e); }
}
setupAutocomplete("origin","origin_code","origin_suggestions");
setupAutocomplete("destination","destination_code","destination_suggestions");

const UZ_MONTHS = ["Yanvar","Fevral","Mart","Aprel","May","Iyun","Iyul","Avgust","Sentabr","Oktabr","Noyabr","Dekabr"];
const UZ_WEEK = ["Du","Se","Ch","Pa","Ju","Sh","Ya"];
const CITY_NAMES = { TAS:"Toshkent", NMA:"Namangan", SKD:"Samarqand", FEG:"Farg‘ona", BHK:"Buxoro", UGC:"Urganch", JED:"Jidda", MED:"Madina", RUH:"Ar-Riyod", DXB:"Dubay", IST:"Istanbul" };
function isoDate(d){ const y=d.getFullYear(); const m=String(d.getMonth()+1).padStart(2,"0"); const day=String(d.getDate()).padStart(2,"0"); return `${y}-${m}-${day}`; }
function parseISODate(v){ if(!v) return null; const [y,m,d]=v.split("-").map(Number); if(!y||!m||!d) return null; return new Date(y,m-1,d); }
function formatUzDate(v){ const d=parseISODate(v); if(!d) return "Sanani tanlang"; return `${d.getDate()} ${UZ_MONTHS[d.getMonth()]} ${d.getFullYear()}`; }

function createCalendar({dropdownId, triggerId, labelId, inputId, minDate, startDate}) {
  const dropdown=document.getElementById(dropdownId);
  const trigger=document.getElementById(triggerId);
  const label=document.getElementById(labelId);
  const input=document.getElementById(inputId);
  if(!dropdown||!trigger||!label||!input) return;
  let view = startDate ? new Date(startDate) : new Date(); view.setDate(1);
  function setValue(iso){ input.value=iso; label.textContent=formatUzDate(iso); }
  function render(){
    const year=view.getFullYear(); const month=view.getMonth();
    const firstDow=(new Date(year,month,1).getDay()+6)%7;
    const daysInMonth=new Date(year,month+1,0).getDate();
    const selected=input.value; const todayIso=isoDate(new Date());
    const minIso=minDate?isoDate(minDate):null;
    let daysHtml="";
    for(let i=0;i<firstDow;i++) daysHtml+=`<button type="button" class="tg-cal-day muted" disabled></button>`;
    for(let day=1; day<=daysInMonth; day++){
      const iso=isoDate(new Date(year,month,day));
      const disabled=minIso && iso<minIso;
      const cls=["tg-cal-day", iso===selected?"selected":"", iso===todayIso?"today":""].join(" ");
      daysHtml+=`<button type="button" class="${cls}" data-iso="${iso}" ${disabled?"disabled":""}>${day}</button>`;
    }
    dropdown.innerHTML=`
      <div class="tg-cal-head">
        <button type="button" class="tg-cal-nav" data-nav="-1">‹</button>
        <strong>${UZ_MONTHS[month]} ${year}</strong>
        <button type="button" class="tg-cal-nav" data-nav="1">›</button>
      </div>
      <div class="tg-cal-week">${UZ_WEEK.map(d=>`<span>${d}</span>`).join("")}</div>
      <div class="tg-cal-grid">${daysHtml}</div>
    `;
    dropdown.querySelectorAll("[data-nav]").forEach(btn=>{ btn.addEventListener("click",(e)=>{ e.stopPropagation(); view.setMonth(view.getMonth()+Number(btn.dataset.nav)); render(); }); });
    dropdown.querySelectorAll(".tg-cal-day[data-iso]").forEach(btn=>{ btn.addEventListener("click",(e)=>{ e.stopPropagation(); setValue(btn.dataset.iso); dropdown.classList.add("hidden"); trigger.classList.remove("open"); if(inputId==="depart_date"){ window.schedulePriceCalendar?.(120); syncPriceAlertRoute(btn.dataset.iso); } }); });
  }
  trigger.addEventListener("click",(e)=>{
    e.stopPropagation();
    const willOpen=dropdown.classList.contains("hidden");
    document.querySelectorAll(".tg-cal-dropdown").forEach(el=>el.classList.add("hidden"));
    document.querySelectorAll(".tg-cal-trigger").forEach(el=>el.classList.remove("open"));
    if(willOpen){ dropdown.classList.remove("hidden"); trigger.classList.add("open"); render(); }
  });
  document.addEventListener("click",()=>{ dropdown.classList.add("hidden"); trigger.classList.remove("open"); });
  dropdown.addEventListener("click",(e)=>e.stopPropagation());
  if(startDate) setValue(isoDate(startDate));
  render();
}
const defaultDepart=new Date(); defaultDepart.setDate(defaultDepart.getDate()+2);
createCalendar({dropdownId:"depart_cal",triggerId:"depart_cal_trigger",labelId:"depart_cal_label",inputId:"depart_date",minDate:new Date(),startDate:defaultDepart});
createCalendar({dropdownId:"expiry_cal",triggerId:"expiry_cal_trigger",labelId:"expiry_cal_label",inputId:"p_expiry",minDate:new Date(),startDate:null});
const defaultOrigin=document.getElementById("origin"); if(defaultOrigin) defaultOrigin.value="Toshkent (TAS)";
const defaultDest=document.getElementById("destination"); if(defaultDest) defaultDest.value="Jidda (JED)";

// ==================== ARZON NARXLAR TAQVIMI (GORIZONTAL) ====================
const UZ_WEEK_SHORT=["Yak","Du","Se","Chor","Pay","Jum","Sha"];
const UZ_MONTHS_SHORT=["Yan","Fev","Mar","Apr","May","Iyn","Iyl","Avg","Sen","Okt","Noy","Dek"];

function currentRouteCodes(){
  const origin=(document.getElementById("origin_code")?.value||"TAS").toUpperCase();
  const destination=(document.getElementById("destination_code")?.value||"JED").toUpperCase();
  return { origin, destination };
}

function calendarPriceLabel(price){
  const p=Number(price)||0;
  if(currentCurrency==="UZS"){
    const uzs=Math.round(p*UZS_RATE);
    return `${Math.round(uzs/1000).toLocaleString("uz-UZ").replace(/,/g," ")}k`;
  }
  return `$${Math.round(p)}`;
}

function renderPriceCalendar(days){
  const strip=document.getElementById("price-calendar");
  if(!strip) return;
  if(!days||!days.length){
    strip.innerHTML=`<div class="pc-loading">Narxlar topilmadi</div>`;
    return;
  }
  const selected=document.getElementById("depart_date")?.value||"";
  strip.innerHTML="";
  days.forEach(day=>{
    const d=parseISODate(day.date);
    if(!d) return;
    const btn=document.createElement("button");
    btn.type="button";
    const isCheapest=day.is_cheapest || day.date===calendarCheapestDate;
    btn.className=["pc-day", isCheapest?"cheap":"", day.date===selected?"selected":""].join(" ").trim();
    btn.dataset.iso=day.date;
    btn.innerHTML=`
      <span class="pc-dow">${UZ_WEEK_SHORT[d.getDay()]}</span>
      <span class="pc-date">${d.getDate()} ${UZ_MONTHS_SHORT[d.getMonth()]}</span>
      <span class="pc-price">${calendarPriceLabel(day.price)}</span>
      ${isCheapest?'<span class="pc-flag">eng arzon</span>':""}
    `;
    btn.addEventListener("click",()=>selectCalendarDay(day.date));
    strip.appendChild(btn);
  });
  const activeEl=strip.querySelector(".pc-day.selected")||strip.querySelector(".pc-day.cheap");
  if(activeEl) activeEl.scrollIntoView({behavior:"smooth", block:"nearest", inline:"center"});
}

function selectCalendarDay(iso){
  const input=document.getElementById("depart_date");
  const label=document.getElementById("depart_cal_label");
  if(input) input.value=iso;
  if(label) label.textContent=formatUzDate(iso);
  state.departDate=iso;
  syncPriceAlertRoute(iso);
  document.querySelectorAll("#price-calendar .pc-day").forEach(el=>{
    el.classList.toggle("selected", el.dataset.iso===iso);
  });
  if(tg.HapticFeedback?.selectionChanged) { try{ tg.HapticFeedback.selectionChanged(); }catch(e){} }
}

async function loadPriceCalendar(){
  const strip=document.getElementById("price-calendar");
  if(!strip||calendarLoading) return;
  const { origin, destination }=currentRouteCodes();
  const routeLabel=document.getElementById("pc-route-label");
  if(routeLabel) routeLabel.textContent=`${origin} ➔ ${destination}`;
  calendarLoading=true;
  strip.innerHTML=`<div class="pc-loading">⏳ Har bir kun uchun eng arzon narxlar yuklanmoqda...</div>`;
  try{
    const startIso=document.getElementById("depart_date")?.value||isoDate(new Date());
    const url=`${API_BASE_URL}/api/calendar?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&start_date=${encodeURIComponent(startIso)}&days=30`;
    const res=await fetch(url);
    if(!res.ok) throw new Error("Taqvim yuklanmadi");
    const data=await res.json();
    lastCalendarDays=data.days||[];
    calendarCheapestDate=data.cheapest_date||null;
    renderPriceCalendar(lastCalendarDays);
  }catch(e){
    console.warn("Taqvim xatosi:", e);
    strip.innerHTML=`<div class="pc-loading">Narxlarni yuklab bo'lmadi. 🔄 tugmasi orqali qayta urinib ko'ring.</div>`;
  }finally{ calendarLoading=false; }
}

let calendarTimer=null;
window.schedulePriceCalendar=function(delay=350){
  clearTimeout(calendarTimer);
  calendarTimer=setTimeout(loadPriceCalendar, delay);
};
document.getElementById("pc-refresh")?.addEventListener("click",()=>loadPriceCalendar());
schedulePriceCalendar(150);


// ==================== NARX TUSHGANDA TELEGRAM OBUNASI ====================
function syncPriceAlertRoute(selectedDate=null){
  const {origin, destination}=currentRouteCodes();
  const routeEl=document.getElementById("price-alert-route");
  if(routeEl) routeEl.textContent=`${origin} ➔ ${destination} yo'nalishi`;

  const fromEl=document.getElementById("alert-date-from");
  const toEl=document.getElementById("alert-date-to");
  const start=selectedDate || document.getElementById("depart_date")?.value || isoDate(defaultDepart);
  if(fromEl && (selectedDate || !fromEl.value)) fromEl.value=start;
  if(toEl && (selectedDate || !toEl.value)){
    const end=parseISODate(start) || new Date();
    end.setDate(end.getDate()+29);
    toEl.value=isoDate(end);
  }
  const today=isoDate(new Date());
  if(fromEl) fromEl.min=today;
  if(toEl) toEl.min=fromEl?.value || today;
}

document.getElementById("alert-date-from")?.addEventListener("change", e=>{
  const toEl=document.getElementById("alert-date-to");
  if(!toEl) return;
  toEl.min=e.target.value;
  if(!toEl.value || toEl.value<e.target.value){
    const end=parseISODate(e.target.value) || new Date();
    end.setDate(end.getDate()+29);
    toEl.value=isoDate(end);
  }
});

function renderPriceAlerts(alerts){
  const list=document.getElementById("price-alerts-list");
  if(!list) return;
  if(!alerts?.length){ list.innerHTML=""; return; }
  const statusText=a=>a.is_active ? "Faol" : (a.last_notified_at ? "Xabar yuborildi" : "Bekor qilingan");
  list.innerHTML=alerts.slice(0,5).map(a=>`
    <div class="price-alert-item ${a.is_active ? "active" : "inactive"}">
      <div>
        <strong>🔔 ${escapeHtml(a.origin)} ➔ ${escapeHtml(a.destination)} · $${Number(a.target_price).toLocaleString()}</strong>
        <span>${escapeHtml(a.date_from)} — ${escapeHtml(a.date_to)} · ${statusText(a)}${a.last_price!=null ? ` · oxirgi $${Number(a.last_price).toLocaleString()}` : ""}</span>
      </div>
      ${a.is_active ? `<button type="button" class="price-alert-cancel" data-alert-id="${Number(a.id)}">Bekor qilish</button>` : ""}
    </div>
  `).join("");
  list.querySelectorAll("[data-alert-id]").forEach(btn=>{
    btn.addEventListener("click",()=>cancelPriceAlert(Number(btn.dataset.alertId)));
  });
}

async function loadPriceAlerts(){
  const list=document.getElementById("price-alerts-list");
  if(!list) return;
  if(!user.id || Number(user.id)<=0){
    list.innerHTML='<p class="price-alert-login-hint">Obuna uchun Mini Appni Telegram ichidan oching.</p>';
    return;
  }
  try{
    const data=await apiJson(
      `${API_BASE_URL}/api/price-alerts?telegram_user_id=${encodeURIComponent(user.id)}`,
      {headers:telegramHeaders()},
    );
    renderPriceAlerts(data.alerts||[]);
  }catch(e){
    list.innerHTML=`<p class="price-alert-login-hint">${escapeHtml(e.message)}</p>`;
  }
}

async function cancelPriceAlert(alertId){
  if(!confirm("Narx obunasini bekor qilasizmi?")) return;
  try{
    await apiJson(`${API_BASE_URL}/api/price-alerts/${alertId}?telegram_user_id=${encodeURIComponent(user.id)}`, {
      method:"DELETE", headers:telegramHeaders(),
    });
    await loadPriceAlerts();
  }catch(e){ tg.showAlert(e.message); }
}

const btnPriceAlert=document.getElementById("btn-price-alert");
btnPriceAlert?.addEventListener("click", async()=>{
  if(!user.id || Number(user.id)<=0){ tg.showAlert("Obuna uchun Mini Appni Telegram ichidan oching."); return; }
  const {origin, destination}=currentRouteCodes();
  const dateFrom=document.getElementById("alert-date-from")?.value||"";
  const dateTo=document.getElementById("alert-date-to")?.value||"";
  const targetPrice=Number(document.getElementById("alert-target-price")?.value||0);
  if(!dateFrom||!dateTo||targetPrice<=0){ tg.showAlert("Sanalar va maqsadli narxni to'g'ri kiriting."); return; }
  const oldText=btnPriceAlert.innerText;
  btnPriceAlert.disabled=true;
  btnPriceAlert.innerText="⏳ Saqlanmoqda...";
  try{
    await apiJson(`${API_BASE_URL}/api/price-alerts`, {
      method:"POST",
      headers:telegramHeaders({"Content-Type":"application/json"}),
      body:JSON.stringify({
        telegram_user_id:user.id,
        username:user.username||null,
        origin, destination,
        date_from:dateFrom,
        date_to:dateTo,
        target_price:targetPrice,
      }),
    });
    tg.showAlert("✅ Obuna saqlandi. Narx tushsa bot xabar beradi.");
    await loadPriceAlerts();
  }catch(e){ tg.showAlert(e.message); }
  finally{ btnPriceAlert.disabled=false; btnPriceAlert.innerText=oldText; }
});

syncPriceAlertRoute();
loadPriceAlerts();


// ==================== 🔥 AVTO NARX TAVSIYALARI (TOP DEALS) ====================
let lastDeals = [];
let dealsLoading = false;

const CITY_NAME_MAP = {
  TAS:"Toshkent", NMA:"Namangan", SKD:"Samarqand", FEG:"Farg'ona", BHK:"Buxoro",
  AZN:"Andijon", UGC:"Urganch", TMJ:"Termiz", NVI:"Navoiy", KSQ:"Qarshi", NCU:"Nukus",
  JED:"Jidda", MED:"Madina", RUH:"Ar-Riyod", DMM:"Dammam"
};

function dealPriceLabel(price){
  const p = Number(price) || 0;
  if(currentCurrency === "UZS"){
    const uzs = Math.round(p * UZS_RATE);
    return `${uzs.toLocaleString("uz-UZ").replace(/,/g," ")} so'm`;
  }
  return `$${Math.round(p)}`;
}

function shortDate(iso){
  const d = parseISODate(iso);
  if(!d) return "";
  return `${d.getDate()} ${UZ_MONTHS_SHORT[d.getMonth()]}`;
}

function renderDeals(deals){
  const strip = document.getElementById("deals-strip");
  if(!strip) return;
  if(!deals || !deals.length){
    strip.innerHTML = `<div class="deals-empty">Hozircha takliflar yo'q. 🔄 tugmasi orqali yangilang.</div>`;
    return;
  }
  strip.innerHTML = "";
  deals.forEach((d, idx) => {
    const originName = d.origin_name || CITY_NAME_MAP[d.origin] || d.origin;
    const destName = d.destination_name || CITY_NAME_MAP[d.destination] || d.destination;
    const card = document.createElement("button");
    card.type = "button";
    card.className = ["deal-card", d.is_cheapest ? "best" : ""].join(" ").trim();
    card.innerHTML = `
      ${d.is_cheapest ? '<span class="deal-badge">🏆 ENG ARZON</span>' : ""}
      <span class="deal-route">
        <b>${d.origin}</b><span class="deal-arrow">✈</span><b>${d.destination}</b>
      </span>
      <span class="deal-cities">${originName} → ${destName}</span>
      <span class="deal-price">${dealPriceLabel(d.price)}</span>
      <span class="deal-date">📅 ${shortDate(d.depart_date)}${d.days_left != null ? ` · ${d.days_left} kun` : ""}</span>
    `;
    card.addEventListener("click", () => applyDeal(d));
    strip.appendChild(card);
    if(idx === 0) card.classList.add("first");
  });
}

function applyDeal(deal){
  const originName = deal.origin_name || CITY_NAME_MAP[deal.origin] || deal.origin;
  const destName = deal.destination_name || CITY_NAME_MAP[deal.destination] || deal.destination;
  setRoute(deal.origin, originName, deal.destination, destName);
  if(deal.depart_date) selectCalendarDay(deal.depart_date);
  if(tg.HapticFeedback?.impactOccurred){ try{ tg.HapticFeedback.impactOccurred("light"); }catch(e){} }
  document.getElementById("btn-search")?.scrollIntoView({behavior:"smooth", block:"center"});
  // Tavsiyani bosgan zahoti qidiruvni ishga tushiramiz
  setTimeout(()=>document.getElementById("btn-search")?.click(), 260);
}

async function loadTopDeals(refresh=false){
  const strip = document.getElementById("deals-strip");
  const sub = document.getElementById("deals-sub");
  if(!strip || dealsLoading) return;
  dealsLoading = true;
  if(refresh) strip.innerHTML = `<div class="deals-skeleton"></div><div class="deals-skeleton"></div><div class="deals-skeleton"></div>`;
  try{
    const res = await fetch(`${API_BASE_URL}/api/top-deals?limit=8${refresh ? "&refresh=true" : ""}`);
    if(!res.ok) throw new Error("Takliflar yuklanmadi");
    const data = await res.json();
    if(data.rate) UZS_RATE = Number(data.rate) || UZS_RATE;
    lastDeals = data.deals || [];
    renderDeals(lastDeals);
    const w = data.window || {};
    if(sub) sub.textContent = `Yaqin ${w.min_days ?? 3}–${w.max_days ?? 35} kun · ${data.updated_at || ""} da yangilandi`;
  }catch(e){
    console.warn("Takliflar xatosi:", e);
    strip.innerHTML = `<div class="deals-empty">Narxlarni yuklab bo'lmadi. 🔄 tugmasi orqali qayta urinib ko'ring.</div>`;
  }finally{ dealsLoading = false; }
}

document.getElementById("deals-refresh")?.addEventListener("click", ()=>loadTopDeals(true));
loadTopDeals();
// Har 10 daqiqada narxlar avtomatik yangilanib turadi
setInterval(()=>loadTopDeals(), 10 * 60 * 1000);


// ==================== 3D KARTA v10 ====================
function init3DCard(){
  const scene=document.getElementById("card-3d-scene");
  const card=document.getElementById("card-3d");
  if(!scene||!card) return;
  const tilt=(x,y)=>{
    const rect=scene.getBoundingClientRect();
    const px=(x-rect.left)/rect.width-0.5;
    const py=(y-rect.top)/rect.height-0.5;
    card.style.transform=`rotateY(${px*22}deg) rotateX(${-py*16}deg)`;
  };
  scene.addEventListener("mousemove",(e)=>tilt(e.clientX,e.clientY));
  scene.addEventListener("touchmove",(e)=>{ if(!e.touches[0]) return; tilt(e.touches[0].clientX,e.touches[0].clientY); },{passive:true});
  const reset=()=>{ card.style.transform="rotateY(0deg) rotateX(0deg)"; };
  scene.addEventListener("mouseleave",reset);
  scene.addEventListener("touchend",reset);
  const numberEl=document.getElementById("card-number");
  const copyNumEl=document.getElementById("copy-card-number");
  const copyOwnerEl=document.getElementById("copy-card-owner");
  const toastEl=document.getElementById("copy-toast");

  function showCopyToast(msg){
    if(!toastEl){ tg.showAlert(msg); return; }
    toastEl.textContent=`✅ ${msg}`;
    toastEl.classList.remove("hidden");
    toastEl.animate?.([{opacity:0, transform:'translateY(4px)'},{opacity:1, transform:'none'}],{duration:200});
    clearTimeout(showCopyToast._t);
    showCopyToast._t=setTimeout(()=>toastEl.classList.add("hidden"), 2600);
  }

  async function copyToClipboard(text){
    try{
      if(navigator.clipboard?.writeText){ await navigator.clipboard.writeText(text); return true; }
    }catch(e){ /* Telegram webview'da ruxsat bo'lmasligi mumkin */ }
    try{
      const ta=document.createElement("textarea");
      ta.value=text;
      ta.setAttribute("readonly","");
      ta.style.position="fixed"; ta.style.top="-1000px"; ta.style.opacity="0";
      document.body.appendChild(ta);
      ta.select(); ta.setSelectionRange(0, ta.value.length);
      const ok=document.execCommand("copy");
      ta.remove();
      return ok;
    }catch(e){ return false; }
  }

  window.copyCardValue=async function(rawText, label, btn){
    const text=(rawText||"").trim();
    if(!text) return;
    const ok=await copyToClipboard(text);
    if(ok){
      showCopyToast(`${label} nusxalandi: ${text}`);
      if(tg.HapticFeedback?.notificationOccurred){ try{ tg.HapticFeedback.notificationOccurred("success"); }catch(e){} }
      if(btn){
        const old=btn.innerText;
        btn.innerText="✅ Nusxalandi";
        btn.classList.add("copied");
        setTimeout(()=>{ btn.innerText=old; btn.classList.remove("copied"); }, 2000);
      }
    } else {
      tg.showAlert(`${label}: ${text}`);
    }
  };

  const btnCopyCard=document.getElementById("btn-copy-card");
  if(btnCopyCard){
    btnCopyCard.addEventListener("click",()=>copyCardValue((copyNumEl?.textContent||"").replace(/\s+/g,""), "Karta raqami", btnCopyCard));
  }
  const btnCopyOwner=document.getElementById("btn-copy-owner");
  if(btnCopyOwner){
    btnCopyOwner.addEventListener("click",()=>copyCardValue(copyOwnerEl?.textContent||"", "Karta egasi", btnCopyOwner));
  }
  if(numberEl){
    numberEl.addEventListener("click", ()=>copyCardValue(numberEl.textContent.replace(/\s+/g,""), "Karta raqami", null));
  }

  fetch(`${API_BASE_URL}/api/payment-info`).then(r=>r.ok?r.json():null).then(data=>{
    if(!data) return;
    if(data.card_number){
      if(numberEl) numberEl.textContent=data.card_number;
      if(copyNumEl) copyNumEl.textContent=data.card_number;
    }
    const ownerEl=document.getElementById("card-owner");
    if(data.card_owner){
      if(ownerEl) ownerEl.textContent=data.card_owner;
      if(copyOwnerEl) copyOwnerEl.textContent=data.card_owner;
    }
  }).catch(()=>{});
}
init3DCard();

function parseFlightData(raw){
  if(!raw) return {};
  if(typeof raw==="string"){ try{ return JSON.parse(raw)||{}; }catch(e){ return {}; } }
  return typeof raw==="object"?raw:{};
}
function seatFromId(id){ const n=Number(id)||1; return `${8+(n%22)}${"ABCDEF"[n%6]}`; }
function gateFromDest(dest,id){ const map={JED:"C12",MED:"B07",RUH:"A04"}; return map[(dest||"").toUpperCase()]||`D${String(((Number(id)||1)%18)+1).padStart(2,"0")}`; }

function boardingPassHTML(order, passport, opts={}){
  const origin=(order.origin||state.origin||"TAS").toUpperCase();
  const dest=(order.destination||state.destination||"JED").toUpperCase();
  const flight=parseFlightData(order.flight_data||state.selectedFlight);
  const name=`${passport.first_name||""} ${passport.last_name||""}`.trim().toUpperCase()||"YO'LOVCHI";
  const seat=seatFromId(order.id||1);
  const gate=gateFromDest(dest, order.id);
  const pnr=`SA${String(order.id||0).padStart(4,"0")}U`;
  const dep=flight.departure_time||"09:30";
  const date=order.depart_date||state.departDate||"-";
  const st=opts.status||order.status||"new";
  const stMap={ new:{t:"KO‘RIB CHIQILMOQDA",c:""}, awaiting_confirmation:{t:"TO‘LOV TEKSHIRILMOQDA",c:""}, confirmed:{t:"TASDIQLANGAN · BOARDING PASS",c:"ok"}, rejected:{t:"RAD ETILGAN",c:"bad"} };
  const badge=stMap[st]||stMap.new;
  return `
    <article class="bp-ticket ${st!=="confirmed"?"pending":""}">
      <div class="bp-main">
        <div class="bp-kicker"><span>SAUDIYA BILETLAR ✦ PREMIUM</span><span>${flight.airline||"Saudiya Biletlar"} · ${flight.flight_number||"SAU-777"}</span></div>
        <div class="bp-route"><div><div class="bp-iata">${origin}</div><div class="bp-city">${CITY_NAMES[origin]||origin}</div></div><div class="bp-plane">✈</div><div style="text-align:right;"><div class="bp-iata">${dest}</div><div class="bp-city">${CITY_NAMES[dest]||dest}</div></div></div>
        <div class="bp-grid">
          <div class="bp-cell"><span>YO‘LOVCHI</span><strong>${name}</strong></div>
          <div class="bp-cell"><span>SANA</span><strong>${date}</strong></div>
          <div class="bp-cell"><span>UCHISH</span><strong>${dep}</strong></div>
          <div class="bp-cell"><span>PNR</span><strong>${pnr}</strong></div>
          <div class="bp-cell"><span>DARVOZA</span><strong>${gate}</strong></div>
          <div class="bp-cell"><span>O‘RINDIQ</span><strong>${seat}</strong></div>
        </div>
        <span class="bp-status ${badge.c}">${badge.t}</span>
      </div>
      <div class="bp-stub"><div class="bp-stub-title">BOARDING</div><div><div class="bp-stub-seat">${seat}</div><div class="bp-stub-gate">GATE ${gate}</div></div><div class="bp-bars" aria-hidden="true"></div></div>
    </article>
  `;
}
window.closeBoardingPass=function(){ const modal=document.getElementById("bp-modal"); if(modal) modal.classList.add("hidden"); };
window.openBoardingPass=function(html){ const modal=document.getElementById("bp-modal"); const body=document.getElementById("bp-modal-body"); if(body) body.innerHTML=html; if(modal) modal.classList.remove("hidden"); };

// ==================== ZAXIRA REYSLAR ====================
function generateComprehensiveFlights(origin, destination, date){
  // MUHIM: bular haqiqiy bron qilingan reyslar EMAS — jadval bo'yicha taxminiy
  // variantlar. Narx va joylar admin tomonidan tasdiqlanadi (source: "estimate").
  const originCode=(origin||"TAS").toUpperCase();
  const destCode=(destination||"JED").toUpperCase();
  const airlinesPool=[
    {name:"Centrum Air", flightNum:"C6-331", depTime:"06:30", arrTime:"10:15", duration:"5s 45d", price:380, baggage:"30 kg + 7 kg", direct:true},
    {name:"Uzbekistan Airways", flightNum:"HY-3381", depTime:"09:45", arrTime:"13:20", duration:"5s 35d", price:420, baggage:"30 kg + 8 kg", direct:true},
    {name:"Flynas", flightNum:"XY-612", depTime:"14:15", arrTime:"18:00", duration:"5s 45d", price:370, baggage:"20 kg + 7 kg", direct:true},
    {name:"Saudia", flightNum:"SV-841", depTime:"18:20", arrTime:"22:05", duration:"5s 45d", price:460, baggage:"2x23 kg (46 kg)", direct:true},
    {name:"Panorama Airways", flightNum:"5P-552", depTime:"04:00", arrTime:"07:45", duration:"5s 45d", price:390, baggage:"30 kg + 7 kg", direct:true},
    {name:"Air Arabia", flightNum:"G9-224", depTime:"11:20", arrTime:"17:40", duration:"7s 20d", price:325, baggage:"30 kg + 7 kg", direct:false},
    {name:"Jazeera Airways", flightNum:"J9-682", depTime:"05:10", arrTime:"10:30", duration:"6s 20d", price:335, baggage:"30 kg + 7 kg", direct:false}
  ];
  return airlinesPool.map((item,idx)=>({ origin:originCode, destination:destCode, price:item.price, airline:item.name, flight_number:item.flightNum, departure_time:item.depTime, arrival_time:item.arrTime, duration:item.duration, baggage:item.baggage, transfers:item.direct?0:1, source:"estimate" }));
}

// ==================== QIDIRUV ====================
const btnSearch=document.getElementById("btn-search");
if(btnSearch){
  btnSearch.addEventListener("click", async ()=>{
    const origin=document.getElementById("origin_code")?.value || document.getElementById("origin")?.value;
    const destination=document.getElementById("destination_code")?.value || document.getElementById("destination")?.value;
    const departDate=document.getElementById("depart_date")?.value;
    const passengers=parseInt(document.getElementById("passengers")?.value||"1",10);
    if(!origin||!destination){ tg.showAlert("Iltimos, uchish va qo'nish shahrini tanlang."); return; }
    if(!departDate){ tg.showAlert("Iltimos, jo'nash sanasini tanlang."); return; }
    state.origin=origin.toUpperCase(); state.destination=destination.toUpperCase(); state.departDate=departDate; state.passengers=passengers;
    tg.MainButton?.showProgress();
    btnSearch.innerHTML='<span>⏳ Reyslar qidirilmoqda...</span>';
    btnSearch.disabled=true;
    try{
      const url=`${API_BASE_URL}/api/search?origin=${encodeURIComponent(origin)}&destination=${encodeURIComponent(destination)}&depart_date=${encodeURIComponent(departDate)}`;
      const res=await fetch(url);
      const data=await res.json();
      let apiResults=data.results||[];
      const allFlights=generateComprehensiveFlights(origin,destination,departDate);
      let combinedResults=[...apiResults];
      allFlights.forEach(f=>{ if(!combinedResults.some(r=>r.airline===f.airline && r.price===f.price)) combinedResults.push(f); });
      lastFlightResults=combinedResults;
      renderResults(combinedResults);
      showScreen("screen-results");
    } catch(e){
      const allFlights=generateComprehensiveFlights(origin,destination,departDate);
      lastFlightResults=allFlights;
      renderResults(allFlights);
      showScreen("screen-results");
    } finally {
      tg.MainButton?.hideProgress();
      btnSearch.innerHTML='<span>✈️ Barcha Chiptalarni Qidirish</span>';
      btnSearch.disabled=false;
    }
  });
}

function addMinutesToTime(hhmm, minutes){
  const [h,m]=(hhmm||"09:30").split(":").map(Number);
  const total=((isNaN(h)?9:h)*60+(isNaN(m)?30:m)+minutes)%1440;
  return `${String(Math.floor(total/60)).padStart(2,"0")}:${String(total%60).padStart(2,"0")}`;
}
function durationToMinutes(text){
  const m=String(text||"").match(/(\d+)\s*s(?:oat)?\s*(\d+)?/i);
  if(!m) return 345;
  return Number(m[1])*60 + Number(m[2]||0);
}
// ==================== NATIJALAR — BOARDING PASS DIZAYNI ====================
function flightBoardingPassHTML(f, idx){
  const origin=(f.origin||state.origin||"TAS").toUpperCase();
  const dest=(f.destination||state.destination||"JED").toUpperCase();
  const airlineName=f.airline||"Centrum Air / Saudia";
  const flightNumber=f.flight_number||"SAU-"+(100+idx);
  let depTime=f.departure_time||"09:30";
  if(f.departure_at){ try{ const d=new Date(f.departure_at); depTime=`${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`; }catch(e){} }
  const duration=f.duration||"5s 45d";
  const arrTime=f.arrival_time||addMinutesToTime(depTime, durationToMinutes(duration));
  const transfers=Number(f.transfers||0);
  const transferText=transfers===0?"TO‘G‘RIDAN-TO‘G‘RI":`${transfers} TA TRANZIT`;
  const baggageText=f.baggage||"30 kg + 7 kg";
  const price=formatPrice(f.price);
  const date=state.departDate||"-";

  // Narx manbasi — halol ko'rsatiladi
  const src=f.source||"estimate";
  const isLive=src==="api";
  const isManual=src==="manual";
  const statusText=isLive
    ? "✅ Jonli narx (aviakassa bazasi)"
    : isManual
      ? "✅ Tasdiqlangan chipta (bizning bazamiz)"
      : "⚠️ Taxminiy narx — admin tasdiqlaydi";
  const statusClass=isLive?"live":(isManual?"manual":"estimate");
  const seatsText=f.seats_available?`${f.seats_available} ta joy`:"So'rov bo'yicha";

  return `
    <article class="bp-ticket bp-result" data-idx="${idx}">
      <div class="bp-main">
        <div class="bp-kicker"><span>SAUDIYA BILETLAR ✦ REYS TAKLIFI</span><span>${airlineName} · ${flightNumber}</span></div>
        <div class="bp-route">
          <div><div class="bp-iata">${origin}</div><div class="bp-city">${CITY_NAMES[origin]||origin} · ${depTime}</div></div>
          <div class="bp-plane">✈</div>
          <div style="text-align:right;"><div class="bp-iata">${dest}</div><div class="bp-city">${CITY_NAMES[dest]||dest} · ${arrTime}</div></div>
        </div>
        <div class="bp-flightline"><span>${transferText}</span><span>⏱ ${duration}</span><span>🧳 ${baggageText}</span></div>
        <div class="bp-grid">
          <div class="bp-cell"><span>SANA</span><strong>${date}</strong></div>
          <div class="bp-cell"><span>UCHISH</span><strong>${depTime}</strong></div>
          <div class="bp-cell"><span>QO‘NISH</span><strong>${arrTime}</strong></div>
          <div class="bp-cell"><span>REYS</span><strong>${flightNumber}</strong></div>
          <div class="bp-cell"><span>BAGAJ</span><strong>${baggageText}</strong></div>
          <div class="bp-cell"><span>JOYLAR</span><strong>${seatsText}</strong></div>
        </div>
        <div class="bp-price-row">
          <div>
            <span class="bp-price-label">1 yo'lovchi uchun</span>
            <div class="bp-price">${price}</div>
          </div>
          <button type="button" class="bp-book-btn" data-book="${idx}">🎫 Band qilish</button>
        </div>
        <span class="bp-status ${statusClass}">${statusText}</span>
      </div>
      <div class="bp-stub">
        <div class="bp-stub-title">REYS</div>
        <div><div class="bp-stub-seat">${flightNumber}</div><div class="bp-stub-gate">${transfers===0?"TO‘G‘RI":"TRANZIT"}</div></div>
        <div class="bp-bars" aria-hidden="true"></div>
      </div>
    </article>
  `;
}

function renderResults(flights){
  const list=document.getElementById("results-list");
  const empty=document.getElementById("results-empty");
  const countBadge=document.getElementById("results-count-badge");
  if(!list) return;
  list.innerHTML="";
  if(!flights||!flights.length){
    if(empty) empty.classList.remove("hidden");
    if(countBadge) countBadge.innerText="0 ta reys";
    return;
  }
  if(empty) empty.classList.add("hidden");
  if(countBadge) countBadge.innerText=`${flights.length} ta reys topildi`;

  flights.forEach((f,idx)=>{
    const wrap=document.createElement("div");
    wrap.className="bp-result-wrap";
    wrap.style.animationDelay=`${idx*55}ms`;
    wrap.innerHTML=flightBoardingPassHTML(f, idx);
    list.appendChild(wrap);
    wrap.querySelector("[data-book]")?.addEventListener("click",(e)=>{ e.stopPropagation(); selectFlight(f); });
    wrap.querySelector(".bp-ticket")?.addEventListener("click",()=>openBoardingPass(flightBoardingPassHTML(f, idx)));
  });

  const liveCount=flights.filter(f=>(f.source||"")==="api"||(f.source||"")==="manual").length;
  const note=document.createElement("p");
  note.className="results-note";
  note.innerHTML=liveCount
    ? `✅ ${liveCount} ta jonli/tasdiqlangan narx · ⚠️ qolganlari <b>taxminiy</b> — admin tasdiqlagach yakuniy narx aytiladi`
    : `⚠️ Narxlar <b>taxminiy</b> (jadval bo'yicha). Yakuniy narx va joy mavjudligi admin tomonidan tasdiqlanadi.`;
  list.appendChild(note);
}

// ==================== TANLASH ====================
function selectFlight(flight){
  state.selectedFlight=flight;
  const summaryEl=document.getElementById("selected-flight-summary");
  if(summaryEl){
    summaryEl.innerHTML=`
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <h3 style="font-size: 15px; font-weight: 800; color: var(--primary);">📋 Tanlangan reys</h3>
        <span style="font-size:10px; background: linear-gradient(135deg,#D4AF37,#F3D77A); color:#0B1B3A; padding:3px 8px; border-radius:8px; font-weight:800;">GOLD EDITION</span>
      </div>
      <div style="display: flex; justify-content: space-between; font-size: 14px; font-weight: 700; margin-bottom: 4px;">
        <span>✈️ ${state.origin} ➔ ${state.destination}</span>
        <span style="color: var(--primary); font-size: 16px;">${formatPrice(flight.price)}</span>
      </div>
      <div style="font-size: 12px; color: var(--text-muted);">🛫 ${flight.airline||"Aviakompaniya"} | 📅 ${state.departDate} | 👥 ${state.passengers} yo'lovchi</div>
    `;
  }
  showScreen("screen-passport");
}

const btnToPayment=document.getElementById("btn-to-payment");
if(btnToPayment){
  btnToPayment.addEventListener("click", ()=>{
    const first_name=document.getElementById("p_first_name")?.value.trim()||"";
    const last_name=document.getElementById("p_last_name")?.value.trim()||"";
    const passport_number=document.getElementById("p_number")?.value.trim()||"";
    const birth_year=document.getElementById("p_birth_year")?.value.trim()||"";
    const expiry_date=document.getElementById("p_expiry")?.value||"";
    if(!first_name||!last_name||!passport_number||!birth_year||!expiry_date){ tg.showAlert("Iltimos, barcha pasport maydonlarini to'ldiring."); return; }
    state.passport={ first_name:first_name.toUpperCase(), last_name:last_name.toUpperCase(), passport_number:passport_number.toUpperCase(), birth_year:parseInt(birth_year,10), expiry_date };
    showScreen("screen-payment");
  });
}

// ==================== TO'LOV ====================
const paymentFileInput=document.getElementById("payment_file");
if(paymentFileInput){
  paymentFileInput.addEventListener("change",(e)=>{
    const file=e.target.files[0]; if(!file) return;
    state.paymentFile=file;
    const preview=document.getElementById("payment_preview");
    if(preview){ preview.src=URL.createObjectURL(file); preview.classList.remove("hidden"); }
  });
}
const btnSubmitOrder=document.getElementById("btn-submit-order");
if(btnSubmitOrder){
  btnSubmitOrder.addEventListener("click", async ()=>{
    if(!state.paymentFile){ tg.showAlert("Iltimos, to'lov cheki skrinshotini yuklang."); return; }
    tg.MainButton?.showProgress();
    btnSubmitOrder.innerText="⏳ Yuborilmoqda...";
    btnSubmitOrder.disabled=true;
    try{
      const orderPayload={ telegram_user_id:user.id, username:user.username||null, origin:state.origin, destination:state.destination, depart_date:state.departDate, passengers:state.passengers, flight_data:state.selectedFlight, passport:state.passport };
      const orderRes=await fetch(`${API_BASE_URL}/api/orders`,{ method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(orderPayload) });
      if(!orderRes.ok) throw new Error("Buyurtma yaratishda xatolik");
      const orderData=await orderRes.json();
      state.lastOrderId=orderData.order_id;
      const formData=new FormData(); formData.append("file",state.paymentFile);
      await fetch(`${API_BASE_URL}/api/orders/${state.lastOrderId}/payment`,{ method:"POST", body:formData });
      const successOrderIdEl=document.getElementById("success-order-id");
      if(successOrderIdEl) successOrderIdEl.textContent=state.lastOrderId;
      showScreen("screen-success");
    } catch(e){ tg.showAlert("Buyurtmani yuborishda xatolik yuz berdi. Qayta urinib ko'ring."); console.error(e); }
    finally { tg.MainButton?.hideProgress(); btnSubmitOrder.innerText="✅ Buyurtmani Tasdiqlashga Yuborish"; btnSubmitOrder.disabled=false; }
  });
}
const btnNewOrder=document.getElementById("btn-new-order");
if(btnNewOrder){
  btnNewOrder.addEventListener("click", ()=>{
    state.selectedFlight=null; state.passport=null; state.paymentFile=null;
    const preview=document.getElementById("payment_preview"); if(preview) preview.classList.add("hidden");
    showScreen("screen-search");
  });
}

// ==================== VIZA ARIZALARI ====================
const VISA_TYPE_LABELS={
  tourist_multi:"1 yillik Multi Turistik Viza",
  umrah_nusuk:"Rasmiy Umra Vizasi (Nusuk)",
};
const VISA_STATUS_LABELS={
  new:"🆕 Yangi",
  processing:"⏳ Ko'rib chiqilmoqda",
  approved:"✅ Tasdiqlangan",
  rejected:"❌ Rad etilgan",
};

function showVisaFormMessage(message, isError=false){
  const el=document.getElementById("visa-form-message");
  if(!el) return;
  el.textContent=message;
  el.classList.remove("hidden", "error", "success");
  el.classList.add(isError?"error":"success");
}

function renderVisaApplications(applications){
  const list=document.getElementById("visa-applications-list");
  if(!list) return;
  if(!applications?.length){
    list.innerHTML='<p class="visa-empty">Hozircha viza arizangiz yo\'q.</p>';
    return;
  }
  list.innerHTML=applications.map(a=>`
    <article class="visa-application-item ${escapeHtml(a.status||"new")}">
      <div class="visa-application-top">
        <strong>#${Number(a.id)||"-"} · ${escapeHtml(VISA_TYPE_LABELS[a.visa_type]||a.visa_type)}</strong>
        <span>${escapeHtml(VISA_STATUS_LABELS[a.status]||a.status)}</span>
      </div>
      <p>👤 ${escapeHtml(a.first_name)} ${escapeHtml(a.last_name)} · 🛂 ${escapeHtml(a.passport_number)}</p>
      <p>📅 Safar: ${escapeHtml(a.travel_date||"Belgilanmagan")}</p>
      ${a.admin_note ? `<p class="visa-admin-note">📝 ${escapeHtml(a.admin_note)}</p>` : ""}
    </article>
  `).join("");
}

async function loadVisaApplications(){
  const list=document.getElementById("visa-applications-list");
  if(!list) return;
  if(!user.id || Number(user.id)<=0){
    list.innerHTML='<p class="visa-empty">Ariza yuborish uchun Mini Appni Telegram ichidan oching.</p>';
    return;
  }
  list.innerHTML='<p class="visa-empty">⏳ Arizalar yuklanmoqda...</p>';
  try{
    const data=await apiJson(
      `${API_BASE_URL}/api/visa-applications?telegram_user_id=${encodeURIComponent(user.id)}`,
      {headers:telegramHeaders()},
    );
    renderVisaApplications(data.applications||[]);
  }catch(e){ list.innerHTML=`<p class="visa-empty error">${escapeHtml(e.message)}</p>`; }
}

document.getElementById("refresh-visa-applications")?.addEventListener("click", loadVisaApplications);
const visaTravelDate=document.getElementById("visa-travel-date");
if(visaTravelDate) visaTravelDate.min=isoDate(new Date());
const visaBirthDate=document.getElementById("visa-birth-date");
if(visaBirthDate) visaBirthDate.max=isoDate(new Date());

const btnSubmitVisa=document.getElementById("btn-submit-visa");
btnSubmitVisa?.addEventListener("click", async()=>{
  if(!user.id || Number(user.id)<=0){ tg.showAlert("Ariza uchun Mini Appni Telegram ichidan oching."); return; }
  const payload={
    telegram_user_id:user.id,
    username:user.username||null,
    visa_type:document.getElementById("visa-type")?.value||"",
    first_name:document.getElementById("visa-first-name")?.value.trim()||"",
    last_name:document.getElementById("visa-last-name")?.value.trim()||"",
    phone:document.getElementById("visa-phone")?.value.trim()||"",
    passport_number:document.getElementById("visa-passport")?.value.trim().toUpperCase()||"",
    birth_date:document.getElementById("visa-birth-date")?.value||"",
    travel_date:document.getElementById("visa-travel-date")?.value||null,
    notes:document.getElementById("visa-notes")?.value.trim()||null,
  };
  if(!payload.first_name||!payload.last_name||!payload.phone||!payload.passport_number||!payload.birth_date){
    showVisaFormMessage("Barcha majburiy maydonlarni to'ldiring.", true);
    return;
  }
  if(!/^[A-Z0-9]{5,20}$/.test(payload.passport_number)){
    showVisaFormMessage("Pasport raqamini to'g'ri kiriting (masalan FA1234567).", true);
    return;
  }

  const oldText=btnSubmitVisa.innerText;
  btnSubmitVisa.disabled=true;
  btnSubmitVisa.innerText="⏳ Yuborilmoqda...";
  try{
    const data=await apiJson(`${API_BASE_URL}/api/visa-applications`, {
      method:"POST",
      headers:telegramHeaders({"Content-Type":"application/json"}),
      body:JSON.stringify(payload),
    });
    showVisaFormMessage(`✅ Ariza #${data.application_id} qabul qilindi. Holati o'zgarsa bot xabar beradi.`);
    ["visa-first-name","visa-last-name","visa-phone","visa-passport","visa-birth-date","visa-travel-date","visa-notes"].forEach(id=>{
      const el=document.getElementById(id); if(el) el.value="";
    });
    await loadVisaApplications();
  }catch(e){ showVisaFormMessage(e.message, true); }
  finally{ btnSubmitVisa.disabled=false; btnSubmitVisa.innerText=oldText; }
});


// ==================== USER ORDERS ====================
async function loadUserOrders(){
  const list=document.getElementById("user-orders-list");
  const empty=document.getElementById("user-orders-empty");
  if(!list) return;
  list.innerHTML=`<div style="text-align:center; padding:20px; font-size:13px; color:var(--text-muted);">⏳ Buyurtmalar yuklanmoqda...</div>`;
  if(empty) empty.classList.add("hidden");
  try{
    const res=await fetch(`${API_BASE_URL}/api/my-orders?telegram_user_id=${user.id}`);
    const data=await res.json();
    const orders=data.orders||[];
    list.innerHTML="";
    if(!orders.length){ if(empty) empty.classList.remove("hidden"); return; }
    orders.forEach(o=>{
      const passport=(Array.isArray(o.passports)&&o.passports[0])|| (o.passports && typeof o.passports==="object"?o.passports:{})||{};
      const wrap=document.createElement("div");
      wrap.innerHTML=boardingPassHTML(o,passport);
      wrap.style.cursor="pointer";
      wrap.animate?.([{opacity:0, transform:'translateY(6px)'},{opacity:1, transform:'none'}],{duration:300});
      wrap.addEventListener("click",()=>openBoardingPass(boardingPassHTML(o,passport)));
      list.appendChild(wrap);
    });
  } catch(e){ list.innerHTML=`<div style="text-align:center; padding:20px; font-size:13px; color:var(--danger);">Buyurtmalarni yuklashda xato yuz berdi.</div>`; }
}
console.log(`Saudiya Biletlar ${APP_VERSION} — Yangi dizayn yuklandi ✈️`);

// ==================== BUILD VERSIYASI (eski deployni aniqlash) ====================
const UI_BUILD = "v13";
async function showBuildInfo(){
  const el = document.getElementById("app-build");
  if(!el) return;
  try{
    const res = await fetch(`${API_BASE_URL}/api/version?t=${Date.now()}`, { cache: "no-store" });
    if(!res.ok) throw new Error("version yo'q");
    const data = await res.json();
    const backend = data.build || "?";
    const match = backend === UI_BUILD;
    el.textContent = `UI ${UI_BUILD} · Backend ${backend}${match ? " ✅" : " ⚠️ eski deploy"}`;
    el.classList.toggle("stale", !match);
  }catch(e){
    // Eski backendda /api/version umuman yo'q — demak eski deploy ishlayapti
    el.textContent = `UI ${UI_BUILD} · Backend: eski versiya ⚠️`;
    el.classList.add("stale");
  }
}
showBuildInfo();
