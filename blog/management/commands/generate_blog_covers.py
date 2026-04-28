"""Genera portadas de blog (1200x630) basadas en fotos reales (Unsplash) o branded.

Modo por defecto: descarga foto de Unsplash (libre de derechos) y sobre ella
aplica un degradado oscuro + título del post + branding jheliz. Esto produce
portadas profesionales tipo "magazine".

Si la URL de Unsplash falla (sin internet), cae en modo branded (gradiente con
color de marca + texto).

Uso:
    python manage.py generate_blog_covers          # Genera todas las que faltan
    python manage.py generate_blog_covers --force  # Re-genera todas (sobrescribe)
    python manage.py generate_blog_covers --slug X # Solo un slug
"""
from __future__ import annotations

import io
import urllib.request
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from blog.models import BlogPost


# --- Estilos por slug -------------------------------------------------------------
# Cada estilo opcionalmente apunta a una foto de Unsplash (libre de derechos).
# Si "photo_url" está presente, se usa como fondo con overlay oscuro.
# Si no, se genera un fondo branded plano con gradiente del color.
STYLES: dict[str, dict] = {
    "como-activar-netflix-premium-2026": {
        "photo_url": "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1600&q=80&fm=jpg",
        "kicker": "Streaming · Guía",
        # Brand fallback / accent
        "primary": (229, 9, 20),
        "primary_dark": (108, 0, 5),
        "logo_text": "NETFLIX",
    },
    "cuenta-completa-vs-perfil-netflix": {
        "photo_url": "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=1600&q=80&fm=jpg",
        "kicker": "Streaming · Comparativa",
        "primary": (229, 9, 20),
        "primary_dark": (50, 0, 3),
        "logo_text": "NETFLIX",
    },
    "office-365-original-vs-pirata": {
        "photo_url": "https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?w=1600&q=80&fm=jpg",
        "kicker": "Software · Comparativa",
        "primary": (242, 80, 34),
        "primary_dark": (160, 30, 0),
        "logo_text": "OFFICE",
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


def _download_photo(url: str) -> Image.Image | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jheliz-cover-gen"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def _cover_from_photo(post: BlogPost, style: dict, photo: Image.Image) -> bytes:
    W, H = 1200, 630
    # Fit/crop the photo to 1200x630 (cover behavior)
    pw, ph = photo.size
    scale = max(W / pw, H / ph)
    new_size = (int(pw * scale), int(ph * scale))
    photo = photo.resize(new_size, Image.Resampling.LANCZOS)
    # Center crop
    left = (new_size[0] - W) // 2
    top = (new_size[1] - H) // 2
    photo = photo.crop((left, top, left + W, top + H))

    # Slight darken via brightness multiplication
    img = photo.convert("RGB")

    # Draw overlay using RGBA layer composited at the end
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    # Vertical gradient overlay: photo visible top, dark bottom for text
    for y in range(0, H):
        if y < 280:
            # Top: slight darken so the brand pill stays readable
            a = 35
        elif y < 360:
            # Mid: ramp up
            a = int(35 + (y - 280) / 80 * 110)
        else:
            # Bottom: very dark for title legibility
            a = int(145 + (y - 360) / (H - 360) * 75)
        a = min(a, 225)
        odraw.line([(0, y), (W, y)], fill=(0, 0, 0, a))

    # Soft pink accent glow bottom-left
    for r, alpha in [(380, 30), (240, 45), (140, 55)]:
        cx, cy = -40, H + 60
        odraw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=(236, 72, 153, alpha),
        )

    # Top-left brand line (jheliz)
    brand_sm_font = _font(28, bold=True)
    odraw.ellipse((60, 64, 78, 82), fill=(236, 72, 153, 255))
    odraw.text((90, 58), "Jheliz", font=brand_sm_font, fill=(255, 255, 255, 250))

    # Pink accent bar above the title
    odraw.rectangle((60, 360, 120, 366), fill=(236, 72, 153, 255))

    # Kicker
    kicker_font = _font(22, bold=True)
    odraw.text(
        (60, 386),
        style["kicker"].upper(),
        font=kicker_font,
        fill=(255, 220, 230, 240),
    )

    # Title — wrapped
    title_font = _font(56, bold=True)
    title_lines = _wrap_text(draw=odraw, text=post.title, font=title_font, max_width=W - 120)[:3]
    y = 426
    for line in title_lines:
        # Subtle text shadow for legibility on photos
        odraw.text((60 + 2, y + 2), line, font=title_font, fill=(0, 0, 0, 180))
        odraw.text((60, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += 66

    # Composite the overlay onto the photo
    final = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    buf = io.BytesIO()
    final.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()


def _cover_branded(post: BlogPost, style: dict) -> bytes:
    """Fallback sin foto: gradiente de marca."""
    W, H = 1200, 630
    primary = style.get("primary", (236, 72, 153))
    dark = style.get("primary_dark", (76, 5, 35))
    img = Image.new("RGB", (W, H), color=dark)
    draw = ImageDraw.Draw(img, "RGBA")

    for y in range(H):
        t = y / H
        r = int(dark[0] + (primary[0] - dark[0]) * t * 0.85)
        g = int(dark[1] + (primary[1] - dark[1]) * t * 0.85)
        b = int(dark[2] + (primary[2] - dark[2]) * t * 0.85)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    for r, alpha in [(520, 14), (340, 22), (200, 30)]:
        cx, cy = W - 80, -40
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, alpha))

    brand_sm_font = _font(34, bold=True)
    draw.ellipse((60, 64, 78, 82), fill=(236, 72, 153, 255))
    draw.text((90, 56), style.get("logo_text", "JHELIZ"), font=brand_sm_font, fill=(255, 255, 255, 250))

    draw.rectangle((60, 360, 120, 366), fill=(236, 72, 153, 255))
    kicker_font = _font(22, bold=True)
    draw.text((60, 386), style["kicker"].upper(), font=kicker_font, fill=(255, 220, 230, 240))

    title_font = _font(54, bold=True)
    title_lines = _wrap_text(draw, post.title, title_font, max_width=W - 120)[:3]
    y = 426
    for line in title_lines:
        draw.text((60, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += 64

    jh_font = _font(26, bold=True)
    jh_text = "jheliz"
    jw = draw.textlength(jh_text, font=jh_font)
    draw.text((W - jw - 60, H - 56), jh_text, font=jh_font, fill=(255, 255, 255, 220))
    draw.ellipse((W - jw - 88, H - 48, W - jw - 70, H - 30), fill=(236, 72, 153, 255))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()


def _make_cover(post: BlogPost, style: dict) -> bytes:
    photo_url = style.get("photo_url")
    if photo_url:
        photo = _download_photo(photo_url)
        if photo is not None:
            return _cover_from_photo(post, style, photo)
    return _cover_branded(post, style)


class Command(BaseCommand):
    help = "Genera portadas de blog 1200x630 con foto Unsplash o gradiente branded."

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
            style = STYLES.get(post.slug, {
                "kicker": (post.category.name if post.category else "Blog"),
                "primary": (236, 72, 153),
                "primary_dark": (76, 5, 35),
                "logo_text": "JHELIZ",
            })
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
