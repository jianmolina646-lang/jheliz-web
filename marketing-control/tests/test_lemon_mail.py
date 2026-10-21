import importlib.util
import sys
import unittest
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('lemon_mail',Path(__file__).parents[1]/'src'/'lemon-mail.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)

class ParserTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(UTC).replace(microsecond=0)
    def message(self,amount='7.0000',name='MARIA ELENA PRUEBA',**headers):
        m=EmailMessage()
        values={'From':module.SENDER,'To':module.MAILBOX,'Date':format_datetime(self.now),
            'Authentication-Results':'mx.google.com; dkim=pass header.i=@notificaciones.lemoncash.com.ar; dmarc=pass header.from=lemoncash.com.ar'}
        values.update(headers)
        for k,v in values.items():
            if v is not None:m[k]=v
        m.set_content(f'{module.BENEFICIARY}, ¡recibiste S/ {amount}! Datos de origen: Nombre: {name} CCI: 000000000 Entidad: TEST Mensaje: YAPE Otros detalles: ID de la operación: 12345678-1234-1234-1234-123456789abc ID externo: 202610210000123456789')
        return m
    def parse(self,m):return module.parse_payment(m.as_bytes(),self.now,self.now)
    def test_valid(self):
        p=self.parse(self.message());self.assertEqual(p['amount_cents'],700);self.assertEqual(p['currency'],'PEN')
    def test_one_sol_is_not_one_thousand(self):self.assertEqual(self.parse(self.message(amount='1.0000'))['amount_cents'],100)
    def test_fractional_cent_rejected(self):self.assertIsNone(self.parse(self.message(amount='7.0001')))
    def test_spoofed_sender(self):self.assertIsNone(self.parse(self.message(From='notificaciones@lemoncash.com.ar.evil.test')))
    def test_wrong_mailbox(self):self.assertIsNone(self.parse(self.message(To='other@gmail.com')))
    def test_wrong_auth(self):
        for value in ('evil.test; dkim=pass header.i=@notificaciones.lemoncash.com.ar; dmarc=pass header.from=lemoncash.com.ar',
            'mx.google.com; dkim=pass header.i=@mailgun.org; dmarc=pass header.from=lemoncash.com.ar',
            'mx.google.com; dkim=fail header.i=@notificaciones.lemoncash.com.ar; dmarc=pass header.from=lemoncash.com.ar',
            'mx.google.com; dkim=pass header.i=@notificaciones.lemoncash.com.ar; dmarc=fail header.from=lemoncash.com.ar',None):
            self.assertIsNone(self.parse(self.message(**{'Authentication-Results':value})))
    def test_older_injected_auth_not_used(self):
        m=self.message(**{'Authentication-Results':'mx.google.com; dkim=fail'})
        m['Authentication-Results']='mx.google.com; dkim=pass header.i=@notificaciones.lemoncash.com.ar; dmarc=pass header.from=lemoncash.com.ar'
        self.assertIsNone(self.parse(m))
    def test_old_or_future(self):
        for date in (self.now-timedelta(days=2),self.now+timedelta(minutes=1)):
            self.assertIsNone(self.parse(self.message(Date=format_datetime(date))))
    def test_duplicate_fields(self):
        m=self.message();m.set_content(m.get_content()+' '+m.get_content());self.assertIsNone(self.parse(m))
    def test_other_beneficiary(self):
        m=self.message();m.set_content(m.get_content().replace(module.BENEFICIARY,'Otro Destinatario'))
        self.assertIsNone(self.parse(m))
    def test_html(self):
        m=self.message();text=m.get_content();m.set_content('');m.add_alternative('<html><style>fake</style><p>'+text+'</p></html>',subtype='html')
        self.assertEqual(self.parse(m)['amount_cents'],700)
    def test_no_operation(self):
        m=self.message();m.set_content(m.get_content().replace('ID de la operación:','Dato:'));self.assertIsNone(self.parse(m))
    def test_delayed_replay_rejected(self):
        self.assertIsNone(module.parse_payment(self.message(Date=format_datetime(self.now-timedelta(hours=2))).as_bytes(),self.now,self.now))

if __name__=='__main__':unittest.main()
