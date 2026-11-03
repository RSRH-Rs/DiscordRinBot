# Console Alignment and Detail Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every console page line up on one left edge and one right-hand control line, with one control height, left-aligned numbers with units inside the field, equal-width segments, indented sub-settings and fixed spacing/radius/weight sets, plus the seven deferred minors.

**Architecture:** Almost all of it is `website/static/css/console.css` and the Jinja templates (`_console_macros.html`, `server.html`), with two new macros (`num`, a `sub` flag on `row`). A small amount of JS changes (`console-core.js`, `dashboard-ui.js`, `modules/moderation.js`, `modules/welcome.js`), and the homepage gets two token-level fixes. A browser alignment checker in the repo is the baseline and the finish line.

**Tech Stack:** Quart + Jinja2 templates, one stylesheet, vanilla JS, Python `unittest`/pytest template and CSS tests, `node --test` with `vm` fakes.

**Spec:** `docs/superpowers/specs/2026-11-03-console-alignment-design.md`

## Global Constraints

- Commit directly on `master` as Jack Luo. Titles are `feat:` / `fix:` / `style:` / `docs:` plus a lowercase imperative summary, with a body. No attribution lines. Never commit `rinbot/cogs/netease.py`. Never push; pushing waits for the user.
- Colour token values and the five font sizes (12, 13, 14, 16, 22px) do not change.
- Keep every form control's element id. No build tools or frameworks. All copy goes in `website/i18n/zh.json`.
- Spacing (`padding*`, `margin*`, `gap`, `row-gap`, `column-gap`): 0, 4, 8, 12, 16, 24, 32, 40, 48px, their negatives, and 1px / -1px. Control-internal rules also allow 2px and 6px. The `.content` bottom 140px is exempt.
- Radii: 0, 4px, 8px, 12px (`var(--radius)`), 999px, 50%. The only 6px is `.theme-switch button`.
- Font weights: 400 and 600 only.
- `.preview*`, `.discord-preview` and `.fake*` copy Discord's own sizes and are exempt from the three numeric rules above.
- `--control-h` is 40px, and 44px below 860px wide.
- The 680px column, the 320px preview column, the 1200px editor breakpoint and the 860px phone breakpoint stay as they are.
- Asset version becomes `v=20261103c` everywhere it is `v=20261103b` now.
- Test commands:
  - `python -m pytest -q` from the repo root
  - `cd website && python -m pytest -q tests`
  - `node --test website/tests/*.test.cjs`

## Review Focus

1. A five-option segmented control on a 320px-wide phone must fit on one line without horizontal overflow (Task 5 checks it at 320px).
2. The largest values next to the widest unit (`mod-mt` = 50 with 次警告, `am-ct` = 100 with %) must show every digit, with nothing hidden under the unit (Task 4 sets these values and runs the checker's N code).
3. Clicking a unit puts focus in its number, and the focus ring stays visible on the 120px field (Task 4 tests `pointer-events: none` on the unit and the `.num:focus` ring).
4. Native `<select>` text must stay vertically centred at a fixed 40px and 44px height (Task 3 sets `padding-block: 0` on fixed-height fields and checks native selects in the preview at both heights).
5. The login gate and error pages share `console.css`, so they must still look right after the spacing and radius pass (Task 2 screenshots them if the preview serves them).

---

### Task 1: Alignment checker

**Files:**
- Create: `website/tests/browser/align-audit.js`

**Interfaces:**
- Produces: a script that is pasted into the browser console (or passed to the preview's JS tool) on any console page. It evaluates to a promise of `{width, theme, problems: {A: string[], B: [], C: [], D: [], E: [], F: [], I: [], N: [], O: [], S: []}}`. On a server page it walks every `.page[data-slug]` and every `[role="tab"][data-tab]` through `location.hash`, waiting 400ms each time. On other pages it audits the document once. Every later task runs it.

- [ ] **Step 1: Write the checker**

Start from `C:\Users\Jack\AppData\Local\Temp\claude\C--Users-Jack-Desktop-rinbot\e4f12831-d409-4772-b664-7401d8b6cc3d\scratchpad\align_audit.js` and the overflow check in `audit.js` next to it. Keep the codes in the spec's §8 table and add three more:

| Code | Reports |
|---|---|
| A | Controls in one visual row (same `top` among siblings of a grid or flex row) with different tops or heights |
| B | A visible `input`, `select` or `textarea` whose computed `text-align` is not `left` or `start` |
| C | A visible `.input`, `.select`, `.select-trigger`, `.num-field`, `.num` outside a `.num-field`, `.seg` or `.btn` (not `.btn--text` or `.btn--icon`) whose height differs from `parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--control-h'))` |
| D | Children of `.row-control`, `.actions`, `.seg-custom` or `.chip-add` whose vertical centres differ by more than 1px |
| E | A block that does not start at the content's left edge. Allow 16px for `.row--sub` and anything inside it. |
| F | A `.row:not(.row--block) > .row-control` whose right edge is more than 1px off its row's right edge |
| I | A row whose `data-depends-on` names a switch that is not a page master (`.tog--head input`) but which lacks `.row--sub`, and a `.row--sub` whose left edge is not 16px in from the list |
| N | A visible `input[type=number]` whose `scrollWidth > clientWidth`, or whose text box overlaps its `.num-unit` |
| O | Any element poking past the viewport's right edge (from `audit.js`) |
| S | A `.seg` whose options differ in width by more than 1px, or sit on more than one line |

Return the theme as `document.documentElement.dataset.theme || 'system'`.

- [ ] **Step 2: Record the baseline**

In the preview (`dashboard-preview`, port 5078), open `/dashboard/server/1000` at 1440×900 and run the checker.

Expected: problems that match the spec's §2:
- A: the giveaway row.
- B: 8 number fields, plus the two custom-duration ones once they are shown.
- C: native selects at 39px, segments at 38px, buttons at 35/36px.
- I: 6 rows.
- S: the giveaway segment and both duration segments.
- O: empty.

If O is not empty, the checker is wrong. Fix it before going on.

- [ ] **Step 3: Commit**

```bash
git add website/tests/browser/align-audit.js
git commit -m "feat: add a browser alignment checker for console pages"
```

Body: what each code checks and how to run it.

---

### Task 2: Spacing, radius and weight sets

**Files:**
- Modify: `website/static/css/console.css` (whole file)
- Modify: every template with `v=20261103b` (`grep -rl 20261103b website/templates`)
- Test: `website/tests/test_console_contrast.py`, `website/tests/test_dashboard_templates.py:354`

**Interfaces:**
- Produces: the `SPACING`, `CONTROL_SPACING`, `CONTROL_CLASSES`, `RADII` and `LAYOUT_EXEMPT` constants and a `rules(css)` helper in `test_console_contrast.py`. It yields `(parts, body)` for every rule outside comments, where `parts` are the comma-split, whitespace-normalised selectors. Later tasks' CSS must pass these tests.

- [ ] **Step 1: Write the failing tests** in `test_console_contrast.py`

```python
SPACING = {0, 1, 4, 8, 12, 16, 24, 32, 40, 48}
CONTROL_SPACING = SPACING | {2, 6}
CONTROL_CLASSES = {'btn', 'input', 'select', 'select-trigger', 'search-select', 'search-btn', 'textarea', 'num', 'num-field', 'num-unit',
                   'seg', 'seg-option', 'chip', 'chip-remove', 'check-chip', 'tog', 'tog-track', 'tog-on', 'tog-off', 'theme-switch',
                   'nav-item', 'tab', 'palette-input'}
RADII = {'0', '4px', '8px', '12px', '999px', '50%', 'var(--radius)'}
LAYOUT_EXEMPT = ('.preview', '.discord-preview', '.fake')

def first_class(part):  # '.btn--primary:hover' -> 'btn'; '.seg-option' -> 'seg-option'
    m = re.match(r'\.([a-z][a-z0-9-]*?)(?:--[a-z0-9-]+)?(?=$|[^a-z0-9-])', part)
    return m.group(1) if m else None

def test_spacing_stays_on_the_grid(self):
    # every px number in padding*/margin*/gap/row-gap/column-gap must be in SPACING,
    # or CONTROL_SPACING when every selector part's first_class is in CONTROL_CLASSES;
    # skip parts that all start with LAYOUT_EXEMPT; skip 140 when parts == ['.content']
    self.assertEqual(bad, [])

def test_radii_use_four_steps(self):
    # every token of border-radius / border-*-radius must be in RADII; '6px' only when parts == ['.theme-switch button']
    self.assertEqual(bad, [])

def test_only_two_font_weights(self):
    # font-weight values and the weight in `font:` shorthands must be 400 or 600; no bold/bolder/lighter
    self.assertEqual(bad, [])

def test_row_and_module_titles_are_regular(self):
    for sel in ['.row-title', '.mod-name', '.server-name', '.lb-name', '.cmd-name', '.user-name']:
        self.assertNotIn('font-weight: 600', block(self.css, sel)); self.assertNotIn('font-weight: 500', block(self.css, sel))
```

Change `test_dashboard_templates.py:354` to expect `padding: 12px 0`.

- [ ] **Step 2: Run them and watch them fail**

Run: `cd website && python -m pytest -q tests/test_console_contrast.py tests/test_dashboard_templates.py`
Expected: FAIL, listing the off-grid values (3, 7, 10, 14, 18, 20, 22, 26, 28, 30, 34, 36, 50), the radii 3/5/6/7/9/10/11/14/20, and weight 500.

- [ ] **Step 3: Move every value onto the sets**

**Spacing.** Round each value to the nearest allowed one; on a tie, take the smaller. For example, outside controls 10→8, 14→12, 20→16, 28→24 and 36→32; inside controls 3→2, 7→6 and 10→8. `.row` padding becomes `12px 0`. The visual pass (Step 5) may move a single value up one step instead; record that as a ruling.

**Radii.** By role:
- **8px:** controls and nav items, `.switcher-btn`, `.switcher-icon` (both sizes), `.server-icon`, `.mod-icon`, `.search-btn`, `.menu-btn`, `.user-logout`, `.note`, `.notice`, `.ov-error`, `.load-feedback`, `.gate-error`.
- **12px:** `.palette`, `.toast`, `.gate`, `.upload-preview`, `.select-popup`, `.emoji-picker`, `.switcher-pop`.
- **4px:** items inside a 12px popup with 8px padding, which is concentric. That is `.select-option`, `.palette-item`, `.ep-item` and `.switcher-item`, so set those containers' padding to 8px. The same step covers `.nav-badge`, `kbd`, `.variable-tools button`, and the overview skeleton text.
- **999px:** `.tog-track`.
- Everything already on a step stays.

**Weights.** Make `.row-title`, `.mod-name`, `.server-name`, `.lb-name`, `.cmd-name`, `.cmd-card code`, `.user-name`, `.brand-name`, `.notice a` and `.select-option[aria-selected="true"]` 400. Leave the 600s the spec lists.

**Version.** Bump every `v=20261103b` to `v=20261103c`.

- [ ] **Step 4: Run the tests**

Run: `cd website && python -m pytest -q tests`
Expected: all pass.

- [ ] **Step 5: Visual pass**

Restart the preview. Screenshot the overview, welcome, automod, utility, `/dashboard` and `/dashboard/settings` at 1440 and 375, plus the login gate and error page if the preview serves them. Compare with the pre-task screenshots. Nothing may look cramped or broken; ledger any value moved up a step. Run the checker: O must be empty.

- [ ] **Step 6: Commit**

```bash
git commit -am "style: put console spacing, radii and weights on fixed sets"
```

Body: the three sets, the tie rule, row padding 14→12, the concentric 4px popup items, and the weights moved to 400.

---

### Task 3: One control height and touch targets

**Files:**
- Modify: `website/static/css/console.css`
- Test: `website/tests/test_dashboard_templates.py`

**Interfaces:**
- Produces: the `--control-h` token in `:root` (40px), overridden to 44px in `@media (max-width: 859px) { :root { … } }`.

- [ ] **Step 1: Write the failing tests**

```python
def test_controls_share_one_height(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    self.assertRegex(re.search(r'\n:root\s*\{([^}]*)\}',css).group(1),r'--control-h:\s*40px')
    narrow=css[css.index('@media (max-width: 859px)'):]
    self.assertRegex(narrow,r':root\s*\{[^}]*--control-h:\s*44px')
    fixed=re.search(r'\n\.input, \.select, \.num, \.select-trigger\s*\{([^}]*)\}',css).group(1)
    for part in ['height: var(--control-h)','padding-block: 0']:self.assertIn(part,fixed)
    self.assertIn('min-height: var(--control-h)',re.search(r'\n\.btn\s*\{([^}]*)\}',css).group(1))
    self.assertIn('height: var(--control-h)',re.search(r'\n\.seg\s*\{([^}]*)\}',css).group(1))
    self.assertIn('height: var(--control-h)',re.search(r'\n\.emoji-trigger\s*\{([^}]*)\}',css).group(1))
    self.assertNotRegex(css,r'\.server-row\.is-unjoined \.btn\s*\{[^}]*min-height')

def test_phone_touch_targets(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8'); narrow=css[css.index('@media (max-width: 859px)'):]
    self.assertRegex(css,r'\n\.tog input\s*\{[^}]*inset: -9px 0')
    self.assertRegex(narrow,r'\.tog\s*\{[^}]*width: 48px;[^}]*height: 28px')
    self.assertRegex(narrow,r'\.tog input\s*\{[^}]*inset: -8px 0')
    self.assertRegex(narrow,r'\.tog input:checked \+ \.tog-track::after\s*\{[^}]*translateX\(20px\)')
    for sel in [r'\.nav-item',r'\.btn--icon',r'\.menu-btn',r'\.user-logout']:self.assertRegex(narrow,sel+r'\s*\{[^}]*min-height: 44px')
    self.assertRegex(narrow,r'\.theme-switch button\s*\{[^}]*width: 44px;[^}]*height: 36px')
    self.assertRegex(narrow,r'\.theme-switch button::after\s*\{[^}]*inset: -4px 0')
```

- [ ] **Step 2: Run and watch them fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py -k "one_height or touch_targets"`
Expected: FAIL. No `--control-h` exists yet.

- [ ] **Step 3: Implement**

- **Token.** Add `--control-h` to `:root`. In the phone `@media`, add `:root { --control-h: 44px; }`.
- **Fields.** Add a rule `.input, .select, .num, .select-trigger { height: var(--control-h); padding-block: 0; }`. The shared field rule keeps its 12px inline padding. `.textarea` keeps its own padding.
- **Buttons, segments, emoji.** `.btn` gets `min-height: var(--control-h)` and `padding: 0 16px`. `.seg` gets `height: var(--control-h)`, with the options filling it. `.emoji-trigger` becomes `width: 44px; height: var(--control-h)`.
- **Server list.** Delete the `min-height` and `padding` from `.server-row.is-unjoined .btn`.
- **Switches.** On desktop, `.tog input` becomes `inset: -9px 0`, a 40px-tall hit area. On phones:
  - `.tog` is 48×28.
  - The knob is 24px at `top: 2px; left: 2px`.
  - The checked knob sits at `translateX(20px)`.
  - `.tog--head .tog-track` is 48px wide.
  - `.tog input` is `inset: -8px 0`.
- **Phone touch targets.**
  - `.nav-item`, `.btn--icon`, `.menu-btn` and `.user-logout` get `min-height: 44px`.
  - `.btn--icon`, `.menu-btn` and `.user-logout` also get `min-width: 44px`.
  - `.theme-switch button` is 44×36 with `position: relative`, and its `::after` has `content: ""; position: absolute; inset: -4px 0`.

- [ ] **Step 4: Run the tests**

Run: `cd website && python -m pytest -q tests`
Expected: all pass.

- [ ] **Step 5: Check in the preview** (Review Focus 4)

Run the checker at 1440 and at 375. C must have no field, select, segment or button entries left; any that remain belong to Tasks 4 and 5's number fields, so note them for those tasks. Zoom into a native `<select>` (moderation's custom-duration unit, utility's filter) at both widths: the text must sit vertically centred. Tap-test the overview switches at 375: a press 8px above or below the track still toggles it and does not open the module.

- [ ] **Step 6: Commit**

```bash
git commit -am "style: give console controls one height and phone-sized touch targets"
```

---

### Task 4: Numbers with units inside the field

**Files:**
- Modify: `website/templates/_console_macros.html`, `website/templates/server.html:203-207,217-219,260-265`, `website/static/css/console.css`, `website/static/js/console-core.js:73-75` (custom-duration amount), `website/i18n/zh.json`
- Test: `website/tests/test_dashboard_templates.py`

**Interfaces:**
- Produces: the macro `num(id, unit, min, max, value, label=None)`, exported from `_console_macros.html` and imported in `server.html`. It renders exactly:
  `<span class="num-field"><input class="num" type="number" inputmode="numeric" id="{id}" min="{min}" max="{max}" value="{value}" aria-describedby="{id}-unit"[ aria-label="{label}"]><span class="num-unit" id="{id}-unit">{unit}</span></span>`
- Produces: new copy keys `automod.within` = 内发, `automod.messages` = 条, `automod.messages_label` = 消息条数.
- Removes: the copy keys `automod.messages_per` and `automod.seconds_label`.

- [ ] **Step 1: Write the failing tests**

```python
def test_number_fields_read_left_with_units_inside(self):
    html,_=self.render('server.html')
    for id_,unit in [('am-si','秒'),('am-st','条'),('am-ct','%'),('am-rt','次'),('mod-mt','次警告'),('mod-kt','次警告'),('mod-bt','次警告')]:
        self.assertRegex(html,rf'<span class="num-field"><input class="num" type="number" inputmode="numeric" id="{id_}"[^>]*aria-describedby="{id_}-unit"[^>]*><span class="num-unit" id="{id_}-unit">{re.escape(unit)}</span></span>')
    self.assertNotIn('class="unit">条 /',html)
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    num=re.search(r'\n\.num\s*\{([^}]*)\}',css).group(1)
    for part in ['width: 120px','text-align: left','appearance: textfield']:self.assertIn(part,num)
    self.assertIn('::-webkit-inner-spin-button',css)
    self.assertIn('width: 120px',re.search(r'\n\.num-field\s*\{([^}]*)\}',css).group(1))
    self.assertIn('pointer-events: none',re.search(r'\n\.num-unit\s*\{([^}]*)\}',css).group(1))

def test_spam_trigger_reads_seconds_then_messages(self):
    html,_=self.render('server.html')
    self.assertLess(html.index('id="am-si"'),html.index('>内发<'));self.assertLess(html.index('>内发<'),html.index('id="am-st"'))
    self.assertIn('<label class="row-title" for="am-si">触发条件</label>',html)
    self.assertRegex(html,r'id="am-st"[^>]*aria-label="消息条数"')
    zh=json.loads((ROOT/'i18n/zh.json').read_text(encoding='utf-8'))
    for key in ['messages_per','seconds_label']:self.assertNotIn(key,zh['automod'])
    self.assertEqual((zh['automod']['within'],zh['automod']['messages']),('内发','条'))
```

Add `import json` at the top of the file.

- [ ] **Step 2: Run and watch them fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py -k "number_fields or spam_trigger"`
Expected: FAIL. There is no `num-field` yet.

- [ ] **Step 3: Implement**

**Macro.** Add `num()` to `_console_macros.html` and add it to `server.html`'s import line.

**Templates.**
- The spam-threshold row reads `num('am-si', 秒)`, then `<span class="unit">内发</span>`, then `num('am-st', 条, label=消息条数)`.
- Its row's `for_id` changes to `am-si`.
- `am-ct` gets `%` and `am-rt` gets `automod.times`.
- `mod-mt`, `mod-kt` and `mod-bt` get `moderation.warnings`.
- Keep each field's min, max and value from the current markup.

**CSS.**
- `.num`: `width: 120px; text-align: left; appearance: textfield; -moz-appearance: textfield`.
- Hide the spinners with `.num::-webkit-inner-spin-button, .num::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }`.
- `.num-field`: `display: inline-grid; width: 120px`, with `.num-field > *` set to `grid-area: 1 / 1`.
- `.num-field .num`: `width: 100%; padding-right: calc(3em + 16px)`.
- `.num-unit`: `align-self: center; justify-self: end; margin-right: 12px; pointer-events: none; color: var(--muted); font-size: 14px`.

**JS.** In `console-core.js`, set `amount.inputMode = 'numeric'` on the custom-duration amount. Make the custom-duration layout `.seg-custom { gap: 8px }`, keeping `.seg-custom .select { width: 96px }`.

**Copy.** Update `zh.json` per Interfaces.

- [ ] **Step 4: Run the tests**

Run: `cd website && python -m pytest -q tests && node --test website/tests/*.test.cjs`
Expected: all pass. If `automod_ui.test.cjs` reads the removed keys, update it to the new ones.

- [ ] **Step 5: Check in the preview** (Review Focus 2 and 3)

Restart the preview. On automod, set `am-ct` to 100. On moderation, set `mod-mt` to 50 and pick 自定义 on the duration. Then:
- Run the checker at 1440 and 375: B, C, D and N must have no number entries.
- Click on a unit: the caret must land in its number.
- Tab into a number: the focus ring must wrap the whole 120px field.

- [ ] **Step 6: Commit**

```bash
git commit -am "style: left-align console numbers and put their units inside the field"
```

Body: the 120px suffix field, hidden spinners, the 秒内发条 order, and the removed keys.

---

### Task 5: Equal-width segmented controls

**Files:**
- Modify: `website/static/css/console.css` (`.seg`, `.seg-option`, phone `.seg`), `website/static/js/console-core.js` (`duration.mount`), `website/templates/server.html:289-292`
- Test: `website/tests/test_dashboard_templates.py`, `website/tests/console_core.test.cjs`

**Interfaces:**
- Produces: every `.seg-option` carries `data-label` equal to its text. The CSS reserves the bold width from that attribute.

- [ ] **Step 1: Write the failing tests**

Python:

```python
def test_segments_are_equal_width(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    seg=re.search(r'\n\.seg\s*\{([^}]*)\}',css).group(1)
    for part in ['display: inline-grid','grid-auto-flow: column','grid-auto-columns: minmax(72px, 1fr)']:self.assertIn(part,seg)
    self.assertNotIn('flex-wrap',seg)
    after=re.search(r'\n\.seg-option::after\s*\{([^}]*)\}',css).group(1)
    for part in ['content: attr(data-label)','height: 0','visibility: hidden','font-weight: 600']:self.assertIn(part,after)
    narrow=css[css.index('@media (max-width: 859px)'):]
    self.assertRegex(narrow,r'\.seg\s*\{[^}]*display: grid;[^}]*width: 100%;[^}]*grid-auto-columns: minmax\(0, 1fr\)')
    html,_=self.render('server.html')
    for label,text in re.findall(r'class="seg-option" data-end-in="[^"]+" data-label="([^"]+)" aria-pressed="[a-z]+">([^<]+)<',html):self.assertEqual(label,text)
    self.assertEqual(len(re.findall(r'class="seg-option" data-end-in=',html)),4)
```

Node, in `console_core.test.cjs`:

```js
test('duration options carry their label for equal-width segments', () => {
    // fake document.createElement returning {dataset:{}, ...}; mount a seg whose data-for input exists;
    // every created option (presets + custom) has dataset.label === textContent
});
```

- [ ] **Step 2: Run and watch them fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py -k segments && cd .. && node --test website/tests/console_core.test.cjs`
Expected: FAIL. `.seg` is still `inline-flex`, and the options have no `data-label`.

- [ ] **Step 3: Implement**

- **CSS.** Make the `.seg` rule match the test, with no `flex-wrap`. `.seg-option` gets `padding: 0 12px`, keeps its left divider, and gets the `::after` reservation (`display: block; overflow: hidden`). In the phone block, `.seg` uses the grid shown in the test, and the `.seg-option { flex: 1 0 auto }` rule is deleted.
- **JS.** `duration.mount` sets `dataset.label` on each preset and on 自定义.
- **Template.** The giveaway template adds `data-label` before `aria-pressed` on its four options.

- [ ] **Step 4: Run all tests**

Run the three suite commands.
Expected: all pass.

- [ ] **Step 5: Check in the preview** (Review Focus 1)

Run the checker at 1440, at 375 and at 320×700. S and O must be empty. Click through each option: the control's width must not change.

- [ ] **Step 6: Commit**

```bash
git commit -am "style: give segmented controls equal-width options that never wrap"
```

---

### Task 6: Indented sub-settings

**Files:**
- Modify: `website/templates/_console_macros.html` (`row`), `website/templates/server.html` (the 6 rows), `website/static/css/console.css`
- Test: `website/tests/test_dashboard_templates.py`

**Interfaces:**
- Produces: `row(title, hint=None, for_id=None, depends=None, block=False, cls='', sub=False)`. When `sub` is true it adds the class `row--sub`.

- [ ] **Step 1: Write the failing test**

```python
def test_sub_settings_are_indented(self):
    html,_=self.render('server.html')
    masters=set(re.findall(r'class="tog tog--head"><input type="checkbox" role="switch" id="([^"]+)"',html))
    rows=re.findall(r'<div class="(row[^"]*)" data-depends-on="([^"]+)"',html)
    self.assertEqual(sorted(d for c,d in rows if 'row--sub' in c.split()),['am-bw','am-caps','am-link','am-repeat','am-spam','am-spam'])
    for cls,dep in rows:self.assertEqual('row--sub' in cls.split(),dep not in masters,(cls,dep))
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    self.assertIn('margin-left: 16px',re.search(r'\n\.row--sub\s*\{([^}]*)\}',css).group(1))
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py -k sub_settings`
Expected: FAIL. The sorted list is empty.

- [ ] **Step 3: Implement**

- Add `sub` to the `row` macro.
- Pass `sub=True` on the rows for `am-st`/`am-si`, `am-mute`, `am-ct`, `am-rt`, `am-bw-new` and `am-wl-new`.
- Add `.row--sub { margin-left: 16px; }`. Because the hairline is the row's own `border-top`, it starts at the indent.

- [ ] **Step 4: Run all tests**

Run the three suite commands.
Expected: all pass.

- [ ] **Step 5: Check in the preview**

Run the checker on `automod/rules`, `automod/words` and `automod/links`: I and E must be empty. Turn 反刷屏 off: its two sub-rows dim but stay visible and indented.

- [ ] **Step 6: Commit**

```bash
git commit -am "style: indent settings that depend on a switch row"
```

---

### Task 7: Editor pages in two columns from the top

**Files:**
- Modify: `website/templates/server.html:90-96` (welcome), `:140-144` (roles)
- Test: `website/tests/test_dashboard_templates.py`

- [ ] **Step 1: Write the failing test**

```python
def test_editor_head_sits_in_the_form_column(self):
    html,_=self.render('server.html')
    for slug in ['welcome','roles']:
        start=html.index(f'id="pg-{slug}"');page=html[start:html.index('</section>',start)]
        self.assertRegex(page,r'^[^>]*>\s*<div class="editor">\s*<div class="editor-form">\s*<div class="page-head">')
        form=page.index('class="editor-form"')
        self.assertLess(form,page.index('class="page-head"'))
        if slug=='welcome':self.assertLess(page.index('class="page-head"'),page.index('class="tabs"'))
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py -k editor_head`
Expected: FAIL. The page head currently comes before `.editor`.

- [ ] **Step 3: Implement**

Move `page_head(...)`, and `tabs(...)` on the welcome page, inside `<div class="editor-form">` as its first children. Leave the CSS alone: the grid's `align-items: start` puts the preview's top on the page head's top. Then search `website/static/js` for `:scope >` and `> .page-head` / `> .tabs`, and fix any selector that assumed the head was a direct child of the page.

- [ ] **Step 4: Run all tests**

Run the three suite commands.
Expected: all pass, including `test_editor_pages` and `test_sticky_preview_scrolls_inside_itself`.

- [ ] **Step 5: Check in the preview**

**Alignment:**
- At 1440, the welcome master switch's right edge equals the 附带欢迎横幅 switch's right edge.
- The preview's top equals the page head's top, within 1px.

**Sticky preview:** at 1366×768 the preview stays beside the form and fits the viewport.

**Narrow layout:**
- At 1100 the layout is one column: head, tabs, form, preview.
- Tabs still switch.
- The unsaved bar still shows after an edit.

- [ ] **Step 6: Commit**

```bash
git commit -am "style: start editor pages as two columns with the head over the form"
```

---

### Task 8: Giveaway form as flat rows

**Files:**
- Modify: `website/templates/server.html:274-305`, `website/static/css/console.css` (delete `.form-grid`, `.field` and `.field ...`; keep `#gw-end` with `width: 240px; margin-top: 8px`), `website/i18n/zh.json` (`giveaway.winners_unit` = 人)
- Test: `website/tests/test_dashboard_templates.py`

**Interfaces:**
- Consumes: `num()` from Task 4, and `data-label` on the segment options from Task 5.

- [ ] **Step 1: Write the failing test**

```python
def test_giveaway_form_is_flat_rows(self):
    html,_=self.render('server.html')
    start=html.index('id="pg-giveaway"');gw=html[start:html.index('</section>',start)]
    self.assertNotIn('form-grid',gw);self.assertNotIn('class="field"',gw)
    titles=re.findall(r'class="row-title"[^>]*>([^<]+)<',gw)
    self.assertEqual(titles[:5],['奖品','中奖人数','发到哪个频道','参加限制','什么时候开奖'])
    self.assertIn('<label class="row-title" for="gw-role">参加限制</label><span class="row-hint">不选就是所有人都能参加</span>',gw)
    self.assertRegex(gw,r'<span class="num-field"><input class="num" type="number" inputmode="numeric" id="gw-winners"[^>]*><span class="num-unit" id="gw-winners-unit">人</span>')
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    self.assertNotIn('.form-grid',css);self.assertNotRegex(css,r'\n\.field[ ,{]')
```

- [ ] **Step 2: Run and watch it fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py -k giveaway_form`
Expected: FAIL on `form-grid`.

- [ ] **Step 3: Implement**

Rewrite the 新建抽奖 list as spec §5.1 orders it:
- 奖品: `row(..., 'gw-prize', block=True)` with the input.
- 中奖人数: `row(..., 'gw-winners')` with `num('gw-winners', 人, 1, 20, 1)`.
- 发到哪个频道: `row(..., 'gw-ch')` with the select.
- 参加限制: `row(..., role_hint, 'gw-role')` with the select.
- 什么时候开奖: keep the existing block row, its `gw-end-label` id and the segment.

Keep the `data-draft`/`data-draft-inline` attributes and every id. Search `website/static/js/modules/giveaway.js` for `.field` or `form-grid` and drop any use.

- [ ] **Step 4: Run all tests**

Run the three suite commands.
Expected: all pass.

- [ ] **Step 5: Check in the preview**

At 1440 and 375, the checker on `giveaway` reports no A, B, C, F or S entries. Create a giveaway in the mock: the request body carries the same fields as before.

- [ ] **Step 6: Commit**

```bash
git commit -am "style: lay the giveaway form out as flat rows"
```

---

### Task 9: Welcome image picker and Chinese case types

**Files:**
- Modify: `website/templates/_console_macros.html:22-34` (`upload`), `website/static/js/modules/welcome.js` (picked status), `website/static/js/modules/moderation.js:16`, `website/static/css/console.css` (delete `input[type="file"]` and `::file-selector-button`), `website/i18n/zh.json`
- Create: `website/tests/moderation_ui.test.cjs`
- Test: `website/tests/test_dashboard_templates.py`, `website/tests/welcome_image_ui.test.cjs`

**Interfaces:**
- Produces: copy keys `welcome.image.pick` = 选一张图片 and `welcome.image.picked` = 已选择 {name}，点「上传图片」才会生效. `moderation.action.{warn,mute,unmute,kick,ban,tempban,unban,purge,other}` = 警告 / 禁言 / 解除禁言 / 踢出 / 封禁 / 临时封禁 / 解除封禁 / 清理消息 / 其他.

- [ ] **Step 1: Write the failing tests**

Python:

```python
def test_file_inputs_hide_behind_a_styled_button(self):
    for name in ['server.html','settings.html']:
        html,_=self.render(name)
        for id_ in re.findall(r'<input class="sr-only" type="file" id="([^"]+)"',html):self.assertIn(f'<label class="btn btn--secondary" for="{id_}">',html)
        self.assertEqual(len(re.findall(r'type="file"',html)),len(re.findall(r'<input class="sr-only" type="file"',html)))
    self.assertNotIn('file-selector-button',(ROOT/'static/css/console.css').read_text(encoding='utf-8'))
```

Node, in `moderation_ui.test.cjs`, with a `vm` harness modelled on `automod_ui.test.cjs`:

```js
test('cases show their type in Chinese', () => {
    // load moderation.js with Console stubs; feed cases [{case_no:1, action:'warn', ...}, {case_no:2, action:'nuke', ...}]
    // mod-cases innerHTML contains '#1 警告' with class chip--warn and '#2 其他' with class chip--other
});
```

In `welcome_image_ui.test.cjs`, after picking a file named `cat.png`, the state text is `已选择 cat.png，点「上传图片」才会生效`.

- [ ] **Step 2: Run and watch them fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py -k file_inputs && cd .. && node --test website/tests/moderation_ui.test.cjs website/tests/welcome_image_ui.test.cjs`
Expected: FAIL. The welcome file inputs are visible, and cases show `warn`.

- [ ] **Step 3: Implement**

- **Upload macro.** The file input becomes `class="sr-only"` and keeps its id, `accept` and `data-draft-ignore`. It moves into `.actions`, right after a new `<label class="btn btn--secondary" for="w-{kind}-file">{{ tr('welcome.image.pick') }}</label>`.
- **Welcome picked status.** The status call becomes `tr('welcome.image.picked', {name: file.name})`.
- **Case chip.** It renders `#{no} {tr('moderation.action.' + kind)}`, escaped as today.
- **CSS.** Delete the native file-input rules.

- [ ] **Step 4: Run all tests**

Run the three suite commands.
Expected: all pass.

- [ ] **Step 5: Check in the preview**

- **Welcome:** On appearance and farewell, pick a file. The button opens the picker and the status shows the filename. Upload still works.
- **Moderation:** Recent cases read #1 警告, #2 禁言.

- [ ] **Step 6: Commit**

```bash
git commit -am "fix: style the welcome image picker and show punishment types in chinese"
```

---

### Task 10: Console minors

**Files:**
- Modify: `website/static/css/console.css`, `website/templates/_console_base.html` (brand row), `website/i18n/zh.json` (delete `nav.homepage_label`), `website/static/js/dashboard-ui.js:186-193`, `website/static/js/console-core.js:204-209`
- Test: `website/tests/test_dashboard_templates.py`, `website/tests/console_core.test.cjs`, `website/tests/dashboard_ui.test.cjs`

- [ ] **Step 1: Write the failing tests**

Python:

```python
def test_empty_lists_drop_their_hairlines(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    self.assertRegex(css,r':is\(\.list, \.case-list, \.lb-list, \.item-list, \.cmd-grid\):has\(> \.empty:only-child\)\s*\{[^}]*border-block: 0')
    self.assertNotIn('.lb-list:has(.empty)',css)

def test_brand_row_is_named_by_its_text(self):
    html,_=self.render('server.html')
    link=re.search(r'<a class="brand-row" href="/"[^>]*>(.*?)</a>',html,re.S)
    self.assertNotIn('aria-label',link.group(0).split('>')[0]); self.assertIn('alt=""',link.group(1))
    self.assertIn('小凛 RinBot',link.group(1)); self.assertIn('主页',link.group(1))
    self.assertNotIn('homepage_label',json.loads((ROOT/'i18n/zh.json').read_text(encoding='utf-8'))['nav'])

def test_emoji_trigger_uses_the_field_colour(self):
    css=(ROOT/'static/css/console.css').read_text(encoding='utf-8')
    self.assertIn('background: var(--field)',re.search(r'\n\.emoji-trigger\s*\{([^}]*)\}',css).group(1))
```

Update the existing home-link test so it no longer expects `aria-label`.

Node:
- `console_core.test.cjs`: `'modifier clicks on the brand row and switcher open a new tab without the draft check'`. Use `core({dirty: true})`. For each of `ctrlKey`, `metaKey` and `shiftKey` set true on the event, `leaveClick` leaves `prevented` false and `calls.confirm` undefined.
- `dashboard_ui.test.cjs`: `'opening the drawer focuses the server switcher'`. `toggleSidebar()` focuses the element with id `switcher-btn`, even though `.brand-row` comes first in the sidebar.

- [ ] **Step 2: Run and watch them fail**

Run: `cd website && python -m pytest -q tests/test_dashboard_templates.py -k "hairlines or brand_row or emoji_trigger" && cd .. && node --test website/tests/console_core.test.cjs website/tests/dashboard_ui.test.cjs`
Expected: FAIL on each.

- [ ] **Step 3: Implement**

- **Empty lists.** Add the `:is(...)` rule from the test and delete the `.lb-list:has(.empty)` one.
- **Brand row.** Drop its `aria-label` and set `alt=""` on its image. Delete `nav.homepage_label`.
- **Drawer focus.** `toggleSidebar` focuses `el('switcher-btn')`, falling back to the current first-focusable query when there is no switcher.
- **Modifier clicks.** In `leaveClick`, right after the `_blank` check, return early when `event.ctrlKey || event.metaKey || event.shiftKey`.
- **Emoji trigger.** `.emoji-trigger` gets `background: var(--field)`.

- [ ] **Step 4: Run all tests**

Run the three suite commands.
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git commit -am "fix: tidy empty lists, the brand row name, drawer focus and modifier clicks"
```

---

### Task 11: Homepage minors

**Files:**
- Modify: `website/templates/index.html:33-37` (boot script and metas), its three palette blocks (`--dc-gold`), `:429`
- Test: `website/tests/test_homepage_theme.py`, `tests/test_homepage.py:169-174`

- [ ] **Step 1: Write the failing tests**

```python
# website/tests/test_homepage_theme.py
def test_manual_theme_sets_the_address_bar_colour(self):
    head=self.page[:self.page.index('</head>')]
    self.assertLess(head.index('name="theme-color"'),head.index("localStorage.getItem('rin-theme')"))
    script=re.search(r"<script>try\{var t=localStorage.getItem\('rin-theme'\).*?</script>",head).group(0)
    for part in ['theme-color','#17171B','#F7F7F8']:self.assertIn(part,script)
```

In `tests/test_homepage.py`, add `("dc-gold", "dc-deep")` to `TEXT_PAIRS`. It is then checked in both palettes by the existing parametrize.

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest -q tests/test_homepage.py && cd website && python -m pytest -q tests/test_homepage_theme.py`
Expected: FAIL. `dc-gold` is missing, and the metas come after the script.

- [ ] **Step 3: Implement**

- **Metas.** Move the two `theme-color` metas above the boot script.
- **Boot script.** When `t` is `light` or `dark`, it also sets every `meta[name="theme-color"]` `content` to `#F7F7F8` or `#17171B`.
- **Gold token.** Add `--dc-gold: #8C5D00` to `:root`, and `--dc-gold: #F0B232` to both the manual-dark and system-dark blocks. These give 5.14:1 and 7.3:1 on `--dc-deep`.
- **Rank colour.** Point `.lb li:first-child .pos` at `var(--dc-gold)`.

- [ ] **Step 4: Run all tests**

Run the three suite commands.
Expected: all pass, including `test_system_dark_matches_manual_dark`.

- [ ] **Step 5: Commit**

```bash
git commit -am "fix: follow the manual theme in the address bar and darken the homepage gold"
```

---

### Task 12: Final alignment pass

**Files:**
- Modify: only what the pass finds; each fix gets a failing test first.

- [ ] **Step 1: Run the checker everywhere**

Restart the preview. Run `align-audit.js` on `/dashboard/server/1000`, `/dashboard` and `/dashboard/settings`, at 1440×900, 1080×800 and 375×812, in both light and dark (`localStorage['rin-theme']`, then reload).
Expected: every code empty on every run. Fix anything found with a test, then re-run.

- [ ] **Step 2: Screenshot review**

At 1440 and 375, light and dark, compare each page with the screenshots from before Task 2:
- the overview;
- every tab of welcome and automod;
- roles, moderation, giveaway, utility and both log pages;
- the server list and settings;
- the homepage at `/home`.

Also confirm that at 1366×768 the welcome preview sits beside the form and fits the viewport.

- [ ] **Step 3: Full suites**

Run all three test commands.
Expected: everything passes. Record the counts.

- [ ] **Step 4: Commit any pass fixes**

```bash
git commit -am "fix: polish alignment after the final checker pass"
```

Skip this commit if the pass found nothing.
