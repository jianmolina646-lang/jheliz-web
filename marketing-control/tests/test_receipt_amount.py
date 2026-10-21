import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('receipt_amount', Path(__file__).parents[1] / 'src/receipt-amount.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReceiptAmountTests(unittest.TestCase):
    def test_operation_date_and_time(self):
        for value in ['21/10/2026 06:53', '21 oct 2026 | 6:53 a. m.', '21 de octubre de 2026 06:53:22', 'Fecha: 21/10/2026\nHora: 06:53']:
            self.assertEqual(module.operation_minutes(value), {'2026-10-21T11:53:00+00:00'})
        self.assertEqual(module.operation_minutes('21/10/2026 6:53 pm'), {'2026-10-21T23:53:00+00:00'})
        self.assertEqual(module.operation_minutes('21/10/2026 12:00 am'), {'2026-10-21T05:00:00+00:00'})
        for value in ['6:53 bateria 80%', '21/10/2026', '31/02/2026 06:53', '21/10/2026 25:53', '06:53\nPago recibido\n21/10/2026']:
            self.assertEqual(module.operation_minutes(value), set())
        self.assertEqual(len(module.operation_minutes('21/10/2026 06:53\n21/10/2026 06:54')), 2)
    def test_currency_and_decimals(self):
        for text in ['S/ 10.00', 'S/10', 'S/. 10,00', 'PEN 10.0000']:
            self.assertEqual(module.amounts(text), {1000})

    def test_no_guessing(self):
        for text in ['10:00 739582457', '$10.00', 'S/ 1.000', 'S/ 0.001', 'S/ 10.0001', 'S/ 0']:
            self.assertEqual(module.amounts(text), set())
        self.assertEqual(module.amounts('S/ 10.00 saldo S/ 50.00'), {1000, 5000})

    def test_real_ocr_synthetic_image(self):
        from PIL import Image, ImageDraw, ImageFont
        import io
        image = Image.new('RGB', (1000, 500), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 60)
        draw.text((50, 100), 'Pago recibido S/ 10.00', fill='black', font=font)
        draw.text((50, 250), '21/10/2026 06:53', fill='black', font=font)
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        self.assertEqual(module.extract(buffer.getvalue()), 1000)
        self.assertEqual(module.extract_details(buffer.getvalue())['operation_minute'], '2026-10-21T11:53:00+00:00')


if __name__ == '__main__': unittest.main()
