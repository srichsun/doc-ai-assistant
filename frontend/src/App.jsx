import { useState, useRef, useEffect } from "react";
import "./App.css";
import {
  getIdToken,
  onAuthChange,
  signInWithGoogle,
  signOutUser,
} from "./firebase";

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

  // Auto-scroll to the newest message whenever the list changes.
  const bottom = useRef(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Ask the backend to read a reply aloud, then play it.
  async function playReply(text) {
    try {
      const res = await fetch(`${API}/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const url = URL.createObjectURL(await res.blob());
      new Audio(url).play();
    } catch {
      // If speech fails, we still showed the text — no big deal.
    }
  }

  // Send a typed message.
  async function send() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setLoading(true);
    try {
      const res = await authFetch(`${API}/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text, session_id: getSessionId() }),
      });
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", text: data.answer }]);
      playReply(data.answer);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry — I couldn't reach the coach." },
      ]);
    } finally {
      setLoading(false);
    }
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

  // Upload recorded audio: Whisper transcribes it, the coach replies.
  async function sendAudio(blob) {
    setRecording(false);
    setLoading(true);
    try {
      const form = new FormData();
      form.append("audio", blob, "clip.webm");
      form.append("session_id", getSessionId());
      const res = await authFetch(`${API}/talk`, { method: "POST", body: form });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "user", text: data.transcript || "🎤 (voice)" },
        { role: "assistant", text: data.answer },
      ]);
      playReply(data.answer);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry — I couldn't hear that." },
      ]);
    } finally {
      setLoading(false);
    }
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
            {m.text}
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
