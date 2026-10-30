import LangSwitch from "./LangSwitch.jsx";

export default function Intro({ session, t, lang, onLang, onStart }) {
  const { test, employee } = session;

  function start() {
    // To'liq ekran (fullscreen) so'rovi shu yerda — bevosita tugma bosilishi ichida chaqirilishi
    // shart (brauzer talabi), aks holda ishlamaydi. Rad etilsa ham testni davom ettiramiz.
    document.documentElement.requestFullscreen?.().catch(() => {});
    onStart();
  }

  return (
    <div className="card narrow">
      <div className="intro-lang-row">
        <LangSwitch lang={lang} onChange={onLang} />
      </div>
      <h1 className="h">{test.name}</h1>
      <p className="sub">{employee}</p>

      {test.introduction && <div className="intro-text">{test.introduction}</div>}

      <div className="intro-meta">
        {!!test.time_limit && (
          <div className="intro-meta-row">
            ⏱ {test.time_limit_scope === "question" ? t.time_per_question : t.time_whole_test}: {test.time_limit} {t.minutes}
          </div>
        )}
        <div className="intro-meta-row">✓ {t.pass_score}: {test.pass_percent}%</div>
      </div>

      <div className="hint">{t.leave_notice}</div>

      <button className="btn gold block" onClick={start}>{t.intro_start} →</button>
    </div>
  );
}
