"""Generador de PDF de "boleta" / recibo elegante para los pedidos.

NO es una boleta oficial SUNAT — es un comprobante interno con look profesional
(logo, items, totales en PEN+USD, método de pago, QR de verificación). Sirve
para que el cliente reciba un PDF bonito por correo al confirmarse la compra.

Usa reportlab platypus (puro Python, sin deps de sistema).
"""

from __future__ import annotations

import io
import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as canvas_mod
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

if TYPE_CHECKING:
    from orders.models import Order

logger = logging.getLogger(__name__)


# --- Paleta de marca (matchea el resto del sitio: rosa/violeta sobre crema) ---
COLOR_PRIMARY = colors.HexColor("#ec4899")  # rosa
COLOR_SECONDARY = colors.HexColor("#8b5cf6")  # violeta
COLOR_DARK = colors.HexColor("#18181b")
COLOR_MUTED = colors.HexColor("#71717a")
COLOR_BORDER = colors.HexColor("#e4e4e7")
COLOR_BG_SOFT = colors.HexColor("#fafafa")
COLOR_OK = colors.HexColor("#10b981")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"],
            fontName="Helvetica-Bold", fontSize=22, leading=26,
            textColor=colors.white, spaceAfter=0,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"],
            fontName="Helvetica", fontSize=11, leading=14,
            textColor=colors.HexColor("#fdf2f8"),
        ),
        "label": ParagraphStyle(
            "label", parent=base["Normal"],
            fontName="Helvetica", fontSize=8, leading=10,
            textColor=COLOR_MUTED, alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "value": ParagraphStyle(
            "value", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=COLOR_DARK, alignment=TA_LEFT,
        ),
        "value_right": ParagraphStyle(
            "value_right", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=COLOR_DARK, alignment=TA_RIGHT,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"],
            fontName="Helvetica", fontSize=8.5, leading=11,
            textColor=COLOR_MUTED,
        ),
        "small_dark": ParagraphStyle(
            "small_dark", parent=base["Normal"],
            fontName="Helvetica", fontSize=9.5, leading=12,
            textColor=COLOR_DARK,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base["Normal"],
            fontName="Helvetica", fontSize=8, leading=10,
            textColor=COLOR_MUTED, alignment=TA_CENTER,
        ),
        "thanks": ParagraphStyle(
            "thanks", parent=base["Normal"],
            fontName="Helvetica-Bold", fontSize=13, leading=16,
            textColor=COLOR_PRIMARY, alignment=TA_CENTER,
            spaceAfter=4,
        ),
    }


def _payment_label(provider: str) -> str:
    return {
        "yape": "Yape QR",
        "binance": "Binance Pay",
        "mercadopago": "Mercado Pago",
        "wallet": "Saldo wallet",
    }.get((provider or "").lower(), provider.title() if provider else "—")


def _to_usd(amount: Decimal, rate: Decimal) -> Decimal | None:
    try:
        if not rate or rate <= 0:
            return None
        return (Decimal(str(amount)) / Decimal(str(rate))).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001
        return None


def _qr_image(text: str, *, size_mm: float = 22) -> Image | None:
    try:
        import qrcode

        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return Image(buf, width=size_mm * mm, height=size_mm * mm)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No pude generar QR para recibo: %s", exc)
        return None


def _site_settings():
    try:
        from catalog.models import SiteSettings
        return SiteSettings.load()
    except Exception:  # noqa: BLE001
        return None


def _payment_settings():
    try:
        from orders.models import PaymentSettings
        return PaymentSettings.load()
    except Exception:  # noqa: BLE001
        return None


def _draw_header_band(canvas: canvas_mod.Canvas, doc: BaseDocTemplate) -> None:
    """Banda superior gradient rosa→violeta + título del recibo."""
    width, height = A4
    band_h = 30 * mm
    # Simulamos un gradient con 60 franjas finas. ReportLab no tiene gradient nativo.
    steps = 60
    r1, g1, b1 = 0xec / 255, 0x48 / 255, 0x99 / 255  # rosa
    r2, g2, b2 = 0x8b / 255, 0x5c / 255, 0xf6 / 255  # violeta
    for i in range(steps):
        t = i / (steps - 1)
        r = r1 + (r2 - r1) * t
        g = g1 + (g2 - g1) * t
        b = b1 + (b2 - b1) * t
        canvas.setFillColorRGB(r, g, b)
        x = i * (width / steps)
        canvas.rect(x, height - band_h, width / steps + 0.5, band_h, fill=1, stroke=0)
    # Logo / nombre + título recibo
    site = doc._site
    name = (site.site_name if site else "VirtualidadSP Store") or "VirtualidadSP Store"
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(15 * mm, height - 16 * mm, name)
    canvas.setFont("Helvetica", 10)
    tagline = (site.tagline if site else "") or "Servicios digitales premium"
    canvas.drawString(15 * mm, height - 22 * mm, tagline[:80])
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawRightString(width - 15 * mm, height - 16 * mm, "RECIBO DE COMPRA")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(width - 15 * mm, height - 22 * mm, "Comprobante interno (no oficial SUNAT)")


def _draw_footer(canvas: canvas_mod.Canvas, doc: BaseDocTemplate) -> None:
    width, _ = A4
    site = doc._site
    canvas.setFillColor(COLOR_BORDER)
    canvas.rect(15 * mm, 18 * mm, width - 30 * mm, 0.5, fill=1, stroke=0)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(COLOR_MUTED)
    bits = []
    if site:
        if site.contact_email:
            bits.append(site.contact_email)
        if site.whatsapp_number:
            bits.append(f"WhatsApp +{site.whatsapp_number}")
        if site.legal_business_name:
            bits.append(site.legal_business_name)
        if site.legal_ruc:
            bits.append(f"RUC {site.legal_ruc}")
    footer_text = "  ·  ".join(bits) if bits else "Gracias por elegirnos"
    canvas.drawCentredString(width / 2, 12 * mm, footer_text)
    canvas.drawCentredString(width / 2, 7 * mm, "Este documento es un comprobante interno. No reemplaza una boleta o factura electrónica SUNAT.")


def generate_receipt_pdf(order: "Order") -> bytes:
    """Devuelve el recibo PDF como bytes."""
    site = _site_settings()
    pay = _payment_settings()
    styles = _styles()

    # ---- Tipo de cambio USD (auto Binance P2P → fallback manual) ----
    usd_rate = Decimal("0")
    try:
        from catalog.context_processors import _usd_rate  # cache 5 min
        usd_rate = _usd_rate() or Decimal("0")
    except Exception:  # noqa: BLE001
        if pay:
            usd_rate = pay.usd_exchange_rate or Decimal("0")

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=38 * mm, bottomMargin=24 * mm,
        title=f"Recibo Pedido {order.display_number}",
        author=(site.site_name if site else "VirtualidadSP Store"),
        subject="Recibo de compra",
    )
    doc._site = site
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height, id="body",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([
        PageTemplate(
            id="main", frames=[frame],
            onPage=lambda c, d: (_draw_header_band(c, d), _draw_footer(c, d)),
        ),
    ])

    story: list = []

    # --- Bloque pedido + cliente (2 columnas) ---
    fecha = timezone.localtime(order.created_at).strftime("%d %b %Y · %H:%M")
    status_label = order.get_status_display()
    customer_name = (order.user.get_full_name() if order.user else "") or order.email or "Cliente"
    customer_email = order.email or (order.user.email if order.user else "—")
    customer_phone = order.phone or "—"

    info_left = [
        [Paragraph("N° DE PEDIDO", styles["label"])],
        [Paragraph(f"#{order.display_number.upper()}", styles["value"])],
        [Spacer(1, 4)],
        [Paragraph("FECHA", styles["label"])],
        [Paragraph(fecha, styles["small_dark"])],
        [Spacer(1, 4)],
        [Paragraph("ESTADO", styles["label"])],
        [Paragraph(f'<font color="#10b981"><b>● {status_label}</b></font>', styles["small_dark"])],
    ]
    info_right = [
        [Paragraph("CLIENTE", styles["label"])],
        [Paragraph(customer_name, styles["value"])],
        [Spacer(1, 4)],
        [Paragraph("CORREO", styles["label"])],
        [Paragraph(customer_email, styles["small_dark"])],
        [Spacer(1, 4)],
        [Paragraph("TELÉFONO", styles["label"])],
        [Paragraph(customer_phone, styles["small_dark"])],
    ]

    left_t = Table(info_left, colWidths=[doc.width / 2 - 5 * mm])
    right_t = Table(info_right, colWidths=[doc.width / 2 - 5 * mm])
    for t in (left_t, right_t):
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))

    info_block = Table(
        [[left_t, right_t]],
        colWidths=[doc.width / 2, doc.width / 2],
    )
    info_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.6, COLOR_BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_SOFT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(info_block)
    story.append(Spacer(1, 14))

    # --- Items table ---
    item_rows = [["#", "Producto", "Plan", "Cant.", "Precio", "Subtotal"]]
    items = list(order.items.all())
    for idx, it in enumerate(items, start=1):
        subtotal = it.unit_price * it.quantity
        item_rows.append([
            str(idx),
            Paragraph(it.product_name or "—", styles["small_dark"]),
            Paragraph(it.plan_name or "—", styles["small"]),
            str(it.quantity),
            f"S/ {it.unit_price:.2f}",
            f"S/ {subtotal:.2f}",
        ])

    items_table = Table(
        item_rows,
        colWidths=[
            8 * mm, 60 * mm, 40 * mm, 14 * mm, 26 * mm, 32 * mm,
        ],
        repeatRows=1,
    )
    items_table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        # Body
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), COLOR_DARK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_BG_SOFT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, COLOR_PRIMARY),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, COLOR_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12))

    # --- Totales (derecha) ---
    subtotal = order.subtotal
    discount = order.discount_amount or Decimal("0")
    combo_discount = getattr(order, "combo_discount_amount", Decimal("0")) or Decimal("0")
    total = order.total or (subtotal - discount - combo_discount)
    usd_total = _to_usd(total, usd_rate)

    totals_rows = [
        ["Subtotal", f"S/ {subtotal:.2f}"],
    ]
    if discount and discount > 0:
        totals_rows.append([f"Descuento ({order.coupon_code or 'cupón'})", f"− S/ {discount:.2f}"])
    if combo_discount and combo_discount > 0:
        totals_rows.append(["Descuento combo", f"− S/ {combo_discount:.2f}"])
    totals_rows.append(["TOTAL", f"S/ {total:.2f}"])
    if usd_total:
        totals_rows.append(["Equivalente USD (Binance P2P)", f"USD {usd_total:.2f}"])

    totals_table = Table(totals_rows, colWidths=[55 * mm, 35 * mm])
    totals_style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TEXTCOLOR", (0, 0), (-1, -1), COLOR_DARK),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        # Row TOTAL
        ("FONTNAME", (0, -2 if usd_total else -1), (-1, -2 if usd_total else -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -2 if usd_total else -1), (-1, -2 if usd_total else -1), 12),
        ("BACKGROUND", (0, -2 if usd_total else -1), (-1, -2 if usd_total else -1), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, -2 if usd_total else -1), (-1, -2 if usd_total else -1), colors.white),
        ("LINEABOVE", (0, -2 if usd_total else -1), (-1, -2 if usd_total else -1), 0.6, COLOR_PRIMARY),
    ]
    if usd_total:
        totals_style.append(("TEXTCOLOR", (0, -1), (-1, -1), COLOR_OK))
        totals_style.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
    totals_table.setStyle(TableStyle(totals_style))

    # Wrap right-aligned via outer table
    totals_wrap = Table([[None, totals_table]], colWidths=[doc.width - 90 * mm, 90 * mm])
    totals_wrap.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(totals_wrap)
    story.append(Spacer(1, 14))

    # --- Método de pago + QR ---
    pay_label = _payment_label(order.payment_provider)
    pay_block_left = [
        [Paragraph("MÉTODO DE PAGO", styles["label"])],
        [Paragraph(pay_label, styles["value"])],
    ]
    if order.payment_reference:
        pay_block_left.append([Spacer(1, 3)])
        pay_block_left.append([Paragraph("REFERENCIA", styles["label"])])
        pay_block_left.append([Paragraph(order.payment_reference, styles["small_dark"])])
    pay_left_t = Table(pay_block_left, colWidths=[doc.width - 35 * mm])
    pay_left_t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    site_url = getattr(settings, "SITE_URL", "https://virtualidadsp.com") or "https://virtualidadsp.com"
    qr_link = f"{site_url.rstrip('/')}/pedidos/{order.uuid}/"
    qr_img = _qr_image(qr_link, size_mm=22)
    qr_cell = qr_img if qr_img else Paragraph(qr_link, styles["small"])

    pay_block = Table(
        [[pay_left_t, qr_cell]],
        colWidths=[doc.width - 35 * mm, 30 * mm],
    )
    pay_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.6, COLOR_BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_SOFT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
    ]))
    story.append(pay_block)
    story.append(Spacer(1, 16))

    # --- Thanks ---
    story.append(KeepTogether([
        Paragraph("¡Gracias por tu compra!", styles["thanks"]),
        Paragraph(
            "Si necesitás soporte o tenés alguna duda con tu pedido, escribinos por WhatsApp y "
            "respondemos en menos de 5 minutos.",
            styles["small"],
        ),
    ]))

    doc.build(story)
    return buf.getvalue()


def receipt_filename(order: "Order") -> str:
    return f"recibo_jheliz_{order.display_number}.pdf"
