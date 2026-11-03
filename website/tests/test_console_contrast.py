"""Both console palettes meet WCAG AA, and every colour token the stylesheet uses is defined."""
import re
import unittest
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / 'static/css/console.css'
PAIRS = [
    ('text', 'bg'), ('text', 'panel'), ('text', 'side'), ('text', 'cur'), ('muted', 'bg'), ('muted', 'panel'), ('muted', 'side'),
    ('on-accent', 'accent'), ('on-accent', 'accent-hover'), ('accent-text', 'accent-soft'), ('accent-text', 'panel'),
    ('ok', 'ok-soft'), ('ok', 'panel'), ('warn', 'warn-soft'), ('bad', 'bad-soft'), ('bar-text', 'bar'), ('#FFFFFF', '#4752C4'),
]
NON_TEXT = [('field-line', 'field'), ('field-line', 'panel'), ('field-line', 'bg')]


def luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def ratio(a, b):
    high, low = sorted([luminance(a), luminance(b)], reverse=True)
    return (high + 0.05) / (low + 0.05)


def block(css, selector):
    match = re.search(re.escape(selector) + r'\s*\{(.*?)\}', css, re.S)
    assert match, f'missing block {selector}'
    return match.group(1)


def declarations(body):
    return dict(re.findall(r'--([a-z-]+):\s*([^;]+);', body))


class ConsoleContrastTests(unittest.TestCase):
    def setUp(self):
        self.css = CSS.read_text(encoding='utf-8')
        self.light = declarations(block(self.css, ':root'))
        self.dark = declarations(block(self.css, ':root[data-theme="dark"]'))
        media = self.css[self.css.index('@media (prefers-color-scheme: dark)'):]
        self.system_dark = declarations(block(media, ':root:not([data-theme="light"])'))

    def palettes(self):
        return [('light', self.light), ('dark', self.dark)]

    def color(self, palette, name):
        return name if name.startswith('#') else palette[name].strip()

    def test_both_palettes_meet_aa(self):
        for label, palette in self.palettes():
            for fg, bg in PAIRS:
                with self.subTest(palette=label, fg=fg, bg=bg):
                    self.assertGreaterEqual(ratio(self.color(palette, fg), self.color(palette, bg)), 4.5)

    def test_field_borders_meet_3_to_1(self):
        for label, palette in self.palettes():
            for fg, bg in NON_TEXT:
                with self.subTest(palette=label, fg=fg, bg=bg):
                    self.assertGreaterEqual(ratio(self.color(palette, fg), self.color(palette, bg)), 3.0)

    def test_hover_is_visible_on_panels_and_fields(self):
        for label, palette in self.palettes():
            for surface in ['panel', 'field', 'side']:
                with self.subTest(palette=label, surface=surface):
                    self.assertGreaterEqual(ratio(self.color(palette, 'hover'), self.color(palette, surface)), 1.08)

    def test_system_dark_matches_manual_dark(self):
        self.assertEqual(self.system_dark, self.dark)

    def test_dark_defines_every_light_colour(self):
        colours = [name for name, value in self.light.items() if value.strip().startswith('#')]
        self.assertEqual([name for name in colours if name not in self.dark], [])

    def test_every_var_used_is_defined(self):
        used = set(re.findall(r'var\(--([a-z-]+)', self.css))
        self.assertEqual(sorted(used - set(self.light)), [])

    def test_reduced_motion_overrides_every_animated_selector(self):
        block_text = self.css[self.css.index('@media (prefers-reduced-motion: reduce)'):]
        for selector in ['.unsaved-bar', '.unsaved-bar.is-open', '.unsaved-bar.is-shaking', '.sidebar', '.shell.is-drawer-open .sidebar', '.skeleton']:
            self.assertIn(selector, block_text)

    def test_no_important(self):
        self.assertNotIn('!important', self.css)


if __name__ == '__main__':
    unittest.main()
