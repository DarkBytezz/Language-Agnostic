// jscript2.js — injects chatbot button and handles popup + queries
(function () {
  document.addEventListener('DOMContentLoaded', () => {
    // --- Configuration (absolute paths are safest) ---
    const POPUP_HTML = '/html/index2.html';
    const POPUP_CSS  = '/css/style2.css';
    const CHAT_ICON  = '/img/chatbot.png';

    // --- Ensure chatbot button exists (create if missing) ---
    function ensureChatbotButton() {
      if (document.querySelector('.chatbot-btn')) {
        console.log('💡 Chatbot button already present.');
        return;
      }

      const btn = document.createElement('button');
      btn.className = 'chatbot-btn';
      btn.title = 'Chatbot';

      const img = document.createElement('img');
      img.src = CHAT_ICON;
      img.alt = 'Chatbot';
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'cover';

      btn.appendChild(img);
      document.body.appendChild(btn);

      if (!document.getElementById('chatbot-inline-style')) {
        const style = document.createElement('style');
        style.id = 'chatbot-inline-style';
        style.textContent = `
          .chatbot-btn{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #ffffff;
            border: none;
            border-radius: 50%;
            width: 64px;
            height: 64px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 6px;
            cursor: pointer;
            box-shadow: 0 6px 18px rgba(0,0,0,0.18);
            z-index: 9999;
          }
          .chatbot-btn img { width: 100%; height: 100%; border-radius: 50%; }
          .chatbot-btn:active { transform: scale(0.98); }
        `;
        document.head.appendChild(style);
      }

      console.log('➕ Chatbot button injected.');
    }

    ensureChatbotButton();

    const chatbotBtn = document.querySelector('.chatbot-btn');
    if (!chatbotBtn) {
      console.error('❌ Chatbot button not found (unexpected).');
      return;
    }

    let popupLoaded = false;

    chatbotBtn.addEventListener('click', function () {
      console.log('🟢 Chatbot button clicked');

      if (!popupLoaded) {
        fetch(POPUP_HTML)
          .then(resp => {
            if (!resp.ok) throw new Error(`Failed to load popup HTML: ${resp.status}`);
            return resp.text();
          })
          .then(html => {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = html.trim();

            const popupEl = tempDiv.querySelector('#chatbotPopup');
            if (!popupEl) throw new Error('Popup element #chatbotPopup not found in popup HTML');

            document.body.appendChild(popupEl);

            if (!document.getElementById('popup-style2')) {
              const link = document.createElement('link');
              link.id = 'popup-style2';
              link.rel = 'stylesheet';
              link.href = POPUP_CSS;
              document.head.appendChild(link);
            }

            popupEl.style.display = 'flex';

            const inputEl = popupEl.querySelector('.popup-input');
            const searchBtn = popupEl.querySelector('.search-icon');
            const micBtn = popupEl.querySelector('.mic-icon');

            let chatContainer = popupEl.querySelector('.chat-container');
            if (!chatContainer) {
              chatContainer = document.createElement('div');
              chatContainer.className = 'chat-container';
              popupEl.insertBefore(chatContainer, popupEl.querySelector('.popup-searchbar'));
            }

            function appendMessage(text, from = 'bot') {
              const el = document.createElement('div');
              el.textContent = text;
              el.style.margin = '8px 0';
              if (from === 'user') {
                el.style.fontWeight = '600';
                el.style.textAlign = 'right';
              } else {
                el.style.textAlign = 'left';
              }
              chatContainer.appendChild(el);
              chatContainer.scrollTop = chatContainer.scrollHeight;
            }

            async function sendQuery() {
              const query = inputEl.value.trim();
              if (!query) return;

              appendMessage(query, 'user');
              inputEl.value = '';

              const loadingMsg = document.createElement('div');
              loadingMsg.textContent = '...loading';
              loadingMsg.style.fontStyle = 'italic';
              loadingMsg.style.color = '#555';
              chatContainer.appendChild(loadingMsg);
              chatContainer.scrollTop = chatContainer.scrollHeight;

              try {
                const formData = new FormData();
                formData.append('query', query);

                const resp = await fetch('/ask_bot/', { method: 'POST', body: formData });
                const data = await resp.json();
                loadingMsg.remove();

                if (data.answer) {
                  appendMessage(data.answer, 'bot');
                  if (data.audio_file) {
                    try {
                      const audio = new Audio(`/download_audio/${data.audio_file}`);
                      audio.play().catch(e => console.warn('Audio play failed:', e));
                    } catch (e) {
                      console.error('Audio play error:', e);
                    }
                  }
                } else if (data.error) {
                  appendMessage('Error: ' + data.error, 'bot');
                } else {
                  appendMessage('No answer received.', 'bot');
                }
              } catch (err) {
                loadingMsg.remove?.();
                appendMessage('❌ Error sending query (see console)', 'bot');
                console.error('❌ Fetch failed:', err);
              }
            }

            if (searchBtn) searchBtn.addEventListener('click', sendQuery);
            if (inputEl) inputEl.addEventListener('keypress', e => { if (e.key === 'Enter') sendQuery(); });

            // 🎤 Mic recording logic
            // 🎤 Mic recording logic
            // ensure mic icon stays clean (remove any leftover text)
micBtn.textContent = "";

  if (micBtn) {
  let mediaRecorder;
  let audioChunks = [];
  let recordingMsg;

  micBtn.addEventListener('click', async () => {
    if (!mediaRecorder || mediaRecorder.state === "inactive") {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];

      // show "Speak now..."
      recordingMsg = document.createElement("div");
      recordingMsg.textContent = "🎤 Speak now...";
      recordingMsg.style.fontStyle = "italic";
      recordingMsg.style.color = "#d9534f";
      chatContainer.appendChild(recordingMsg);
      chatContainer.scrollTop = chatContainer.scrollHeight;

      mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

      mediaRecorder.onstop = async () => {
        if (recordingMsg) recordingMsg.remove();

        const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
        const formData = new FormData();
        formData.append("file", audioBlob, "recording.wav");

        const loadingMsg = document.createElement("div");
        loadingMsg.textContent = "🎤 Processing...";
        loadingMsg.style.fontStyle = "italic";
        chatContainer.appendChild(loadingMsg);

        try {
          const resp = await fetch("/record_and_transcribe/", { method: "POST", body: formData });
          const data = await resp.json();
          loadingMsg.remove();

          if (data.transcript) appendMessage(data.transcript, "user");
          if (data.answer) appendMessage(data.answer, "bot");
          else if (data.error) appendMessage("❌ Error: " + data.error, "bot");
        } catch (err) {
          loadingMsg.remove();
          appendMessage("❌ Mic send failed", "bot");
          console.error(err);
        }
      };

      mediaRecorder.start();

      // 🔵 add recording class
      micBtn.classList.add("recording");

      // 🔴 add pulse effect via inline style (JS-controlled)
      micBtn.style.animation = "pulse 1.5s infinite";
    } else {
      mediaRecorder.stop();

      // back to normal icon
      micBtn.classList.remove("recording");
      micBtn.style.animation = "none"; // stop pulsing
    }
  });
}


            const closeBtn = popupEl.querySelector('#closePopup');
            if (closeBtn) closeBtn.onclick = () => { popupEl.style.display = 'none'; };

            popupEl.onclick = e => { if (e.target === popupEl) popupEl.style.display = 'none'; };

            popupLoaded = true;
            console.log('✅ Popup loaded and ready');
          })
          .catch(err => {
            console.error('Error loading popup:', err);
          });
      } else {
        const el = document.getElementById('chatbotPopup');
        if (el) el.style.display = 'flex';
      }
    });
  });
})();
