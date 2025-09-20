// jscript2.js — injects chatbot button and handles popup + queries
(function () {
  document.addEventListener('DOMContentLoaded', () => {
    // ✅ Ask on page reload if we should clear chat
    if (performance.navigation.type === performance.navigation.TYPE_RELOAD) {
      const shouldClear = confirm("Reload detected. Your chat history will be cleared. Continue?");
      if (shouldClear) {
        sessionStorage.removeItem("chatHistory");
        sessionStorage.removeItem("chatbotOpen");
      }
    }

    // --- Configuration ---
    const POPUP_HTML = '/html/index2.html';
    const POPUP_CSS  = '/css/style2.css';
    const CHAT_ICON  = '/img/chatbot.png';

    // --- Ensure chatbot button exists ---
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
          /* toast */
          .chatbot-toast {
            position: fixed;
            bottom: 96px;
            right: 20px;
            background: rgba(0,0,0,0.85);
            color: #fff;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            z-index: 10000;
            box-shadow: 0 6px 18px rgba(0,0,0,0.25);
            opacity: 0;
            transition: opacity 200ms ease;
          }
          .chatbot-toast.show { opacity: 1; }
          /* ensure popup is the topmost element */
          #chatbotPopup { z-index: 9999 !important; position: fixed; }
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

    // Small helper: show a toast message
    function showToast(msg, timeout = 2200) {
      let t = document.querySelector('.chatbot-toast');
      if (!t) {
        t = document.createElement('div');
        t.className = 'chatbot-toast';
        document.body.appendChild(t);
      }
      t.textContent = msg;
      t.classList.add('show');
      clearTimeout(t._timer);
      t._timer = setTimeout(() => {
        t.classList.remove('show');
      }, timeout);
    }

    /* ---------------------
       Navigation helper (true redirect + auto reopen)
       --------------------- */
    function navigatePreservePopup(url) {
      if (!url) return;
      sessionStorage.setItem("chatbotOpen", "true"); // keep popup state across redirect
      window.location.href = url; 
    }

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

            // ✅ Restore popup open state
            if (sessionStorage.getItem("chatbotOpen") === "true") {
              popupEl.style.display = 'flex';
            }

            const inputEl = popupEl.querySelector('.popup-input');
            const searchBtn = popupEl.querySelector('.search-icon');
            const micBtn = popupEl.querySelector('.mic-icon');

            // --- VOICE TOGGLE ELEMENT (grab it early so we can reference it) ---
            const voiceToggle = popupEl.querySelector('#voiceNavToggle');

            // If toggle exists, restore saved state (persisted in localStorage)
            if (voiceToggle) {
              const saved = localStorage.getItem('voiceNavEnabled');
              if (saved === 'true') voiceToggle.checked = true;
              else if (saved === 'false') voiceToggle.checked = false;
            }

            let chatContainer = popupEl.querySelector('.chat-container');
            if (!chatContainer) {
              chatContainer = document.createElement('div');
              chatContainer.className = 'chat-container';
              popupEl.insertBefore(chatContainer, popupEl.querySelector('.popup-searchbar'));
            }

            // ✅ Restore chat history
            let history = JSON.parse(sessionStorage.getItem("chatHistory") || "[]");
            history.forEach(msg => {
              const el = document.createElement('div');
              el.className = `chat-message ${msg.from}`;
              el.textContent = msg.text;
              chatContainer.appendChild(el);
            });
            chatContainer.scrollTop = chatContainer.scrollHeight;

            // --- Chat message append (styled by CSS classes) ---
            function appendMessage(text, from = 'bot') {
              const el = document.createElement('div');
              el.className = `chat-message ${from}`;
              el.textContent = text;
              chatContainer.appendChild(el);
              chatContainer.scrollTop = chatContainer.scrollHeight;

              // ✅ Save to sessionStorage
              let history = JSON.parse(sessionStorage.getItem("chatHistory") || "[]");
              history.push({ text, from });
              sessionStorage.setItem("chatHistory", JSON.stringify(history));
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

                  const voiceOn = voiceToggle ? voiceToggle.checked : false;
                  if (data.redirect && voiceOn) {
                    console.log('🔀 Redirecting (server-suggested) to:', data.redirect);
                    navigatePreservePopup(data.redirect);
                    return;
                  }

                  // Keyword fallback
                  const keywords = {
                    "mba": "mba.html",
                    "mca": "mca.html",
                    "bba": "bba.html",
                    "bca": "bca.html",
                    "ma": "ma.html",
                    "ba": "ba.html",
                    "scholarship": "index4.html",
                    "courses": "index3.html"
                  };

                  const qLower = query.toLowerCase();
                  if (voiceOn) {
                    for (const key in keywords) {
                      if (qLower.includes(key)) {
                        const target = "/" + keywords[key].replace(".html", "");
                        console.log('🔀 Redirecting (client-detected) to:', target);
                        navigatePreservePopup(target);
                        return;
                      }
                    }
                  } else {
                    console.log('Voice navigation is OFF — skipped redirect for text query.');
                    showToast('Redirect skipped — Voice Navigation is OFF');
                  }

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
                if (loadingMsg && loadingMsg.remove) loadingMsg.remove();
                appendMessage('❌ Error sending query (see console)', 'bot');
                console.error('❌ Fetch failed:', err);
              }
            }

            if (searchBtn) searchBtn.addEventListener('click', sendQuery);
            if (inputEl) inputEl.addEventListener('keypress', e => { if (e.key === 'Enter') sendQuery(); });

            // 🎤 Mic recording logic
            if (micBtn) micBtn.textContent = "";
            if (micBtn) {
              let mediaRecorder;
              let audioChunks = [];
              let recordingMsg;

              micBtn.addEventListener('click', async () => {
                try {
                  if (!mediaRecorder || mediaRecorder.state === "inactive") {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];

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

                        const voiceOn = voiceToggle ? voiceToggle.checked : false;
                        if (data.redirect && voiceOn) {
                          console.log('🔀 Redirecting (server-suggested from STT) to:', data.redirect);
                          navigatePreservePopup(data.redirect);
                          return;
                        }

                        if (voiceOn && data.transcript) {
                          const keywords = {
                            "mba": "mba.html",
                            "mca": "mca.html",
                            "bba": "bba.html",
                            "bca": "bca.html",
                            "ma": "ma.html",
                            "ba": "ba.html",
                            "scholarship": "index4.html",
                            "courses": "index3.html"
                          };
                          const tLower = (data.transcript || "").toLowerCase();
                          for (const key in keywords) {
                            if (tLower.includes(key)) {
                              const target = "/" + keywords[key].replace(".html", "");
                              console.log('🔀 Redirecting (client-detected from transcript) to:', target);
                              navigatePreservePopup(target);
                              return;
                            }
                          }
                        } else {
                          console.log('Voice navigation is OFF — skipped redirect for speech query.');
                          showToast('Redirect skipped — Voice Navigation is OFF');
                        }

                      } catch (err) {
                        if (loadingMsg && loadingMsg.remove) loadingMsg.remove();
                        appendMessage("❌ Mic send failed", "bot");
                        console.error(err);
                      }
                    };

                    mediaRecorder.start();
                    micBtn.classList.add("recording");
                  } else {
                    mediaRecorder.stop();
                    micBtn.classList.remove("recording");
                  }
                } catch (err) {
                  appendMessage("❌ Microphone access or recording failed", "bot");
                  console.error('Mic error:', err);
                  showToast('Mic permission denied or unavailable');
                }
              });
            }

            // ✅ VOICE NAVIGATION TOGGLE
            if (voiceToggle) {
              voiceToggle.addEventListener('change', () => {
                const enabled = voiceToggle.checked;
                localStorage.setItem('voiceNavEnabled', enabled ? 'true' : 'false');
                if (enabled) {
                  console.log("🎤 Voice navigation mode ENABLED");
                  showToast('Voice Navigation: ON');
                } else {
                  console.log("⏹ Voice navigation mode DISABLED");
                  showToast('Voice Navigation: OFF');
                }
              });
            }

            const closeBtn = popupEl.querySelector('#closePopup');
            if (closeBtn) closeBtn.onclick = () => {
              popupEl.style.display = 'none';
              sessionStorage.setItem("chatbotOpen", "false");
            };

            popupEl.onclick = e => {
              if (e.target === popupEl) {
                popupEl.style.display = 'none';
                sessionStorage.setItem("chatbotOpen", "false");
              }
            };

            function makePopupDraggable(el) {
              let offsetX = 0, offsetY = 0, isDown = false;
              if (!el) return;
              el.style.position = "fixed";
              el.style.resize = "both";
              el.style.overflow = "auto";
              el.addEventListener("mousedown", (e) => {
                isDown = true;
                offsetX = e.clientX - el.offsetLeft;
                offsetY = e.clientY - el.offsetTop;
                el.style.cursor = "move";
              });
              document.addEventListener("mouseup", () => { isDown = false; if (el) el.style.cursor = "default"; });
              document.addEventListener("mousemove", (e) => {
                if (!isDown) return;
                el.style.left = (e.clientX - offsetX) + "px";
                el.style.top = (e.clientY - offsetY) + "px";
              });
            }

            try { makePopupDraggable(popupEl.querySelector(".popup-content")); } catch (e) { }

            popupLoaded = true;
            console.log('✅ Popup loaded and ready');

            popupEl.style.display = 'flex';
            sessionStorage.setItem("chatbotOpen", "true");
          })
          .catch(err => {
            console.error('Error loading popup:', err);
            showToast('Failed to load chatbot popup');
          });
      } else {
        const el = document.getElementById('chatbotPopup');
        if (el) {
          el.style.display = 'flex';
          sessionStorage.setItem("chatbotOpen", "true");
        }
      }
    });

    // 🔄 Auto-reopen popup after full page load if left open
    if (sessionStorage.getItem("chatbotOpen") === "true") {
      setTimeout(() => {
        document.querySelector('.chatbot-btn')?.click();
      }, 300);
    }

  });
})();