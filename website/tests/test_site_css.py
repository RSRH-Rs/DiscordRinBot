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

    def test_focus_ring_keeps_the_element_radius(self):
        self.assertNotRegex(self.css, r':focus-visible\s*\{[^}]*border-radius')

    def test_button_press(self):
        self.assertRegex(self.css, r'\.btn:active\s*\{[^}]*scale\(\.97\)')

    def test_titles_use_the_rounded_face_without_faux_bold(self):
        self.assertRegex(self.css, r"--title:\s*'Fredoka',\s*'ZCOOL KuaiLe'")
        self.assertRegex(self.css, r'font-synthesis:\s*none')

    def test_chinese_titles_get_room(self):
        body = re.search(r'html\[data-lang="zh"\][^{]*h1[^{]*\{([^}]*)\}', self.css).group(1)
        self.assertIn('line-height: 1.3', body)
        self.assertIn('letter-spacing: .02em', body)

    def test_mixed_script_spacing(self):
        self.assertRegex(self.css, r'text-autospace:\s*normal')

    def test_reduced_motion_turns_off_transitions(self):
        blocks = re.findall(r'@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n\}', self.css, re.S)
        self.assertTrue(blocks)
        self.assertIn('transition: none', blocks[0])
        self.assertIn('animation: none', blocks[0])


PAGE_SIZES = {13, 14, 15, 16, 18, 24, 32, 40}


class PageCssTests(unittest.TestCase):
    """新页面各自的样式表只用页面字号表里的字号。"""

    def read(self, name):
        return (CSS_DIR / name).read_text(encoding='utf-8')

    def test_legal_pages_use_the_page_scale(self):
        self.assertLessEqual(font_sizes(self.read('legal.css')), PAGE_SIZES)

    def test_commands_page_uses_the_page_scale(self):
        css = self.read('commands.css')
        self.assertLessEqual(font_sizes(css), PAGE_SIZES)
        self.assertIn('var(--muted)', re.search(r'\.search \.slash\s*\{([^}]*)\}', css).group(1))
        panel = re.search(r'\.panel\s*\{([^}]*)\}', css).group(1)
        self.assertIn('max-height', panel)
        self.assertIn('overflow-y: auto', panel)

    def test_copy_feedback_and_toast_position(self):
        css = self.read('commands.css')
        toast = re.search(r'\.toast\s*\{([^}]*)\}', css).group(1)
        self.assertIn('top: 16px', toast)
        self.assertNotIn('bottom', toast)
        self.assertIn('.copy.is-done', css)

    def test_permissions_page_works_without_script(self):
        css = self.read('permissions.css')
        self.assertLessEqual(font_sizes(css), PAGE_SIZES)
        self.assertIn(':has(input:not(:checked))', css)
        ticked = re.search(r'input:checked\s*\{([^}]*)\}', css).group(1)
        self.assertIn('var(--dc-name)', ticked)
        self.assertNotIn('--accent', ticked)

    def test_commands_scroll_targets_clear_the_sticky_search(self):
        # site.css 的 section[id] { scroll-margin-top: 72px } 比 .sec 更具体；分组要用更具体的选择器才能留出搜索框的高度，
        # 方向键选中的行也要留，不然会滚到导航和搜索框底下
        css = self.read('commands.css')
        self.assertRegex(css, r'#list \.sec\s*\{[^}]*scroll-margin-top:\s*140px')
        self.assertRegex(re.search(r'\n\.row\s*\{([^}]*)\}', css).group(1), r'scroll-margin-top:\s*140px')

    def test_commands_search_hides_without_script(self):
        # 搜索要靠脚本；外壳在脚本能跑时给 html 加 .js，没有 .js 就不显示搜索框和"按 / 键"提示
        css = self.read('commands.css')
        rule = re.search(r'html:not\(\.js\) \.cmds \.search,\s*html:not\(\.js\) \.cmds \.found\s*\{([^}]*)\}', css)
        self.assertTrue(rule)
        self.assertIn('display: none', rule.group(1))

    def test_commands_selection_is_styled_by_aria_current(self):
        css = self.read('commands.css')
        self.assertIn('.row[aria-current="true"]', css)
        self.assertNotIn('aria-selected', css)
        self.assertIn('.sr-only', css)

    def test_legal_prose_is_narrow_and_the_table_is_wider(self):
        css = self.read('legal.css')
        self.assertRegex(css, r'max-width:\s*38em')
        self.assertRegex(re.search(r'\.data\s*\{([^}]*)\}', css).group(1), r'760px')


if __name__ == '__main__':
    unittest.main()
