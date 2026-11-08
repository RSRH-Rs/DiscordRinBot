"""The homepage shares the console palette in both themes and boots the saved theme before styles."""
import re
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
        # 首页的颜色和绘制前脚本都在公共外壳里：颜色在 site.css，脚本在 _site_base.html
        self.html = (ROOT / 'templates/_site_base.html').read_text(encoding='utf-8')
        self.page = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        style = (ROOT / 'static/css/site.css').read_text(encoding='utf-8')
        self.site_css = style
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
        self.assertLess(self.html.index("localStorage.getItem('rin-theme')"), self.html.index('css/site.css'))

    def test_manual_theme_sets_the_address_bar_colour(self):
        # The metas come first so the boot script can point both at the saved palette's background.
        head = self.html[:self.html.index('</head>')]
        self.assertLess(head.index('name="theme-color"'), head.index("localStorage.getItem('rin-theme')"))

    def test_no_old_palette_left(self):
        for old in OLD:
            for name, text in [('base', self.html), ('index', self.page), ('site.css', self.site_css)]:
                with self.subTest(old=old, file=name):
                    self.assertNotIn(old, text)

    def test_discord_mock_and_side_text_meet_aa_in_both_palettes(self):
        for label, palette in [('light', self.home_light), ('dark', self.home_dark)]:
            for fg, bg in [('dc-text', 'dc-bg'), ('dc-muted', 'dc-bg'), ('dc-muted', 'dc-deep'), ('muted', 'side'), ('text', 'side'), ('muted', 'bg')]:
                with self.subTest(palette=label, fg=fg, bg=bg):
                    self.assertGreaterEqual(ratio(palette[fg].strip(), palette[bg].strip()), 4.5)



class InvitePeekTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')

    def test_rin_peeks_over_both_invite_buttons(self):
        images = re.findall(r'<img class="peek-rin"[^>]*>', self.html)
        self.assertEqual(len(images), 2)
        for image in images:
            self.assertIn('bot-avatar-96.webp', image)
            self.assertIn('alt=""', image)
            self.assertIn('width="36"', image)

    def test_peek_answers_hover_only_and_never_takes_clicks(self):
        self.assertRegex(self.html, r'@media \(hover: hover\)\s*\{\s*\.peek:hover \.peek-rin')
        self.assertRegex(re.search(r'\.peek-rin\s*\{([^}]*)\}', self.html).group(1), r'pointer-events:\s*none')
        self.assertIn('cubic-bezier(.34, 1.56, .64, 1)', self.html)


if __name__ == '__main__':
    unittest.main()
