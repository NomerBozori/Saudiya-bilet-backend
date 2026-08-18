import io
import json
from datetime import datetime, timedelta

from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas

from config import settings


PRIMARY = colors.HexColor("#0B1B3A")
PRIMARY_MID = colors.HexColor("#12264F")
NAVY = colors.HexColor("#16325C")
GOLD = colors.HexColor("#D4AF37")
GOLD_LIGHT = colors.HexColor("#F3D77A")
CREAM = colors.HexColor("#F7F1E3")
WHITE = colors.white
MUTED = colors.HexColor("#8A93A6")
INK = colors.HexColor("#101828")



CITY_NAMES = {
    "TAS": "TASHKENT",
    "NMA": "NAMANGAN",
    "SKD": "SAMARKAND",
    "FEG": "FERGANA",
    "BHK": "BUKHARA",
    "UGC": "URGENCH",
    "TMJ": "TERMEZ",
    "JED": "JEDDAH",
    "MED": "MADINAH",
    "RUH": "RIYADH",
    "DXB": "DUBAI",
    "IST": "ISTANBUL",
    "AYT": "ANTALYA",
}


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _city(code: str) -> str:
    code = (code or "-").upper()
    return CITY_NAMES.get(code, code)


def _parse_time(flight: dict, key: str, fallback: str) -> str:
    raw = flight.get(key) or flight.get("departure_at")
    if isinstance(raw, str) and "T" in raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "")).strftime("%H:%M")
        except ValueError:
            pass
    if isinstance(raw, str) and ":" in raw and len(raw) <= 8:
        return raw[:5]
    return fallback


def _boarding_meta(order: dict, flight: dict) -> dict:
    order_id = int(order.get("id") or 0)
    dep = _parse_time(flight, "departure_time", "09:30")
    arr = _parse_time(flight, "arrival_time", "13:15")
    try:
        dep_dt = datetime.strptime(dep, "%H:%M")
        board = (dep_dt - timedelta(minutes=45)).strftime("%H:%M")
    except ValueError:
        board = "08:45"
    seat_row = 8 + (order_id % 22)
    seat_letter = "ABCDEF"[order_id % 6]
    gates = {"JED": "C12", "MED": "B07", "RUH": "A04"}
    dest = str(order.get("destination") or "JED").upper()
    return {
        "dep": dep,
        "arr": arr,
        "board": board,
        "seat": f"{seat_row}{seat_letter}",
        "gate": gates.get(dest, f"D{(order_id % 18) + 1:02d}"),
        "pnr": f"SA{order_id:04d}U",
        "seq": f"{(order_id % 90) + 10:03d}",
        "zone": "2",
        "group": "B",
    }


def generate_ticket_pdf(order: dict, passport: dict) -> bytes:
    buf = io.BytesIO()
    page = landscape(A4)
    c = canvas.Canvas(buf, pagesize=page)
    _draw_boarding_pass(c, page, order, passport)
    c.showPage()
    _draw_eticket_page(c, A4, order, passport)
    c.save()
    buf.seek(0)
    return buf.read()


def _draw_boarding_pass(c: canvas.Canvas, page, order: dict, passport: dict) -> None:
    width, height = page
    flight = _as_dict(order.get("flight_data"))
    meta = _boarding_meta(order, flight)
    order_id = int(order.get("id") or 0)
    origin = str(order.get("origin") or "-").upper()
    dest = str(order.get("destination") or "-").upper()
    depart_date = str(order.get("depart_date") or "-")
    airline = str(flight.get("airline") or "Saudiya Biletlar")
    flight_num = str(flight.get("flight_number") or "SAU-777")
    first_n = (passport.get("first_name") or "").strip()
    last_n = (passport.get("last_name") or "").strip()
    full_name = f"{first_n} {last_n}".strip().upper() or "PASSENGER"
    passport_num = str(passport.get("passport_number") or "-").upper()

    # Background
    c.setFillColor(colors.HexColor("#E9EDF5"))
    c.rect(0, 0, width, height, fill=True, stroke=False)

    # Card
    x, y, w, h = 1.2 * cm, 1.4 * cm, width - 2.4 * cm, height - 2.8 * cm
    stub_w = 6.6 * cm
    main_w = w - stub_w

    c.setFillColor(PRIMARY)
    c.roundRect(x, y, w, h, 16, fill=True, stroke=False)

    # Gold top stripe
    c.setFillColor(GOLD)
    c.rect(x, y + h - 0.18 * cm, w, 0.18 * cm, fill=True, stroke=False)

    # Header band
    c.setFillColor(PRIMARY_MID)
    c.rect(x, y + h - 2.15 * cm, w, 1.97 * cm, fill=True, stroke=False)

    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 0.7 * cm, y + h - 0.85 * cm, "SAUDIYA BILETLAR")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(x + 0.7 * cm, y + h - 1.55 * cm, "BOARDING PASS")
    c.setFont("Helvetica", 8)
    c.setFillColor(GOLD_LIGHT)
    c.drawString(x + 6.4 * cm, y + h - 1.5 * cm, "ELECTRONIC  ·  CONFIRMED")

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(x + main_w - 0.6 * cm, y + h - 0.9 * cm, airline.upper())
    c.setFont("Helvetica", 8)
    c.setFillColor(GOLD_LIGHT)
    c.drawRightString(x + main_w - 0.6 * cm, y + h - 1.45 * cm, f"E-TICKET  #{order_id:06d}")

    # Route block
    route_y = y + h - 5.4 * cm
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 36)
    c.drawString(x + 0.7 * cm, route_y + 0.55 * cm, origin)
    c.setFont("Helvetica", 8)
    c.setFillColor(GOLD_LIGHT)
    c.drawString(x + 0.7 * cm, route_y + 0.15 * cm, _city(origin))

    # Plane line
    line_x1 = x + 4.4 * cm
    line_x2 = x + 8.4 * cm
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.line(line_x1, route_y + 1.05 * cm, line_x2, route_y + 1.05 * cm)
    c.setFillColor(GOLD)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString((line_x1 + line_x2) / 2, route_y + 1.25 * cm, "✈")
    c.setFont("Helvetica", 7)
    c.drawCentredString((line_x1 + line_x2) / 2, route_y + 0.55 * cm, "DIRECT")

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 36)
    c.drawRightString(x + main_w - 0.7 * cm, route_y + 0.55 * cm, dest)
    c.setFont("Helvetica", 8)
    c.setFillColor(GOLD_LIGHT)
    c.drawRightString(x + main_w - 0.7 * cm, route_y + 0.15 * cm, _city(dest))

    # Info grid
    labels = [
        ("PASSENGER", full_name),
        ("PASSPORT", passport_num),
        ("DATE", depart_date),
        ("FLIGHT", flight_num),
        ("DEPARTURE", meta["dep"]),
        ("ARRIVAL", meta["arr"]),
        ("GATE", meta["gate"]),
        ("SEAT", meta["seat"]),
        ("BOARDING", meta["board"]),
        ("PNR / BOOKING", meta["pnr"]),
        ("SEQ", meta["seq"]),
        ("CLASS", "ECONOMY / UMRA"),
    ]
    grid_top = y + 6.3 * cm
    col_w = main_w / 4
    for i, (label, value) in enumerate(labels):
        col = i % 4
        row = i // 4
        gx = x + 0.7 * cm + col * col_w
        gy = grid_top - row * 1.55 * cm
        c.setFillColor(GOLD)
        c.setFont("Helvetica", 7)
        c.drawString(gx, gy, label)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(gx, gy - 0.42 * cm, str(value)[:22])

    # Barcode
    try:
        barcode = Code128(f"SAU{order_id:06d}{origin}{dest}", barHeight=28, barWidth=0.95, humanReadable=False)
        barcode.drawOn(c, x + 0.7 * cm, y + 0.85 * cm)
    except Exception:
        c.setFillColor(WHITE)
        c.rect(x + 0.7 * cm, y + 0.85 * cm, 8 * cm, 0.8 * cm, fill=True, stroke=False)

    c.setFillColor(GOLD_LIGHT)
    c.setFont("Helvetica", 7)
    c.drawString(x + 0.7 * cm, y + 0.5 * cm, f"SAU{order_id:06d}  ·  GATE CLOSES 20 MIN BEFORE DEPARTURE")

    # Perforation
    perf_x = x + main_w
    c.setStrokeColor(GOLD)
    c.setDash(2, 3)
    c.setLineWidth(0.8)
    c.line(perf_x, y + 0.35 * cm, perf_x, y + h - 0.35 * cm)
    c.setDash()
    c.setFillColor(colors.HexColor("#E9EDF5"))
    c.circle(perf_x, y, 0.28 * cm, fill=True, stroke=False)
    c.circle(perf_x, y + h, 0.28 * cm, fill=True, stroke=False)

    # Stub
    c.setFillColor(CREAM)
    c.rect(perf_x, y, stub_w, h, fill=True, stroke=False)
    c.setFillColor(GOLD)
    c.rect(perf_x, y + h - 0.18 * cm, stub_w, 0.18 * cm, fill=True, stroke=False)

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(perf_x + stub_w / 2, y + h - 0.85 * cm, "BOARDING PASS")
    c.setFont("Helvetica", 7)
    c.setFillColor(NAVY)
    c.drawCentredString(perf_x + stub_w / 2, y + h - 1.25 * cm, "SAUDIYA BILETLAR")

    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(PRIMARY)
    c.drawCentredString(perf_x + stub_w / 2, y + h - 2.4 * cm, f"{origin}  ✈  {dest}")

    stub_rows = [
        ("PASSENGER", full_name[:18]),
        ("FLIGHT", flight_num),
        ("DATE", depart_date),
        ("TIME", meta["dep"]),
        ("GATE", meta["gate"]),
        ("SEAT", meta["seat"]),
        ("PNR", meta["pnr"]),
    ]
    sy = y + h - 3.3 * cm
    for label, value in stub_rows:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 6.5)
        c.drawString(perf_x + 0.55 * cm, sy, label)
        c.setFillColor(PRIMARY)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(perf_x + 0.55 * cm, sy - 0.35 * cm, str(value))
        sy -= 1.05 * cm

    try:
        stub_bar = Code128(f"{meta['pnr']}{meta['seat']}", barHeight=22, barWidth=0.8, humanReadable=False)
        stub_bar.drawOn(c, perf_x + 0.45 * cm, y + 0.55 * cm)
    except Exception:
        pass


def _draw_eticket_page(c: canvas.Canvas, page, order: dict, passport: dict) -> None:
    width, height = page
    flight = _as_dict(order.get("flight_data"))
    meta = _boarding_meta(order, flight)
    order_id = int(order.get("id") or 0)
    origin = str(order.get("origin") or "-").upper()
    dest = str(order.get("destination") or "-").upper()
    depart_date = str(order.get("depart_date") or "-")
    airline = str(flight.get("airline") or "Saudiya Biletlar")
    flight_num = str(flight.get("flight_number") or "SAU-777")

    c.setFillColor(PRIMARY)
    c.rect(0, height - 3.6 * cm, width, 3.6 * cm, fill=True, stroke=False)
    c.setFillColor(GOLD)
    c.rect(0, height - 3.72 * cm, width, 0.12 * cm, fill=True, stroke=False)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(1.7 * cm, height - 1.6 * cm, "ELECTRONIC FLIGHT TICKET")
    c.setFont("Helvetica", 10)
    c.drawString(1.7 * cm, height - 2.25 * cm, "Saudiya Biletlar & Umra  ·  Rasmiy tasdiqnoma")
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(width - 1.7 * cm, height - 1.6 * cm, f"E-TICKET #{order_id:06d}")
    c.setFont("Helvetica", 9)
    c.setFillColor(GOLD_LIGHT)
    c.drawRightString(width - 1.7 * cm, height - 2.25 * cm, "STATUS: CONFIRMED")

    y = height - 5.0 * cm
    c.setFillColor(colors.HexColor("#F4F7FB"))
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.roundRect(1.5 * cm, y - 2.3 * cm, width - 3.0 * cm, 2.6 * cm, 8, fill=True, stroke=True)
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(2.1 * cm, y - 1.05 * cm, f"{origin}   →   {dest}")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 10)
    c.drawString(2.1 * cm, y - 1.75 * cm, f"{_city(origin)}  ·  {_city(dest)}")
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(width - 2.1 * cm, y - 1.0 * cm, f"{airline}  {flight_num}")
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawRightString(width - 2.1 * cm, y - 1.55 * cm, f"{depart_date}  {meta['dep']}")

    y -= 3.4 * cm
    first_n = (passport.get("first_name") or "").strip()
    last_n = (passport.get("last_name") or "").strip()
    full_name = f"{first_n} {last_n}".strip().upper() or "-"
    rows = [
        ("Yo'lovchi / Passenger", full_name),
        ("Pasport", str(passport.get("passport_number") or "-").upper()),
        ("Tug'ilgan yil", str(passport.get("birth_year") or "-")),
        ("Pasport muddati", str(passport.get("expiry_date") or "-")),
        ("O'rindiq / Seat", meta["seat"]),
        ("Darvoza / Gate", meta["gate"]),
        ("PNR", meta["pnr"]),
        ("Yo'lovchilar", f"{order.get('passengers') or 1} kishi"),
        ("Bagaj", "30 kg + 7 kg qo'l yuki"),
        ("Klass", "Ekonom / Umra"),
        ("To'lov", f"${order.get('price') if order.get('price') is not None else '-'} USD  ·  PAID"),
    ]

    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1.5 * cm, y, "REYS VA YO'LOVCHI MA'LUMOTLARI")
    y -= 0.35 * cm
    c.setFillColor(WHITE)
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    box_h = 0.55 * cm * len(rows) + 0.5 * cm
    c.roundRect(1.5 * cm, y - box_h, width - 3.0 * cm, box_h, 6, fill=True, stroke=True)
    yy = y - 0.55 * cm
    for label, value in rows:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(2.0 * cm, yy, label)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(8.2 * cm, yy, str(value))
        yy -= 0.55 * cm

    admin_username = getattr(settings, "ADMIN_USERNAME", "nuriddinovdfg")
    y = 3.4 * cm
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(1.5 * cm, y, "MUHIM ESLATMALAR")
    y -= 0.45 * cm
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    notices = [
        "1. Aeroportga parvozdan kamida 3 soat oldin yetib keling. Boarding darvoza yopilishidan 20 daqiqa oldin yakunlanadi.",
        "2. Pasport amal qilish muddati Saudiya Arabistoniga kirish sanasidan kamida 6 oy bo'lishi shart.",
        "3. Elektron viza va ushbu boarding pass / e-ticket nusxasini o'zingiz bilan olib yuring.",
        f"4. Savol va transfer uchun Telegram: @{admin_username}",
    ]
    for n in notices:
        c.drawString(1.5 * cm, y, n)
        y -= 0.38 * cm

    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.line(1.5 * cm, 1.7 * cm, width - 1.5 * cm, 1.7 * cm)
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(MUTED)
    c.drawString(1.5 * cm, 1.2 * cm, "Saudiya Biletlar — rasmiy elektron boarding pass va e-ticket")
    c.drawRightString(width - 1.5 * cm, 1.2 * cm, "saudiya-bilet")
