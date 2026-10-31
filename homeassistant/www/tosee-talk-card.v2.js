
class ToSeeTalkCardV2 extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    this.ws = null;
    this.connected = false;
    this.serverStatus = "offline";

    this.phase = "idle";
    this.attempt = 0;
    this.startSent = false;

    this.stream = null;
    this.audioContext = null;
    this.processor = null;
    this.source = null;
    this.audioStarting = false;

    this.samples = [];
    this.sum = 0;
    this.count = 0;

    this.pollTimer = null;
    this.retryTimer = null;
    this.talkTimer = null;
  }

  log(event, details = "") {
    console.info(
      `[TOSEE_UI] ${event}`,
      details,
      "phase=" + this.phase,
      "server=" + this.serverStatus,
      "attempt=" + this.attempt
    );
  }

  setConfig(config) {
    this.talkWsUrl = config.talk_ws_url || null;

    if (!this.shadowRoot.querySelector("#talk")) {
      this.render();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (this.connected && !this.ws) this.connect();
  }

  connectedCallback() {
    this.connected = true;
    if (!this.shadowRoot.querySelector("#talk")) this.render();
    this.connect();
  }

  disconnectedCallback() {
    this.connected = false;
    clearInterval(this.pollTimer);
    clearTimeout(this.retryTimer);
    this.stopTalk("card_disconnected");

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        .panel {
          padding: 16px;
          text-align: center;
          font-family: sans-serif;
        }
        button {
          padding: 14px 30px;
          border: 0;
          border-radius: 12px;
          font-size: 18px;
          background: #1976d2;
          color: white;
          cursor: pointer;
        }
        button:disabled {
          background: #777;
          cursor: not-allowed;
        }
        button.active {
          background: #c62828;
        }
        .status {
          margin-top: 12px;
          font-size: 14px;
        }
      </style>
      <div class="panel">
        <button id="talk" disabled>🎤 Mów</button>
        <div class="status" id="status">
          Łączenie z serwerem rozmowy...
        </div>
      </div>
    `;

    this.shadowRoot.querySelector("#talk")
      .addEventListener("click", () => this.toggleTalk());
  }

  updateUI(message = "") {
    const button = this.shadowRoot.querySelector("#talk");
    const status = this.shadowRoot.querySelector("#status");
    if (!button || !status) return;

    const inProgress = this.phase !== "idle";
    const wsReady = this.ws?.readyState === WebSocket.OPEN;

    button.disabled = !inProgress &&
      (!wsReady || this.serverStatus !== "idle");

    button.classList.toggle("active", inProgress);
    button.textContent = inProgress
      ? "■ Zakończ"
      : "🎤 Mów";

    const labels = {
      offline: "Brak połączenia z serwerem rozmowy",
      blocked: "Oczekiwanie na dzwonek i LIVE",
      idle: "Możesz nacisnąć Mów",
      pending: "Oczekiwanie na START 07...",
      starting: "Łączenie z dzwonkiem...",
      active: "Mówisz — transmisja aktywna",
      unavailable: "Rozmowa niedostępna"
    };

    if (this.phase === "preparing") {
      status.textContent = "Otwieranie mikrofonu...";
    } else {
      status.textContent = message ||
        labels[this.serverStatus] || "";
    }
  }

  connect() {
    if (!this.connected || this.ws) return;

    const token = this._hass?.auth?.data?.access_token;
    if (!token) {
      this.log("AUTH_TOKEN_MISSING");
      this.updateUI("Brak tokenu Home Assistant");
      return;
    }

    if (!this.talkWsUrl) {
      this.updateUI("Brak talk_ws_url w konfiguracji karty");
      return;
    }

    const ws = new WebSocket(this.talkWsUrl);
    this.ws = ws;

    ws.onopen = () => {
      this.log("WS_OPEN");
      ws.send(token);
      ws.send("STATUS");

      clearInterval(this.pollTimer);
      this.pollTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send("STATUS");
        }
      }, 700);
    };

    ws.onmessage = (event) => {
      if (this.ws !== ws) return;
      const message = event.data;

      if (typeof message !== "string") return;

      if (message.startsWith("STATUS:")) {
        const state = message.slice(7);
        const previous = this.serverStatus;
        this.serverStatus = state;

        if (state !== previous) {
          this.log("STATUS_CHANGED", `${previous} -> ${state}`);
        }

        if (this.phase === "preparing") {
          // Nie przerywamy getUserMedia na podstawie
          // odpowiedzi STATUS.
          this.updateUI();
          return;
        }

        if (this.phase !== "idle") {
          if (state === "active" && this.startSent) {
            this.phase = "active";
            this.startAudio().catch((error) => {
              this.log("AUDIO_START_ERROR", error.name);
              this.stopTalk("audio_start_error");
            });
          } else if (
            state === "blocked" || state === "unavailable"
          ) {
            this.stopTalk("server_" + state);
          }
        }

        this.updateUI();
      } else if (message === "START_OK") {
        this.log("START_OK");
        if (this.startSent && this.phase !== "idle") {
          this.phase = "starting";
          this.serverStatus = "pending";
        }
        this.updateUI();
      } else if (
        message === "START_BLOCKED" ||
        message === "AUDIO_BLOCKED"
      ) {
        this.log(message);
        this.stopTalk(message);
        this.serverStatus = "blocked";
        this.updateUI();
      } else if (message === "STOP_OK") {
        this.log("STOP_OK");
      }
    };

    ws.onclose = () => {
      if (this.ws !== ws) return;

      this.log("WS_CLOSED");
      clearInterval(this.pollTimer);
      this.stopTalk("ws_closed");

      this.ws = null;
      this.serverStatus = "offline";
      this.updateUI();

      if (this.connected) {
        clearTimeout(this.retryTimer);
        this.retryTimer = setTimeout(
          () => this.connect(), 3000
        );
      }
    };

    ws.onerror = () => {
      if (this.ws !== ws) return;
      this.log("WS_ERROR");
      this.serverStatus = "offline";
      this.updateUI();
    };
  }

  async toggleTalk() {
    this.log("UI_TALK_CLICK");

    if (this.phase !== "idle") {
      this.stopTalk("user_stop");
      return;
    }

    if (
      this.serverStatus !== "idle" ||
      this.ws?.readyState !== WebSocket.OPEN
    ) {
      this.log("UI_START_NOT_SENT", "not_ready");
      this.updateUI();
      return;
    }

    const ws = this.ws;
    const currentAttempt = ++this.attempt;

    this.phase = "preparing";
    this.startSent = false;
    this.updateUI();

    let stream;

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        },
        video: false
      });
    } catch (error) {
      this.log("MICROPHONE_ERROR", error.name);
      if (currentAttempt === this.attempt) {
        this.stopTalk("microphone_error");
        this.updateUI("Błąd mikrofonu: " + error.name);
      }
      return;
    }

    if (
      currentAttempt !== this.attempt ||
      this.phase !== "preparing" ||
      this.ws !== ws ||
      ws.readyState !== WebSocket.OPEN
    ) {
      stream.getTracks().forEach(track => track.stop());
      this.log("UI_START_NOT_SENT", "attempt_cancelled");
      return;
    }

    this.stream = stream;

    // Nie wysyłamy START, jeśli serwer przestał
    // zgłaszać gotowość podczas otwierania mikrofonu.
    if (this.serverStatus !== "idle") {
      this.log("UI_START_NOT_SENT", "status_changed");
      this.stopTalk("not_ready_after_microphone");
      return;
    }

    this.phase = "starting";
    this.startSent = true;

    this.log("UI_START_SENT");
    ws.send("START");

    this.talkTimer = setTimeout(() => {
      if (currentAttempt === this.attempt) {
        this.stopTalk("local_timeout");
      }
    }, 14500);

    this.updateUI();
  }

  encodeALaw(sample) {
    let pcm = Math.max(-32768, Math.min(
      32767, Math.round(sample * 32767)
    ));

    const mask = pcm >= 0 ? 0xD5 : 0x55;
    if (pcm < 0) pcm = -pcm - 1;
    pcm = Math.min(pcm, 32635);

    let segment = 0;
    const limits = [
      0xFF, 0x1FF, 0x3FF, 0x7FF,
      0xFFF, 0x1FFF, 0x3FFF, 0x7FFF
    ];

    while (segment < 8 && pcm > limits[segment]) segment++;

    if (segment >= 8) return 0x7F ^ mask;

    const value = segment === 0
      ? (pcm >> 4)
      : ((segment << 4) | ((pcm >> (segment + 3)) & 15));

    return value ^ mask;
  }

  async startAudio() {
    if (
      this.phase !== "active" ||
      !this.stream ||
      this.audioContext ||
      this.audioStarting
    ) return;

    this.audioStarting = true;
    const attempt = this.attempt;

    try {
      const context = new AudioContext();
      this.audioContext = context;

      this.source = context.createMediaStreamSource(
        this.stream
      );
      this.processor = context.createScriptProcessor(
        2048, 1, 1
      );

      const samplesPerOutput = context.sampleRate / 8000;
      this.samples = [];
      this.sum = 0;
      this.count = 0;

      this.processor.onaudioprocess = (event) => {
        event.outputBuffer.getChannelData(0).fill(0);

        if (
          attempt !== this.attempt ||
          this.phase !== "active" ||
          this.serverStatus !== "active" ||
          this.ws?.readyState !== WebSocket.OPEN
        ) return;

        const input = event.inputBuffer.getChannelData(0);

        for (const sample of input) {
          this.sum += sample;
          this.count++;

          if (this.count >= samplesPerOutput) {
            const average = this.sum / this.count;
            this.samples.push(this.encodeALaw(average));
            this.sum = 0;
            this.count -= samplesPerOutput;

            if (this.samples.length === 320) {
              if (this.ws.bufferedAmount < 3200) {
                this.ws.send(
                  new Uint8Array(this.samples)
                );
              }
              this.samples = [];
            }
          }
        }
      };

      this.source.connect(this.processor);
      this.processor.connect(context.destination);

      await context.resume();

      if (
        attempt !== this.attempt ||
        this.phase !== "active"
      ) return;

      this.log("AUDIO_STREAM_STARTED");
    } finally {
      this.audioStarting = false;
    }
  }

  stopTalk(reason = "user_stop") {
    const wasRunning = this.phase !== "idle";
    const shouldSendStop = this.startSent;

    ++this.attempt;
    clearTimeout(this.talkTimer);
    this.talkTimer = null;

    this.phase = "idle";
    this.startSent = false;

    if (
      shouldSendStop &&
      this.ws?.readyState === WebSocket.OPEN
    ) {
      this.ws.send("STOP");
      this.log("UI_STOP_SENT", reason);
    } else if (wasRunning) {
      this.log("UI_STOP_LOCAL", reason);
    }

    if (this.processor) {
      this.processor.disconnect();
      this.processor.onaudioprocess = null;
      this.processor = null;
    }

    if (this.source) {
      this.source.disconnect();
      this.source = null;
    }

    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }

    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }

    this.samples = [];
    this.audioStarting = false;
    this.updateUI();
  }
}

if (!customElements.get("tosee-talk-card-v2")) {
  customElements.define("tosee-talk-card-v2", ToSeeTalkCardV2);
}
