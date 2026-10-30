import { useEffect, useRef, useState } from "react";
import { submit as submitApi, checkAnswer as checkAnswerApi, lockAnswer as lockAnswerApi } from "../api.js";
import { tx, matchLabel } from "../i18n.js";
import { loadProgress, saveProgress } from "../App.jsx";
import LangSwitch from "./LangSwitch.jsx";

const LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"];

export default function Quiz({ session, t, lang, onLang, onFinish, registerFinish }) {
  const { token, test, questions } = session;
  // Kviz odatda toza holatda ochiladi (sahifa yangilansa test yakunlanadi,
  // seans tiklanmaydi — App.jsx ga qarang). Bu yozuv faqat AYNAN shu seansga
  // tegishli bo'lsa o'qiladi (token solishtiriladi), ya'ni boshqa xodimning
  // eski yozuvi tasodifan qo'llanib ketmaydi.
  const saved = (() => {
    const p = loadProgress();
    return p && p.token === token ? p : null;
  })();

  const [idx, setIdx] = useState(saved?.idx ?? 0);
  const [answers, setAnswers] = useState(saved?.answers ?? {});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState(null);
  // Tekshirilgan savollar hukmi: {savol_id: true/false}. Faqat "darhol javobni
  // ko'rsatish" rejimida to'ladi — boshqa rejimda xodim javobning to'g'ri yoki
  // xatoligini test davomida umuman bilmaydi, shuning uchun bu bo'sh qoladi.
  // `feedback` har savol almashganda tozalanadi, bu esa saqlanib qoladi —
  // navigatorda oldingi savollarning rangi ko'rinib turishi uchun.
  const [verdicts, setVerdicts] = useState(saved?.verdicts ?? {});
  // Serverda qulflangan savollar — javobini o'zgartirib bo'lmaydi.
  const [locked, setLocked] = useState(() => {
    const fromServer = Object.keys(session.locked_answers || {}).map(Number);
    return new Set([...(saved?.locked ?? []), ...fromServer]);
  });

  // Ogohlantirish matnlari bir marta ulanadigan hodisa (event) ichida
  // ishlatiladi — o'sha paytdagi `t` ni "muzlatib" qolmasligi uchun ref orqali
  // olinadi, aks holda til almashtirilgandan keyin ham eski tildagi matn chiqardi.
  const tRef = useRef(t);
  tRef.current = t;

  const timingsRef = useRef(saved?.timings ?? {});
  const questionStartRef = useRef(Date.now());
  const violationsRef = useRef(saved?.violations ?? 0);
  // `flushTiming` taymer ichidan ham chaqiriladi; interval o'zi yaratilgan
  // paytdagi `idx` ni ushlab qolmasligi uchun joriy indeks ref orqali o'qiladi
  // (aks holda vaqt tugaganda oxirgi savolning vaqti 1-savolga yozilardi).
  const idxRef = useRef(idx);
  idxRef.current = idx;
  // Always points to the latest finish() so the timer callback doesn't capture stale answers
  const finishRef = useRef(null);
  const [warning, setWarning] = useState("");

  function flushTiming() {
    const qid = questions[idxRef.current].id;
    const elapsed = Math.max(0, Math.round((Date.now() - questionStartRef.current) / 1000));
    timingsRef.current[qid] = (timingsRef.current[qid] || 0) + elapsed;
    questionStartRef.current = Date.now();
  }

  useEffect(() => {
    function registerViolation(msg) {
      violationsRef.current += 1;
      setWarning(msg);
    }
    function onVisibility() {
      if (document.hidden) registerViolation(tRef.current.warn_tab);
    }
    function onFullscreenChange() {
      if (!document.fullscreenElement) registerViolation(tRef.current.warn_fullscreen);
    }
    function onBeforeUnload(e) { e.preventDefault(); e.returnValue = ""; }
    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      document.removeEventListener("fullscreenchange", onFullscreenChange);
      window.removeEventListener("beforeunload", onBeforeUnload);
      if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    };
  }, []);

  useEffect(() => {
    if (!warning) return;
    const id = setTimeout(() => setWarning(""), 5000);
    return () => clearTimeout(id);
  }, [warning]);

  useEffect(() => { setFeedback(null); }, [idx]);

  const strict = test.mode === "maksimal";
  // TZ: "Erkin — savollarga istalgan tartibda javob berish, o'tkazib yuborish
  // mumkin". Ya'ni savollar navigatori orqali istalgan savolga sakrash faqat shu
  // rejimda beriladi; "Oddiy"da ketma-ket (Orqaga/Keyingi) yuriladi, "Maksimal"da
  // esa orqaga qaytish ham yo'q.
  const freeJump = test.mode === "erkin";
  const totalSeconds = (test.time_limit || 0) * 60;
  const perQuestion = test.time_limit_scope === "question";

  // Har bir savol uchun qolgan vaqt: {savol id: soniya}. Savolga qayta kirilganda
  // vaqt TIKLANMAYDI — ilgari "Keyingi → Orqaga" bosib har savolga cheksiz vaqt
  // olish mumkin edi. Qiymatlar saqlanadi, shuning uchun F5 ham yordam bermaydi.
  const perQLeftRef = useRef(saved?.perQLeft ?? {});
  function initialLeft() {
    if (!totalSeconds) return 0;
    if (!perQuestion) {
      // Butun test uchun taymer server bergan o'tgan vaqtdan hisoblanadi —
      // sahifa yangilansa ham vaqt nolga qaytmaydi.
      return Math.max(0, totalSeconds - (session.elapsed_seconds || 0));
    }
    const qid = questions[idx]?.id;
    return perQLeftRef.current[qid] ?? totalSeconds;
  }
  const [left, setLeft] = useState(initialLeft);

  useEffect(() => {
    if (!totalSeconds) return;
    setLeft(initialLeft());
    const id = setInterval(() => {
      setLeft((s) => {
        const next = s - 1;
        if (perQuestion) perQLeftRef.current[questions[idxRef.current].id] = Math.max(0, next);
        if (next <= 0) {
          clearInterval(id);
          flushTiming();
          if (perQuestion && idxRef.current < questions.length - 1) {
            // Vaqti tugagan savol qulflanadi — keyin qaytib o'zgartirib bo'lmaydi.
            lockCurrent();
            setIdx((i) => i + 1);
          } else {
            // force=true — "Tekshirish" so'rovi ketayotgan bo'lsa ham yakunlanadi.
            finishRef.current?.(undefined, false, true);
          }
          return 0;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [perQuestion ? idx : 0, totalSeconds]);

  // Xodim oxirgi savolgacha yetib borganmi — shundan keyin orqaga qaytsa ham
  // "Yakunlash" tugmasi qo'lida qoladi.
  const [visitedLast, setVisitedLast] = useState(saved?.visitedLast ?? false);
  useEffect(() => {
    if (idx === questions.length - 1) setVisitedLast(true);
  }, [idx, questions.length]);

  const q = questions[idx];
  const isLocked = locked.has(q.id);
  const isText = q.qtype === "text" || q.qtype === "fillblank";
  const isOrdering = q.qtype === "ordering";
  const isMatching = q.qtype === "matching";
  const isLast = idx === questions.length - 1;
  const chosen = isText || isOrdering || isMatching ? [] : answers[q.id] || [];
  const textValue = isText ? answers[q.id] || "" : "";
  const orderList = isOrdering ? answers[q.id] || q.options.map((o) => o.id) : [];
  const matchAnswers = isMatching ? answers[q.id] || {} : {};

  // Javobni serverda qulflaydi va mahalliy holatga belgilaydi. Qulflangandan
  // keyin javob o'zgartirilmaydi — yakunlashda server aynan shu javobni oladi.
  function lockCurrent(questionId = questions[idxRef.current].id) {
    if (locked.has(questionId)) return;
    const value = answerFor(questionId);
    setLocked((prev) => new Set(prev).add(questionId));
    lockAnswerApi(token, questionId, value).catch(() => {});
  }

  function answerFor(questionId) {
    const qq = questions.find((x) => x.id === questionId);
    const a = answers[questionId];
    if (a !== undefined) return a;
    if (qq?.qtype === "text" || qq?.qtype === "fillblank") return "";
    if (qq?.qtype === "matching") return {};
    return [];
  }

  function toggle(optId) {
    if (isLocked) return;
    setAnswers((prev) => {
      const cur = prev[q.id] || [];
      if (q.qtype === "multiple") {
        const next = cur.includes(optId) ? cur.filter((x) => x !== optId) : [...cur, optId];
        return { ...prev, [q.id]: next };
      }
      return { ...prev, [q.id]: [optId] };
    });
  }

  function setText(value) {
    if (isLocked) return;
    setAnswers((prev) => ({ ...prev, [q.id]: value }));
  }

  function moveOrder(pos, dir) {
    if (isLocked) return;
    setAnswers((prev) => {
      const cur = prev[q.id] || q.options.map((o) => o.id);
      const j = pos + dir;
      if (j < 0 || j >= cur.length) return prev;
      const next = [...cur];
      [next[pos], next[j]] = [next[j], next[pos]];
      return { ...prev, [q.id]: next };
    });
  }

  function setMatch(leftId, value) {
    if (isLocked) return;
    setAnswers((prev) => ({ ...prev, [q.id]: { ...(prev[q.id] || {}), [leftId]: value } }));
  }

  // "Tartiblash" savolida xodim ekranda ko'rgan tartibni to'g'ri deb qoldirsa,
  // ilgari javob umuman yuborilmasdi va savol javobsiz/xato deb belgilanardi.
  // Shuning uchun savol ochilishi bilan ko'rsatilgan tartib javob sifatida yoziladi.
  useEffect(() => {
    if (q.qtype !== "ordering" || answers[q.id] !== undefined) return;
    setAnswers((prev) => ({ ...prev, [q.id]: q.options.map((o) => o.id) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);

  // Joriy javob/vaqt/buzilishlar brauzerda saqlanadi — bu SEANSNI TIKLASH uchun
  // EMAS (test davomida F5 taqiqlangan), balki App.jsx sahifa yangilanganda
  // testni AYNAN shu ondagi javoblar bilan majburan yakunlashi (interrupted
  // submit) uchun. `started: true` — bu yozuv kviz ekranida saqlanayotganini
  // bildiradi (App.jsx StartGate'dagi yangilanishdan shu bilan ajratadi).
  useEffect(() => {
    saveProgress({
      token, lang, idx, answers, started: true,
      timings: timingsRef.current,
      violations: violationsRef.current,
      perQLeft: perQLeftRef.current,
      locked: [...locked],
      verdicts,
      visitedLast,
    });
  }, [idx, answers, locked, verdicts, lang, token, visitedLast]);

  function goNext() {
    flushTiming();
    // Maksimal rejimda orqaga qaytish yo'q — savol ortda qolgach javobi
    // serverda qulflanadi, ya'ni cheklov endi brauzerda emas, serverda ham amal qiladi.
    if (strict) lockCurrent(q.id);
    if (idx < questions.length - 1) setIdx(idx + 1);
  }

  function goPrev() {
    flushTiming();
    if (idx > 0) setIdx(idx - 1);
  }

  function goToQuestion(i) {
    if (i === idx || !freeJump) return;
    flushTiming();
    setIdx(i);
  }

  function isAnswered(qid) {
    const a = answers[qid];
    if (a === undefined) return false;
    if (Array.isArray(a)) return a.length > 0;
    if (a && typeof a === "object") return Object.keys(a).length > 0;
    if (typeof a === "string") return a.trim() !== "";
    return false;
  }

  function currentAnswer() {
    if (isText) return answers[q.id] || "";
    if (isMatching) return answers[q.id] || {};
    return answers[q.id] || [];
  }

  async function checkCurrent(overrideAnswer) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await checkAnswerApi(
        token, q.id, overrideAnswer !== undefined ? overrideAnswer : currentAnswer(), lang,
      );
      setFeedback(res);
      // Hukm navigatorda ham ko'rinadi: to'g'ri — yashil, xato — qizil.
      setVerdicts((prev) => ({ ...prev, [q.id]: !!res?.is_correct }));
      // Server javobni qulfladi (to'g'ri javobni ko'rsatishdan oldin) — mijozda
      // ham variantlarni bloklaymiz, aks holda xodim javobni ko'rib, keyin
      // to'g'rilab yuborardi va bu rejimda hamma 100% olardi.
      if (res?.locked) setLocked((prev) => new Set(prev).add(q.id));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // Yakunlash bir martagina yuborilsin: tugma ikki marta bosilsa yoki javob
  // kechiksa, ikkinchi so'rov ketmaydi. Server tomonida ham himoya bor
  // (takroriy so'rov yangi natija yaratmaydi), bu esa birinchi to'siq.
  const finishingRef = useRef(false);

  // `force` — taymer tugaganda yoki video nazorat uzilganda chaqiriladi.
  // Bunday chaqiriq `busy` (masalan, ayni damda ketayotgan "Tekshirish"
  // so'rovi) sababli QAYTMASLIGI shart: taymer intervali allaqachon
  // to'xtatilgan bo'ladi va yakunlashni boshqa hech kim chaqirmaydi — test
  // 00:00 da ochiq qolib ketardi. Takroriy yuborishdan `finishingRef` saqlaydi.
  async function finish(overrideAnswers, shareStopped, force) {
    if ((busy && !force) || finishingRef.current) return;
    finishingRef.current = true;
    flushTiming();
    setBusy(true);
    setError("");
    try {
      const res = await submitApi(
        token,
        overrideAnswers !== undefined ? overrideAnswers : answers,
        timingsRef.current,
        violationsRef.current,
        shareStopped,
        lang,
      );
      onFinish(res);
    } catch (e) {
      finishingRef.current = false;
      setError(e.message);
      setBusy(false);
    }
  }

  // Updated every render so the timer always calls the latest finish (with current answers)
  finishRef.current = finish;
  registerFinish?.(finish);

  // "Keyingi"/"Yakunlash" tugmasi: agar test "Noto'g'ri javobni darhol
  // bildirish" bilan sozlangan bo'lsa va bu savol hali tekshirilmagan bo'lsa —
  // birinchi bosishda faqat natija (to'g'ri/noto'g'ri) ko'rsatiladi, savol
  // o'zgarmaydi; ikkinchi bosishda (natija allaqachon ko'rsatilgan bo'lgani
  // uchun) haqiqatan keyingi savolga o'tadi.
  // Savol allaqachon tekshirilgan (javobi qulflangan) bo'lsa, qayta "Tekshirish"
  // taklif qilinmaydi — xodim orqaga qaytganda darhol "Keyingi"/"Yakunlash"
  // tugmasini ko'radi, aks holda o'sha savolda ikki marta bosishga majbur bo'lardi.
  const needsCheck = test.instant_feedback && !feedback && !isLocked;

  async function handleNextClick() {
    if (needsCheck) {
      await checkCurrent();
      return;
    }
    goNext();
  }

  async function handleFinishClick() {
    if (needsCheck) {
      await checkCurrent();
      return;
    }
    finish();
  }

  function dontKnow() {
    if (isLocked) { goNext(); return; }
    const cleared = isText ? "" : isMatching ? {} : [];
    const next = { ...answers, [q.id]: cleared };
    setAnswers(next);
    // On last question: submit immediately with the just-cleared answer
    if (isLast) finish(next);
    else goNext();
  }

  const mm = String(Math.floor(left / 60)).padStart(2, "0");
  const ss = String(left % 60).padStart(2, "0");

  return (
    <div className="card">
      <div className="qbar">
        <span>{t.question} {idx + 1} {t.of} {questions.length}</span>
        <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <LangSwitch lang={lang} onChange={onLang} />
          {!!totalSeconds && (
            <span className={"timer" + (left <= 30 ? " warn" : "")}>⏱ {mm}:{ss}</span>
          )}
        </span>
      </div>

      <div className="qnav">
        {questions.map((qq, i) => {
          const answered = isAnswered(qq.id);
          // Hukm ma'lum bo'lsa (darhol javob rejimi) rang aynan shundan
          // olinadi: to'g'ri — yashil, xato — qizil. Hukm yo'q bo'lsa,
          // avvalgidek "javob berilgan" belgisi qoladi. Javob berilmagan
          // savol esa hech qanday rang olmaydi.
          const verdict = verdicts[qq.id];
          const cls = "qnav-item"
            + (i === idx ? " current" : "")
            + (verdict === true ? " correct"
              : verdict === false ? " wrong"
              : answered ? " answered" : "");
          const state = verdict === true ? t.correct_excl
            : verdict === false ? t.wrong_excl
            : answered ? t.answered : "";
          return (
            <button
              key={qq.id}
              type="button"
              className={cls}
              onClick={() => goToQuestion(i)}
              disabled={!freeJump}
              title={state ? `${t.question} ${i + 1} — ${state}` : `${t.question} ${i + 1}`}
            >
              {i + 1}
            </button>
          );
        })}
      </div>

      {warning && <div className="alert">{warning}</div>}

      {q.group_name && <div className="qgroup">{q.group_name}</div>}
      <div className="qtext">{tx(q, lang)}</div>
      {q.image && <img className="qimg" src={q.image} alt="" />}
      {q.qtype === "multiple" && <div className="hint">{t.multi_hint}</div>}

      {/* Javob qulflanganda hech qanday xabar chiqmaydi — variantlar shunchaki
          bosilmaydigan holatga o'tadi. */}
      {isText ? (
        <input
          className="field"
          value={textValue}
          onChange={(e) => setText(e.target.value)}
          placeholder={t.your_answer}
          autoComplete="off"
          disabled={isLocked}
        />
      ) : isOrdering ? (
        <div className={"order-list" + (isLocked ? " is-locked" : "")}>
          {orderList.map((optId, pos) => {
            const opt = q.options.find((o) => o.id === optId);
            return (
              <div className="order-item" key={optId}>
                <span className="order-num">{pos + 1}</span>
                <span>{tx(opt, lang)}</span>
                <div className="order-btns">
                  <button onClick={() => moveOrder(pos, -1)} disabled={isLocked || pos === 0}>↑</button>
                  <button onClick={() => moveOrder(pos, 1)} disabled={isLocked || pos === orderList.length - 1}>↓</button>
                </div>
              </div>
            );
          })}
        </div>
      ) : isMatching ? (
        <div className="match-list">
          {q.options.map((o) => (
            <div className="match-row" key={o.id}>
              <span className="match-left">{tx(o, lang)}</span>
              <select
                className="field"
                value={matchAnswers[o.id] || ""}
                onChange={(e) => setMatch(o.id, e.target.value)}
                disabled={isLocked}
              >
                <option value="">{t.select_ph}</option>
                {q.match_options.map((mv, i) => (
                  <option key={i} value={mv}>{matchLabel(q, mv, lang)}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      ) : (
        <div className="opts">
          {q.options.map((o, i) => {
            const sel = chosen.includes(o.id);
            return (
              <button
                key={o.id}
                className={"opt" + (sel ? " sel" : "") + (isLocked ? " locked" : "")}
                onClick={() => toggle(o.id)}
                disabled={isLocked}
              >
                <span className="key">{LETTERS[i]}</span>
                {/* Variantda rasm, matn yoki ikkalasi ham bo'lishi mumkin.
                    Rasm o'lchami CSS bilan cheklangan — katta fayl ham
                    variant ramkasidan chiqib ketmaydi. */}
                <span className="opt-body">
                  {/* `loading="lazy"` ATAYLAB yo'q: bir vaqtda bitta savol
                      ko'rsatiladi, ya'ni rasm bir nechta. Kechikib yuklanishi
                      esa vaqti cheklangan testda rasm "sakrab" chiqishiga
                      olib kelardi. */}
                  {o.image_url && <img className="opt-img" src={o.image_url} alt="" />}
                  {tx(o, lang) && <span className="opt-text">{tx(o, lang)}</span>}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {feedback && (
        <div className={"alert " + (feedback.is_correct ? "ok" : "")}>
          <b>{feedback.is_correct ? `✓ ${t.correct_excl}` : `✗ ${t.wrong_excl}`}</b>{" "}
          {feedback.given_text !== undefined && !feedback.is_correct &&
            <>{t.correct_answer}: {feedback.correct_text}</>}
          {feedback.given_order !== undefined && !feedback.is_correct &&
            <>{t.correct_answer}: {feedback.correct_order.join(" → ")}</>}
          {/* To'g'ri variantlar. Rasm ham ko'rsatiladi — aks holda rasmli
              (matnsiz) variantda "To'g'ri javob:" dan keyin bo'sh joy qolardi. */}
          {feedback.options !== undefined && !feedback.is_correct && (
            <>
              {t.correct_answer}:{" "}
              <span className="fb-correct">
                {feedback.options.filter((o) => o.is_correct).map((o, i) => (
                  <span className="fb-correct-item" key={i}>
                    {o.image && <img className="opt-img" src={o.image} alt="" />}
                    {o.text && <span>{o.text}</span>}
                  </span>
                ))}
              </span>
            </>
          )}
          {feedback.pairs !== undefined && (
            <div className="rev">
              {feedback.pairs.map((p, i) => (
                <div key={i} className={"rev-line " + (p.is_correct ? "good" : "wrong")}>
                  {p.left}: {p.chosen || "—"}{!p.is_correct && ` — ${p.correct}`}
                </div>
              ))}
            </div>
          )}
          {feedback.explanation && <div className="rev-exp">ℹ {feedback.explanation}</div>}
        </div>
      )}

      {error && <div className="alert">{error}</div>}

      <div className="btnrow" style={{ justifyContent: "space-between" }}>
        <div>
          {!strict && (
            <button className="btn ghost" onClick={goPrev} disabled={idx === 0}>
              ← {t.prev}
            </button>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {!strict && (
            <button className="btn ghost" onClick={dontKnow}>{t.dont_know}</button>
          )}
          {isLast ? (
            <button className="btn gold" onClick={handleFinishClick} disabled={busy}>
              {needsCheck ? t.check : `${t.finish} ✓`}
            </button>
          ) : (
            <>
              <button className="btn" onClick={handleNextClick} disabled={busy}>
                {needsCheck ? t.check : `${t.next} →`}
              </button>
              {/* Orqaga qaytilgan bo'lsa, oxirgi savolga qadar bosib borish shart
                  emas — testni shu yerdan ham yakunlash mumkin. */}
              {visitedLast && !needsCheck && (
                <button className="btn gold" onClick={() => finish()} disabled={busy}>
                  {t.finish} ✓
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
