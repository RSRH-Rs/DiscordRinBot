"""Every console text/background pair meets WCAG AA (4.5:1)."""
import re
import unittest
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / 'static/css/console.css'
PAIRS = [
    ('text', 'bg'), ('text', 'panel'), ('muted', 'bg'), ('muted', 'panel'), ('#FFFFFF', 'rin'),
    ('#FFFFFF', 'rin-hover'), ('chip-text', 'chip-bg'), ('side-text', 'chan'), ('side-text', 'rail'),
    ('text', 'active'), ('ok', 'ok-bg'), ('warn', 'warn-bg'), ('bad', 'bad-bg'),
    ('bar-text', 'bar'), ('bar-reset', 'bar'), ('#FFFFFF', '#4752C4'),
]


def luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def ratio(a, b):
    high, low = sorted([luminance(a), luminance(b)], reverse=True)
    return (high + 0.05) / (low + 0.05)


class ConsoleContrastTests(unittest.TestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding='utf-8')
        root = re.search(r':root\s*\{(.*?)\}', self.css, re.S).group(1)
        self.tokens = dict(re.findall(r'--([a-z-]+):\s*(#[0-9A-Fa-f]{6})\s*;', root))

    def color(self, name):
        return name if name.startswith('#') else self.tokens[name]

    def test_pairs_meet_aa(self):
        for fg, bg in PAIRS:
            with self.subTest(fg=fg, bg=bg):
                self.assertGreaterEqual(ratio(self.color(fg), self.color(bg)), 4.5)

    def test_reduced_motion_overrides_every_animated_selector(self):
        block = self.css[self.css.index('@media (prefers-reduced-motion: reduce)'):]
        for selector in ['.unsaved-bar', '.unsaved-bar.is-open', '.unsaved-bar.is-shaking', '.sidebar', '.shell.is-drawer-open .sidebar', '.skeleton']:
            self.assertIn(selector, block)

    def test_no_important(self):
        self.assertNotIn('!important', self.css)


if __name__ == '__main__':
    unittest.main()
