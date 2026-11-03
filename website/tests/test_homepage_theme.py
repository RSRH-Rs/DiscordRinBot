"""The homepage shares the console palette in both themes and boots the saved theme before styles."""
import unittest
from pathlib import Path

from test_console_contrast import block, declarations, ratio

ROOT = Path(__file__).resolve().parents[1]
SHARED = ['bg', 'panel', 'side', 'line', 'text', 'muted', 'accent', 'accent-hover', 'on-accent', 'accent-soft', 'accent-text']
OLD = ['#B0335A', '#DCC3CD', '#E7D4DC', '#D9C1CB', '#DFCAD3', '#3A2433', '--rin:', 'var(--rin)', 'rgba(201, 63, 105']


class HomepageThemeTests(unittest.TestCase):
    def setUp(self):
        css = (ROOT / 'static/css/console.css').read_text(encoding='utf-8')
        self.console_light = declarations(block(css, ':root'))
        self.console_dark = declarations(block(css, ':root[data-theme="dark"]'))
        self.html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        style = self.html[self.html.index('<style>'):self.html.index('</style>')]
        self.home_light = declarations(block(style, ':root'))
        self.home_dark = declarations(block(style, ':root[data-theme="dark"]'))
        media = style[style.index('@media (prefers-color-scheme: dark)'):]
        self.home_system_dark = declarations(block(media, ':root:not([data-theme="light"])'))

    def test_homepage_shares_console_tokens_in_both_palettes(self):
        for name in SHARED:
            with self.subTest(token=name):
                self.assertEqual(self.home_light[name].strip().upper(), self.console_light[name].strip().upper())
                self.assertEqual(self.home_dark[name].strip().upper(), self.console_dark[name].strip().upper())

    def test_system_dark_matches_manual_dark(self):
        self.assertEqual(self.home_system_dark, self.home_dark)

    def test_theme_boots_before_styles(self):
        self.assertLess(self.html.index("localStorage.getItem('rin-theme')"), self.html.index('<style>'))

    def test_no_old_palette_left(self):
        for old in OLD:
            with self.subTest(old=old):
                self.assertNotIn(old, self.html)

    def test_discord_mock_and_side_text_meet_aa_in_both_palettes(self):
        for label, palette in [('light', self.home_light), ('dark', self.home_dark)]:
            for fg, bg in [('dc-text', 'dc-bg'), ('dc-muted', 'dc-bg'), ('dc-muted', 'dc-deep'), ('muted', 'side'), ('text', 'side'), ('muted', 'bg')]:
                with self.subTest(palette=label, fg=fg, bg=bg):
                    self.assertGreaterEqual(ratio(palette[fg].strip(), palette[bg].strip()), 4.5)


if __name__ == '__main__':
    unittest.main()
