# 🕋 Saudiya Biletlar — Backend + Telegram Bot + Mini App

Umra va ziyorat reyslari uchun aviachipta xizmati: FastAPI backend, aiogram Telegram bot,
Telegram Mini App (statik frontend) va admin boshqaruv paneli.

---

## ✨ Asosiy funksiyalar

### 0A. Viza arizalari
Mini Appdagi **Viza** bo'limidan 1 yillik Multi Turistik yoki Nusuk Umra vizasi uchun
ariza yuboriladi. Ariza Supabase'da saqlanadi va admin Telegram guruhiga xabar boradi.

- Mijoz o'z arizalari va ularning `new / processing / approved / rejected` holatini ko'radi
- Admin panelda arizalarni filtrlash, holat/izohni yangilash va o'chirish mumkin
- Holat yangilanganda mijozga Telegram orqali avtomatik xabar yuboriladi
- Pasport raqami, sanalar va maydon uzunliklari backendda tekshiriladi
- Shaxsiy endpointlar Telegram `initData` HMAC imzosi bilan himoyalangan; boshqa user ID bilan o'qib bo'lmaydi

### 0B. Narx tushganda obuna bo'lish
Mijoz yo'nalish, 60 kungacha sana oralig'i va maqsadli USD narxini belgilaydi.
`/api/cron/price-alerts` faol obunalarni tekshiradi. Faqat Travelpayouts API yoki admin
kiritgan tasdiqlangan narx maqsadga tushsa Telegram xabari yuboriladi; taxminiy
(`estimate`) narxlar hech qachon xabarni ishga tushirmaydi.

- Bir martalik xabardan so'ng obuna avtomatik nofaol qilinadi
- Mijoz obunalarini ko'rishi va bekor qilishi mumkin
- Admin panelda barcha/faol obunalarni ko'rish va o'chirish mumkin
- Oxirgi tekshirilgan narx va vaqt saqlanadi

### 1. Avto-post sanalari — faqat yaqin 3–35 kun
Kanalga chiqadigan kunlik post endi **faqat bugundan 3 kundan 35 kungacha** bo'lgan reyslarni ko'rsatadi.
Uzoq dekabr/yanvar sanalari umuman tushmaydi.

- `travelpayouts.MIN_DAYS_AHEAD = 3`, `travelpayouts.MAX_DAYS_AHEAD = 35`
- `filter_offers_by_window()` — sanasi yo'q yoki oynadan tashqaridagi takliflarni o'chiradi
- `_fetch_window_for_route()` — Travelpayouts `prices_for_dates` (v3) orqali aniq sanali narxlar
  oyma-oy so'raladi, so'ng qat'iy filtrlanadi; API bo'sh qaytarsa `prices/latest` (v2) zaxira sifatida
  ishlatiladi va u ham filtrdan o'tadi
- Post matnida sana o'zbekcha ko'rinishda: `24.08.2026 (Dushanba) — 3 kundan keyin`
- Oynani so'rovda o'zgartirish mumkin: `/api/cron/daily-post?secret=...&min_days=3&max_days=35`

### 2. O'zbekistonning 11 ta aeroporti — aralash reyslar
`TAS, NMA, SKD, FEG, BHK, AZN, UGC, TMJ, NVI, KSQ, NCU` → `JED` va `MED`.

- `pick_mixed_offers()` — bitta shahar ikki marta takrorlanmaydi, Jidda/Madina navbatma-navbat aralashadi
- `top_up_missing_cities()` — API'dan tushmagan shaharlar 3–35 kunlik zaxira takliflar bilan
  to'ldiriladi, shuning uchun postda har doim 11 ta aeroport qatnashadi

### 3. Arzon narxlar taqvimi — `GET /api/calendar`
Mini Appdagi gorizontal taqvim: har bir kun uchun eng arzon narx, eng arzon kun alohida belgilanadi.

```
GET /api/calendar?origin=TAS&destination=JED&start_date=2026-09-01&days=30
```
Qo'lda qo'shilgan (manual) chiptalar API narxidan arzon bo'lsa — taqvimda ular ustun turadi.

### 3B. 🔥 Avto narx tavsiyalari — `GET /api/top-deals`
Mini App ochilishi bilan **qidiruvdan oldin** eng arzon takliflar avtomatik ko'rsatiladi
(11 ta aeroportdan, faqat 3–35 kun oynasida, eng arzoni 🏆 belgisi bilan).

- Narxlar serverda 30 daqiqa keshlanadi, ilovada har 10 daqiqada avtomatik yangilanadi
- Taklifni bosish → yo'nalish va sana avtomatik tanlanadi va qidiruv ishga tushadi
- USD/So'm o'zgartirgichga bo'ysunadi

```
GET /api/top-deals?limit=8[&refresh=true]
```

### 3C. Keshni o'chirish (eski dizayn muammosi)
Telegram Mini App statik fayllarni uzoq keshlaydi va foydalanuvchi eski dizaynni ko'rib qolardi.
Endi `.html/.js/.css` uchun `Cache-Control: no-store` qaytariladi + asset versiyalari (`?v=13`)
yangilandi — ilova har doim eng so'nggi versiyani yuklaydi.

### 4. Telegram admin 1-click inline tugmalari
Yangi buyurtma va to'lov cheki xabari tagida: **[✅ Tasdiqlash & PDF]** va **[❌ Rad etish]**.

- Tasdiqlash — PDF chiptani generatsiya qilib mijozga yuboradi va statusni `confirmed` qiladi
- Rad etish — tasodifan bosilmasligi uchun ikkinchi bosqich: **[🚫 Ha, rad etilsin] / [↩️ Bekor qilish]**
- Tugmalarni faqat admin (yoki admin guruhi) bosa oladi

### 5. Boarding pass ko'rinishidagi chiptalar
Mini App qidiruv natijalari va buyurtmalar tarixi haqiqiy parvoz chiptasi (boarding pass) dizaynida:
perforatsiya, stub qismi, IATA kodlari, gate/seat/bagaj maydonlari, bosish orqali kattalashadigan modal.

### 6. 3D virtual bank kartasi + 📋 Nusxalash
To'lov oynasida 3D effektli (parallax) UZCARD/HUMO kartasi. Karta raqami va egasi yonida
**[📋 Nusxalash]** tugmasi — bir bosishda clipboardga nusxalanadi (Telegram WebApp haptic + toast bilan).

### 7. Admin panel
- 🗑 **O'chirish** — har bir buyurtma uchun (tasdiqlash modali bilan)
- 🗑 **Rad etilganlarni tozalash** — barcha `rejected` buyurtmalarni bir bosishda o'chiradi
- 📊 **Excel yuklab olish** — CSV (UTF-8 BOM) va formatlangan `.xlsx` (openpyxl)
- 💱 **Markaziy Bank (CBU) jonli kursi** — `cbu.uz`dan 30 daqiqalik kesh bilan, tushum so'mda ham ko'rsatiladi

### 8. `/admin` → `/admin/` avtomatik redirect
StaticFiles mountdan oldin e'lon qilingan `307` redirect — panel har doim ochiladi.

---

## 🔌 API endpointlari

| Metod | Yo'l | Tavsif |
|-------|------|--------|
| `GET` | `/api/health` | Servis holati |
| `GET` | `/api/search` | Chipta qidirish (manual + Travelpayouts) |
| `GET` | `/api/calendar` | Arzon narxlar taqvimi |
| `GET` | `/api/top-deals` | 🔥 Avto narx tavsiyalari (eng arzon takliflar) |
| `GET` | `/api/cbu-rate` | Markaziy Bank USD kursi |
| `POST/GET` | `/api/visa-applications` | Viza arizasini yuborish / mijoz arizalari |
| `POST/GET` | `/api/price-alerts` | Narx obunasini yaratish / mijoz obunalari |
| `DELETE` | `/api/price-alerts/{id}` | Mijozning narx obunasini bekor qilish |
| `GET/POST` | `/api/cron/price-alerts` | Faol narx obunalarini tekshirish va Telegram xabari |
| `POST` | `/api/orders` | Buyurtma yaratish (adminga inline tugmali xabar) |
| `POST` | `/api/orders/{id}/payment` | To'lov chekini yuklash |
| `GET` | `/api/my-orders` | Mijoz buyurtmalari tarixi |
| `GET` | `/api/payment-info` | Karta ma'lumotlari |
| `GET/POST` | `/api/cron/daily-post` | Kanalga kunlik avto-post (3–35 kun oynasi) |
| `GET` | `/api/admin/orders` | Buyurtmalar ro'yxati |
| `GET` | `/api/admin/orders/export?format=csv\|xlsx` | Excel/CSV eksport |
| `POST` | `/api/admin/orders/{id}/confirm` | Tasdiqlash + PDF |
| `POST` | `/api/admin/orders/{id}/reject` | Rad etish |
| `POST` | `/api/admin/orders/clear-rejected` | Rad etilganlarni tozalash |
| `DELETE` | `/api/admin/orders/{id}` | Buyurtmani o'chirish |
| `GET/PATCH/DELETE` | `/api/admin/visa-applications` | Viza arizalarini boshqarish |
| `GET/DELETE` | `/api/admin/price-alerts` | Narx obunalarini boshqarish |
| `GET/POST/DELETE` | `/api/admin/flights` | Qo'lda chipta qo'shish/o'chirish |

Admin endpointlari `X-Admin-Password` sarlavhasini talab qiladi.

---

## 🗄 Supabase migratsiyasi

Yangi funksiyalarni deploy qilishdan oldin Supabase Dashboard → **SQL Editor** orqali
quyidagi faylni bir marta ishga tushiring:

```text
migrations/20260822_visa_and_price_alerts.sql
```

Migratsiya `visa_applications` va `price_alerts` jadvallarini, indekslar, cheklovlar,
`updated_at` triggerlari va RLS himoyasini yaratadi. Backend `service_role` kaliti bilan ishlaydi;
ushbu kalitni frontendga joylamang.

## 🚀 Ishga tushirish

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env      # kerakli qiymatlarni to'ldiring
uvicorn main:app --host 0.0.0.0 --port 8000
```

- Mini App: `http://localhost:8000/`
- Admin panel: `http://localhost:8000/admin` (avtomatik `/admin/` ga o'tadi)

### Cron vazifalari
```bash
# Kunlik kanal posti
curl -X POST "https://<domen>/api/cron/daily-post?secret=$CRON_SECRET"

# Narx obunalarini tekshirish (tavsiya: har 30–60 daqiqada)
curl -X POST "https://<domen>/api/cron/price-alerts?secret=$CRON_SECRET"
```

## 🧪 Testlar

```bash
pip install pytest pytest-asyncio
pytest tests -q
```
