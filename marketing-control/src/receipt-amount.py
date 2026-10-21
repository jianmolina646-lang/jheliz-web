"""Local OCR only. Never log image content or recognized text."""
import io
import json
import re
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone, timedelta


def operation_minutes(text):
    # Require a date immediately followed by its time, never a status-bar clock.
    months = {'ene':1,'feb':2,'mar':3,'abr':4,'may':5,'jun':6,'jul':7,'ago':8,'sep':9,'set':9,'oct':10,'nov':11,'dic':12}
    text = text.lower()
    text = re.sub(r'(\d{1,2})\s+(?:de\s+)?(ene\w*|feb\w*|mar\w*|abr\w*|may\w*|jun\w*|jul\w*|ago\w*|sep\w*|set\w*|oct\w*|nov\w*|dic\w*)\s+(?:de\s+)?(\d{4})',
                  lambda m: f'{m[1]}/{months[m[2][:3]]}/{m[3]}', text)
    pattern = r'(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)[\s,|·–-]{1,12}(?:hora(?: de (?:la )?operaci[oó]n)?\s*:?\s*)?(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]\s*\.?\s*m\.?)?(?!\d)'
    values = set()
    for m in re.finditer(pattern, text):
        day, month, year, hour, minute = map(int, m.group(1,2,3,4,5))
        if m[6] is not None and int(m[6]) > 59: return set()
        if m[7]:
            if not 1 <= hour <= 12: return set()
            hour = hour % 12 + (12 if m[7].startswith('p') else 0)
        try:
            value = datetime(year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=-5)))
        except ValueError: return set()
        values.add(value.astimezone(timezone.utc).isoformat())
    return values


def amounts(text):
    # Require an explicit PEN currency marker; never interpret timestamps or IDs.
    values = set()
    for match in re.finditer(r'(?<!\w)(?:S\s*/\s*\.?|PEN\s+)\s*(\d+(?:[.,]\d+)?)(?![\d.,])', text, re.I):
        raw = match.group(1)
        if re.search(r'[.,]\d{3}$', raw): return set()  # ambiguous thousands
        value = Decimal(raw.replace(',', '.')) * 100
        if value != value.to_integral_value() or not 0 < value <= 10000000:
            return set()
        values.add(int(value))
    return values


def extract_details(data):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 12000000
    if not data or len(data) > 5000000: return None
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in ('JPEG', 'PNG') or image.width * image.height > 12000000:
            return None
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((2000, 3000))
        with tempfile.TemporaryDirectory(prefix='receipt-ocr-') as folder:
            path = Path(folder) / 'receipt.png'
            image.save(path)
            readings = []
            times = []
            for mode in ('6', '11'):
                result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'spa+eng', '--psm', mode],
                    capture_output=True, timeout=12, check=True)
                text = result.stdout.decode('utf-8', errors='replace')
                readings.append(amounts(text))
                times.append(operation_minutes(text))
            return {
                'amount_cents': next(iter(readings[0])) if len(readings[0]) == 1 and readings[0] == readings[1] else None,
                'operation_minute': next(iter(times[0])) if len(times[0]) == 1 and times[0] == times[1] else None,
            }
    return None


def extract(data):
    return (extract_details(data) or {}).get('amount_cents')


if __name__ == '__main__':
    try: result = extract_details(sys.stdin.buffer.read(5000001))
    except Exception: result = None
    print(json.dumps(result or {'amount_cents': None, 'operation_minute': None}))
