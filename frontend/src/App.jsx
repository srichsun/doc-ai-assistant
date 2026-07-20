import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";
import {
  getIdToken,
  onAuthChange,
  signInWithGoogle,
  signOutUser,
} from "./firebase";

// Split a stored wins blob into its individual lines, tolerating the older
// markdown-bulleted format from before wins became plain one-liners.
function winLines(wins) {
  return (wins || "")
    .split("\n")
    .map((l) => l.replace(/^\s*[-*•]\s*/, "").replace(/\*\*/g, "").trim())
    .filter(Boolean);
}

// Group win-entries by their calendar day, newest first, keeping order.
function groupByDay(items) {
  const map = new Map();
  for (const e of items) {
    const day = (e.created_at || "").slice(0, 10);
    if (!map.has(day)) map.set(day, []);
    map.get(day).push(e);
  }
  return [...map.entries()];
}

// "2026-07-19" -> "Today" / "Yesterday" / "Sat, 19 Jul".
function dayLabel(day) {
  const today = new Date();
  const iso = (d) => d.toISOString().slice(0, 10);
  if (day === iso(today)) return "Today";
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (day === iso(yesterday)) return "Yesterday";
  return new Date(day + "T00:00:00").toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

// File extension for a recording's MIME type. Browsers disagree on what they
// record: Chrome produces "audio/webm;codecs=opus", iOS Safari "audio/mp4".
function audioExtension(mimeType) {
  const type = (mimeType || "").toLowerCase();
  if (type.includes("mp4") || type.includes("m4a")) return "mp4";
  if (type.includes("ogg")) return "ogg";
  if (type.includes("wav")) return "wav";
  if (type.includes("mpeg")) return "mp3";
  return "webm";
}

// Roughly how much text to synthesise at once. Small enough that the first
// chunk comes back in about a second, large enough not to chop her delivery
// into breathless fragments.
const SPEECH_CHUNK_CHARS = 220;

// Split a reply into speakable chunks, breaking on sentence ends so each one
// sounds like a finished thought rather than a cut-off line.
function splitForSpeech(text) {
  const plain = (text || "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/[*_`#>]/g, "")
    .replace(/\n{2,}/g, "\n");
  const sentences = plain.match(/[^.!?\n]+[.!?]*\n?/g) || [];
  const chunks = [];
  let current = "";
  for (const s of sentences) {
    if (current && (current + s).length > SPEECH_CHUNK_CHARS) {
      chunks.push(current.trim());
      current = "";
    }
    current += s;
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks.filter(Boolean);
}

// Line icons for the play control. Drawn rather than emoji so they inherit the
// text colour and match the hairline weight the rest of the page uses.
function PlayIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true">
      <path d="M4 2.6 L11.4 7 L4 11.4 Z" fill="currentColor" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true">
      <rect x="3.4" y="3" width="2.6" height="8" rx="0.9" fill="currentColor" />
      <rect x="8" y="3" width="2.6" height="8" rx="0.9" fill="currentColor" />
    </svg>
  );
}

function WaitIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 14 14" aria-hidden="true">
      <circle cx="7" cy="7" r="5.4" fill="none" stroke="currentColor"
              strokeWidth="1.4" opacity="0.25" />
      <path d="M7 1.6 A5.4 5.4 0 0 1 12.4 7" fill="none" stroke="currentColor"
            strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

// A tiny silent clip used to "unlock" the audio element inside a tap, so the
// browser (iOS Safari, Chrome) lets the reply — fetched a moment later — play.
const SILENT =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";

// Where the FastAPI backend runs. In the deployed build the frontend is served
// by the same server, so VITE_API_BASE is "" (same origin); local dev falls
// back to the separate dev server.
const API = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

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
  const [view, setView] = useState("chat");      // "chat" | "wins" | "you"
  const [wins, setWins] = useState([]);          // entries that recorded wins
  const [passage, setPassage] = useState("");    // who you are, in her words
  const [mantras, setMantras] = useState([]);    // lines you keep for hard days
  const [mantraDraft, setMantraDraft] = useState("");
  const [editingId, setEditingId] = useState(null); // mantra being reworded

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
  const [loadingIdx, setLoadingIdx] = useState(null);   // which msg is fetching
  // Speech already fetched this session, so replaying is instant and free.
  const audioCache = useRef(new Map());
  const abortRef = useRef(null); // lets a second tap cancel a request in flight
  // Which reply is currently claimed for playback. A ref rather than state
  // because taps arrive faster than React re-renders.
  const activeRef = useRef(null);
  // Resolves the chunk currently playing, so stopping can release the queue.
  const endPlaybackRef = useRef(null);

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

  // Load whichever review screen was opened: the day-by-day wins, or the
  // passage about who they are.
  useEffect(() => {
    if (!user || view === "chat") return;
    let cancelled = false;
    (async () => {
      try {
        const path =
          view === "wins"
            ? "/wins"
            : view === "mantra"
              ? "/mantras"
              : "/strengths";
        const res = await authFetch(`${API}${path}`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        if (view === "wins") setWins(data.wins || []);
        else if (view === "mantra") setMantras(data.mantras || []);
        else setPassage(data.strengths || "");
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user, view]);

  // Read one reply aloud — called from a tap on its speaker button.
  //
  // Synthesis cost is wildly superlinear: one sentence comes back in ~0.6s, a
  // whole reply takes ~11s. So we ask for it a chunk at a time and start
  // playing the first while the next is still being made. Speaking a chunk
  // takes about ten times longer than making one, so after the first there is
  // always another ready and the seams stay inaudible.
  //
  // "Which reply is active" lives in a ref, not state: two quick taps land in
  // the same render, so a state check would still read null on the second and
  // start a rival playback on top of the first.
  async function playReply(text, idx) {
    const a = audioRef.current || (audioRef.current = new Audio());

    // Tapping the same reply again — loading or playing — means stop.
    if (activeRef.current === idx) {
      stopSpeech();
      return;
    }
    stopSpeech(); // switching replies: abandon whatever was going
    activeRef.current = idx; // claimed synchronously, before any await

    // Unlock playback NOW, synchronously inside the tap — browsers block a
    // play() called later (after the await), which is why sound was missing.
    try {
      a.src = SILENT;
      a.play().catch(() => {});
    } catch {
      /* ignore */
    }

    const chunks = splitForSpeech(text);
    if (!chunks.length) {
      stopSpeech();
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setLoadingIdx(idx);

    let pending = prefetchSpeech(chunks[0], controller.signal);
    try {
      for (let i = 0; i < chunks.length; i++) {
        const url = await pending;
        if (activeRef.current !== idx) return; // stopped while we waited
        // Start making the next chunk before playing this one.
        pending =
          i + 1 < chunks.length
            ? prefetchSpeech(chunks[i + 1], controller.signal)
            : null;
        if (i === 0) {
          setLoadingIdx(null);
          setSpeakingIdx(idx);
        }
        await playOne(a, url);
        if (activeRef.current !== idx) return;
      }
    } catch {
      /* aborted by another tap, or speech failed — the text is still there */
    }
    if (activeRef.current === idx) stopSpeech();
  }

  // Fetch one chunk's audio, reusing anything already fetched this session so
  // replaying costs neither time nor money.
  async function fetchSpeech(chunk, signal) {
    const cached = audioCache.current.get(chunk);
    if (cached) return cached;
    const res = await authFetch(`${API}/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: chunk }),
      signal,
    });
    if (!res.ok) throw new Error("speech failed");
    const url = URL.createObjectURL(await res.blob());
    audioCache.current.set(chunk, url);
    return url;
  }

  // Same, but tolerates being abandoned: a prefetch nobody ends up awaiting
  // would otherwise surface as an unhandled rejection.
  function prefetchSpeech(chunk, signal) {
    const p = fetchSpeech(chunk, signal);
    p.catch(() => {});
    return p;
  }

  // Play one chunk; resolves when it ends, fails, or playback is stopped, so
  // the queue above can never hang waiting on audio that will never finish.
  function playOne(a, url) {
    return new Promise((resolve) => {
      endPlaybackRef.current = resolve;
      a.onended = resolve;
      a.onerror = resolve;
      a.src = url;
      a.play().catch(resolve);
    });
  }

  // One place that undoes everything, so no path can leave a request running,
  // a flag set, or the queue awaiting a chunk that stopped.
  function stopSpeech() {
    activeRef.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
    const a = audioRef.current;
    if (a) {
      a.onended = null;
      a.onerror = null;
      a.pause();
    }
    endPlaybackRef.current?.();
    endPlaybackRef.current = null;
    setSpeakingIdx(null);
    setLoadingIdx(null);
  }

  // Stream the coach's reply to a question into a new assistant bubble, typing
  // it out live. Shared by typed and voice input.
  async function streamReply(question) {
    setLoading(true); // typing dots until the first token arrives
    try {
      const res = await authFetch(`${API}/agent/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
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
      // Ask the recorder what it actually produced rather than assuming: Chrome
      // gives webm, iOS Safari gives mp4, and mislabelling it means the
      // transcriber can't read the file at all.
      sendAudio(new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" }));
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
      // The name carries the format — the transcriber reads the extension to
      // know how to decode the bytes.
      form.append("audio", blob, `clip.${audioExtension(blob.type)}`);
      const res = await authFetch(`${API}/transcribe`, { method: "POST", body: form });
      if (!res.ok) throw new Error("transcription failed");
      text = (await res.json()).text;
    } catch {
      setLoading(false);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry — I couldn't hear that." },
      ]);
      return;
    }
    // Silence, or nothing the transcriber could make out: say so rather than
    // sending an empty message off to her.
    if (!text || !text.trim()) {
      setLoading(false);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "I didn't catch that — try again?" },
      ]);
      return;
    }
    setLoading(false);
    // On the mantra screen the microphone is a way of writing, not talking —
    // the words belong in the box, not in a conversation.
    if (view === "mantra") {
      setMantraDraft((prev) => (prev ? `${prev} ${text}` : text));
      return;
    }
    setMessages((prev) => [...prev, { role: "user", text }]);
    await streamReply(text);
  }

  // --- mantras: the lines you keep for the hard days ---

  async function saveMantra() {
    const text = mantraDraft.trim();
    if (!text) return;
    setMantraDraft("");
    const res = await authFetch(`${API}/mantras`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) return;
    const saved = await res.json();
    setMantras((prev) => [saved, ...prev]); // newest first
  }

  async function editMantra(id, text) {
    setEditingId(null);
    const trimmed = text.trim();
    if (!trimmed) return;
    const res = await authFetch(`${API}/mantras/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: trimmed }),
    });
    if (!res.ok) return;
    const saved = await res.json();
    setMantras((prev) => prev.map((m) => (m.id === id ? saved : m)));
  }

  async function removeMantra(id) {
    // Drop it from the screen first; putting it back on failure is kinder than
    // making someone wait to see a line disappear.
    const previous = mantras;
    setMantras((prev) => prev.filter((m) => m.id !== id));
    const res = await authFetch(`${API}/mantras/${id}`, { method: "DELETE" });
    if (!res.ok) setMantras(previous);
  }

  // Before the first auth check, show nothing to avoid a sign-in flash.
  if (!authReady) return null;

  // Signed out: a landing page that introduces the product, then sign-in.
  if (!user) {
    return (
      <div className="landing">
        <header className="lhero">
          <div className="lmark">◈</div>
          <h1>Minerva</h1>
          <p>
            A friend for the hard days. She steadies you when the fear takes
            over, helps you think when nothing is clear, and reminds you what
            you're capable of — because she's been keeping the record.
          </p>
          <button className="google" onClick={() => signInWithGoogle()}>
            Sign in with Google
          </button>
          <span className="lnote">Free to try · Your journal stays private</span>
        </header>

        <section className="lfeatures">
          <div className="lfeature">
            <span className="licon">❝</span>
            <h3>When the fear takes over</h3>
            <p>
              Say it out loud — she listens, and she doesn't rush you out of
              it. She names what's actually happening, then walks you back to
              steady ground.
            </p>
          </div>
          <div className="lfeature">
            <span className="licon">✦</span>
            <h3>When nothing feels clear</h3>
            <p>
              Think through it with someone who knows your whole story. She
              helps you separate what's true from what's fear, until the next
              step is obvious.
            </p>
          </div>
          <div className="lfeature">
            <span className="licon">☖</span>
            <h3>When you've forgotten yourself</h3>
            <p>
              She's been writing it all down. Every small thing you did while
              afraid — and what all of it proves about who you are.
            </p>
          </div>
        </section>

        <section className="lhow">
          <div className="lstep">
            <span className="lnum">01</span>
            <h4>Talk, don't type</h4>
            <p>
              Just speak. She transcribes what you said and answers in a warm,
              unhurried voice — the way a friend would.
            </p>
          </div>
          <div className="lstep">
            <span className="lnum">02</span>
            <h4>She remembers you</h4>
            <p>
              A living memory of your goals, patterns, and struggles, so every
              conversation starts further along than the last.
            </p>
          </div>
          <div className="lstep">
            <span className="lnum">03</span>
            <h4>Your record builds</h4>
            <p>
              Every small thing you did is kept — and folded into a picture of
              who you are that you can read on the bad days.
            </p>
          </div>
        </section>

        <footer className="lfoot">
          <p>
            Just in case no one told you yet today: I love you, and I believe in your ability to change your life for the better.
          </p>
          <button className="google" onClick={() => signInWithGoogle()}>
            Get started
          </button>
        </footer>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="head">
        <h1>Minerva</h1>
        <p className="creed">Just in case no one told you yet today: I love you, and I believe in your ability to change your life for the better.</p>
        <div className="who">
          <span>{user.displayName || user.email}</span>
          <button className="signout" onClick={() => signOutUser()}>
            Sign out
          </button>
        </div>
        <div className="tabs">
          <button
            className={view === "chat" ? "on" : ""}
            onClick={() => setView("chat")}
          >
            Talk
          </button>
          <button
            className={view === "wins" ? "on" : ""}
            onClick={() => setView("wins")}
          >
            Wins
          </button>
          <button
            className={view === "you" ? "on" : ""}
            onClick={() => setView("you")}
          >
            You
          </button>
          <button
            className={view === "mantra" ? "on" : ""}
            onClick={() => setView("mantra")}
          >
            Mantra
          </button>
        </div>
      </header>

      {view === "mantra" ? (
        <main className="chat mantra-view">
          <p className="winlede">Lines to come back to</p>

          <div className="mantra-add">
            <input
              value={mantraDraft}
              onChange={(e) => setMantraDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveMantra()}
              placeholder="Something worth remembering when it's hard…"
            />
            <button
              type="button"
              className={"mic" + (recording ? " on" : "")}
              onClick={toggleRecord}
              title={recording ? "Stop recording" : "Speak it instead"}
            >
              {recording ? "■" : "●"}
            </button>
            <button type="button" className="keep" onClick={saveMantra}>
              Keep
            </button>
          </div>

          {mantras.length === 0 && (
            <p className="empty">Nothing kept yet.</p>
          )}
          {mantras.map((m) => (
            <blockquote key={m.id} className="mantra">
              {editingId === m.id ? (
                <input
                  autoFocus
                  defaultValue={m.text}
                  onBlur={(e) => editMantra(m.id, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") editMantra(m.id, e.target.value);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                />
              ) : (
                <p onClick={() => setEditingId(m.id)} title="Click to reword">
                  {m.text}
                </p>
              )}
              <button
                type="button"
                className="drop"
                onClick={() => removeMantra(m.id)}
                title="Let it go"
              >
                ×
              </button>
            </blockquote>
          ))}
        </main>
      ) : view === "you" ? (
        <main className="chat you-view">
          {passage ? (
            <article className="passage">{passage}</article>
          ) : (
            <p className="empty">Keep talking — this takes a few days to form.</p>
          )}
        </main>
      ) : view === "wins" ? (
        <main className="chat wins-view">
          {wins.length === 0 && (
            <p className="empty">Your wins will show up here as you talk.</p>
          )}
          {groupByDay(wins).map(([day, items]) => (
            <section key={day} className="winday">
              <h3>{dayLabel(day)}</h3>
              <ul>
                {items.flatMap((e) => winLines(e.wins).map((line, i) => (
                  <li key={`${e.id}-${i}`}>{line}</li>
                )))}
              </ul>
            </section>
          ))}
        </main>
      ) : (
      <>
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
                onClick={() => playReply(m.text, i)}
                title={
                  loadingIdx === i || speakingIdx === i ? "Stop" : "Play aloud"
                }
                className={
                  "speak" + (loadingIdx === i ? " busy" : "")
                }
              >
                {loadingIdx === i ? (
                  <>
                    <WaitIcon />
                    Preparing her voice…
                  </>
                ) : speakingIdx === i ? (
                  <>
                    <StopIcon />
                    Stop
                  </>
                ) : (
                  <>
                    <PlayIcon />
                    Listen
                  </>
                )}
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
      </>
      )}
    </div>
  );
}
