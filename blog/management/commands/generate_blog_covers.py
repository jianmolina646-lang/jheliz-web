"""Genera portadas de blog (1200x630) con la marca de cada plataforma.

Cada portada lleva:
  - Fondo con gradiente del color de la marca (Netflix rojo, Office naranja, etc).
  - Logotipo simbólico (texto grande de la plataforma).
  - Título del post sobre overlay oscuro.
  - Marca "Jheliz" en la esquina inferior.

Uso:
    python manage.py generate_blog_covers          # Genera todas las que faltan
    python manage.py generate_blog_covers --force  # Re-genera todas (sobrescribe)
"""
from __future__ import annotations

import io
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from blog.models import BlogPost


# --- Estilos por slug (color brand + logotipo + accent) -----------------------
STYLES: dict[str, dict] = {
    "como-activar-netflix-premium-2026": {
        "primary": (229, 9, 20),       # Netflix red
        "primary_dark": (108, 0, 5),
        "logo_text": "NETFLIX",
        "kicker": "Streaming · Guía",
    },
    "cuenta-completa-vs-perfil-netflix": {
        "primary": (229, 9, 20),
        "primary_dark": (50, 0, 3),
        "logo_text": "NETFLIX",
        "kicker": "Streaming · Comparativa",
    },
    "office-365-original-vs-pirata": {
        "primary": (242, 80, 34),      # Office orange
        "primary_dark": (160, 30, 0),
        "logo_text": "OFFICE",
        "kicker": "Software · Comparativa",
    },
    # Defaults para slugs futuros
    "_default_disney": {
        "primary": (29, 78, 216),
        "primary_dark": (10, 20, 80),
        "logo_text": "DISNEY+",
        "kicker": "Streaming",
    },
    "_default_spotify": {
        "primary": (30, 215, 96),
        "primary_dark": (10, 80, 30),
        "logo_text": "SPOTIFY",
        "kicker": "Música",
    },
}


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
        if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = " ".join(cur + [w])
        if draw.textlength(trial, font=font) <= max_width:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines


def _make_cover(post: BlogPost, style: dict) -> bytes:
    W, H = 1200, 630
    primary = style["primary"]
    dark = style["primary_dark"]
    img = Image.new("RGB", (W, H), color=dark)
    draw = ImageDraw.Draw(img, "RGBA")

    # Diagonal gradient: dark → primary
    for y in range(H):
        t = y / H
        r = int(dark[0] + (primary[0] - dark[0]) * t * 0.85)
        g = int(dark[1] + (primary[1] - dark[1]) * t * 0.85)
        b = int(dark[2] + (primary[2] - dark[2]) * t * 0.85)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Layered subtle radial glows in upper-right corner
    for r, alpha in [(520, 14), (340, 22), (200, 30)]:
        cx, cy = W - 80, -40
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=(255, 255, 255, alpha),
        )

    # Bottom-right secondary glow for balance
    for r, alpha in [(280, 14), (160, 22)]:
        cx, cy = W + 60, H + 40
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=(255, 255, 255, alpha),
        )

    # Top-left brand line (small, sharp)
    brand_sm_font = _font(34, bold=True)
    draw.ellipse((60, 64, 78, 82), fill=(236, 72, 153, 255))
    draw.text(
        (90, 56),
        style["logo_text"],
        font=brand_sm_font,
        fill=(255, 255, 255, 250),
    )

    # Pink accent bar above the title (brand consistent)
    draw.rectangle((60, 360, 120, 366), fill=(236, 72, 153, 255))

    # Kicker
    kicker_font = _font(22, bold=True)
    draw.text(
        (60, 386),
        style["kicker"].upper(),
        font=kicker_font,
        fill=(255, 220, 230, 240),
    )

    # Title — wrapped
    title_font = _font(54, bold=True)
    title_lines = _wrap_text(draw, post.title, title_font, max_width=W - 120)[:3]
    y = 426
    for line in title_lines:
        draw.text((60, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += 64

    # Bottom-right brand
    jh_font = _font(26, bold=True)
    jh_text = "jheliz"
    jw = draw.textlength(jh_text, font=jh_font)
    draw.text(
        (W - jw - 60, H - 56),
        jh_text,
        font=jh_font,
        fill=(255, 255, 255, 220),
    )
    # Pink dot before
    draw.ellipse(
        (W - jw - 88, H - 48, W - jw - 70, H - 30),
        fill=(236, 72, 153, 255),
    )

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()


class Command(BaseCommand):
    help = "Genera portadas de blog 1200x630 con marca por plataforma."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="Re-genera incluso si ya hay portada.")
        parser.add_argument("--slug", help="Solo generar para un slug específico.")

    def handle(self, *args, **opts):
        force = opts["force"]
        only_slug = opts.get("slug")
        qs = BlogPost.objects.all()
        if only_slug:
            qs = qs.filter(slug=only_slug)

        generated = 0
        skipped = 0
        for post in qs:
            if post.cover_image and not force:
                skipped += 1
                self.stdout.write(f"  · skip (ya tiene portada): {post.slug}")
                continue
            style = STYLES.get(post.slug)
            if not style:
                # Fallback: pink-ish brand cover
                style = {
                    "primary": (236, 72, 153),
                    "primary_dark": (76, 5, 35),
                    "logo_text": "JHELIZ",
                    "kicker": (post.category.name.upper() if post.category else "BLOG"),
                }
            # Borra la portada anterior si existe (para reusar el mismo nombre)
            if post.cover_image:
                try:
                    post.cover_image.delete(save=False)
                except Exception:  # noqa: BLE001
                    pass
            data = _make_cover(post, style)
            filename = f"{post.slug}.jpg"
            post.cover_image.save(filename, ContentFile(data), save=True)
            generated += 1
            self.stdout.write(self.style.SUCCESS(f"  ✓ {post.slug}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nListo. Generadas: {generated} · Saltadas: {skipped}"
            )
        )
