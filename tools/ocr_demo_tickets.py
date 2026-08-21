#!/usr/bin/env python3
"""Demo biletlarni (boarding pass PDF) OCR orqali tekshirish vositasi.

Ishlash tartibi:
1. pdf_generator yordamida demo buyurtmalardan boarding pass + e-ticket PDF generatsiya qilinadi
2. Har bir sahifa PyMuPDF bilan yuqori aniqlikda (300 DPI) PNG ga aylantiriladi
3. RapidOCR (ONNX) bilan matn o'qiladi
4. Kutilgan maydonlar (ism, pasport, reys, PNR, seat, gate...) OCR natijasida
   bor-yo'qligi tekshiriladi va hisobot chiqariladi

Ishlatish:
    python tools/ocr_demo_tickets.py                 # demo biletlarni yaratib OCR qiladi
    python tools/ocr_demo_tickets.py --count 5       # 5 ta demo bilet
    python tools/ocr_demo_tickets.py image.png ...   # tayyor rasm(lar)ni OCR qiladi
"""
import argparse
import os
import re
import sys
from pathlib import Path

# config.py Settings() import vaqtida env talab qiladi — dummy qiymatlar
os.environ.setdefault("BOT_TOKEN", "123456:fake_bot_token_for_ocr")
os.environ.setdefault("ADMIN_CHAT_ID", "-100123456789")
os.environ.setdefault("CHANNEL_ID", "-100987654321")
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy")
os.environ.setdefault("TRAVELPAYOUTS_TOKEN", "dummy_travelpayouts_token")
os.environ.setdefault("WEBHOOK_BASE_URL", "https://example.com")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pdf_generator  # noqa: E402
from rapidocr_onnxruntime import RapidOCR  # noqa: E402
import fitz  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "ocr_output"
PDF_DIR = OUT_DIR / "pdfs"
PNG_DIR = OUT_DIR / "pngs"
TXT_DIR = OUT_DIR / "texts"

# ------------------------- Demo buyurtmalar -------------------------
DEMO_ORDERS = [
    {
        "id": 12345,
        "origin": "TAS",
        "destination": "JED",
        "depart_date": "2026-09-15",
        "passengers": 1,
        "price": 429,
        "flight_data": {
            "airline": "Saudia",
            "flight_number": "SV-501",
            "departure_time": "09:30",
            "arrival_time": "13:15",
        },
        "passport": {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "passport_number": "AC1234567",
            "birth_year": "1994",
            "expiry_date": "2030-05-12",
        },
    },
    {
        "id": 12346,
        "origin": "NMA",
        "destination": "MED",
        "depart_date": "2026-09-22",
        "passengers": 2,
        "price": 512,
        "flight_data": {
            "airline": "Flynas",
            "flight_number": "XY-302",
            "departure_time": "07:45",
            "arrival_time": "12:30",
        },
        "passport": {
            "first_name": "Zilola",
            "last_name": "Karimova",
            "passport_number": "AB9876543",
            "birth_year": "1990",
            "expiry_date": "2029-11-03",
        },
    },
    {
        "id": 12347,
        "origin": "SKD",
        "destination": "JED",
        "depart_date": "2026-10-05",
        "passengers": 1,
        "price": 398,
        "flight_data": {
            "airline": "Uzbekistan Airways",
            "flight_number": "HY-778",
            "departure_time": "18:20",
            "arrival_time": "22:05",
        },
        "passport": {
            "first_name": "Jasur",
            "last_name": "Toxirov",
            "passport_number": "AA1122334",
            "birth_year": "1988",
            "expiry_date": "2028-07-21",
        },
    },
]


# ------------------------- PDF -> rasm -> matn -------------------------
def pdf_to_images(pdf_bytes: bytes, dpi: int = 300) -> list:
    """PDF sahifalarini yuqori aniqlikdagi PNG baytlariga aylantiradi."""
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    for page in doc:
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        images.append(pix.tobytes("png"))
    doc.close()
    return images


def ocr_lines(ocr: RapidOCR, png_bytes: bytes) -> list:
    """Rasmni OCR qilib, (y, x, matn) ro'yxatini qaytaradi (yuqoridan pastga tartiblangan)."""
    result, _ = ocr(png_bytes)
    lines = []
    for box, text, _score in result or []:
        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        lines.append((max(ys), min(xs), text.strip()))
    lines.sort(key=lambda t: (round(t[0] / 20), t[1]))
    return [t[2] for t in lines]


def norm(s: str) -> str:
    """Taqqoslash uchun normalizatsiya: katta harf, probellarni siqish."""
    return re.sub(r"\s+", " ", s.upper()).strip()


def compact(s: str) -> str:
    """Barcha probellarni olib tashlaydi — OCR ko'pincha so'zlarni birlashtirib o'qiydi."""
    return re.sub(r"\s+", "", s.upper())


def find_field(lines: list, expected: str, compact_match: bool = False) -> bool:
    """Kutilgan qiymat OCR qatorlaridan birida borligini tekshiradi."""
    exp = norm(expected)
    if not exp:
        return True
    if any(exp in norm(ln) for ln in lines):
        return True
    # OCR probelsiz o'qisa ham qabul qilamiz (masalan ALI VALIYEV -> ALIVALIYEV)
    if compact_match:
        exp_c = compact(expected)
        return any(exp_c in compact(ln) for ln in lines)
    return False


# ------------------------- Hisobot -------------------------
def verify_ticket(lines: list, order: dict) -> dict:
    passport = order["passport"]
    full_name = f"{passport['first_name']} {passport['last_name']}".upper()
    flight = order["flight_data"]
    checks = {
        "Yo'lovchi ismi": (full_name, True),
        "Pasport raqami": (passport["passport_number"], False),
        "Jo'nash shahri": (order["origin"], False),
        "Borgan shahri": (order["destination"], False),
        "Sana": (order["depart_date"], False),
        "Reys raqami": (flight["flight_number"], False),
        "Aviakompaniya": (flight["airline"], True),
    }
    ok = {}
    for label, (value, compact_match) in checks.items():
        ok[label] = find_field(lines, value, compact_match=compact_match)
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo biletlarni OCR orqali tekshirish")
    parser.add_argument("images", nargs="*", help="Ixtiyoriy: tayyor rasm fayllarini OCR qilish")
    parser.add_argument("--count", type=int, default=3, help="Nechta demo bilet generatsiya qilish (default: 3)")
    parser.add_argument("--dpi", type=int, default=300, help="PDF->PNG aniqlik (default: 300)")
    args = parser.parse_args()

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    TXT_DIR.mkdir(parents=True, exist_ok=True)

    ocr = RapidOCR()

    if args.images:
        # Tayyor rasm(lar)ni OCR qilish
        for img_path in args.images:
            p = Path(img_path)
            print(f"\n{'=' * 60}\n📄 {p.name}\n{'=' * 60}")
            lines = ocr_lines(ocr, p.read_bytes())
            for ln in lines:
                print("  " + ln)
            (TXT_DIR / f"{p.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
        return

    # 1. Demo biletlar generatsiya qilish
    orders = DEMO_ORDERS[: args.count]
    report_rows = []
    for i, order in enumerate(orders, 1):
        pdf_bytes = pdf_generator.generate_ticket_pdf(order, order["passport"])
        pdf_path = PDF_DIR / f"demo_ticket_{i}_{order['origin']}-{order['destination']}.pdf"
        pdf_path.write_bytes(pdf_bytes)

        print(f"\n{'=' * 60}\n✈️  Demo bilet #{i}: {order['origin']} → {order['destination']} "
              f"({order['passport']['first_name']} {order['passport']['last_name']})\n{'=' * 60}")

        all_lines = []
        page_names = ["boarding_pass", "e_ticket"]
        for page_idx, png_bytes in enumerate(pdf_to_images(pdf_bytes, args.dpi)):
            page_name = page_names[page_idx] if page_idx < len(page_names) else f"page_{page_idx + 1}"
            png_path = PNG_DIR / f"{pdf_path.stem}_{page_name}.png"
            png_path.write_bytes(png_bytes)

            lines = ocr_lines(ocr, png_bytes)
            all_lines.extend(lines)
            print(f"\n  ── {page_name} ({png_path.name}) ──")
            for ln in lines:
                print(f"    {ln}")

        txt_path = TXT_DIR / f"{pdf_path.stem}.txt"
        txt_path.write_text("\n".join(all_lines), encoding="utf-8")

        # 2. Tekshirish
        checks = verify_ticket(all_lines, order)
        passed = sum(checks.values())
        total = len(checks)
        print(f"\n  ✅ Tekshiruv: {passed}/{total} maydon topildi")
        for label, ok in checks.items():
            mark = "✅" if ok else "❌"
            print(f"    {mark} {label}")
        report_rows.append((order, checks, all_lines))

    # 3. Xulosa
    print("\n" + "=" * 60)
    print("📊 XULOSA")
    print("=" * 60)
    total_ok = total_fail = 0
    for order, checks, _ in report_rows:
        passed = sum(checks.values())
        failed = [k for k, v in checks.items() if not v]
        total_ok += passed
        total_fail += len(failed)
        status = "✅ OK" if not failed else f"❌ {len(failed)} xato: {', '.join(failed)}"
        print(f"  #{order['id']} {order['origin']}→{order['destination']}: {status}")
    print(f"\n  Jami: {total_ok} maydon to'g'ri, {total_fail} maydon topilmadi")
    print(f"\n  Natijalar papkasi: {OUT_DIR.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
