"""Both console palettes meet WCAG AA, and every colour token the stylesheet uses is defined."""
import re
import unittest
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / 'static/css/console.css'
PAIRS = [
    ('text', 'bg'), ('text', 'panel'), ('text', 'side'), ('text', 'cur'), ('muted', 'bg'), ('muted', 'panel'), ('muted', 'side'),
    ('on-accent', 'accent'), ('on-accent', 'accent-hover'), ('accent-text', 'accent-soft'), ('accent-text', 'panel'),
    ('accent-text', 'accent-soft-hover'), ('bad', 'bad-soft-hover'),
    ('ok', 'ok-soft'), ('ok', 'panel'), ('warn', 'warn-soft'), ('bad', 'bad-soft'), ('bar-text', 'bar'), ('#FFFFFF', '#4752C4'),
]
NON_TEXT = [('field-line', 'field'), ('field-line', 'panel'), ('field-line', 'bg')]
ALLOWED_SIZES = {12, 13, 14, 16, 22}
EXEMPT = ('.preview', '.fake')
# Spacing, radius and weight sets (spec 2026-11-03-console-alignment §4.7-4.9). The Discord mock and the login sketch copy Discord's sizes.
SPACING = {0, 1, 4, 8, 12, 16, 24, 32, 40, 48}
CONTROL_SPACING = SPACING | {2, 6}
CONTROL_CLASSES = {'btn', 'input', 'select', 'select-trigger', 'search-select', 'search-btn', 'textarea', 'num', 'num-field', 'num-unit',
                   'seg', 'seg-option', 'chip', 'chip-remove', 'check-chip', 'tog', 'tog-track', 'tog-on', 'tog-off', 'theme-switch',
                   'nav-item', 'tab', 'palette-input'}
RADII = {'0', '4px', '8px', '12px', '999px', '50%', 'var(--radius)'}
LAYOUT_EXEMPT = ('.preview', '.discord-preview', '.fake')
SPACING_PROPS = re.compile(r'(?:^|;)\s*((?:padding|margin)(?:-[a-z-]+)?|gap|row-gap|column-gap)\s*:\s*([^;]+)')


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


def rules(css):
    """(selector parts, body) for every rule, comments stripped; parts are comma-split and whitespace-normalised."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        yield [' '.join(part.split()) for part in selector.split(',')], body


def first_class(part):
    """'.btn--primary:hover' -> 'btn'; '.seg-option' -> 'seg-option'; 'input[type=file]' -> None."""
    match = re.match(r'\.([a-z][a-z0-9-]*?)(?:--[a-z0-9-]+)?(?=$|[^a-z0-9-])', part)
    return match.group(1) if match else None


def rule(css, selector):
    """Body of the rule whose selector is exactly `selector` at the start of a line."""
    match = re.search(r'(?:^|\n)\s*' + re.escape(selector) + r'\s*\{([^}]*)\}', css)
    assert match, f'missing rule {selector}'
    return match.group(1)


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

    def test_console_uses_five_font_sizes(self):
        css = re.sub(r'/\*.*?\*/', '', self.css, flags=re.S)
        bad = []
        for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
            parts = [part.strip() for part in ' '.join(selector.split()).split(',')]
            if all(part.startswith(EXEMPT) for part in parts):
                continue
            for size in re.findall(r'font(?:-size)?:[^;]*?(\d+(?:\.\d+)?)px', body):
                if float(size) not in ALLOWED_SIZES:
                    bad.append((' '.join(selector.split()), size))
        self.assertEqual(bad, [])

    def test_button_press_and_hover(self):
        self.assertNotRegex(self.css, r'transition:\s*all')
        self.assertRegex(self.css, r'\.btn:active:not\(:disabled,\s*\[aria-busy="true"\]\)\s*\{[^}]*scale\(\.97\)')
        hover = self.css[self.css.index('@media (hover: hover)'):]
        self.assertIn('.btn--secondary:hover', hover)
        outside = self.css[:self.css.index('@media (hover: hover)')]
        self.assertNotIn('.btn--secondary:hover', outside)

    def test_buttons_have_two_sizes(self):
        small = rule(self.css, '.btn--sm')
        self.assertIn('min-height: 32px', small)
        self.assertIn('font-size: 13px', small)
        self.assertNotRegex(self.css, r'\.server-row\.is-unjoined \.btn\s*\{[^}]*font-size')
        self.assertNotRegex(rule(self.css, '.cmd-bulk'), 'font-(size|weight)|min-height')
        self.assertNotIn('.variable-tools button', self.css)

    def test_text_button_has_no_resting_underline(self):
        self.assertNotIn('underline', rule(self.css, '.btn--text'))

    def test_mixed_script_spacing(self):
        self.assertRegex(self.css, r'text-autospace:\s*normal')

    def test_latin_face_comes_first(self):
        stack = self.light['font-body']
        self.assertLess(stack.index('Segoe UI'), stack.index('Microsoft YaHei'))

    def test_segments_slide(self):
        self.assertRegex(self.css, r'\.seg::before\s*\{[^}]*transition:\s*transform')
        self.assertIn('.seg-option:nth-child(5)[aria-pressed="true"]', self.css)
        self.assertRegex(self.css, r'\.theme-switch::before\s*\{[^}]*transition:\s*transform')

    def test_chip_remove_grows_its_hit_area(self):
        self.assertIn('inset: -4px', rule(self.css, '.chip-remove::after'))

    def test_toggle_stretches_while_pressed(self):
        self.assertRegex(self.css, r'\.tog input:active \+ \.tog-track::after\s*\{[^}]*width: 20px')

    def test_popups_ease_in(self):
        self.assertRegex(self.css, r'@starting-style\s*\{\s*\.select-popup, \.palette, \.switcher-pop, \.emoji-picker\s*\{[^}]*scale\(\.97\)')

    def test_avatars_keep_an_edge_in_both_themes(self):
        self.assertIn('img-line', self.light)
        self.assertIn('img-line', self.dark)

    def test_page_rhythm(self):
        self.assertIn('margin-bottom: 16px', rule(self.css, '.note:not(:last-child)'))
        self.assertIn('margin-top: 24px', rule(self.css, '.actions + .section-hint'))
        self.assertRegex(self.css, r'\.tab-panel:has\(> \.section \+ \.section\)\s*\{[^}]*gap: 32px')
        self.assertNotIn('margin-bottom', rule(self.css, '.section-head'))
        self.assertIn('margin-top: 8px', rule(self.css, ':is(.section-title, .section-hint, .section-head) + :is(.list, .case-list, .lb-list)'))

    def test_no_important(self):
        self.assertNotIn('!important', self.css)

    def test_spacing_stays_on_the_grid(self):
        bad = []
        for parts, body in rules(self.css):
            if all(part.startswith(LAYOUT_EXEMPT) for part in parts):
                continue
            allowed = CONTROL_SPACING if all(first_class(part) in CONTROL_CLASSES for part in parts) else SPACING
            for prop, value in SPACING_PROPS.findall(body):
                for number in re.findall(r'-?\d+(?:\.\d+)?px', value):
                    size = abs(float(number[:-2]))
                    if size == 140 and parts == ['.content']:
                        continue
                    if size not in allowed:
                        bad.append((', '.join(parts), prop, number))
        self.assertEqual(bad, [])

    def test_radii_use_four_steps(self):
        bad = []
        for parts, body in rules(self.css):
            if all(part.startswith(LAYOUT_EXEMPT) for part in parts):
                continue
            for value in re.findall(r'border(?:-[a-z]+)*-radius\s*:\s*([^;]+)', body):
                for token in value.split():
                    if token not in RADII and not (token == '6px' and parts == ['.theme-switch button']):
                        bad.append((', '.join(parts), token))
        self.assertEqual(bad, [])

    def test_only_two_font_weights(self):
        bad = []
        for parts, body in rules(self.css):
            if all(part.startswith(LAYOUT_EXEMPT) for part in parts):
                continue
            weights = re.findall(r'font-weight\s*:\s*([^;]+)', body) + re.findall(r'(?:^|;)\s*font\s*:\s*(\d{3})\s', body)
            bad += [(', '.join(parts), w.strip()) for w in weights if w.strip() not in ('400', '600')]
        self.assertEqual(bad, [])

    def test_no_empty_rules(self):
        self.assertEqual([', '.join(parts) for parts, body in rules(self.css) if not body.strip()], [])

    def test_row_and_module_titles_are_regular(self):
        for selector in ['.row-title', '.mod-name', '.server-name', '.lb-name', '.user-name']:
            body = rule(self.css, selector)
            self.assertNotIn('font-weight: 600', body, selector)
            self.assertNotIn('font-weight: 500', body, selector)


if __name__ == '__main__':
    unittest.main()
