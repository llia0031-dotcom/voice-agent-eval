// The recordings: play and pause, the playhead on the timeline, the transcript line being heard.
// Tabs, the title, rising blocks and counting numbers come from kit.js. The page reads fully without this file.
(() => {
  const root = document.documentElement;
  root.classList.add('js');
  const body = document.body;
  const pauseLabel = body.dataset.pause || 'Pause';
  const errorText = body.dataset.loadError || '';
  const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const players = [];

  document.querySelectorAll('[data-player]').forEach((box) => {
    const key = box.dataset.player;
    const audio = box.querySelector('audio');
    const btn = box.querySelector('[data-play]');
    if (!audio || !btn) return;
    audio.removeAttribute('controls');
    const time = box.querySelector('[data-time]');
    const status = box.querySelector('[data-status]') || time;
    const fig = document.querySelector(`[data-clip="${key}"]`);
    const head = fig ? fig.querySelector('.playhead') : null;
    const dur = head ? parseFloat(head.dataset.dur) : 0;
    let lines = [];
    if (fig) {
      const next = fig.nextElementSibling;
      if (next && next.classList.contains('lines')) lines = [...next.querySelectorAll('li')];
    }
    const label = btn.textContent;
    const p = { audio };
    players.push(p);

    const paint = () => {
      const t = audio.currentTime;
      if (time) time.textContent = fmt(t);
      if (head && dur) {
        const x = (1000 * Math.min(t, dur)) / dur;
        head.setAttribute('x1', x.toFixed(1));
        head.setAttribute('x2', x.toFixed(1));
      }
      let now = null;
      for (const li of lines) if (parseFloat(li.dataset.t) <= t) now = li;
      lines.forEach((li) => li.classList.toggle('is-now', li === now && !audio.paused));
    };
    const reset = () => {
      btn.textContent = label;
      btn.setAttribute('aria-pressed', 'false');
      btn.removeAttribute('data-state');
      if (fig) fig.classList.remove('is-playing');
      lines.forEach((li) => li.classList.remove('is-now'));
    };
    btn.setAttribute('aria-pressed', 'false');
    btn.addEventListener('click', () => {
      if (audio.paused) {
        players.forEach((o) => { if (o !== p && !o.audio.paused) o.audio.pause(); });
        btn.dataset.state = 'loading';
        const go = audio.play();
        if (go && go.catch) go.catch(() => reset());
      } else {
        audio.pause();
      }
    });
    audio.addEventListener('playing', () => {
      btn.removeAttribute('data-state');
      btn.textContent = pauseLabel;
      btn.setAttribute('aria-pressed', 'true');
      if (fig) fig.classList.add('is-playing');
    });
    audio.addEventListener('pause', reset);
    audio.addEventListener('ended', () => { reset(); audio.currentTime = 0; paint(); });
    audio.addEventListener('timeupdate', paint);
    audio.addEventListener('error', () => {
      reset();
      btn.disabled = true;
      if (status && errorText) status.textContent = errorText;
    });
  });

  // switching to another moment stops whatever is playing
  document.querySelectorAll('[role="tab"]').forEach((t) => t.addEventListener('click', () => {
    players.forEach((o) => { if (!o.audio.paused) o.audio.pause(); });
  }));
})();
