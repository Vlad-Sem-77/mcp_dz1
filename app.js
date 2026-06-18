/* ====================================================
   AI TRAVEL AGENT — Frontend logic
   - WebSocket для real-time логов MCP/LLM
   - HTTP POST /api/chat для общения с агентом
   - Кнопка сброса /api/reset
==================================================== */

const chatMessages = document.getElementById('chatMessages');
const chatForm     = document.getElementById('chatForm');
const chatInput    = document.getElementById('chatInput');
const sendBtn      = document.getElementById('sendBtn');
const resetBtn     = document.getElementById('resetBtn');
const logsStream   = document.getElementById('logsStream');
const logCountEl   = document.getElementById('logCount');
const statusPulse  = document.querySelector('.status-pulse');
const statusText   = document.getElementById('connectionStatusText');

let logCount = 0;
let socket   = null;

/* ── WebSocket для логов ───────────────────────── */
function connectWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${protocol}://${location.host}/ws/logs`;

  socket = new WebSocket(url);

  socket.addEventListener('open', () => {
    statusPulse.classList.add('connected');
    statusText.textContent = 'логи подключены';
  });

  socket.addEventListener('close', () => {
    statusPulse.classList.remove('connected');
    statusText.textContent = 'переподключение...';
    setTimeout(connectWebSocket, 2500);
  });

  socket.addEventListener('error', () => {
    statusPulse.classList.remove('connected');
    statusText.textContent = 'ошибка соединения';
  });

  socket.addEventListener('message', (event) => {
    let data;
    try { data = JSON.parse(event.data); } catch { return; }

    if (data.type === 'connected') return; // системное сообщение

    appendLogEntry(data);
  });
}

function appendLogEntry(event) {
  const placeholder = logsStream.querySelector('.log-placeholder');
  if (placeholder) placeholder.remove();

  logCount++;
  logCountEl.textContent = logCount;

  const entry = document.createElement('div');
  entry.className = [
    'log-entry',
    `direction-${(event.direction || 'status').toLowerCase()}`,
  ].join(' ');

  const serverKey = (event.server || 'agent').toLowerCase();
  const serverClass = `log-server-${serverKey}`;

  const header = document.createElement('div');
  header.className = 'log-entry-header';
  header.innerHTML = `
    <span class="log-ts">${event.timestamp || ''}</span>
    <span class="log-server ${serverClass}">${event.server || '?'}</span>
    <span class="log-title">${escapeHtml(event.title || '')}</span>
  `;

  const payload = document.createElement('div');
  payload.className = 'log-payload';
  payload.textContent = typeof event.payload === 'string'
    ? event.payload
    : JSON.stringify(event.payload, null, 2);

  entry.appendChild(header);
  entry.appendChild(payload);

  // Разворачивать/сворачивать payload по клику
  entry.addEventListener('click', () => entry.classList.toggle('expanded'));

  logsStream.appendChild(entry);

  // Автоскролл — только если пользователь не прокрутил вверх
  const isAtBottom = logsStream.scrollHeight - logsStream.clientHeight - logsStream.scrollTop < 60;
  if (isAtBottom) logsStream.scrollTop = logsStream.scrollHeight;
}

/* ── Чат ─────────────────────────────────────────── */
function appendMessage(text, role) {
  const wrapper = document.createElement('div');
  wrapper.className = `message message-${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = text;

  wrapper.appendChild(bubble);
  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return wrapper;
}

function appendTypingIndicator() {
  const wrapper = document.createElement('div');
  wrapper.className = 'message message-agent message-typing';
  wrapper.innerHTML = `
    <div class="message-bubble">
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    </div>`;
  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return wrapper;
}

function setUIBusy(busy) {
  sendBtn.disabled = busy;
  chatInput.disabled = busy;
  resetBtn.disabled = busy;
}

chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const text = chatInput.value.trim();
  if (!text) return;

  chatInput.value = '';
  appendMessage(text, 'user');
  const typingEl = appendTypingIndicator();
  setUIBusy(true);

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });

    const data = await response.json();
    typingEl.remove();

    if (data.error) {
      appendMessage('Ошибка: ' + data.error, 'agent');
    } else {
      appendMessage(data.reply || '(нет ответа)', 'agent');
    }
  } catch (err) {
    typingEl.remove();
    appendMessage('Не удалось соединиться с сервером: ' + err.message, 'agent');
  } finally {
    setUIBusy(false);
    chatInput.focus();
  }
});

resetBtn.addEventListener('click', async () => {
  try {
    await fetch('/api/reset', { method: 'POST' });
    chatMessages.innerHTML = '';
    appendMessage('Новый диалог начат. Чем могу помочь?', 'agent');
    logsStream.innerHTML = '<div class="log-placeholder">Ожидание событий от MCP-серверов и LLM...</div>';
    logCount = 0;
    logCountEl.textContent = '0';
  } catch (err) {
    console.error('Reset error', err);
  }
});

/* ── Вспомогательные ─────────────────────────────── */
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* Enter без Shift — отправка */
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

/* Запуск */
connectWebSocket();
chatInput.focus();
