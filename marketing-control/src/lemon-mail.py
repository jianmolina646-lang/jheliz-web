"""Read-only Gmail collector. JSON goes to the parent process, never to app logs."""
import email
import imaplib
import json
import re
import ssl
import sys
from datetime import UTC, datetime
from decimal import Decimal
from email import policy
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

MAILBOX = 'natalivillalima@gmail.com'
SENDER = 'notificaciones@lemoncash.com.ar'
BENEFICIARY = 'Jhedy Javier Villa Lima'


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('head', 'style', 'script'): self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ('head', 'style', 'script'): self.hidden = max(0, self.hidden-1)
    def handle_data(self, value):
        if not self.hidden and value.strip(): self.parts.append(value.strip())


def parse_payment(raw, received_at, now):
    if len(raw) > 500000: return None
    msg = email.message_from_bytes(raw, policy=policy.default)
    senders = getaddresses(msg.get_all('From', []))
    if len(senders) != 1 or senders[0][1].lower() != SENDER: return None
    recipients = {a.lower() for _, a in getaddresses(msg.get_all('To', []))}
    if MAILBOX not in recipients: return None
    auth = str(msg.get('Authentication-Results', ''))
    if not re.match(r'\s*mx\.google\.com\s*;', auth, re.I): return None
    segments = auth.split(';')[1:]
    if not any(re.match(r'\s*dkim=pass\b', s, re.I) and re.search(
            r'\bheader\.(?:i|d)=@?(?:notificaciones\.)?lemoncash\.com\.ar(?=\s|$)', s, re.I) for s in segments): return None
    if not any(re.match(r'\s*dmarc=pass\b', s, re.I) and re.search(
            r'\bheader\.from=lemoncash\.com\.ar(?=\s|$)', s, re.I) for s in segments): return None
    try:
        sent = parsedate_to_datetime(str(msg.get('Date', '')))
        if sent.tzinfo is None or not 0 <= (now-sent).total_seconds() <= 86400: return None
        if not 0 <= (now-received_at).total_seconds() <= 86400: return None
        if abs((sent-received_at).total_seconds()) > 600: return None
    except (ValueError, TypeError, OverflowError): return None
    body = msg.get_body(preferencelist=('html', 'plain'))
    if body is None or body.get_content_disposition() == 'attachment': return None
    try: content = body.get_content()
    except (LookupError, UnicodeError): return None
    if body.get_content_type() == 'text/html':
        parser = VisibleText(); parser.feed(content); content = ' '.join(parser.parts)
    content = re.sub(r'\s+', ' ', content).strip()
    amounts = re.findall(re.escape(BENEFICIARY)+r',\s*¡?recibiste\s+S/\s*(\d+(?:\.\d{1,4})?)\s*!', content, re.I)
    names = re.findall(r'Datos de origen:\s*Nombre:\s*(.*?)\s*CCI:', content, re.I)
    operations = re.findall(r'ID de la operación:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?=\s|$)', content, re.I)
    external = re.findall(r'ID externo:\s*(\d{10,60})(?=\s|$)', content, re.I)
    if not all(len(values) == 1 for values in (amounts,names,operations,external)): return None
    cents = Decimal(amounts[0])*100
    if cents != cents.to_integral_value() or not 0 < cents <= 10000000: return None
    name = names[0].strip()
    if not 5 <= len(name) <= 160 or len(name.split()) < 2: return None
    return {'operation_id': operations[0].upper(), 'external_id': external[0],
        'payer': name, 'amount_cents': int(cents), 'currency': 'PEN',
        'paid_at': sent.isoformat(), 'received_at': received_at.isoformat()}


def collect():
    password = ''.join(Path('/run/secrets/lemon-gmail-app-password').read_text(encoding='utf-8-sig').split())
    if not re.fullmatch(r'[A-Za-z]{16}', password): raise ValueError('credential_format')
    conn = imaplib.IMAP4_SSL('imap.gmail.com', 993, ssl_context=ssl.create_default_context(), timeout=20)
    try:
        conn.login(MAILBOX, password); password = None
        if conn.select('INBOX', readonly=True)[0] != 'OK': raise RuntimeError('inbox')
        status, data = conn.uid('search', None, 'X-GM-RAW', '"newer_than:1d from:notificaciones@lemoncash.com.ar"')
        if status != 'OK': raise RuntimeError('search')
        ids = (data[0] or b'').split()
        if len(ids) > 200: raise RuntimeError('too_many_messages_for_safe_matching')
        payments = []
        now = datetime.now(UTC)
        for uid in ids:
            status, parts = conn.uid('fetch', uid, '(INTERNALDATE BODY.PEEK[]<0.500001>)')
            if status != 'OK': raise RuntimeError('incomplete_fetch')
            found = False
            for part in parts or []:
                if not isinstance(part, tuple): continue
                found = True
                match = re.search(rb'INTERNALDATE "([^"]+)"', part[0])
                if not match: raise RuntimeError('missing_server_date')
                received = datetime.strptime(match[1].decode('ascii'), '%d-%b-%Y %H:%M:%S %z')
                payment = parse_payment(part[1], received, now)
                if payment: payments.append(payment)
            if not found: raise RuntimeError('incomplete_fetch')
        return payments
    finally:
        try: conn.logout()
        except Exception: pass


if __name__ == '__main__':
    try:
        print(json.dumps({'ok': True, 'payments': collect()}))
    except Exception:
        print(json.dumps({'ok': False, 'error': 'gmail_verification_unavailable'}))
        sys.exit(1)
