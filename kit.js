// The light behaviour that goes with kit.css. No dependencies; load it as a module at the end of the page:
//   <script type="module" src="kit.js"></script>
// It does three things when the system does not ask for less motion: blocks rise in as they come on screen,
// a marked title arrives piece by piece, and marked numbers count up to their value. It also runs the tabs.
const root = document.documentElement
const motion = !matchMedia('(prefers-reduced-motion: reduce)').matches
if (motion) root.classList.add('k-motion')

// ---- titles: a Chinese character is a piece, a Latin word is a piece; a screen reader gets the title whole
document.querySelectorAll('[data-k-title]').forEach((h) => {
  const text = h.textContent.trim()
  if (!text) return
  h.setAttribute('aria-label', text)
  const box = document.createElement('span'); box.setAttribute('aria-hidden', 'true')
  let c = 0
  for (const u of text.match(/[A-Za-z0-9’'-]+[,.;:?!]*|\s+|[^\sA-Za-z0-9’'-][，。？！、；：）》”’?!,.;:]*/g) || []) {
    if (/^\s+$/.test(u)) { box.append(' '); continue }
    const s = document.createElement('span'); s.className = 'k-ch'; s.style.setProperty('--c', c++); s.textContent = u; box.append(s)
  }
  h.replaceChildren(box)
})

// ---- numbers: every figure in the text counts from 0 to its value, keeping its decimals; the rest stays put
function count(el) {
  const final = el.textContent
  const parts = final.split(/(\d+(?:\.\d+)?)/)
  const t0 = performance.now(), dur = 900
  const step = (now) => {
    const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3)
    el.textContent = parts.map((p, i) => (i % 2 ? (Number(p) * e).toFixed((p.split('.')[1] || '').length) : p)).join('')
    if (k < 1) requestAnimationFrame(step); else el.textContent = final
  }
  requestAnimationFrame(step)
}

// ---- things arrive when they come on screen (once)
const marked = [...document.querySelectorAll('[data-k-rise], [data-k-title], [data-k-count]')]
if (!motion) marked.forEach((el) => el.classList.add('k-in'))
else {
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (!e.isIntersecting) return
    io.unobserve(e.target); e.target.classList.add('k-in')
    if (e.target.hasAttribute('data-k-count')) count(e.target)
  }), { rootMargin: '0px 0px -8% 0px', threshold: 0.08 })
  marked.forEach((el) => io.observe(el))
}

// ---- tabs: <div data-k-tabs> holds a [role=tablist] of buttons (aria-controls = a panel's id) and the panels
document.querySelectorAll('[data-k-tabs]').forEach((box) => {
  const tabs = [...box.querySelectorAll('[role="tab"]')], panels = tabs.map((t) => document.getElementById(t.getAttribute('aria-controls')))
  if (!tabs.length) return
  let cur = 0
  const show = (i, focus) => {
    cur = (i + tabs.length) % tabs.length
    tabs.forEach((t, k) => { t.setAttribute('aria-selected', String(k === cur)); t.tabIndex = k === cur ? 0 : -1 })
    panels.forEach((p, k) => { if (p) p.hidden = k !== cur })
    if (focus) tabs[cur].focus()
  }
  tabs.forEach((t, i) => t.addEventListener('click', () => show(i)))
  box.querySelector('[role="tablist"]').addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); show(cur + 1, true) }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); show(cur - 1, true) }
    else if (e.key === 'Home') { e.preventDefault(); show(0, true) }
    else if (e.key === 'End') { e.preventDefault(); show(tabs.length - 1, true) }
  })
  show(0)
})
