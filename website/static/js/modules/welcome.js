/* Welcome page: channel, message, optional look, farewell, auto roles and custom images. */
const WELCOME_IMAGE_MAX_BYTES = 5 * 1024 * 1024;
const WELCOME_IMAGE_MAX_DIMENSION = 4096;
const WELCOME_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp']);

function welcomeImageFileError(file) {
    if (!file) return '请先选择一张图片';
    if (!WELCOME_IMAGE_TYPES.has(file.type)) return '仅支持 PNG、JPG、GIF 或 WebP 图片';
    if (file.size > WELCOME_IMAGE_MAX_BYTES) return '图片不能超过 5 MB';
    return '';
}

function welcomeImageDimensions(file) {
    return new Promise(resolve => {
        const url = URL.createObjectURL(file);
        const image = new Image();
        image.onload = () => { const result = {width: image.naturalWidth, height: image.naturalHeight}; URL.revokeObjectURL(url); resolve(result); };
        image.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
        image.src = url;
    });
}

async function validateWelcomeImageFile(file) {
    const basicError = welcomeImageFileError(file);
    if (basicError) return basicError;
    const dimensions = await welcomeImageDimensions(file);
    if (!dimensions) return '图片文件损坏或无法读取';
    if (dimensions.width > WELCOME_IMAGE_MAX_DIMENSION || dimensions.height > WELCOME_IMAGE_MAX_DIMENSION) return '图片尺寸不能超过 4096×4096';
    return '';
}
/* ── end validation ── */

(() => {
    const {tr} = Console;
    const el = id => document.getElementById(id);
    const images = {welcome: {uploaded: false, objectUrl: ''}, farewell: {uploaded: false, objectUrl: ''}};
    window.WelcomeImageUploads = {has: kind => !!images[kind]?.uploaded};
    const imageUrl = kind => `/api/guild/${window.GID}/welcome/image/${kind}?v=${Date.now()}`;
    const TEXT_FIELDS = {'w-msg': 'welcome_msg', 'w-fmsg': 'farewell_msg', 'w-title': 'welcome_title', 'w-thumb': 'thumbnail_url', 'w-image': 'image_url'};

    function setImageState(kind, uploaded, previewUrl = '', status = '') {
        const state = images[kind];
        if (state.objectUrl && state.objectUrl !== previewUrl) URL.revokeObjectURL(state.objectUrl);
        state.objectUrl = previewUrl.startsWith('blob:') ? previewUrl : '';
        state.uploaded = !!uploaded;
        const image = el(`w-${kind}-image-preview`);
        image.hidden = !previewUrl;
        if (previewUrl) image.src = previewUrl; else image.removeAttribute('src');
        el(`w-${kind}-clear`).hidden = !uploaded;
        el(`w-${kind}-image-state`).textContent = status || tr(uploaded ? 'welcome.image.uploaded' : 'welcome.image.none');
        window.DashboardPreview?.refresh();
    }
    async function preview(kind, input) {
        const file = input.files?.[0];
        const error = await validateWelcomeImageFile(file);
        if (error) {
            input.value = '';
            Console.toast(error, 'bad');
            const current = images[kind].uploaded;
            setImageState(kind, current, current ? imageUrl(kind) : '');
            return;
        }
        setImageState(kind, images[kind].uploaded, URL.createObjectURL(file), tr('welcome.image.picked', {name: file.name}));
    }
    async function upload(kind) {
        const input = el(`w-${kind}-file`), button = el(`w-${kind}-upload`), file = input.files?.[0];
        const error = await validateWelcomeImageFile(file);
        if (error) { Console.toast(error, 'bad'); return; }
        await Console.busy(button, async () => {
            try {
                const form = new FormData(); form.append('image', file);
                const response = await fetch(`/api/guild/${window.GID}/welcome/image/${kind}`, {method: 'POST', body: form});
                const result = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(result.error || tr('common.request_failed', {status: response.status}));
                input.value = '';
                setImageState(kind, true, `${result.image_url}?v=${Date.now()}`);
                Console.toast(tr('welcome.image.upload_done'), 'ok');
            } catch (e) {
                Console.toast(tr('welcome.image.upload_failed', {reason: e.message}), 'bad');
        }
        });
    }
    async function clear(kind) {
        if (!window.confirm(tr('welcome.image.clear_confirm'))) return;
        const button = el(`w-${kind}-clear`);
        await Console.busy(button, async () => {
            try {
                const response = await fetch(`/api/guild/${window.GID}/welcome/image/${kind}`, {method: 'DELETE'});
                const result = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(result.error || tr('common.request_failed', {status: response.status}));
                el(`w-${kind}-file`).value = '';
                setImageState(kind, false);
                Console.toast(tr('welcome.image.cleared'), 'ok');
            } catch (e) { Console.toast(tr('welcome.image.clear_failed', {reason: e.message}), 'bad'); }
        });
    }
    function renderRoles(roles, selected) {
        const box = el('w-roles');
        box.replaceChildren(...roles.map(role => {
            const label = document.createElement('label'); label.className = 'check-chip';
            const input = document.createElement('input'); input.type = 'checkbox'; input.value = role.id; input.id = 'w-role-' + role.id;
            input.checked = selected.includes(String(role.id));
            label.append(input, document.createTextNode(role.name));
            return label;
        }));
    }

    Console.module({
        slug: 'welcome',
        async load() {
            const [cfg, channels, roles] = await Promise.all([Console.api('/welcome'), Console.channels(), Console.roles()]);
            Console.channelOptions(el('w-ch'), channels, cfg.welcome_channel);
            Console.channelOptions(el('w-fch'), channels, cfg.farewell_channel, 'welcome.farewell_off');
            for (const [id, key] of Object.entries(TEXT_FIELDS)) el(id).value = cfg[key] || '';
            el('w-card').checked = !!cfg.show_card;
            el('w-enabled').checked = cfg.enabled !== 0;
            for (const kind of ['welcome', 'farewell']) {
                const uploaded = !!cfg[`has_${kind}_image`];
                setImageState(kind, uploaded, uploaded ? imageUrl(kind) : '');
            }
            renderRoles(roles, cfg.auto_roles ? String(cfg.auto_roles).split(',').filter(Boolean) : []);
        },
        async save() {
            const payload = {
                welcome_channel: el('w-ch').value,
                farewell_channel: el('w-fch').value,
                auto_roles: [...document.querySelectorAll('#w-roles input:checked')].map(i => i.value).join(','),
                show_card: el('w-card').checked,
                enabled: el('w-enabled').checked,
            };
            for (const [id, key] of Object.entries(TEXT_FIELDS)) payload[key] = el(id).value;
            await Console.api('/welcome', 'POST', payload);
        },
    });

    document.addEventListener('DOMContentLoaded', () => {
        if (!el('pg-welcome')) return;
        for (const kind of ['welcome', 'farewell']) {
            el(`w-${kind}-file`).addEventListener('change', e => preview(kind, e.target));
            el(`w-${kind}-upload`).addEventListener('click', () => upload(kind));
            el(`w-${kind}-clear`).addEventListener('click', () => clear(kind));
        }
        const search = el('w-roles-search'), result = el('w-roles-result');
        search.addEventListener('input', () => {
            let count = 0;
            el('w-roles').querySelectorAll('.check-chip').forEach(label => { label.hidden = !DashboardExtras.matches(label.textContent, search.value); if (!label.hidden) count++; });
            result.textContent = search.value ? tr('welcome.roles_found', {n: count}) : '';
        });
    });
})();
