import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from config.secret_config import secret_config


class SecretConfigTests(TestCase):
    def test_reads_environment_value_without_file(self):
        with patch.dict(os.environ, {"TEST_SECRET": "desde-env"}, clear=False):
            self.assertEqual(secret_config("TEST_SECRET"), "desde-env")

    def test_file_takes_precedence_over_environment(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as file:
            file.write("desde-archivo\n")
            file_path = file.name

        try:
            with patch.dict(
                os.environ,
                {
                    "TEST_SECRET": "desde-env",
                    "TEST_SECRET_FILE": file_path,
                },
                clear=False,
            ):
                self.assertEqual(secret_config("TEST_SECRET"), "desde-archivo")
        finally:
            os.unlink(file_path)

    def test_rejects_empty_secret_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as file:
            file_path = file.name

        try:
            with patch.dict(
                os.environ,
                {"TEST_SECRET_FILE": file_path},
                clear=False,
            ):
                with self.assertRaisesRegex(RuntimeError, "está vacío"):
                    secret_config("TEST_SECRET")
        finally:
            os.unlink(file_path)
