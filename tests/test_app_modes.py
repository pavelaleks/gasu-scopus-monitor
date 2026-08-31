import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _login(at: AppTest) -> AppTest:
    at.run()
    for inp in at.text_input:
        if "Пароль" in (inp.label or ""):
            inp.input("12345")
            break
    for button in at.button:
        if "Войти" in (button.label or ""):
            return button.click().run()
    return at


def _labels(at: AppTest) -> set[str]:
    return {button.label or "" for button in at.button}


class AppModeTests(unittest.TestCase):
    def test_three_modes_keep_rsf_off_the_university_screen(self):
        at = AppTest.from_file(str(APP_PATH), default_timeout=20)
        _login(at)
        self.assertFalse(at.exception)
        options = list(at.radio[0].options)
        self.assertEqual(options, ["Мониторинг ГАГУ", "РНФ", "Поиск по автору"])

        labels = _labels(at)
        self.assertIn("Статьи ГАГУ за текущий год", labels)
        self.assertIn("Найти публикации", labels)
        self.assertFalse(any("от 8 статей" in item or "от 5 статей" in item for item in labels))
        self.assertFalse(any("Авторы ГАГУ" in item for item in labels))

        at.radio[0].set_value("РНФ").run()
        self.assertFalse(at.exception)
        labels = _labels(at)
        self.assertTrue(any("от 8 статей" in item for item in labels))
        self.assertTrue(any("от 5 статей" in item for item in labels))
        self.assertNotIn("Статьи ГАГУ за текущий год", labels)
        self.assertNotIn("Найти публикации", labels)
        self.assertFalse(any("Авторы ГАГУ" in item for item in labels))

        at.radio[0].set_value("Поиск по автору").run()
        self.assertFalse(at.exception)
        labels = _labels(at)
        self.assertIn("Найти публикации", labels)
        self.assertFalse(any("от 8 статей" in item or "от 5 статей" in item for item in labels))
        self.assertIn("Фамилия", {item.label for item in at.text_input})


if __name__ == "__main__":
    unittest.main()
