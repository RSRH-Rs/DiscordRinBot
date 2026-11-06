"""官网公共外壳 site.css：两套配色的对比度、字号和减少动态效果。"""
import re
import unittest
from pathlib import Path

from test_console_contrast import block, declarations, ratio

ROOT = Path(__file__).resolve().parents[1]
CSS_DIR = ROOT / 'static' / 'css'

# 外壳里实际出现的文字和底色组合，加上新页面要用到的提示、高亮和 Discord 输入框
PAIRS = [
    ('text', 'bg'), ('muted', 'bg'), ('text', 'panel'), ('muted', 'panel'), ('accent-text', 'bg'),
    ('on-accent', 'accent'), ('accent-text', 'accent-soft'), ('warn', 'warn-soft'), ('warn', 'bg'),
    ('text', 'mark'), ('text', 'row-hover'), ('dc-name', 'dc-slot'), ('dc-text', 'dc-input'), ('dc-muted', 'dc-deep'),
]


def font_sizes(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    return {float(size) for size in re.findall(r'font(?:-size)?:[^;{}]*?(\d+(?:\.\d+)?)px', css)}


class SiteCssTests(unittest.TestCase):
    def setUp(self):
        self.css = (CSS_DIR / 'site.css').read_text(encoding='utf-8')
        self.light = declarations(block(self.css, ':root'))
        self.dark = declarations(block(self.css, ':root[data-theme="dark"]'))
        media = self.css[self.css.index('@media (prefers-color-scheme: dark)'):]
        self.system_dark = declarations(block(media, ':root:not([data-theme="light"])'))

    def test_both_palettes_meet_aa(self):
        for label, palette in [('light', self.light), ('dark', self.dark)]:
            for fg, bg in PAIRS:
                with self.subTest(palette=label, fg=fg, bg=bg):
                    self.assertGreaterEqual(ratio(palette[fg].strip(), palette[bg].strip()), 4.5)

    def test_field_borders_meet_3_to_1(self):
        for palette in (self.light, self.dark):
            self.assertGreaterEqual(ratio(palette['field-line'].strip(), palette['bg'].strip()), 3)

    def test_system_dark_matches_manual_dark(self):
        self.assertEqual(self.system_dark, self.dark)

    def test_shell_keeps_the_homepage_font_sizes(self):
        self.assertLessEqual(font_sizes(self.css), {12, 14, 15, 16, 18})

    def test_reduced_motion_turns_off_transitions(self):
        blocks = re.findall(r'@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n\}', self.css, re.S)
        self.assertTrue(blocks)
        self.assertIn('transition: none', blocks[0])
        self.assertIn('animation: none', blocks[0])


if __name__ == '__main__':
    unittest.main()
