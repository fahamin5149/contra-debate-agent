// Contra — Phase 1 browser transport.
//
// Audio never touches UI state. The RTCPeerConnection and the <audio> element
// live entirely outside any rendering logic, so re-rendering the log can never
// introduce jank into a path with a 10 ms margin.

const startBtn = document.getElementById("start");
const stateEl = document.getElementById("state");
const agentEl = document.getElementById("agent");
const logEl = document.getElementById("log");

function log(msg, cls) {
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = `${new Date().toLocaleTimeString()}  ${msg}`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

function setState(s) {
  stateEl.textContent = s;
  stateEl.dataset.s = s;
}

let pc = null;

async function start() {
  startBtn.disabled = true;
  setState("connecting");

  // Echo cancellation is MANDATORY — the user is on speakers (ADR-0012).
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
      sampleRate: 16000,
    },
    video: false,
  });

  const track = stream.getAudioTracks()[0];
  log(`mic: ${track.label}`);

  const s = track.getSettings();
  log(`AEC=${s.echoCancellation}  NS=${s.noiseSuppression}  AGC=${s.autoGainControl}`);
  if (s.echoCancellation === false) {
    log("WARNING: echo cancellation is OFF — the agent will hear itself.", "warn");
  }

  pc = new RTCPeerConnection({ iceServers: [] }); // local only, no STUN needed
  pc.addTrack(track, stream);

  pc.ontrack = (ev) => {
    log("inbound agent track attached");
    agentEl.srcObject = ev.streams[0];
  };

  pc.onconnectionstatechange = () => {
    log(`peer connection: ${pc.connectionState}`);
    if (pc.connectionState === "connected") setState("listening");
    if (["failed", "closed", "disconnected"].includes(pc.connectionState)) {
      setState("disconnected");
      startBtn.disabled = false;
    }
  };

  const offer = await pc.createOffer({ offerToReceiveAudio: true });
  await pc.setLocalDescription(offer);
  await iceComplete(pc);
  log("offer ready, posting to server");

  const res = await fetch("/api/webrtc/offer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sdp: pc.localDescription.sdp,
      type: pc.localDescription.type,
    }),
  });
  if (!res.ok) throw new Error(`signalling failed: HTTP ${res.status}`);

  await pc.setRemoteDescription(await res.json());
  log("answer applied — speak when the state shows 'listening'");
}

// Wait for ICE gathering so we can send one complete offer (no trickle ICE).
function iceComplete(peer) {
  if (peer.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const check = () => {
      if (peer.iceGatheringState === "complete") {
        peer.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    };
    peer.addEventListener("icegatheringstatechange", check);
  });
}

startBtn.addEventListener("click", () =>
  start().catch((e) => {
    log(`ERROR: ${e.message}`, "warn");
    setState("error");
    startBtn.disabled = false;
  })
);
