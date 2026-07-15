import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";
import {
  getIdToken,
  onAuthChange,
  signInWithGoogle,
  signOutUser,
} from "./firebase";

// A tiny silent clip used to "unlock" the audio element inside a tap, so the
// browser (iOS Safari, Chrome) lets the reply — fetched a moment later — play.
const SILENT =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";

// Where the FastAPI backend runs. In the deployed build the frontend is served
// by the same server, so VITE_API_BASE is "" (same origin); local dev falls
// back to the separate dev server.
const API = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

// One random id per browser, saved so it survives page reloads.
function getSessionId() {
  let id = localStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("session_id", id);
  }
  return id;
}

// fetch() with the signed-in user's ID token attached, so the backend knows
// who's asking and can scope the journal to them.
async function authFetch(url, options = {}) {
  const token = await getIdToken();
  return fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

export default function App() {
  // --- state: the things that change over time ---
  const [user, setUser] = useState(null);        // the signed-in Firebase user
  const [authReady, setAuthReady] = useState(false); // first auth check done?
  const [messages, setMessages] = useState([]); // [{ role, text }]
  const [input, setInput] = useState("");        // what's typed in the box
  const [loading, setLoading] = useState(false); // waiting for a reply?
  const [recording, setRecording] = useState(false);

  // Track sign-in state; runs once on mount.
  useEffect(() => {
    return onAuthChange((u) => {
      setUser(u);
      setAuthReady(true);
    });
  }, []);

  // Kept between renders: the recorder and the audio chunks it produces.
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  // One reusable <audio>; playback only ever starts from a tap on the speaker
  // button, so the browser never blocks it — and nothing plays out loud unless
  // the person asks for it.
  const audioRef = useRef(null);
  const [speakingIdx, setSpeakingIdx] = useState(null); // which msg is playing

  // Auto-scroll to the newest message whenever the list changes.
  const bottom = useRef(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // When signed in, load today's conversation so the screen isn't blank each
  // visit — each saved entry becomes a user turn followed by the coach's reply.
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch(`${API}/entries`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        setMessages(
          (data.entries || []).flatMap((e) => [
            { role: "user", text: e.transcript },
            { role: "assistant", text: e.ai_reply },
          ]),
        );
      } catch {
        /* ignore — just start with an empty screen */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  // Read one reply aloud — called from a tap on its speaker button. Tapping the
  // same button again while it's playing stops it.
  async function playReply(text, idx) {
    const a = audioRef.current || (audioRef.current = new Audio());
    if (speakingIdx === idx) {
      a.pause();
      setSpeakingIdx(null);
      return;
    }
    // Unlock playback NOW, synchronously inside the tap — browsers block a
    // play() called later (after the await), which is why sound was missing.
    try {
      a.src = SILENT;
      a.play().catch(() => {});
    } catch {
      /* ignore */
    }
    try {
      setSpeakingIdx(idx);
      const res = await fetch(`${API}/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        setSpeakingIdx(null);
        return;
      }
      a.pause();
      a.src = URL.createObjectURL(await res.blob());
      a.onended = () => setSpeakingIdx(null);
      await a.play();
    } catch {
      setSpeakingIdx(null); // speech failed; the text is still there
    }
  }

  // Stream the coach's reply to a question into a new assistant bubble, typing
  // it out live. Shared by typed and voice input.
  async function streamReply(question) {
    setLoading(true); // typing dots until the first token arrives
    try {
      const res = await authFetch(`${API}/agent/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: getSessionId() }),
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let started = false;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        if (!started) {
          started = true;
          setLoading(false); // first token in — drop the dots, start the bubble
          setMessages((prev) => [...prev, { role: "assistant", text: chunk }]);
        } else {
          setMessages((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { ...last, text: last.text + chunk };
            return copy;
          });
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry — I couldn't reach the coach." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  // Send a typed message.
  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    await streamReply(text);
  }

  // Start/stop recording. On stop, the audio is sent to /talk.
  async function toggleRecord() {
    if (recording) {
      recorderRef.current?.stop();
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream);
    chunksRef.current = [];
    rec.ondataavailable = (e) => chunksRef.current.push(e.data);
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop()); // release the mic
      sendAudio(new Blob(chunksRef.current, { type: "audio/webm" }));
    };
    recorderRef.current = rec;
    rec.start();
    setRecording(true);
  }

  // Upload recorded audio: Whisper transcribes it, then the reply streams in —
  // same streaming path as typing, so voice replies aren't a long wait.
  async function sendAudio(blob) {
    setRecording(false);
    setLoading(true);
    let text;
    try {
      const form = new FormData();
      form.append("audio", blob, "clip.webm");
      const res = await authFetch(`${API}/transcribe`, { method: "POST", body: form });
      text = (await res.json()).text;
    } catch {
      setLoading(false);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry — I couldn't hear that." },
      ]);
      return;
    }
    setMessages((prev) => [...prev, { role: "user", text: text || "🎤 (voice)" }]);
    await streamReply(text);
  }

  // Before the first auth check, show nothing to avoid a sign-in flash.
  if (!authReady) return null;

  // Signed out: a simple gate. The coach is per-person, so sign in first.
  if (!user) {
    return (
      <div className="app gate">
        <header className="head">
          <h1>Daily Coach</h1>
          <p>Your personal coach that remembers, and gets to know you.</p>
        </header>
        <button className="google" onClick={() => signInWithGoogle()}>
          Sign in with Google
        </button>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="head">
        <h1>Daily Coach</h1>
        <p>Talk about your day — I'll remember, and help you see your wins.</p>
        <div className="who">
          <span>{user.displayName || user.email}</span>
          <button className="signout" onClick={() => signOutUser()}>
            Sign out
          </button>
        </div>
      </header>

      <main className="chat">
        {messages.length === 0 && (
          <p className="empty">Say or type how your day is going.</p>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" ? (
              <div className="md">
                <ReactMarkdown>{m.text}</ReactMarkdown>
              </div>
            ) : (
              m.text
            )}
            {m.role === "assistant" && m.text && (
              <button
                type="button"
                className="speak"
                onClick={() => playReply(m.text, i)}
                title={speakingIdx === i ? "Stop" : "Play aloud"}
              >
                {speakingIdx === i ? "⏸ Playing…" : "🔊 Play"}
              </button>
            )}
          </div>
        ))}

        {loading && (
          <div className="msg assistant typing">
            <span></span><span></span><span></span>
          </div>
        )}

        <div ref={bottom} />
      </main>

      <form
        className="bar"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <button
          type="button"
          className={`mic ${recording ? "on" : ""}`}
          onClick={toggleRecord}
          title={recording ? "Stop recording" : "Record"}
        >
          {recording ? "■" : "🎤"}
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={recording ? "Listening…" : "Type, or tap the mic…"}
        />
        <button disabled={loading}>Send</button>
      </form>
    </div>
  );
}
