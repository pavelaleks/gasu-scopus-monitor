import unittest

from auth import access_token, passwords_match


class AuthTests(unittest.TestCase):
    def test_token_changes_when_password_changes(self):
        self.assertNotEqual(access_token("12345"), access_token("other"))

    def test_token_is_stable(self):
        self.assertEqual(access_token("12345"), access_token("12345"))

    def test_passwords_match(self):
        self.assertTrue(passwords_match("12345", "12345"))
        self.assertFalse(passwords_match("12345", "54321"))
        self.assertFalse(passwords_match("", "12345"))


if __name__ == "__main__":
    unittest.main()
