"""Console string dictionary: lookups, interpolation and file shape."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import i18n  # noqa: E402


class ConsoleStringTests(unittest.TestCase):
    def test_tr_returns_value(self):
        self.assertEqual(i18n.tr('bar.save'), '保存')

    def test_tr_interpolates(self):
        self.assertEqual(i18n.tr('common.count', n=3), '3 个')

    def test_missing_key_returns_key(self):
        with self.assertLogs('rinbot.i18n', 'WARNING'):
            self.assertEqual(i18n.tr('nope.key'), 'nope.key')

    def test_dictionary_is_flat_strings(self):
        strings = i18n.console_strings()
        self.assertTrue(strings)
        for key, value in strings.items():
            self.assertRegex(key, r'^[a-z_]+(\.[A-Za-z0-9_]+)+$')
            self.assertIsInstance(value, str)
            self.assertTrue(value.strip(), key)


if __name__ == '__main__':
    unittest.main()
