// Nisbiy manzil — qarang: api.js dagi API_BASE izohi (HTTPS/mixed content).
const _LIVE_API = () => "/api";

// Ba'zi tarmoqlarda (firewall) ikkita ish stansiyasi o'rtasida to'g'ridan-to'g'ri
// (host kandidat) ulanish bo'lmaydi — shu sabab o'zimizning TURN serverimiz
// (video trafikni backend kabi shu serverning o'zi orqali qayta yo'naltiradi)
// asosiy variant sifatida qo'shilgan. Google STUN'lar internet mavjud bo'lgan
// tarmoqlarda qo'shimcha yordam sifatida qoladi (mavjud bo'lmasa, sekinlik
// qilmay e'tiborsiz qoldiriladi).
function _iceServers() {
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

function _livePost(path, body) {
  return fetch(_LIVE_API() + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  }).catch(() => {});
}

// `cache: "no-store"` shart — bu funksiya bir xil URL'ni (masalan
// "…/signal/?...&after=0") tez-tez qayta so'raydi; brauzer buni keshlab,
// serverda haqiqatan yangi ma'lumot paydo bo'lgan bo'lsa ham, 304 (o'zgarmagan)
// javob bilan eski (bo'sh) natijani qaytarib yuborishi mumkin edi.
function _liveGet(path) {
  return fetch(_LIVE_API() + path, { cache: "no-store" }).then((r) => r.json()).catch(() => ({}));
}

export async function startLiveShare(token, canvasStream) {
  const pc = new RTCPeerConnection(_iceServers());

  for (const track of canvasStream.getTracks()) {
    pc.addTrack(track, canvasStream);
  }

  // Trickle ICE: har bir kandidat topilgan zahoti alohida yuboriladi —
  // barcha kandidatlar yig'ilishini kutib, bittada SDP'ga qo'shib yuborish
  // (oldingi usul) ba'zan 4 soniyalik belgilangan vaqtga ulgurmay, ulanish
  // tasodifiy ishlamay qolishiga sabab bo'lardi.
  //
  // MUHIM: offer serverga yetib borgunicha kandidatlar YUBORILMAYDI, navbatda
  // (`pending`) turadi. Sabab: `setLocalDescription()` dan keyin host
  // kandidatlar deyarli bir zumda topiladi va ular offer so'rovidan OLDIN
  // serverga yetib borishi mumkin edi; server esa yangi offer kelganda
  // "yangi ulanish — eski ma'lumot yaroqsiz" deb kandidatlar ro'yxatini
  // tozalaydi va shu erta yuborilgan kandidatlarni o'chirib yuborardi.
  // Natijada admin ularni hech qachon olmasdi va ulanish tasodifiy
  // (o'lchovda ~8 tadan 1 marta) "muvaffaqiyatsiz" bo'lib qolardi.
  let offerSent = false;
  const pending = [];
  const sendCandidate = (candidate) =>
    _livePost("/employee/live/signal/", { token, candidate: JSON.stringify(candidate) });

  pc.onicecandidate = (e) => {
    if (!e.candidate) return;
    if (offerSent) sendCandidate(e.candidate);
    else pending.push(e.candidate);
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  await _livePost("/employee/live/offer/", {
    token,
    offer: JSON.stringify(pc.localDescription),
  });

  offerSent = true;
  while (pending.length) sendCandidate(pending.shift());

  // Admin javobi va uning ICE kandidatlarini polling — ulanish tugallangach
  // (yoki butunlay uzilgach) to'xtatiladi, aks holda so'rov cheksiz davom etardi.
  let answered = false;
  let candAfter = 0;
  let ticks = 0;
  const pollId = setInterval(async () => {
    ticks += 1;
    const cs = pc.connectionState;
    if (cs === "connected" || cs === "failed" || cs === "closed" || ticks > 120) {
      clearInterval(pollId);
      return;
    }
    const data = await _liveGet(`/employee/live/signal/?token=${encodeURIComponent(token)}&after=${candAfter}`);
    if (data.candidates && data.candidates.length) {
      for (const c of data.candidates) {
        try { await pc.addIceCandidate(JSON.parse(c)); } catch { /* eskirgan/mos kelmagan kandidat — o'tkazib yuboriladi */ }
      }
      candAfter = data.total;
    }
    if (!answered && data.answer) {
      answered = true;
      await pc.setRemoteDescription(JSON.parse(data.answer)).catch(() => {});
    }
  }, 500);

  return { pc, pollId };
}

export function stopLiveShare(state) {
  if (!state) return;
  clearInterval(state.pollId);
  state.pc.close();
}

// Video nazorat: ekran va yuz (veb-kamera) oqimlarini bitta videoga birlashtirib
// yozib oladi — yuz videosi ekran videosining pastki o'ng burchagida kichik
// oyna (picture-in-picture) sifatida chiqadi. Ovoz mikrofondan (va ekran
// ulashishda tizim ovozi berilgan bo'lsa, undan ham) yagona audio trekka
// birlashtiriladi. Shu sababli bitta fayl saqlanadi, kam joy oladi va
// ko'rish/yuklab olish qulay.
// Fayl faqat brauzerda vaqtincha (xotirada) yig'iladi, test tugagach serverga
// yuklanadi va u yerda diskka yoziladi — baza faqat manzilni saqlaydi.

// Video test DAVOMIDA bo'lak-bo'lak yuboriladi (qarang: CHUNK_MS va startProctoring)
// — shuning uchun format WebM bo'lishi SHART.
//
// Ilgari MP4 afzal ko'rilardi. O'lchov shuni ko'rsatdi: MP4'da MediaRecorder
// belgilangan oraliqni umuman hisobga olmaydi — 15 soniyalik yozuvda, har 3
// soniyada bo'lak so'ralganda atigi 2 ta bo'lak keldi: 1.2 KB sarlavha, va
// qolgan 2.4 MB HAMMASI oxirida, `stop()` paytida. Ya'ni MP4'da oraliqda
// yuboradigan narsa yo'q — video oxirigacha brauzer xotirasida yotadi.
//
// WebM'da esa bo'laklar aniq jadval bo'yicha keladi (o'lchangan: 3.3s, 6.3s,
// 9.3s, 12.3s, 15.0s) va — eng muhimi — YARIM kelgan fayl ham ochiladi.
// Shuning uchun brauzer yopilib qolsa faqat oxirgi bo'lak yo'qoladi, butun
// video emas.
//
// Narxi: MediaRecorder WebM'ni "jonli oqim" sifatida yozadi va sarlavhaga
// umumiy davomiylikni yozmaydi — pleyerda video uzunligi noma'lum ko'rinadi.
// Video ochiladi va ko'riladi, faqat sakrash noqulayroq bo'ladi.
function pickMimeType(withAudio) {
  const candidates = withAudio
    ? [
        "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm",
        "video/mp4",
      ]
    : [
        "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm",
        "video/mp4",
      ];
  for (const c of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(c)) return c;
  }
  return "";
}

// Har necha soniyada bir bo'lak chiqarilib, darhol serverga yuboriladi.
// 10 soniya — yo'qotish oynasi (brauzer yopilsa shuncha video ketadi) bilan
// so'rovlar soni orasidagi muvozanat: bitta test uchun daqiqasiga 6 ta so'rov.
const CHUNK_MS = 10000;

// --- Video sifati -----------------------------------------------------------
// Yozuvning maqsadi — ekrandagi MATNNI o'qish, harakatni emas. Shuning uchun
// tejash o'lchamdan emas, kadr chastotasidan qilinadi:
//
//   • o'lcham saqlanadi  -> matn aniq qoladi;
//   • kadr chastotasi kam -> ekran deyarli qimirlamagani uchun sezilmaydi,
//     lekin har bir kadrga ko'proq bit tushadi, ya'ni matn YANADA aniqroq.
//
// O'lchangan: eski sozlama (25 kadr, bitrate belgilanmagan) 2.2 Mbit/s berardi —
// bu eski MP4'dan ikki baravar ko'p va 20 xodimda diskni tez to'ldiradi.
const CAPTURE_FPS = 8;
const VIDEO_BITS_PER_SECOND = 1000000;   // ~1 Mbit/s
const AUDIO_BITS_PER_SECOND = 64000;     // gap tushunarli bo'lishi uchun yetarli

// Kanvas o'lchami shu chegaradan oshsa kichraytiriladi. 1920 — odatdagi
// monitorlar tegilmasligi, faqat 4K kabi juda katta ekranlar kichrayishi uchun.
const MAX_CAPTURE_WIDTH = 1920;

function waitForMetadata(video) {
  if (video.videoWidth) return Promise.resolve();
  return new Promise((resolve) => {
    video.addEventListener("loadedmetadata", () => resolve(), { once: true });
  });
}

export async function startProctoring(onChunk) {
  // preferCurrentTab: brauzer to'liq oyna/tab tanlash ro'yxatini ko'rsatish
  // o'rniga darhol joriy tabni taklif qiladi — foydalanuvchi bitta "Share"
  // tugmasini bossa yetarli (ro'yxatdan qidirish shart emas). Ekranni
  // ulashish ruxsati brauzer xavfsizlik siyosati bo'yicha hech qachon
  // "eslab qolinmaydi" (kamera/mikrofondan farqli) — bu darcha har safar
  // chiqadi, faqat shu tarzda tezroq/soddaroq bo'ladi.
  const screenStream = await navigator.mediaDevices.getDisplayMedia({
    video: true, audio: true, preferCurrentTab: true,
  });
  const faceStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });

  const screenVideo = document.createElement("video");
  screenVideo.muted = true;
  screenVideo.srcObject = screenStream;
  await screenVideo.play();
  await waitForMetadata(screenVideo);

  const faceVideo = document.createElement("video");
  faceVideo.muted = true;
  faceVideo.srcObject = faceStream;
  await faceVideo.play();
  await waitForMetadata(faceVideo);

  // Yozuvning MAQSADI — ekrandagi savol va javob MATNINI o'qish. Shuning uchun
  // o'lcham (piksel soni) atayin kamaytirilmaydi: matn kichraytirilsa xiralashadi
  // va yozuvning ma'nosi yo'qoladi. Tejash kadr chastotasi va bitrate hisobiga
  // qilinadi (qarang: CAPTURE_FPS, VIDEO_BITS_PER_SECOND).
  //
  // Chegara faqat juda katta ekranlar uchun: 4K monitorda kanvas keraksiz
  // og'ir bo'lardi. Odatdagi 1920 va undan kichik ekranlar TEGILMAYDI.
  const srcWidth = screenVideo.videoWidth || 1280;
  const srcHeight = screenVideo.videoHeight || 720;
  const scale = srcWidth > MAX_CAPTURE_WIDTH ? MAX_CAPTURE_WIDTH / srcWidth : 1;
  const width = Math.round(srcWidth * scale);
  const height = Math.round(srcHeight * scale);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");

  const pipWidth = Math.round(width * 0.18);
  const faceRatio = (faceVideo.videoHeight && faceVideo.videoWidth) ? faceVideo.videoHeight / faceVideo.videoWidth : 0.75;
  const pipHeight = Math.round(pipWidth * faceRatio);
  const margin = Math.round(width * 0.015);
  const pipX = width - pipWidth - margin;
  const pipY = height - pipHeight - margin;

  // Chizish ham CAPTURE_FPS tezligida bo'ladi. `requestAnimationFrame` o'zi
  // sekundiga ~60 marta chaqiriladi va ilgari har safar chizilardi — bu
  // xodimning kompyuterida keraksiz yuk edi, chunki oqim baribir CAPTURE_FPS
  // tezligida olinadi.
  const frameInterval = 1000 / CAPTURE_FPS;
  const frame = { id: null, last: 0 };
  function draw(now) {
    if (now - frame.last >= frameInterval) {
      frame.last = now;
      ctx.drawImage(screenVideo, 0, 0, width, height);
      ctx.drawImage(faceVideo, pipX, pipY, pipWidth, pipHeight);
      ctx.lineWidth = 3;
      ctx.strokeStyle = "#ffffff";
      ctx.strokeRect(pipX, pipY, pipWidth, pipHeight);
    }
    frame.id = requestAnimationFrame(draw);
  }
  frame.id = requestAnimationFrame(draw);

  // Mikrofon va (bo'lsa) ekran/tizim ovozini bitta audio trekka birlashtiramiz.
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const audioCtx = new AudioCtx();
  const audioDest = audioCtx.createMediaStreamDestination();
  let hasAudio = false;
  [faceStream, screenStream].forEach((s) => {
    const track = s.getAudioTracks()[0];
    if (track) {
      audioCtx.createMediaStreamSource(new MediaStream([track])).connect(audioDest);
      hasAudio = true;
    }
  });

  const canvasStream = canvas.captureStream(CAPTURE_FPS);
  const outputStream = new MediaStream([
    ...canvasStream.getVideoTracks(),
    ...(hasAudio ? audioDest.stream.getAudioTracks() : []),
  ]);

  const mimeType = pickMimeType(hasAudio);
  // Bitrate ATAYIN belgilanadi. Belgilanmasa brauzer o'zi tanlaydi va o'lchov
  // bo'yicha bu 2.2 Mbit/s ga chiqib ketardi — kerakligidan ancha ko'p.
  const opts = {
    videoBitsPerSecond: VIDEO_BITS_PER_SECOND,
    ...(hasAudio ? { audioBitsPerSecond: AUDIO_BITS_PER_SECOND } : {}),
    ...(mimeType ? { mimeType } : {}),
  };
  const recorder = new MediaRecorder(outputStream, opts);
  // Bo'lak tayyor bo'lishi bilan darhol tashqariga beriladi — bu yerda hech
  // narsa to'planmaydi. Ilgari barcha bo'laklar massivda yig'ilib, test
  // oxirida bitta katta fayl bo'lib yuborilardi: brauzer yopilsa yoki
  // yuklash uzilsa BUTUN video yo'qolardi.
  recorder.ondataavailable = (e) => { if (e.data && e.data.size) onChunk?.(e.data); };
  recorder.start(CHUNK_MS);

  return {
    screenStream, faceStream, screenVideo, faceVideo, canvas,
    canvasStream, outputStream, audioCtx, recorder, frame,
    mimeType: mimeType || "video/webm",
    // Yozuv aynan HOZIR (birinchi bo'lak emas, `recorder.start()` chaqirilgan
    // payt) boshlandi — shu vaqtdan `stopProctoring` chaqirilgunicha o'tgan
    // masofa yozuvning HAQIQIY davomiyligi bo'ladi. Server buni fayl
    // sarlavhasiga yozadi (qarang: adminApi.js `reportRecordingDuration`,
    // backend `_ensure_recording_duration_fixed`) — fayl o'zi bo'lak-bo'lak
    // yozilgani uchun bu qiymatni faylning o'zidan bilib bo'lmaydi.
    startedAt: Date.now(),
  };
}

export function stopProctoring(state) {
  return new Promise((resolve) => {
    if (!state) return resolve();
    cancelAnimationFrame(state.frame.id);

    function finish() {
      [state.screenStream, state.faceStream, state.canvasStream, state.outputStream].forEach(
        (s) => s && s.getTracks().forEach((tr) => tr.stop())
      );
      state.audioCtx?.close().catch(() => {});
      resolve();
    }

    // `stop()` oxirgi bo'lakni `ondataavailable` orqali chiqaradi va shundan
    // keyingina `onstop` ishlaydi — ya'ni bu yerda tugagach oxirgi bo'lak
    // allaqachon yuklovchi navbatiga tushgan bo'ladi.
    if (!state.recorder || state.recorder.state === "inactive") return finish();
    state.recorder.onstop = finish;
    state.recorder.stop();
  });
}
