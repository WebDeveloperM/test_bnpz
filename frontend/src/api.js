// Backend manzili NISBIY ("/api") — ya'ni sahifa qaysi manzil va protokolda
// ochilgan bo'lsa, so'rovlar ham o'shanga ketadi. Bu HTTPS uchun shart: ilgari
// manzil "http://<host>:8000/api" deb qattiq yozilgan edi va HTTPS sahifadan
// bunday so'rovlarni brauzer "mixed content" sifatida BUTUNLAY bloklardi.
// So'rovni backend'ga yetkazish teskari proksining (nginx, yoki ishlab chiqish
// paytida Vite) vazifasi — qarang: nginx/nginx.conf va frontend/vite.config.js.
export const API_BASE = "/api";

async function post(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || "Xatolik yuz berdi");
    err.code = data.code;
    err.status = res.status;
    throw err;
  }
  return data;
}

export function login(employeeId, password) {
  return post("/employee/login/", { employee_id: employeeId, password });
}

export async function listManualEmployees() {
  const res = await fetch(API_BASE + "/employee/manual-list/");
  const data = await res.json().catch(() => ([]));
  if (!res.ok) throw new Error(data.error || "Xatolik yuz berdi");
  return data;
}

export async function getSettings() {
  const res = await fetch(API_BASE + "/settings/", { cache: "no-store" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Xatolik yuz berdi");
  return data;
}

export function acceptOffer(token) {
  return post("/employee/offer-accept/", { token });
}

export function submit(token, answers, timings, violations, shareStopped, language, interrupted) {
  return post("/employee/submit/", {
    token, answers, timings: timings || {}, violations: violations || 0,
    share_stopped: !!shareStopped,
    // Sahifa yangilangani sababli majburan yakunlanmoqda.
    interrupted: !!interrupted,
    // Xodim testni qaysi tilda yakunlagani — natija va protokol shu tilda saqlanadi.
    language,
  });
}

export function checkAnswer(token, questionId, answer, language) {
  return post("/employee/check/", { token, question_id: questionId, answer, language });
}

// Javobni serverda qulflaydi (to'g'ri javob ko'rsatilmaydi) — "Maksimal" rejimda
// savol ortda qolganda chaqiriladi, shundan keyin javob o'zgartirilmaydi.
export function lockAnswer(token, questionId, answer) {
  return post("/employee/lock-answer/", { token, question_id: questionId, answer });
}

// Diqqat: seansni tiklash (`restoreSession`) ATAYLAB olib tashlangan.
// Test davomida sahifani yangilash taqiqlangan — yangilagan xodim testga
// qaytmaydi, test o'sha ondagi javoblari bilan yakunlanadi (App.jsx ga qarang).
// Serverdagi `/employee/session/` endpointi ham endi 410 qaytaradi.

export async function identifyFace(photoBlob) {
  const form = new FormData();
  form.append("photo", photoBlob, "face.jpg");
  const res = await fetch(API_BASE + "/employee/identify/", { method: "POST", body: form });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Xatolik yuz berdi");
  return data;
}

export async function checkinStatus(checkinToken) {
  const res = await fetch(API_BASE + "/employee/checkin-status/?token=" + encodeURIComponent(checkinToken));
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Xatolik yuz berdi");
  return data;
}

function extensionFor(mimeType) {
  if ((mimeType || "").includes("mp4")) return "mp4";
  return "webm";
}

// Bitta bo'lakni yuborish. Muvaffaqiyatli bo'lsa true qaytaradi.
//
// DIQQAT: ilgari bu yerda javob umuman tekshirilmasdi — `fetch` faqat tarmoq
// uzilganda xato beradi, server 413 yoki 500 qaytarsa esa muvaffaqiyat deb
// hisoblanardi. Ya'ni video jimgina yo'qolardi va buni hech kim bilmasdi.
const RETRY_DELAYS = [0, 2000, 6000];

async function sendChunk(token, kind, blob, index, ext) {
  for (const delay of RETRY_DELAYS) {
    if (delay) await new Promise((r) => setTimeout(r, delay));
    const form = new FormData();
    form.append("token", token);
    form.append("kind", kind);
    form.append("index", String(index));
    form.append("file", blob, `${kind}-${index}.${ext}`);
    try {
      const res = await fetch(API_BASE + "/employee/recording/", { method: "POST", body: form });
      if (res.ok) return true;
      // 413 — bo'lak server chegarasidan katta. Aynan shu baytlarni qayta
      // yuborish baribir sig'maydi, urinishdan foyda yo'q.
      if (res.status === 413) return false;
    } catch {
      // tarmoq uzildi — keyingi urinishda qaytadan sinaymiz
    }
  }
  return false;
}

// Test DAVOMIDA video bo'laklarini yuborib turadigan yuklovchi.
//
// Bo'laklar serverda BITTA faylga ketma-ket qo'shiladi, shuning uchun tartib
// buzilmasligi shart — har bir yuborish oldingisi tugaguncha kutadi
// (`queue`). Bo'laklar 10 soniyada bir keladi, yuborish esa undan ancha tez,
// ya'ni navbat amalda to'planib qolmaydi.
export function createRecordingUploader(token, kind, mimeType) {
  const ext = extensionFor(mimeType);
  let index = 0;
  let queue = Promise.resolve();
  let broken = false;

  return {
    push(blob) {
      if (!blob || !blob.size || broken) return;
      const at = index++;
      queue = queue.then(async () => {
        const ok = await sendChunk(token, kind, blob, at, ext);
        // Bo'lak yetib bormasa — keyingilarini ham yubormaymiz: fayl o'rtasida
        // bo'shliq qolsa, o'sha joydan keyingi qismi baribir ochilmaydi.
        // Shu bilan serverda YAROQLI, faqat qisqaroq video qoladi.
        if (!ok) broken = true;
      });
    },
    // Navbatdagi hamma narsa yuborilib bo'lgunicha kutadi.
    finish() {
      return queue;
    },
  };
}

// Yozuv NECHA SONIYA davom etgani — buni faylning o'zidan bilib bo'lmaydi
// (bo'lak-bo'lak yozilgani uchun sarlavhada umuman yo'q), shuning uchun
// buni o'lchagan brauzerning o'zi xabar beradi. Server bu qiymatni birinchi
// ko'rilganda faylning sarlavhasiga yozadi — shundan keyin pleyer to'g'ri
// davomiylikni darhol ko'rsatadi va katta faylda ham tez ochiladi (qarang:
// backend `_ensure_recording_duration_fixed`).
//
// Xatoga chidamli: bu yerda urinib ko'rilmasa ham test natijasiga ta'sir
// qilmaydi — video baribir ochiladi, faqat ko'rish biroz sekinroq bo'ladi
// (brauzer o'zi taxmin qilishga urinadi, qarang: fixVideoDuration.js).
export function reportRecordingDuration(token, kind, durationMs) {
  return post("/employee/recording/duration/", { token, kind, duration_ms: Math.round(durationMs) })
    .catch(() => {});
}
