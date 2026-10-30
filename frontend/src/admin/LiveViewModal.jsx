import { useEffect, useRef, useState } from "react";
import { liveGetOffer, livePostAnswer, livePostAdminCandidate, liveGetEmpCandidates, liveGetStatus } from "../adminApi.js";

// Ulangandan keyin "test tugadimi?" deb shuncha vaqtda bir so'raladi.
//
// Kutish SHART: xodim brauzeri jimgina yopilishi mumkin va WebRTC buni bir
// necha o'n soniyagacha sezmaydi — ya'ni ulanish holatiga qarab turishning
// o'zi yetarli emas. Yakunlanganini faqat server aniq biladi.
//
// 3 soniya — admin uchun bu darhol sezilmaydigan kechikish, server uchun esa
// bitta ochiq oynaga daqiqasiga 20 ta yengil so'rov, ya'ni arzimas yuk.
const FINISH_POLL_MS = 3000;

// Ba'zi tarmoqlarda (firewall) ikkita ish stansiyasi o'rtasida to'g'ridan-to'g'ri
// ulanish bo'lmaydi — shu sabab o'zimizning TURN serverimiz (video trafikni
// backend kabi shu serverning o'zi orqali qayta yo'naltiradi) asosiy variant
// sifatida qo'shilgan. Google STUN'lar internet mavjud tarmoqlarda qo'shimcha
// yordam sifatida qoladi.
function iceServers() {
  const host = window.location.hostname;
  return {
    iceServers: [
      {
        urls: [`turn:${host}:3478?transport=udp`, `turn:${host}:3478?transport=tcp`],
        username: "bnpzturn",
        credential: "bnpzturnsecret",
      },
      { urls: "stun:stun.l.google.com:19302" },
      { urls: "stun:stun1.l.google.com:19302" },
    ],
  };
}

export default function LiveViewModal({ attemptId, name, onClose }) {
  const videoRef = useRef(null);
  const [status, setStatus] = useState("Ulanmoqda…");
  const [connected, setConnected] = useState(false);
  const pcRef = useRef(null);
  const candPollRef = useRef(null);
  const finishPollRef = useRef(null);

  useEffect(() => {
    // Muhim: `cancelled` shu effekt chaqiruviga xos mahalliy o'zgaruvchi —
    // ref emas. React StrictMode dev rejimida effektni ulash→uzish→qayta
    // ulashni ataylab ikki marta bajaradi; agar bu bayroq umumiy ref bo'lganida,
    // ikkinchi ulanish uni qayta false qilib qo'yardi va birinchi (eskirgan)
    // polling sikli hech qachon to'xtamay, ikkalasi parallel ishlab so'rovlar
    // ikkilanib ketardi.
    //
    // `controller.abort()` esa alohida muammoni hal qiladi: backend'dagi
    // "offer olish" so'rovi (GET) yon ta'sirga ega — har chaqirilganda
    // "admin_wants_view" bayrog'ini true qiladi. Agar eskirgan (StrictMode
    // qayta ulashdan oldingi) so'rov cancel qilinmasa, u baribir serverga
    // yetib borib shu bayroqni qayta true qilib qo'yardi — xodim tomonida
    // buni ko'rib, ALLAQACHON ULANGAN video oqimini keraksiz qayta boshlar,
    // natijada "Ulandi ✓" bir necha soniyadan keyin "uzildi, qayta
    // urinmoqda…" ga aylanib ketardi.
    let cancelled = false;
    const controller = new AbortController();

    // `cancelled` kabi shu effekt chaqiruviga xos — ref emas (yuqoridagi
    // izohga qarang). Test tugagani BIR MARTA e'lon qilinishi kerak: uni
    // ham davriy so'rov, ham ulanish uzilishi aniqlashi mumkin, ikkalasi
    // deyarli bir vaqtda kelib qolsa admin ikkita darchani yopishi kerak
    // bo'lardi.
    let finished = false;

    function endAsFinished() {
      if (finished || cancelled) return;
      finished = true;
      if (candPollRef.current) { clearInterval(candPollRef.current); candPollRef.current = null; }
      if (finishPollRef.current) { clearInterval(finishPollRef.current); finishPollRef.current = null; }
      if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
      setConnected(false);
      setStatus("✅ Test yakunlandi — jonli ko'rish to'xtatildi.");
      window.alert("Test yakunlandi.");
    }

    async function checkFinished() {
      if (finished || cancelled) return;
      const data = await liveGetStatus(attemptId, controller.signal).catch(() => ({}));
      if (data.finished) endAsFinished();
    }

    async function connect() {
      setStatus("Xodim ekraniga ulanish so'rovi yuborildi…");
      let offer = null;
      for (let i = 0; i < 30 && !cancelled; i++) {
        const data = await liveGetOffer(attemptId, controller.signal).catch(() => ({}));
        if (cancelled) return;
        // Xodim biz ulanishga ulgurmasdan yakunlagan bo'lishi mumkin — bu
        // "ulanib bo'lmadi" emas, oddiy holat va shunday deb aytilishi kerak.
        if (data.finished) { endAsFinished(); return; }
        if (data.offer) { offer = data.offer; break; }
        if (i === 4) setStatus("Xodim brauzeri javob bermoqda, kuting…");
        await new Promise((r) => setTimeout(r, 1000));
      }
      if (!offer || cancelled) {
        if (!cancelled) setStatus("Ulanib bo'lmadi. Test proctoring bilan o'tkazilayotganini tekshiring.");
        return;
      }

      const pc = new RTCPeerConnection(iceServers());
      pcRef.current = pc;

      // Trickle ICE: har bir kandidatni topilgan zahoti yuboramiz — barcha
      // kandidatlar yig'ilishini kutib bitta SDP'da yuborish (eski usul)
      // ba'zan belgilangan vaqtga ulgurmay, ulanish tasodifiy ishlamay
      // qolishiga sabab bo'lardi.
      pc.onicecandidate = (e) => {
        if (e.candidate) {
          livePostAdminCandidate(attemptId, JSON.stringify(e.candidate)).catch(() => {});
        }
      };

      pc.ontrack = (e) => {
        const stream = (e.streams && e.streams.length > 0)
          ? e.streams[0]
          : new MediaStream([e.track]);
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
        setConnected(true);
        setStatus("Ulandi ✓");
      };

      // Ulanish uzilishining ikki sababi bor: haqiqiy tarmoq muammosi yoki
      // testning oddiy yakunlanishi — va ikkinchisi ancha ko'p uchraydi.
      // Shu sabab har uzilishda serverdan darhol so'raymiz: javob "tugagan"
      // bo'lsa, xabar shu zahoti to'g'rilanadi va admin "qayta urinmoqda…"
      // yozuvini bekorga o'qib o'tirmaydi.
      //
      // `finished` tekshiruvi shart: yakunlanganini e'lon qilgach pc'ni O'ZIMIZ
      // yopamiz, ya'ni bu ishlov beruvchilar yana ishga tushadi va yakuniy
      // xabarni "Ulanish yopildi" bilan almashtirib yuborardi.
      pc.oniceconnectionstatechange = () => {
        if (finished) return;
        const s = pc.iceConnectionState;
        if (s === "checking")     setStatus("ICE tekshirilmoqda…");
        if (s === "connected" || s === "completed") setStatus("ICE ulandi, video oqim kutilmoqda…");
        if (s === "disconnected") { setStatus("ICE vaqtinchalik uzildi, qayta urinmoqda…"); checkFinished(); }
        if (s === "failed")       { setStatus("ICE muvaffaqiyatsiz — tarmoqni tekshiring."); setConnected(false); checkFinished(); }
        if (s === "closed")       { setStatus("Ulanish yopildi."); setConnected(false); checkFinished(); }
      };

      pc.onconnectionstatechange = () => {
        if (finished) return;
        const s = pc.connectionState;
        if (s === "connected")   { setStatus("Ulandi ✓"); setConnected(true); }
        if (s === "failed")      { setStatus("Ulanish muvaffaqiyatsiz."); setConnected(false); checkFinished(); }
        if (s === "disconnected") { setStatus("Ulanish uzildi, qayta urinmoqda…"); checkFinished(); }
      };

      setStatus("Offer qabul qilindi, javob tayyorlanmoqda…");
      await pc.setRemoteDescription(JSON.parse(offer));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);

      await livePostAnswer(attemptId, JSON.stringify(pc.localDescription));
      setStatus("Javob yuborildi, ICE ulanish o'rnatilmoqda…");

      // Shu yerdan boshlab testning yakunlanishini kuzatib turamiz. Ulanish
      // holatiga tayanib bo'lmaydi: xodim brauzeri yopilganda WebRTC buni
      // darhol sezmaydi, ba'zan umuman sezmaydi — video shunchaki muzlab
      // qoladi va admin nima bo'lganini bilmay qoladi.
      finishPollRef.current = setInterval(checkFinished, FINISH_POLL_MS);

      // Xodimning ICE kandidatlarini doimiy so'rab, kelgan sayin qo'shamiz —
      // ulanish tugallangach (yoki butunlay uzilgach) to'xtatiladi, aks holda
      // so'rov cheksiz davom etardi.
      let candAfter = 0;
      let ticks = 0;
      candPollRef.current = setInterval(async () => {
        if (cancelled) { clearInterval(candPollRef.current); return; }
        ticks += 1;
        const cs = pc.connectionState;
        if (cs === "connected" || cs === "failed" || cs === "closed" || ticks > 120) {
          clearInterval(candPollRef.current);
          return;
        }
        const data = await liveGetEmpCandidates(attemptId, candAfter).catch(() => ({}));
        if (data.candidates && data.candidates.length) {
          for (const c of data.candidates) {
            try { await pc.addIceCandidate(JSON.parse(c)); } catch { /* eskirgan/mos kelmagan kandidat */ }
          }
          candAfter = data.total;
        }
      }, 500);
    }

    connect().catch((e) => { if (!cancelled) setStatus("Xato: " + e.message); });

    return () => {
      cancelled = true;
      controller.abort();
      if (candPollRef.current) { clearInterval(candPollRef.current); candPollRef.current = null; }
      if (finishPollRef.current) { clearInterval(finishPollRef.current); finishPollRef.current = null; }
      if (pcRef.current) { pcRef.current.close(); pcRef.current = null; }
    };
  }, [attemptId]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal wide"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 940, padding: "20px 24px" }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h3 style={{ margin: 0 }}>
            Jonli ekran — <span style={{ fontWeight: 400 }}>{name}</span>
          </h3>
          <button className="btn2" onClick={onClose}>✕ Yopish</button>
        </div>

        <div style={{ fontSize: 13, color: connected ? "#14a877" : "var(--muted)", marginBottom: 10 }}>
          {status}
        </div>

        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          style={{ width: "100%", maxHeight: 560, background: "#111", borderRadius: 8, display: "block" }}
        />
      </div>
    </div>
  );
}
