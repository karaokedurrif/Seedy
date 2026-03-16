/**
 * Seedy Chat Widget 🌱
 * 
 * Widget de chat IA para OvoSfera (hub.ovosfera.com).
 * Se conecta a seedy-api.neofarm.io via proxy en el backend Seedy
 * para ocultar la API key del frontend.
 * 
 * Uso: <script src="https://seedy-api.neofarm.io/dashboard/seedy-widget.js"></script>
 * O inyectar via Nginx Proxy Manager custom JS.
 */
(function() {
  'use strict';

  const CHAT_API = 'https://seedy-api.neofarm.io/ovosfera/chat';
  const MAX_HISTORY = 10;

  // State
  let isOpen = false;
  let messages = [];
  let isStreaming = false;

  // ── Create widget DOM ──
  function createWidget() {
    // Remove existing Seedy button if present
    document.querySelectorAll('button[title="Seedy IA"]').forEach(el => el.remove());

    // Container
    const container = document.createElement('div');
    container.id = 'seedy-widget';
    container.innerHTML = `
      <style>
        #seedy-widget { font-family: system-ui, -apple-system, sans-serif; }
        #seedy-fab {
          position: fixed; bottom: 24px; right: 24px; z-index: 9999;
          width: 56px; height: 56px; border-radius: 50%; border: none;
          background: linear-gradient(135deg, #22C55E, #10B981);
          color: #fff; font-size: 28px; cursor: pointer;
          box-shadow: 0 4px 20px rgba(34,197,94,0.35);
          display: flex; align-items: center; justify-content: center;
          transition: transform 0.2s, box-shadow 0.2s;
        }
        #seedy-fab:hover { transform: scale(1.08); box-shadow: 0 6px 28px rgba(34,197,94,0.5); }
        #seedy-fab.open { transform: rotate(45deg) scale(0.9); }

        #seedy-panel {
          position: fixed; bottom: 92px; right: 24px; z-index: 9998;
          width: 380px; max-width: calc(100vw - 48px);
          max-height: min(600px, calc(100vh - 140px));
          background: #fff; border-radius: 16px;
          box-shadow: 0 12px 48px rgba(0,0,0,0.2);
          display: flex; flex-direction: column;
          opacity: 0; transform: translateY(12px) scale(0.95);
          pointer-events: none; transition: all 0.25s ease;
          overflow: hidden;
        }
        #seedy-panel.open {
          opacity: 1; transform: translateY(0) scale(1); pointer-events: auto;
        }

        .seedy-header {
          padding: 16px 20px; display: flex; align-items: center; gap: 12px;
          background: linear-gradient(135deg, #22C55E, #10B981); color: #fff;
          flex-shrink: 0;
        }
        .seedy-header-avatar { font-size: 28px; }
        .seedy-header-info h3 { font-size: 15px; font-weight: 700; margin: 0; }
        .seedy-header-info p { font-size: 11px; opacity: 0.8; margin: 2px 0 0; }
        .seedy-close {
          margin-left: auto; background: none; border: none; color: rgba(255,255,255,0.8);
          font-size: 20px; cursor: pointer; padding: 4px 8px; border-radius: 6px;
        }
        .seedy-close:hover { background: rgba(255,255,255,0.15); color: #fff; }

        .seedy-messages {
          flex: 1; overflow-y: auto; padding: 16px; display: flex;
          flex-direction: column; gap: 12px; min-height: 200px;
          scrollbar-width: thin; scrollbar-color: #ddd transparent;
        }

        .seedy-msg {
          max-width: 85%; padding: 10px 14px; border-radius: 12px;
          font-size: 13px; line-height: 1.55; word-break: break-word;
        }
        .seedy-msg.user {
          align-self: flex-end; background: #f0fdf4; color: #15803d;
          border-bottom-right-radius: 4px;
        }
        .seedy-msg.assistant {
          align-self: flex-start; background: #f8f9fa; color: #1a1a2e;
          border-bottom-left-radius: 4px;
        }
        .seedy-msg.assistant code {
          background: #e8e8e8; padding: 1px 4px; border-radius: 3px; font-size: 12px;
        }
        .seedy-msg.system {
          align-self: center; background: transparent; color: #9ca3af;
          font-size: 12px; font-style: italic; padding: 4px;
        }

        .seedy-typing {
          align-self: flex-start; padding: 10px 14px; background: #f8f9fa;
          border-radius: 12px; display: none; gap: 4px;
        }
        .seedy-typing.active { display: flex; }
        .seedy-typing span {
          width: 6px; height: 6px; border-radius: 50%; background: #9ca3af;
          animation: seedyBounce 1.4s ease-in-out infinite;
        }
        .seedy-typing span:nth-child(2) { animation-delay: 0.2s; }
        .seedy-typing span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes seedyBounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-6px); }
        }

        .seedy-input-bar {
          display: flex; align-items: center; gap: 8px;
          padding: 12px 16px; border-top: 1px solid #eee; flex-shrink: 0;
        }
        .seedy-input {
          flex: 1; border: 1px solid #e5e7eb; border-radius: 10px;
          padding: 10px 14px; font-size: 13px; outline: none;
          transition: border-color 0.15s; resize: none; max-height: 80px;
          font-family: inherit;
        }
        .seedy-input:focus { border-color: #22C55E; }
        .seedy-send {
          width: 36px; height: 36px; border-radius: 50%; border: none;
          background: #22C55E; color: #fff; font-size: 16px; cursor: pointer;
          display: flex; align-items: center; justify-content: center;
          transition: background 0.15s;
          flex-shrink: 0;
        }
        .seedy-send:hover { background: #16a34a; }
        .seedy-send:disabled { background: #d1d5db; cursor: default; }

        .seedy-welcome {
          text-align: center; padding: 20px; color: #6b7280;
        }
        .seedy-welcome .emoji { font-size: 40px; margin-bottom: 8px; }
        .seedy-welcome h4 { font-size: 14px; color: #1f2937; margin: 8px 0 4px; }
        .seedy-welcome p { font-size: 12px; line-height: 1.5; }
        .seedy-quick-btns { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; justify-content: center; }
        .seedy-quick {
          font-size: 11px; padding: 6px 12px; border-radius: 20px;
          border: 1px solid #e5e7eb; background: #fff; color: #374151;
          cursor: pointer; transition: all 0.15s;
        }
        .seedy-quick:hover { background: #f0fdf4; border-color: #22C55E; color: #15803d; }
      </style>

      <button id="seedy-fab" title="Seedy IA">🌱</button>

      <div id="seedy-panel">
        <div class="seedy-header">
          <span class="seedy-header-avatar">🌱</span>
          <div class="seedy-header-info">
            <h3>Seedy</h3>
            <p>Asistente IA de Avicultura</p>
          </div>
          <button class="seedy-close" title="Cerrar">✕</button>
        </div>
        <div class="seedy-messages" id="seedy-messages">
          <div class="seedy-welcome">
            <div class="emoji">🐔</div>
            <h4>¡Hola! Soy Seedy</h4>
            <p>Tu asistente de avicultura inteligente.<br>Pregúntame sobre razas, nutrición, sanidad, genética...</p>
            <div class="seedy-quick-btns">
              <button class="seedy-quick" data-q="¿Cuáles son las mejores razas de capones?">🐓 Razas capones</button>
              <button class="seedy-quick" data-q="¿Qué alimentación necesitan las gallinas ponedoras?">🌾 Nutrición</button>
              <button class="seedy-quick" data-q="¿Cómo prevenir enfermedades en gallineros?">💉 Sanidad</button>
              <button class="seedy-quick" data-q="¿Cuánto tarda un capón en alcanzar peso de sacrificio?">⚖️ Engorde</button>
            </div>
          </div>
          <div class="seedy-typing" id="seedy-typing">
            <span></span><span></span><span></span>
          </div>
        </div>
        <div class="seedy-input-bar">
          <textarea class="seedy-input" id="seedy-input" placeholder="Pregunta a Seedy..." rows="1"></textarea>
          <button class="seedy-send" id="seedy-send" title="Enviar">➤</button>
        </div>
      </div>
    `;
    document.body.appendChild(container);

    // Bind events
    const fab = document.getElementById('seedy-fab');
    const panel = document.getElementById('seedy-panel');
    const closeBtn = container.querySelector('.seedy-close');
    const input = document.getElementById('seedy-input');
    const sendBtn = document.getElementById('seedy-send');

    fab.addEventListener('click', () => togglePanel());
    closeBtn.addEventListener('click', () => togglePanel(false));
    sendBtn.addEventListener('click', () => sendMessage());
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 80) + 'px';
    });

    // Quick buttons
    container.querySelectorAll('.seedy-quick').forEach(btn => {
      btn.addEventListener('click', () => {
        input.value = btn.dataset.q;
        sendMessage();
      });
    });
  }

  function togglePanel(forceState) {
    isOpen = forceState !== undefined ? forceState : !isOpen;
    document.getElementById('seedy-fab').classList.toggle('open', isOpen);
    document.getElementById('seedy-panel').classList.toggle('open', isOpen);
    if (isOpen) {
      setTimeout(() => document.getElementById('seedy-input').focus(), 300);
    }
  }

  function addMessage(role, content) {
    const msgsEl = document.getElementById('seedy-messages');
    const welcome = msgsEl.querySelector('.seedy-welcome');
    if (welcome) welcome.remove();

    const div = document.createElement('div');
    div.className = `seedy-msg ${role}`;
    div.textContent = content;
    const typing = document.getElementById('seedy-typing');
    msgsEl.insertBefore(div, typing);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    return div;
  }

  function updateLastAssistant(text) {
    const msgsEl = document.getElementById('seedy-messages');
    const msgs = msgsEl.querySelectorAll('.seedy-msg.assistant');
    if (msgs.length > 0) {
      const last = msgs[msgs.length - 1];
      last.textContent = text;
      msgsEl.scrollTop = msgsEl.scrollHeight;
    }
  }

  async function sendMessage() {
    const input = document.getElementById('seedy-input');
    const text = input.value.trim();
    if (!text || isStreaming) return;

    input.value = '';
    input.style.height = 'auto';
    addMessage('user', text);
    messages.push({ role: 'user', content: text });

    // Show typing
    isStreaming = true;
    document.getElementById('seedy-typing').classList.add('active');
    document.getElementById('seedy-send').disabled = true;

    let assistantText = '';
    const assistantDiv = addMessage('assistant', '');

    try {
      const resp = await fetch(CHAT_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: messages.slice(-MAX_HISTORY),
          stream: true,
        }),
      });

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (data === '[DONE]') break;

          try {
            const parsed = JSON.parse(data);
            const delta = parsed.choices?.[0]?.delta?.content;
            if (delta) {
              assistantText += delta;
              assistantDiv.textContent = assistantText;
              document.getElementById('seedy-messages').scrollTop =
                document.getElementById('seedy-messages').scrollHeight;
            }
          } catch(e) { /* skip parse errors */ }
        }
      }
    } catch(err) {
      assistantText = '❌ Error conectando con Seedy. Inténtalo de nuevo.';
      assistantDiv.textContent = assistantText;
      console.error('Seedy chat error:', err);
    }

    messages.push({ role: 'assistant', content: assistantText });
    // Trim history
    if (messages.length > MAX_HISTORY * 2) {
      messages = messages.slice(-MAX_HISTORY);
    }

    isStreaming = false;
    document.getElementById('seedy-typing').classList.remove('active');
    document.getElementById('seedy-send').disabled = false;
    document.getElementById('seedy-input').focus();
  }

  // Init
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createWidget);
  } else {
    createWidget();
  }
})();
