"""Regresiones del clasificador con correos y enlaces sintéticos."""

import unicodedata
from unittest import TestCase

from codes.netflix import parse_netflix_email


class NetflixNoticeTests(TestCase):
    def test_household_confirmation_is_not_an_update_request(self):
        subjects = (
            "Confirmación: Se ha confirmado tu Hogar con Netflix",
            "RV: Confirmación: Se ha confirmado tu Hogar con Netflix",
            "fw: CONFIRMACION: SE HA CONFIRMADO TU HOGAR CON NETFLIX",
            " FWD : RV:  Confirmación : Se ha confirmado tu Hogar con Netflix ",
            unicodedata.normalize(
                "NFD", "RV: Confirmación: Se ha confirmado tu Hogar con Netflix"
            ),
        )
        for subject in subjects:
            with self.subTest(subject=subject):
                result = parse_netflix_email(
                    subject,
                    html=(
                        "<p>Se ha confirmado tu Hogar con Netflix.</p>"
                        '<a href="https://www.netflix.com/browse?test=synthetic">'
                        "Disfruta de Netflix</a>"
                    ),
                )
                self.assertEqual(result.kind, "other")
                self.assertEqual(result.code, "")

    def test_new_device_notice_is_not_a_password_reset_request(self):
        subjects = (
            "Un nuevo dispositivo está usando tu cuenta",
            "RV: Un nuevo dispositivo está usando tu cuenta",
            "FW: UN NUEVO DISPOSITIVO ESTA USANDO TU CUENTA",
            " FWD: RV : Un nuevo dispositivo está usando tu cuenta ",
            unicodedata.normalize(
                "NFD", "RV: Un nuevo dispositivo está usando tu cuenta"
            ),
        )
        for subject in subjects:
            with self.subTest(subject=subject):
                result = parse_netflix_email(
                    subject,
                    html=(
                        "<p>Un dispositivo inició sesión en tu cuenta.</p>"
                        '<a href="https://www.netflix.com/password?test=synthetic">'
                        "Cambia tu contraseña si no fuiste tú</a>"
                    ),
                )
                self.assertEqual(result.kind, "other")
                self.assertEqual(result.code, "")

    def test_forwarded_action_requests_remain_available(self):
        cases = (
            (
                "RV: Importante: Cómo actualizar tu Hogar con Netflix",
                "household",
                "https://www.netflix.com/account/update-primary-location?test=synthetic",
                "Sí, la envié yo",
            ),
            (
                "RV: Tu código de acceso temporal de Netflix",
                "temp_code",
                "https://www.netflix.com/account/travel/verify?test=synthetic",
                "Obtener código",
            ),
            (
                "FWD: RV: Restablece tu contraseña",
                "password_reset",
                "https://www.netflix.com/password?test=synthetic",
                "Crear contraseña nueva",
            ),
        )
        for subject, kind, url, label in cases:
            with self.subTest(subject=subject):
                result = parse_netflix_email(
                    subject, html=f'<p>{subject}</p><a href="{url}">{label}</a>'
                )
                self.assertEqual(result.kind, kind)
                self.assertEqual(result.action_url, url)

    def test_notice_quoted_in_action_body_does_not_block_request(self):
        url = "https://www.netflix.com/password?test=synthetic"
        result = parse_netflix_email(
            "RV: Restablece tu contraseña",
            html=(
                '<p>Asunto anterior: Un nuevo dispositivo está usando tu cuenta</p>'
                f'<a href="{url}">Crear contraseña nueva</a>'
            ),
        )
        self.assertEqual(result.kind, "password_reset")
        self.assertEqual(result.action_url, url)
