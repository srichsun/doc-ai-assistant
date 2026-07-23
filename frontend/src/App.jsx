import { useCallback, useEffect, useState } from "react";
import "./App.css";
import Greeting from "./Greeting";
import Landing from "./Landing";
import Ask from "./tabs/Ask";
import Insights from "./tabs/Insights";
import Mantras from "./tabs/Mantras";
import Record from "./tabs/Record";
import { onAuthChange, signOutUser } from "./firebase";

const TABS = [
  { key: "record", label: "Record", Screen: Record },
  { key: "reading", label: "Reading", Screen: Insights },
  { key: "ask", label: "Ask", Screen: Ask },
  { key: "mantra", label: "Mantras", Screen: Mantras },
];

// Today, in Taiwan time — the same day the backend means. Working it out here
// rather than asking the server keeps the screen from disagreeing with itself
// while a request is in flight.
function todayInTaipei() {
  const now = new Date();
  const taipei = new Date(now.getTime() + (now.getTimezoneOffset() + 480) * 60000);
  return taipei.toISOString().slice(0, 10);
}

export default function App() {
  const [user, setUser] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [tab, setTab] = useState("record");
  const [greeted, setGreeted] = useState(false);

  useEffect(
    () =>
      onAuthChange((u) => {
        setUser(u);
        setAuthReady(true);
      }),
    [],
  );

  const finishGreeting = useCallback(() => setGreeted(true), []);

  // A new screen starts at its top. Without this you arrive halfway down it,
  // at whatever depth the last screen happened to be scrolled to.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [tab]);

  // Before the first auth check, show nothing to avoid a sign-in flash.
  if (!authReady) return null;
  if (!user) return <Landing />;
  if (!greeted) return <Greeting onDone={finishGreeting} />;

  const { Screen } = TABS.find((t) => t.key === tab);

  return (
    <div className="app">
      <header className="head">
        <h1>Dear Myself</h1>
        <button className="signout" onClick={() => signOutUser()}>
          Sign out
        </button>
      </header>

      <Screen today={todayInTaipei()} />

      <nav className="tabbar">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? "on" : ""}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
