import { useEffect, useRef, useState } from "react";
import FaceLogin from "./pages/FaceLogin.jsx";
import ManualLogin from "./pages/ManualLogin.jsx";
import StartGate from "./pages/StartGate.jsx";
import Quiz from "./pages/Quiz.jsx";
import ResultView from "./pages/Result.jsx";
import { useT } from "./i18n.js";
import { stopProctoring, startLiveShare, stopLiveShare } from "./proctoring.js";
import { createRecordingUploader, reportRecordingDuration, submit as submitTest } from "./api.js";
import { API_BASE } from "./api.js";

// Test jarayoni brauzerda saqlanadi — sahifa yangilansa (F5), tasodifan yopilib
// qayta ochilsa yoki brauzer qayta ishga tushsa, xodim testni BOSHIDAN emas,
// o'sha joyidan davom ettiradi. Saqlanmagan paytda xodim F5 bosib yangi seans
// ochishi, taymerni nolga qaytarishi va boshqa savollarni olishi mumkin edi.
const PROGRESS_KEY = "bnpztest_progress";

// "Admin meni ko'rmoqchimi?" so'rovining oralig'i.
//
// Ilgari 3 soniya edi va HAR BIRI bazaga borardi — 20 xodimda sekundiga ~7 ta
// keraksiz baza ulanishi. Endi server javobni xotiradan beradi (1.1 ms), ya'ni
// so'rovning narxi deyarli yo'q va oraliqni uzoq qilishning zarurati qolmadi.
//
// 5 soniya ikki talab orasidagi muvozanat:
//   • admin "Ko'rish" ni bosgach ekran tez ochilsin;
//   • bu oraliq serverdagi `_LIVE_WANT_TTL` (15 s) dan SEZILARLI kichik
//     bo'lsin — aks holda xodim "admin kutyapti" belgisini ko'rmay qolib,
//     jonli ekran umuman ochilmasdi. Hozir zaxira uch barobar.
const LIVE_STATUS_POLL_MS = 5000;

export function loadProgress() {
  try {
    return JSON.parse(localStorage.getItem(PROGRESS_KEY) || "null");
  } catch {
    return null;
  }
}
export function saveProgress(data) {
  try {
    localStorage.setItem(PROGRESS_KEY, JSON.stringify(data));
  } catch { /* xotira to'lgan bo'lsa — test baribir davom etaveradi */ }
}
export function clearProgress() {
  try {
    localStorage.removeItem(PROGRESS_KEY);
  } catch { /* e'tiborsiz */ }
}

export default function App() {
  // Saqlangan jarayon bor-yo'qligi darhol tekshiriladi, shunda tiklash paytida
  // kirish sahifasi bir zumga "chaqnab" ketmaydi.
  const [restoring, setRestoring] = useState(() => !!loadProgress()?.token);
  // Oqim qisqartirildi: ilgari login -> oferta -> ruxsat -> kirish -> test edi;
  // endi oferta, video nazorat ruxsati va boshlash BITTA sahifada (StartGate).
  const [screen, setScreen] = useState("login"); // login | start | quiz | result
  const [loginMode, setLoginMode] = useState("face"); // face | manual
  const [session, setSession] = useState(null);
  const [result, setResult] = useState(null);
  const recRef = useRef(null);       // ekran/kamera yozuvi holati (proctoring.js)
  // Video bo'laklarini test davomida yuborib turadigan yuklovchi (api.js).
  // Yozuv boshlanganda StartGate yaratadi, chunki bo'lak birinchi marta
  // o'sha yerda — proctoring boshlangandan 10 soniya keyin — paydo bo'ladi.
  const uploaderRef = useRef(null);
  const liveRef = useRef(null);      // WebRTC jonli ulash holati
  const liveStartingRef = useRef(false); // ikki marta start olmasligi uchun
  const quizFinishRef = useRef(null);    // Quiz'ning joriy finish() funksiyasi (majburiy to'xtatish uchun)
  const forceStoppedRef = useRef(false); // ekran/kamera ruxsati bekor qilinganda faqat bir marta ishlasin

  // Til xodim profilidan boshlanadi, lekin test davomida o'zgartirilishi mumkin —
  // shuning uchun seansdan olinadigan qiymat emas, alohida holat.
  const [lang, setLang] = useState("uz");
  const t = useT(lang);

  function handleLogin(data) {
    forceStoppedRef.current = false;
    setLang(data.language || "uz");
    setSession(data);
    saveProgress({ token: data.token, lang: data.language || "uz" });
    setScreen("start");
  }

  // Test davomida sahifa yangilangan (yoki brauzer yopilib qayta ochilgan) —
  // TESTGA QAYTISH YO'Q. Saqlangan jarayon topilsa, test o'sha ondagi javoblar
  // bilan darhol yakunlanadi va xodim to'g'ridan-to'g'ri natija ekranini ko'radi.
  //
  // Ilgari bu yerda seans tiklanardi va xodim o'sha joyidan davom etardi.
  // Endi yangilash testni tugatadi: server ham buni mustahkamlaydi —
  // `/employee/session/` 410 qaytaradi va tashlab ketilgan seans keyingi
  // urinishda davom ettirilmaydi, majburan yakunlanadi.
  useEffect(() => {
    const saved = loadProgress();
    if (!saved?.token) return;
    // Test HALI BOSHLANMAGAN bo'lsa (xodim StartGate — oferta/ruxsat sahifasida
    // yangilagan) uni majburan yakunlamaymiz: aks holda bitta savolga ham javob
    // bermay 0% "yiqilardi". Kirish sahifasiga qaytamiz; boshlanmagan seans
    // keyin o'zi "stale" bo'ladi (yoki admin qayta boshlab beradi). "started"
    // bayrog'i faqat kviz ekraniga o'tilganda qo'yiladi (handleStartReady/Quiz).
    if (!saved.started) { clearProgress(); setRestoring(false); return; }
    let cancelled = false;
    submitTest(
      saved.token,
      saved.answers || {},
      saved.timings || {},
      saved.violations || 0,
      false,          // ekran ulashish sababli emas
      saved.lang || "uz",
      true,           // interrupted — sahifa yangilangani sababli
    )
      .then((res) => {
        if (cancelled) return;
        setLang(saved.lang || "uz");
        setResult(res);
        setScreen("result");
      })
      .catch(() => {
        // Seans topilmadi/eskirgan — kirish sahifasiga tushamiz.
        if (!cancelled) clearProgress();
      })
      .finally(() => {
        // Jarayon har qanday holatda tozalanadi: shu tokenga qayta urinish yo'q.
        clearProgress();
        if (!cancelled) setRestoring(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // StartGate'da ruxsatlar berilib bo'lgach chaqiriladi — test darhol boshlanadi.
  function handleStartReady() {
    // Diqqat: bu yerda oldindan ("hech kim hali tomosha qilmayotganda") live-share
    // boshlanmaydi — buni faqat pastdagi polling (admin_wants_view'ni kuzatuvchi)
    // qiladi. Ikkalasi ham ishlaganida, admin ba'zan BIRINCHI (hali hech kim
    // ulanmagan) taklifga bog'lanib qolar, keyin xodim uni yangisiga almashtirganda
    // admin eski, endi o'lik ulanishda ICE'ni abadiy kutib qolardi ("ICE
    // tekshirilmoqda…" ilib qoladi, hech qachon ulanmaydi).
    // Ekran ulashish yoki kamera ruxsati test davomida bekor qilinsa (brauzerning
    // "Stop sharing" tugmasi yoki qurilma uzilib qolishi), video nazorat butunlay
    // to'xtaganini bildiradi — test darhol (joriy javoblar bilan) yakunlanadi.
    const onEnded = () => {
      if (forceStoppedRef.current || !quizFinishRef.current) return;
      forceStoppedRef.current = true;
      window.alert("Video nazorat (ekran yoki kamera) to'xtatildi. Test darhol yakunlanadi.");
      // force=true — boshqa so'rov ketayotgan bo'lsa ham majburan yakunlanadi.
      quizFinishRef.current(undefined, true, true);
    };
    [recRef.current?.screenStream, recRef.current?.faceStream].forEach((s) => {
      s?.getTracks().forEach((tr) => { tr.onended = onEnded; });
    });
    // "started" — endi test haqiqatan boshlandi. Shundan keyingina sahifa
    // yangilansa test majburan yakunlanadi (yuqoridagi restoring effektiga qarang).
    saveProgress({ ...(loadProgress() || {}), token: session.token, lang, started: true });
    setScreen("quiz");
  }
  async function handleFinish(res) {
    quizFinishRef.current = null;
    clearProgress(); // test yakunlandi — saqlangan jarayon endi kerak emas
    stopLiveShare(liveRef.current);
    liveRef.current = null;
    liveStartingRef.current = false;
    const recordingStartedAt = recRef.current?.startedAt;
    if (recRef.current) {
      // `stop()` oxirgi bo'lakni chiqaradi va u yuklovchi navbatiga tushadi.
      await stopProctoring(recRef.current);
      recRef.current = null;
    }
    // Navbat fonda tugaydi — natija ekranini kutib turmaymiz. Videoning
    // katta qismi test davomida allaqachon serverga yetib borgan, bu yerda
    // faqat oxirgi bo'lak qoladi (~10 soniya).
    const uploadQueue = uploaderRef.current?.finish();
    // Davomiylik xabari OXIRGI bo'lak yetib borguncha KUTADI (lekin natija
    // ekranini emas — shu funksiya bilan parallel, fonda): server buni
    // faylning o'zida saqlaydi, keyin birinchi ko'rilganda sarlavhaga
    // yozadi. Agar bo'lakdan OLDIN yetib borsa, server hali fayl mavjud
    // bo'lmagan yozuvni topa olmasligi yoki noyaxlit faylni tuzatib
    // qo'yishga urinishi mumkin edi.
    if (recordingStartedAt && uploadQueue) {
      const durationMs = Date.now() - recordingStartedAt;
      uploadQueue
        .then(() => reportRecordingDuration(session.token, "screen", durationMs))
        .catch(() => {});
    }
    uploaderRef.current = null;
    setResult(res);
    setScreen("result");
  }
  function handleHome() {
    clearProgress();
    setSession(null);
    setResult(null);
    setScreen("login");
  }

  // Proctoring ruxsat berilgan har qanday bosqichda (intro/quiz — video
  // nazorat "proctor" bosqichidan keyin darhol yoqiladi) admin ko'rish
  // so'rovini kuzatamiz. Live-share FAQAT shu yerda, faqat admin haqiqatan
  // ham tomosha qilmoqchi bo'lganda boshlanadi — bu yagona joy, shuning
  // uchun ikkita raqobatlashuvchi ulanish yaralish ehtimoli yo'q.
  // Interval har doim yoqiladi; canvasStream mavjudligini ichkarida tekshiramiz.
  useEffect(() => {
    // Jonli ko'rish faqat test ketayotganda mumkin — video nazorat oqimi
    // (canvasStream) endi aynan test boshlanish onida paydo bo'ladi.
    if (!session || screen !== "quiz") return;
    const token = session.token;

    const id = setInterval(async () => {
      // Ulanish jarayonida bo'lsa — skip
      if (liveStartingRef.current) return;
      // Proctoring bo'lmasa canvasStream yo'q — live view imkonsiz
      if (!recRef.current?.canvasStream) return;
      try {
        const res = await fetch(
          `${API_BASE}/employee/live/status/?token=${encodeURIComponent(token)}`,
          { cache: "no-store" },
        );
        const data = await res.json().catch(() => ({}));
        // Aloqa allaqachon ulangan bo'lsa, qayta boshlash shart emas — bu
        // holat "admin_wants_view" bayrog'i (backend'dagi eskirgan/qo'sh
        // so'rovdan) noto'g'ri qayta true bo'lib qolganda ham, ishlab
        // turgan ulanishni keraksiz uzib-ulashning oldini oladi.
        const alreadyConnected = liveRef.current?.pc?.connectionState === "connected";
        if (data.admin_wants_view && !alreadyConnected) {
          // Eski ulanishni to'xtatib (mavjud bo'lsa), yangi boshlаymiz
          stopLiveShare(liveRef.current);
          liveRef.current = null;
          liveStartingRef.current = true;
          startLiveShare(token, recRef.current.canvasStream)
            .then((live) => { liveRef.current = live; liveStartingRef.current = false; })
            .catch(() => { liveStartingRef.current = false; });
        }
      } catch { /* tarmoq xatosi — keyingi siklda qayta urinamiz */ }
    }, LIVE_STATUS_POLL_MS);

    return () => clearInterval(id);
  }, [screen, session]);

  if (restoring) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <div className="face-status">
            <div className="spinner" />
            <p>{t.loading}</p>
          </div>
        </div>
      </div>
    );
  }

  if (screen === "login") {
    return loginMode === "face"
      ? <FaceLogin onLogin={handleLogin} onSwitch={() => setLoginMode("manual")} />
      : <ManualLogin onLogin={handleLogin} onSwitch={() => setLoginMode("face")} />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <span className="logo">Bnpz<span>Test</span></span>
      </header>
      {/* Test ishlash ekrani kengroq panelда — variantlarga ko'proq joy
          beradi, ya'ni ular pastga cho'zilmasdan kengroq ko'rinadi. */}
      <main className={"container" + (screen === "quiz" ? " quiz-wide" : "")}>
        {screen === "start" && (
          <StartGate
            session={session} t={t} lang={lang} onLang={setLang}
            recRef={recRef} uploaderRef={uploaderRef} onStart={handleStartReady}
          />
        )}
        {screen === "quiz" && (
          <Quiz
            session={session} t={t} lang={lang} onLang={setLang} onFinish={handleFinish}
            registerFinish={(fn) => { quizFinishRef.current = fn; }}
          />
        )}
        {screen === "result" && <ResultView result={result} t={t} onHome={handleHome} />}
      </main>
    </div>
  );
}
