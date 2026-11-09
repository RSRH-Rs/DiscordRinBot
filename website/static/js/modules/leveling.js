/* Leveling: master switch, where level-up notices go, level rewards and the leaderboard. */
window.LevelRewards = (() => {
    const MAX_LEVEL = 999;
    const nextLevel = levels => levels.length ? Math.min(Math.max(...levels) + 5, MAX_LEVEL) : 5;
    const warningKey = (roleId, blocked) => blocked[roleId] ? 'leveling.warn.' + blocked[roleId] : null;
    function validLevel(text) {
        const level = Number(text);
        return text !== '' && Number.isInteger(level) && level >= 1 && level <= MAX_LEVEL;
    }
    // A deleted channel or role cannot block switching the feature off: its row can no longer be edited then.
    function problems({enabled, mode, channel, channelLost, rows}) {
        const found = [], levels = new Set(), roles = new Set();
        if (mode === 'channel' && channel === '0' && (enabled || !channelLost)) found.push({index: 'channel', key: 'leveling.error.need_channel'});
        rows.forEach(({level, role, lost}, index) => {
            if (role === '0' && !lost) found.push({index, key: 'leveling.error.need_role'});
            else if (role === '0' && enabled) found.push({index, key: 'leveling.warn.deleted'});
            else if (role !== '0' && roles.has(role)) found.push({index, key: 'leveling.error.duplicate_role'});
            roles.add(role);
            if (!validLevel(level)) found.push({index, key: 'leveling.error.level_range'});
            else if (levels.has(Number(level))) found.push({index, key: 'leveling.error.duplicate_level'});
            levels.add(Number(level));
        });
        return found;
    }
    return {nextLevel, warningKey, problems};
})();

(() => {
    const {tr, escapeHtml} = Console;
    const R = window.LevelRewards;
    const MEDALS = ['🥇', '🥈', '🥉'];
    const MAX_REWARDS = 20;
    const el = id => document.getElementById(id);
    let loaded = false, rows = [], roleList = [], blocked = {}, channelLost = '', showErrors = false, saved = null;
    let pointerDown = false, pendingSort = false;

    const isEnabled = () => !!el('lv-enabled').checked;
    function levelOf(row) {
        const level = Number(row.level.value);
        return row.level.value !== '' && Number.isFinite(level) ? level : Infinity;
    }
    const formState = () => ({
        enabled: isEnabled(), mode: el('lv-mode').value, channel: el('lv-channel').value, channelLost: !!channelLost,
        rows: rows.map(row => ({level: row.level.value, role: row.select.value, lost: !!row.lost})),
    });

    function renderNotes() {
        const issues = showErrors ? R.problems(formState()) : [];
        rows.forEach((row, index) => {
            const issue = issues.find(found => found.index === index);
            const key = issue?.key || (row.lost ? 'leveling.warn.deleted' : R.warningKey(row.select.value, blocked));
            row.note.hidden = !key;
            row.note.textContent = key ? tr(key) : '';
            row.note.classList.toggle('lv-note--bad', !!issue || !!row.lost);
        });
        const channelIssue = issues.find(found => found.index === 'channel');
        el('lv-channel-error').hidden = !channelIssue;
        el('lv-channel-error').textContent = channelIssue ? tr(channelIssue.key) : '';
    }
    // The draft keys fields by name; without one every row would share a key and the tab would always look unsaved.
    function renumber() {
        rows.forEach((row, index) => { row.level.name = `lv-level-${index}`; row.select.name = `lv-role-${index}`; });
    }
    function syncChrome() {
        const full = rows.length >= MAX_REWARDS;
        el('lv-add').disabled = !isEnabled() || full;
        el('lv-limit').hidden = !full;
        el('lv-empty').hidden = rows.length > 0;
    }
    function syncChannelRow() { el('lv-channel-row').hidden = el('lv-mode').value !== 'channel'; }
    function paintDot(row) {
        const color = roleList.find(role => String(role.id) === row.select.value)?.color;
        row.dot.style.background = color ? '#' + color.toString(16).padStart(6, '0') : '';
    }
    function changed() {
        renumber(); syncChrome(); renderNotes();
        DashboardUI.changed('pg-leveling');
    }

    function sortRows() {
        const next = [...rows].sort((a, b) => levelOf(a) - levelOf(b));
        if (next.every((row, index) => row === rows[index])) return;
        const focused = document.activeElement, list = el('lv-rewards');
        rows = next;
        rows.forEach(row => list.append(row.node));
        if (focused?.isConnected && document.activeElement !== focused) focused.focus({preventScroll: true});
        changed();
    }
    // Moving rows between press and release would land the click on the wrong row, so a press holds the sort back.
    // On touch the press has already ended when focus moves, so a blur towards another row waits for that tap to land.
    function queueSort(event) {
        if (pointerDown) pendingSort = true;
        else if (el('lv-rewards').contains(event?.relatedTarget)) setTimeout(sortRows, 0);
        else sortRows();
    }
    function releasePointer() {
        pointerDown = false;
        if (pendingSort) { pendingSort = false; setTimeout(sortRows, 0); }
    }
    document.addEventListener('pointerdown', () => { pointerDown = true; }, true);
    document.addEventListener('pointerup', releasePointer, true);
    document.addEventListener('pointercancel', releasePointer, true);

    function removeRow(row) {
        const index = rows.indexOf(row);
        rows.splice(index, 1);
        row.node.remove();
        changed();
        (rows[index] || rows[index - 1])?.remove.focus({preventScroll: true});
        if (!rows.length) el('lv-add').focus({preventScroll: true});
    }
    function addRow(level, roleId, lost) {
        const node = document.createElement('div'); node.className = 'lv-reward';
        const field = document.createElement('span'); field.className = 'num-field';
        const input = document.createElement('input');
        input.className = 'num lv-level'; input.type = 'number'; input.inputMode = 'numeric'; input.min = '1'; input.max = '999'; input.value = String(level);
        input.setAttribute('aria-label', tr('leveling.level_label'));
        const unit = document.createElement('span'); unit.className = 'num-unit'; unit.textContent = tr('leveling.level_unit');
        field.append(input, unit);
        const dot = document.createElement('span'); dot.className = 'lv-dot'; dot.setAttribute('aria-hidden', 'true');
        const select = document.createElement('select');
        select.className = 'select lv-role'; select.dataset.search = tr('leveling.role_label'); select.setAttribute('aria-label', tr('leveling.role_label'));
        Console.roleOptions(select, roleList, roleId, 'leveling.pick_role');
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'btn btn--icon'; remove.setAttribute('aria-label', tr('leveling.remove'));
        remove.innerHTML = '<svg class="icon" width="16" height="16" aria-hidden="true"><use href="/static/icons.svg#i-x"/></svg>';
        const note = document.createElement('div'); note.className = 'lv-note'; note.hidden = true;
        node.append(field, dot, select, remove, note);
        el('lv-rewards').append(node);
        const row = {node, level: input, dot, select, remove, note, lost};
        input.addEventListener('input', renderNotes);
        input.addEventListener('blur', queueSort);
        select.addEventListener('change', () => { row.lost = ''; paintDot(row); renderNotes(); });
        remove.addEventListener('click', () => removeRow(row));
        rows.push(row);
        paintDot(row);
        window.DashboardExtras?.enhanceSelects(node);
        return row;
    }

    el('lv-add')?.addEventListener('click', () => {
        if (rows.length >= MAX_REWARDS) return;
        const row = addRow(R.nextLevel(rows.map(levelOf).filter(Number.isFinite)), '0', '');
        changed();
        row.level.focus({preventScroll: true});
    });
    el('lv-enabled')?.addEventListener('change', () => { syncChrome(); renderNotes(); });
    el('lv-mode')?.addEventListener('change', () => { syncChannelRow(); renderNotes(); });
    el('lv-channel')?.addEventListener('change', renderNotes);

    function renderBoard(list) {
        const box = el('lb-list');
        if (!list?.length) {
            box.innerHTML = `<div class="empty"><img src="/static/images/rin/confused-480.webp" alt="" width="96" height="96" loading="lazy"><p>${escapeHtml(tr('leveling.empty'))}</p></div>`;
        } else {
            box.innerHTML = list.map((u, i) => `<div class="lb-row${i < 3 ? ' lb-row--top' : ''}"><span class="lb-rank">${MEDALS[i] || '#' + (i + 1)}</span><span class="lb-name" title="${escapeHtml(u.username)}">${escapeHtml(u.username)}</span><span class="lb-stat">Lv.${escapeHtml(u.level)} · ${escapeHtml(Number(u.xp).toLocaleString())} XP</span></div>`).join('');
        }
    }
    function renderSettings(cfg, channels, roles) {
        // null means Discord could not be read, and /roles answers an empty list then: nothing can be called deleted.
        const down = cfg.can_manage_roles === null, channelId = String(cfg.notify_channel);
        const channelsUnread = down || !channels, rolesUnread = down || !roles.length;
        const known = (list, id) => list.some(item => String(item.id) === String(id));
        const channelList = channels || [], missing = channelId !== '0' && !known(channelList, channelId);
        blocked = cfg.blocked_roles || {};
        channelLost = missing && !channelsUnread ? channelId : '';
        roleList = roles;
        if (rolesUnread) roleList = [...roles, ...cfg.rewards.filter(r => !known(roles, r.role_id)).map(r => ({id: r.role_id, name: tr('leveling.unknown_role'), color: 0}))];
        el('lv-no-permission').hidden = cfg.can_manage_roles !== false;
        el('lv-enabled').checked = cfg.enabled;
        el('lv-mode').value = cfg.notify_mode;
        Console.channelOptions(el('lv-channel'), missing && channelsUnread ? [...channelList, {id: channelId, name: tr('leveling.unknown_channel')}] : channelList, channelId);
        el('lv-rewards').replaceChildren();
        rows = [];
        showErrors = false;
        cfg.rewards.forEach(r => addRow(r.level, r.role_id, known(roleList, r.role_id) ? '' : r.role_id));
        syncChannelRow(); renumber(); syncChrome(); renderNotes();
    }
    function showFirstProblem(issue) {
        if (el('panel-leveling-settings').hidden) Console.go('leveling', 'settings');
        (issue.index === 'channel' ? el('lv-channel-row') : rows[issue.index].node).scrollIntoView({block: 'center'});
    }

    Console.module({
        slug: 'leveling',
        isLoaded: () => loaded,
        async load() {
            const [channels, roles, cfg, board] = await Promise.all([Console.channels().catch(() => null), Console.roles().catch(() => []), Console.api('/leveling'), Console.api('/leaderboard')]);
            saved = {cfg, channels, roles};
            renderBoard(board);
            renderSettings(cfg, channels, roles);
            loaded = true;
        },
        reset() {
            renderSettings(saved.cfg, saved.channels, saved.roles);
            Console.dependencies(el('pg-leveling'));
            window.DashboardExtras?.refreshSelects?.();
        },
        async save() {
            sortRows();
            const issues = R.problems(formState());
            if (issues.length) {
                showErrors = true;
                renderNotes();
                showFirstProblem(issues[0]);
                throw new Error(tr('leveling.error.fix_first'));
            }
            const mode = el('lv-mode').value, channel = el('lv-channel').value;
            const body = {
                enabled: isEnabled(), notify_mode: mode,
                notify_channel: mode !== 'channel' ? '0' : channel !== '0' ? channel : channelLost || '0',
                rewards: rows.map(row => ({level: Number(row.level.value), role_id: row.select.value !== '0' ? row.select.value : row.lost})),
            };
            await Console.api('/leveling', 'POST', body);
            saved.cfg = {...saved.cfg, ...body};
            showErrors = false;
            renderNotes();
        },
    });
})();
