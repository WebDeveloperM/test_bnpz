import { useEffect, useState } from "react";
import { getSettings, acceptOffer, createRecordingUploader } from "../api.js";
import { startProctoring } from "../proctoring.js";
import LangSwitch from "./LangSwitch.jsx";

// YAGONA boshlash sahifasi. Ilgari xodim uch sahifadan o'tardi:
// oferta (OfferGate) -> video nazorat ruxsati (ProctorGate) -> kirish (Intro).
// Endi hammasi bitta kartada: test haqida ma'lumot, oferta (sozlangan bo'lsa)
// va BITTA tugma — bosilganda rozilik qayd etiladi, brauzer ruxsatlari
// so'raladi va test darhol boshlanadi.
export default function StartGate({ session, t, lang, onLang, recRef, uploaderRef, onStart }) {
  const { test, employee, token } = session;

  // Oferta sozlanmagan bo'lsa (matn ham, video ham yo'q) — bo'limi umuman
  // ko'rsatilmaydi va rozilik so'ralmaydi (avvalgi OfferGate ham shunday edi).
  const [offer, setOffer] = useState(null);
  const [offerLoaded, setOfferLoaded] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getSettings()
      .then((s) => {
        if (s.offer_text || s.offer_video_url) {
          setOffer({ text: s.offer_text, video: s.offer_video_url });
        }
      })
      .catch(() => { /* oferta o'qilmasa — bu qadamsiz davom etamiz */ })
      .finally(() => setOfferLoaded(true));
  }, []);

  const canStart = offerLoaded && (!offer || agreed) && !busy;

  async function start() {
    if (!canStart) return;
    setBusy(true);
    setError("");
    // To'liq ekran so'rovi BEVOSITA bosish ichida, async ishlardan OLDIN
    // bo'lishi shart (brauzer talabi) — ruxsat so'rovlaridan keyin chaqirilsa,
    // brauzer uni "foydalanuvchi harakati emas" deb rad etadi.
    document.documentElement.requestFullscreen?.().catch(() => {});
    // Rozilik faqat audit uchun qayd etiladi — javobini kutish shart emas,
    // xato bo'lsa ham test to'xtamaydi (avvalgi OfferGate bilan bir xil).
    if (offer) acceptOffer(token).catch(() => {});
    try {
      if (test.proctoring) {
        // Har bir video bo'lagi tayyor bo'lishi bilan darhol serverga ketadi —
        // test tugashini kutmaydi. Yuklovchi birinchi bo'lakda yaratiladi,
        // chunki format (mimeType) faqat proctoring boshlangandan keyin ma'lum
        // bo'ladi; birinchi bo'lak esa undan 10 soniya keyin keladi.
        recRef.current = await startProctoring((blob) => {
          if (!uploaderRef.current) {
            uploaderRef.current = createRecordingUploader(
              token, "screen", recRef.current?.mimeType,
            );
          }
          uploaderRef.current.push(blob);
        });
      }
      onStart();
    } catch {
      // Ruxsat rad etildi — to'liq ekrandan chiqib, tushunarli xato ko'rsatamiz.
      // Tugma qayta bosilsa, so'rovlar qaytadan chiqadi.
      document.exitFullscreen?.().catch(() => {});
      setError(t.perm_denied);
      setBusy(false);
    }
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

      {offer && (
        <div className="offer-box">
          <div className="offer-box-title">{t.offer_title}</div>
          {/* preload="metadata": video faqat "Play" bosilganda yuklanadi. Aks
              holda brauzer har bir xodim uchun katta videoni darhol yuklashga
              tushardi — 10 kishi birga kirganda shuncha marta. */}
          {offer.video && <video className="offer-video" src={offer.video} controls preload="metadata" />}
          {offer.text && <div className="intro-text offer-box-text">{offer.text}</div>}
          <label className="chk">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
            {t.offer_agree}
          </label>
        </div>
      )}

      {error && <div className="alert">{error}</div>}

      <button className="btn gold block" onClick={start} disabled={!canStart}>
        {busy ? t.starting : `${test.proctoring ? t.start_grant : t.intro_start} →`}
      </button>
    </div>
  );
}
