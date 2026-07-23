import { useState } from "react";
import { signInWithGoogle } from "./firebase";

// The signed-out page. It has one job: say what this is for, in the voice the
// app itself uses, and get out of the way.
//
// Bilingual: the copy is kept as {en, zh} pairs and a small toggle switches
// between them. The default follows the browser — a Traditional-Chinese visitor
// lands in Chinese without hunting for a switch. English is the fallback for
// everyone else.
const COPY = {
  lede: {
    en: "A quiet place to write the day down, and a way to read it back — so you can see what actually lifts you, and what keeps taking more than it gives.",
    zh: "一個安靜寫下這一天的地方，也是一種把它讀回去的方式 —— 讓你看清楚什麼真的讓你有力氣，什麼一直拿走的比給的多。",
  },
  cta: { en: "Continue with Google", zh: "用 Google 繼續" },
  note: { en: "Free to try · Your journal stays yours", zh: "免費試用 · 你的日記只屬於你" },
  features: [
    {
      title: { en: "One day, one page", zh: "一天，一頁" },
      body: {
        en: "Write once, at the end of the day. No feed, no streak, nothing to keep up with. When the day is done, it's done.",
        zh: "一天寫一次，在結束的時候。沒有動態牆、沒有連續天數、沒有要追趕的東西。一天過完了，就過完了。",
      },
    },
    {
      title: { en: "Your energy, in colour", zh: "你的能量，用顏色看" },
      body: {
        en: "Rate the day and watch the weeks take shape. The pattern you can't see from inside a hard week is obvious from a month away.",
        zh: "為一天打個分數，看著這幾週慢慢成形。難熬的那一週裡看不見的模式，退一個月看就一目了然。",
      },
    },
    {
      title: { en: "What you did, kept", zh: "你做到的事，被留下來" },
      body: {
        en: "Every win and every kindness is pulled out and held onto — so on the days you've forgotten who you are, there's a record to show you.",
        zh: "每一個勝利、每一份善意都會被挑出來留住 —— 所以在你忘了自己是誰的那些日子，有一份紀錄能拿出來給你看。",
      },
    },
  ],
  creed: {
    en: "Just in case no one has told you yet today: you are doing better than you think.",
    zh: "以防今天還沒有人告訴你：你做得比你以為的還要好。",
  },
  begin: { en: "Begin", zh: "開始" },
};

function browserDefault() {
  // Any Chinese locale lands in Chinese; everyone else in English.
  const langs = navigator.languages || [navigator.language || "en"];
  return langs.some((l) => l.toLowerCase().startsWith("zh")) ? "zh" : "en";
}

export default function Landing() {
  const [lang, setLang] = useState(browserDefault);
  const t = (pair) => pair[lang];

  return (
    <div className="landing">
      <button
        className="langtoggle"
        onClick={() => setLang(lang === "en" ? "zh" : "en")}
      >
        {lang === "en" ? "中文" : "English"}
      </button>

      <header className="lhero">
        <div className="lmark">◈</div>
        <h1>Dear Myself</h1>
        <p className="llede">{t(COPY.lede)}</p>
        <button className="primary" onClick={() => signInWithGoogle()}>
          {t(COPY.cta)}
        </button>
        <span className="lnote">{t(COPY.note)}</span>
      </header>

      <section className="lfeatures">
        {COPY.features.map((f, i) => (
          <div className="lfeature" key={i}>
            <span className="lnum">0{i + 1}</span>
            <h3>{t(f.title)}</h3>
            <p>{t(f.body)}</p>
          </div>
        ))}
      </section>

      <footer className="lfoot">
        <p className="creed">{t(COPY.creed)}</p>
        <button className="primary" onClick={() => signInWithGoogle()}>
          {t(COPY.begin)}
        </button>
      </footer>
    </div>
  );
}
