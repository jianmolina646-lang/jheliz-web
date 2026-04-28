"""Markdown renderer ligero para artículos del blog.

No instala dependencias nuevas. Soporta:
    # H1 / ## H2 / ### H3
    **negrita** / *cursiva*
    - lista / 1. lista numerada
    > cita
    [texto](url)
    `código inline` y bloques ```código```
    --- → <hr>

Suficiente para artículos de blog. Si en el futuro quieres soporte completo (tablas,
imágenes, footnotes), puedes cambiar a la librería `markdown` y `bleach` para sanitizar.
Por ahora HTML-escapamos todo lo no marcado para evitar XSS.
"""

from __future__ import annotations

import html
import re

INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITALIC = re.compile(r"\*([^*]+)\*")
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline(text: str) -> str:
    text = html.escape(text)
    text = INLINE_CODE.sub(r"<code>\1</code>", text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = ITALIC.sub(r"<em>\1</em>", text)
    text = LINK.sub(
        lambda m: f'<a href="{html.escape(m.group(2))}" rel="noopener" target="_blank">{m.group(1)}</a>',
        text,
    )
    return text


def render_markdown(text: str) -> str:
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    in_ul = False
    in_ol = False
    in_quote = False
    in_pre = False

    def close_lists():
        nonlocal in_ul, in_ol, in_quote
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False
        if in_quote:
            out.append("</blockquote>")
            in_quote = False

    for raw in lines:
        line = raw.rstrip()

        # Bloques de código ```
        if line.startswith("```"):
            close_lists()
            if in_pre:
                out.append("</code></pre>")
                in_pre = False
            else:
                out.append('<pre><code>')
                in_pre = True
            continue
        if in_pre:
            out.append(html.escape(line))
            continue

        if not line.strip():
            close_lists()
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close_lists()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            continue

        # Hr
        if re.match(r"^---+$", line):
            close_lists()
            out.append("<hr/>")
            continue

        # Quote
        if line.startswith(">"):
            if not in_quote:
                close_lists()
                out.append("<blockquote>")
                in_quote = True
            out.append(_inline(line[1:].strip()) + "<br/>")
            continue
        elif in_quote:
            out.append("</blockquote>")
            in_quote = False

        # Listas
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue
        m = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue

        # Si veníamos en lista y la línea no es lista, ciérrala
        if in_ul or in_ol:
            close_lists()

        out.append(f"<p>{_inline(line)}</p>")

    if in_pre:
        out.append("</code></pre>")
    close_lists()
    return "\n".join(out)
