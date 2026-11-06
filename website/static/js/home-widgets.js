/* 首页英雄区的两个小组件。
   大厅聊天：首屏那段放完后接着轮播几段剧情（模板里的 <template data-scene>）；
   暂停按钮、滚出屏幕、切走标签页都会让它停下，系统要求减少动效时保持静止。
   戳一下小凛：点贴纸她换个表情晃一下，旁边的气泡逐字说一句话；连戳会生气。
   没有 JS 时英雄区就是原来那段静态聊天。 */
window.RinHome = (() => {
    const GAP = 1500;          // 普通消息之后停多久
    const RIN_GAP = 2600;      // 小凛的消息多给点时间读
    const TYPING = 1200;       // “正在输入…”亮多久
    const BEFORE_DELETE = 1600;
    const AFTER_DELETE = 900;
    const SCENE_GAP = 3200;
    const FIRST_SCENE = 2600;  // 首屏消息的入场动画（见 index.html）大约这么长
    const RAPID_WINDOW = 4000;
    const RAPID_COUNT = 5;

    /* 随机挑一句，不和上一句重复 */
    function nextLine(count, last, rng = Math.random) {
        if (count <= 1) return 0;
        if (last < 0 || last >= count) return Math.floor(rng() * count);
        const i = Math.floor(rng() * (count - 1));
        return i >= last ? i + 1 : i;
    }

    /* 4 秒内戳了 5 下 */
    function isRapid(times, now) {
        return times.filter(t => now - t < RAPID_WINDOW).length >= RAPID_COUNT;
    }

    /* 一段剧情的节奏：小凛说话前先“正在输入…”，广告先出现再被删 */
    function beats(messages) {
        const plan = [];
        messages.forEach((m, index) => {
            if (m.rin) plan.push({kind: 'typing', ms: TYPING});
            plan.push({kind: 'show', index});
            if (m.deleted) {
                plan.push({kind: 'wait', ms: BEFORE_DELETE}, {kind: 'delete', index}, {kind: 'wait', ms: AFTER_DELETE});
            } else {
                plan.push({kind: 'wait', ms: m.rin ? RIN_GAP : GAP});
            }
        });
        return plan;
    }

    /* 可暂停的计时：只在没有任何暂停理由时走时间 */
    class Clock {
        constructor(now, schedule, onChange) {
            this.now = now;
            this.schedule = schedule;
            this.onChange = onChange || (() => {});
            this.reasons = new Set();
        }

        get paused() {
            return this.reasons.size > 0;
        }

        pause(reason) {
            this.reasons.add(reason);
            this.onChange(this.paused);
        }

        resume(reason) {
            this.reasons.delete(reason);
            this.onChange(this.paused);
        }

        wait(ms) {
            return new Promise(resolve => {
                let left = ms;
                let last = this.now();
                const tick = () => {
                    const now = this.now();
                    if (!this.paused) left -= now - last;
                    last = now;
                    if (left <= 0) resolve();
                    else this.schedule(tick, 100);
                };
                this.schedule(tick, 100);
            });
        }
    }

    function startChat(chat, reduce) {
        const body = chat.querySelector('.chat-body');
        const typing = chat.querySelector('.typing');
        const button = chat.querySelector('.chat-pause');
        const templates = [...chat.querySelectorAll('template[data-scene]')];
        if (reduce || !body || !typing || !button || !templates.length) return;

        // 首屏那段也放进轮播，作为第 0 段
        const first = document.createElement('template');
        [...body.children].forEach(m => first.content.appendChild(m.cloneNode(true)));
        const scenes = [first, ...templates];

        const clock = new Clock(() => performance.now(), (fn, ms) => setTimeout(fn, ms),
            paused => chat.classList.toggle('is-paused', paused));
        chat.classList.add('has-loop');

        // 聊天框高度固定成首屏那段的高度，新消息从底下进来，旧的从顶上出去
        function measure() {
            const probe = body.cloneNode(false);
            probe.style.cssText = 'position:absolute;left:0;right:0;top:0;height:auto;visibility:hidden';
            probe.appendChild(first.content.cloneNode(true));
            chat.appendChild(probe);
            const h = probe.offsetHeight;
            probe.remove();
            return h;
        }
        const lock = () => { body.style.height = measure() + 'px'; };
        lock();
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(lock);  // 网页字体加载完行高会变
        let resizeTimer = 0;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(lock, 150);
        });

        button.addEventListener('click', () => {
            const on = button.getAttribute('aria-pressed') !== 'true';
            button.setAttribute('aria-pressed', String(on));
            if (on) clock.pause('button'); else clock.resume('button');
        });
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) clock.pause('hidden'); else clock.resume('hidden');
        });
        if ('IntersectionObserver' in window) {
            new IntersectionObserver(entries => {
                entries.forEach(e => { if (e.isIntersecting) clock.resume('offscreen'); else clock.pause('offscreen'); });
            }).observe(chat);
        }

        // 完全滚出顶部的消息删掉，DOM 里只留看得见的
        function prune() {
            const top = body.getBoundingClientRect().top;
            let m = body.firstElementChild;
            while (m && m.nextElementSibling && m.getBoundingClientRect().bottom <= top) {
                m.remove();
                m = body.firstElementChild;
            }
        }

        async function play(scene) {
            const messages = [...scene.content.children].map(n => n.cloneNode(true));
            const plan = beats(messages.map(m => ({
                rin: !!m.querySelector('.nm.rin'),
                deleted: m.hasAttribute('data-deleted'),
            })));
            for (const b of plan) {
                if (b.kind === 'wait') {
                    await clock.wait(b.ms);
                } else if (b.kind === 'typing') {
                    typing.classList.add('on');
                    await clock.wait(b.ms);
                    typing.classList.remove('on');
                } else if (b.kind === 'show') {
                    messages[b.index].classList.add('live');
                    body.appendChild(messages[b.index]);
                    prune();
                } else if (b.kind === 'delete') {
                    messages[b.index].classList.add('deleting');
                    await clock.wait(700);
                    messages[b.index].remove();
                }
            }
        }

        (async () => {
            await clock.wait(FIRST_SCENE);
            chat.classList.add('is-live');  // 首屏入场放完了，之后的消息各自入场
            await clock.wait(SCENE_GAP);
            for (let s = 1; ; s = (s + 1) % scenes.length) {
                await play(scenes[s]);
                await clock.wait(SCENE_GAP);
            }
        })();
    }

    function startPoke(button, reduce) {
        const img = button.querySelector('img[data-poke-srcset]');
        const bubble = button.parentNode.querySelector('.rin-say');
        const lines = document.getElementById('rin-lines');
        if (!img || !bubble || !lines) return;
        const shown = bubble.querySelector('.say-shown');
        const spoken = bubble.querySelector('.say-sr');
        const plain = [...lines.content.querySelectorAll('p[data-line]:not([data-line="angry"])')];
        const angry = lines.content.querySelector('p[data-line="angry"]');
        const normal = img.getAttribute('srcset');
        const poked = img.getAttribute('data-poke-srcset');
        const preload = new Image();
        preload.sizes = img.sizes;
        preload.srcset = poked;

        let last = -1;
        let times = [];
        let job = 0;
        let faceTimer = 0;
        let hideTimer = 0;

        function hide() {
            bubble.classList.remove('on');
        }

        function say(line) {
            const mine = ++job;
            clearTimeout(hideTimer);
            const copy = () => [...line.childNodes].map(n => n.cloneNode(true));
            spoken.replaceChildren(...copy());
            shown.replaceChildren(...copy());
            bubble.classList.add('on');
            if (reduce) {
                hideTimer = setTimeout(hide, 5000);
                return;
            }
            // 中英两份一起逐字打，切语言时也是打到一半的样子
            const spans = [...shown.querySelectorAll('[data-l]')];
            const chars = spans.map(s => [...s.textContent]);
            spans.forEach(s => { s.textContent = ''; });
            const total = Math.max(...chars.map(c => c.length));
            let i = 0;
            const step = () => {
                if (mine !== job) return;
                i += 1;
                spans.forEach((s, k) => { s.textContent = chars[k].slice(0, i).join(''); });
                if (i < total) setTimeout(step, 45);
                else hideTimer = setTimeout(hide, 4200);
            };
            step();
        }

        button.addEventListener('click', () => {
            const now = performance.now();
            times = times.filter(t => now - t < RAPID_WINDOW).concat(now);
            button.classList.remove('poked');
            void button.offsetWidth;  // 重新触发晃动动画
            button.classList.add('poked');
            img.srcset = poked;
            clearTimeout(faceTimer);
            faceTimer = setTimeout(() => {
                img.srcset = normal;
                button.classList.remove('poked');
            }, 1400);
            if (angry && isRapid(times, now)) {
                times = [];
                say(angry);
            } else {
                last = nextLine(plain.length, last);
                say(plain[last]);
            }
        });
    }

    if (typeof document !== 'undefined') {
        const reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        const chat = document.querySelector('.hero-chat');
        if (chat) startChat(chat, reduce);
        const poke = document.querySelector('.stk-poke');
        if (poke) startPoke(poke, reduce);
    }

    return {nextLine, isRapid, beats, Clock};
})();
