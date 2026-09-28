/* ChefMate voice AI sous-chef — mic button + floating chat panel.
   Uses the browser's Web Speech API (recognition + synthesis). Works best in
   Chrome / Edge; typed input always available as fallback. */
(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const panel = document.getElementById('voicePanel');
  if (!panel) return;
  const log = document.getElementById('vLog');
  const msgBox = document.getElementById('vMsg');
  const micBtn = document.getElementById('vMic');
  const fab = document.getElementById('vFab');
  const closeBtn = document.getElementById('vClose');
  const speakBtn = document.getElementById('vSpeak');
  const status = document.getElementById('vStatus');
  let history = [];
  let speakOn = true;

  function esc(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
  function bubble(cls, text) {
    const d = document.createElement('div');
    d.className = 'bubble ' + cls;
    d.innerHTML = esc(text);
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }
  function setStatus(t, listening) {
    status.textContent = t;
    fab.classList.toggle('listening', !!listening);
    fab.textContent = listening ? '⏺' : '🎤';
  }

  /* ---------- speech synthesis (reply spoken aloud) ---------- */
  function speak(text) {
    if (!speakOn || !('speechSynthesis' in window)) return;
    speechSynthesis.cancel();
    // speak a short version — full text stays in the bubble
    let short = text.replace(/[*#`]/g, '').replace(/\s+/g, ' ').trim();
    if (short.length > 320) short = short.slice(0, 320).replace(/[^.!?]*$/, '') + ' … you can read the full answer on screen.';
    const u = new SpeechSynthesisUtterance(short);
    const voices = speechSynthesis.getVoices();
    const v = voices.find(v => v.lang === 'en-IN') || voices.find(v => v.lang.startsWith('en'));
    if (v) u.voice = v;
    u.lang = v ? v.lang : 'en-IN';
    u.rate = 1.0;
    speechSynthesis.speak(u);
  }
  speakBtn.addEventListener('click', () => {
    speakOn = !speakOn;
    speakBtn.style.opacity = speakOn ? 1 : .4;
    speakBtn.title = speakOn ? 'Voice replies ON' : 'Voice replies OFF';
    if (!speakOn) speechSynthesis.cancel();
  });

  /* ---------- ask the server ---------- */
  function ask(text) {
    text = (text || '').trim();
    if (!text) return;
    openPanel();
    bubble('user', text);
    history.push({ role: 'user', text });
    msgBox.value = '';
    const typing = bubble('bot typing', '');
    typing.innerHTML = '<i></i><i></i><i></i>';
    fetch('/api/assistant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: history.slice(-8) })
    }).then(r => r.json()).then(d => {
      typing.remove();
      const reply = d.ok ? d.reply : 'Something went wrong — please try again.';
      bubble('bot', reply);
      history.push({ role: 'assistant', text: reply });
      speak(reply);
    }).catch(() => { typing.remove(); bubble('bot', 'Network error — please try again.'); });
  }

  /* ---------- speech recognition (voice to text) ---------- */
  let rec = null, listening = false;
  if (SR) {
    rec = new SR();
    rec.lang = 'en-IN';
    rec.interimResults = true;
    rec.continuous = false;
    rec.onstart = () => { listening = true; setStatus('Listening… speak now', true); };
    rec.onerror = (e) => { listening = false; setStatus(e.error === 'not-allowed' ? 'Microphone blocked — check browser permissions' : 'Mic error — try again or type below', false); };
    rec.onend = () => { listening = false; setStatus('Tap the mic to speak again', false); };
    rec.onresult = (e) => {
      let interim = '', final = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) final += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      if (interim) { openPanel(); status.textContent = '“' + interim + '”'; }
      if (final) { ask(final); }
    };
  } else {
    micBtn.style.display = 'none';
    setStatus('Voice not supported in this browser — type below', false);
  }

  micBtn.addEventListener('click', () => {
    if (!rec) return;
    if (listening) { rec.stop(); return; }
    try { rec.start(); } catch (e) { /* already started */ }
  });

  /* ---------- panel behaviour ---------- */
  function openPanel() { panel.classList.add('open'); msgBox.focus(); }
  fab.addEventListener('click', () => {
    if (panel.classList.contains('open')) { panel.classList.remove('open'); speechSynthesis.cancel(); if (rec && listening) rec.stop(); }
    else { openPanel(); if (rec) try { rec.start(); } catch (e) {} }
  });
  closeBtn.addEventListener('click', () => { panel.classList.remove('open'); speechSynthesis.cancel(); if (rec && listening) rec.stop(); });
  document.getElementById('vSend').addEventListener('click', () => ask(msgBox.value));
  msgBox.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(msgBox.value); } });
})();
