import { API_BASE } from "./api.js";

const TOKEN_KEY = "bnpztest_admin_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function summarizeErrors(data) {
  if (!data || typeof data !== "object") return null;
  const parts = [];
  for (const v of Object.values(data)) {
    parts.push(Array.isArray(v) ? v.join(" ") : String(v));
  }
  return parts.join(" ") || null;
}

async function req(path, { method = "GET", body, signal } = {}) {
  const token = getToken();
  const res = await fetch(API_BASE + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Token " + token } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
    // Ba'zi so'rovlar (masalan live-view offer'ini so'rash) bir xil URL'ga
    // tez-tez qayta murojaat qiladi. Brauzer buni keshlab, serverda haqiqatan
    // yangilanish bo'lsa ham, 304 (o'zgarmagan) javob bilan eski natijani
    // qaytarishi mumkin — bu esa "res.ok=false" bo'lgani uchun ilovada
    // kutilmagan xatolik sifatida ko'rinardi.
    cache: "no-store",
  });
  if ((res.status === 401 || res.status === 403) && path !== "/admin/login/") {
    clearToken();
    window.location.reload();
    return new Promise(() => {}); // sahifa qayta yuklanmoqda
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || summarizeErrors(data) || "Xatolik yuz berdi");
    err.status = res.status;
    // Server ba'zan mashina o'qiy oladigan kod ham qaytaradi (masalan "no_face")
    // — mijoz shunga qarab boshqacha yo'l tutishi mumkin.
    err.code = data.code;
    throw err;
  }
  return data;
}

// Yagona kirish eshigi — barcha administratorlar shu yerdan kiradi. Javobda
// tokendan tashqari foydalanuvchining roli va ruxsatlari ham keladi.
export function adminLogin(login, password) {
  return req("/admin/login/", { method: "POST", body: { login, password } }).then((d) => {
    setToken(d.token);
    return d;
  });
}

// Joriy foydalanuvchi: {username, is_superuser, role, permissions}.
// Panel har ochilganda shu yerdan so'raladi — rol o'zgartirilgan bo'lsa,
// menyu darhol yangilanadi va eskirgan ma'lumotga tayanilmaydi.
export function getMe() {
  return req("/admin/me/");
}

// --- Rollar va foydalanuvchilar (faqat superuser) --------------------------

export function listPermissionCatalog() {
  return req("/admin/permissions/");
}

export function listRoles() {
  return req("/admin/roles/");
}
export function createRole(data) {
  return req("/admin/roles/", { method: "POST", body: data });
}
export function updateRole(id, data) {
  return req(`/admin/roles/${id}/`, { method: "PATCH", body: data });
}
export function deleteRole(id) {
  return req(`/admin/roles/${id}/`, { method: "DELETE" });
}

export function listAdminUsers() {
  return req("/admin/users/");
}
export function createAdminUser(data) {
  return req("/admin/users/", { method: "POST", body: data });
}
export function updateAdminUser(id, data) {
  return req(`/admin/users/${id}/`, { method: "PATCH", body: data });
}
export function deleteAdminUser(id) {
  return req(`/admin/users/${id}/`, { method: "DELETE" });
}

// --- Tizim bo'limlari ------------------------------------------------------

export function listActivity(params = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== "" && v != null),
  ).toString();
  return req("/admin/activity/" + (q ? "?" + q : ""));
}

// Video yozuvlar arxivi.
//   params: {limit, offset, kind, q, tabel, tsex, date_from, date_to, with_options}
//   `with_options: 1` — javobga sex ro'yxati (`tsex_options`) ham qo'shiladi.
//     Panel uni tab ochilganda BIR MARTA so'raydi, har qidiruv harfida emas.
export function listRecordings(params = {}) {
  const q = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== "" && v != null),
  ).toString();
  return req("/admin/recordings/" + (q ? "?" + q : ""));
}

// Yuklashdan OLDINGI so'rov: {count, size_mb, missing, too_many, too_big,
// max_files, max_mb}. Arxiv bir necha gigabayt bo'lishi mumkin, shuning uchun
// administrator avval nechta fayl va qancha hajm ekanini ko'rib tasdiqlaydi.
export function probeRecordingsArchive(params = {}) {
  const q = new URLSearchParams(
    Object.entries({ ...params, probe: 1 }).filter(([, v]) => v !== "" && v != null),
  ).toString();
  return req("/admin/recordings/archive/?" + q);
}

// Arxivni yuklab olish manzili — FILTR bilan bir xil parametrlar.
//
// Token so'rov parametrida (qarang: `resultsCsvUrl`): faylni brauzerning
// o'zi yuklab oladi, <a download> esa Authorization sarlavhasini qo'sha
// olmaydi. `fetch` + blob ATAYLAB ishlatilmaydi — u arxivni butunlay
// brauzer xotirasiga yig'ardi, bu yerda esa gap gigabaytlar haqida.
export function recordingsArchiveUrl(params = {}) {
  const q = new URLSearchParams(
    Object.entries({ ...params, token: getToken() }).filter(([, v]) => v !== "" && v != null),
  ).toString();
  return `${API_BASE}/admin/recordings/archive/?${q}`;
}

export function getSystemStatus() {
  return req("/admin/system-status/");
}

export function listTests() {
  return req("/admin/tests/");
}
export function createTest(data) {
  return req("/admin/tests/", { method: "POST", body: data });
}
export function updateTest(id, data) {
  return req(`/admin/tests/${id}/`, { method: "PATCH", body: data });
}
export function deleteTest(id) {
  return req(`/admin/tests/${id}/`, { method: "DELETE" });
}

export function listQuestions(testId) {
  return req(`/admin/questions/?test=${testId}`);
}
export function createQuestion(data) {
  return req("/admin/questions/", { method: "POST", body: data });
}
export function updateQuestion(id, data) {
  return req(`/admin/questions/${id}/`, { method: "PATCH", body: data });
}
export function deleteQuestion(id) {
  return req(`/admin/questions/${id}/`, { method: "DELETE" });
}

export async function uploadQuestionImage(id, file) {
  const token = getToken();
  const formData = new FormData();
  formData.append("image", file);
  const res = await fetch(`${API_BASE}/admin/questions/${id}/image/`, {
    method: "POST",
    headers: { ...(token ? { Authorization: "Token " + token } : {}) },
    body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Rasmni yuklab bo'lmadi.");
  return data;
}
export function deleteQuestionImage(id) {
  return req(`/admin/questions/${id}/image/`, { method: "DELETE" });
}

// Variant (javob varianti) rasmi — savol rasmi bilan bir xil oqim: avval savol
// saqlanadi (variant id'lari shunda ma'lum bo'ladi), keyin rasm yuklanadi.
export async function uploadOptionImage(id, file) {
  const token = getToken();
  const formData = new FormData();
  formData.append("image", file);
  const res = await fetch(`${API_BASE}/admin/options/${id}/image/`, {
    method: "POST",
    headers: { ...(token ? { Authorization: "Token " + token } : {}) },
    body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Rasmni yuklab bo'lmadi.");
  return data;
}
export function deleteOptionImage(id) {
  return req(`/admin/options/${id}/image/`, { method: "DELETE" });
}

export async function importQuestions(testId, file) {
  const token = getToken();
  const formData = new FormData();
  formData.append("test", testId);
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/admin/questions/import/`, {
    method: "POST",
    headers: { ...(token ? { Authorization: "Token " + token } : {}) },
    body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || "Faylni import qilib bo'lmadi.");
    // Server har bir xatolikni alohida qaytaradi (qaysi qator/savol, nima
    // noto'g'ri). Ularni ham olib o'tamiz — aks holda administrator "xatolik
    // bor" degan umumiy xabarni ko'radi-yu, nimani to'g'rilashini bilmaydi.
    err.errors = Array.isArray(data.errors) ? data.errors : [];
    err.rowLabel = data.row_label || "qator";
    throw err;
  }
  return data;
}

export function listGroups(testId) {
  return req(`/admin/groups/?test=${testId}`);
}
export function createGroup(data) {
  return req("/admin/groups/", { method: "POST", body: data });
}
export function updateGroup(id, data) {
  return req(`/admin/groups/${id}/`, { method: "PATCH", body: data });
}
export function deleteGroup(id) {
  return req(`/admin/groups/${id}/`, { method: "DELETE" });
}

export function listEmployees() {
  return req("/admin/employees/");
}
export function createEmployee(data) {
  return req("/admin/employees/", { method: "POST", body: data });
}
export function updateEmployee(id, data) {
  return req(`/admin/employees/${id}/`, { method: "PATCH", body: data });
}
export function deleteEmployee(id) {
  return req(`/admin/employees/${id}/`, { method: "DELETE" });
}

export function listActiveAttempts() {
  return req("/admin/active-attempts/");
}

// WebRTC signaling
export function liveGetOffer(attemptId, signal) {
  return req(`/admin/live/${attemptId}/offer/`, { signal });
}
export function livePostAnswer(attemptId, answer) {
  return req(`/admin/live/${attemptId}/answer/`, { method: "POST", body: { answer } });
}
export function livePostAdminCandidate(attemptId, candidate) {
  return req(`/admin/live/${attemptId}/signal/`, { method: "POST", body: { candidate } });
}
export function liveGetEmpCandidates(attemptId, after) {
  return req(`/admin/live/${attemptId}/signal/?after=${after}`);
}
// Seans hali davom etyaptimi. ATAYLAB alohida: `liveGetOffer` ni takroran
// so'rash mumkin emas — u ulangandan keyin serverdagi seansni tozalab,
// xodimning ishlab turgan ulanishini uzib yuboradi (qarang: AdminLiveStatusView).
export function liveGetStatus(attemptId, signal) {
  return req(`/admin/live/${attemptId}/status/`, { signal });
}

export function listCheckins() {
  return req("/admin/checkins/");
}
// Testni boshlash. `params` — "Testni boshlash" oynasida o'zgartirilgan test
// sozlamalari: ular ALOHIDA `updateTest` bilan emas, shu so'rovning o'zida
// saqlanadi. Sabab: `updateTest` "tests" ruxsatini talab qiladi — faqat
// "Kutish ro'yxati" ruxsati berilgan administrator 403 olib, paneldan
// chiqarib yuborilardi. Sozlamalarni tayinlashda belgilash — shu bo'lim ishi.
export function startCheckin(id, testId, params) {
  return req(`/admin/checkins/${id}/start/`, {
    method: "POST",
    body: { test_id: testId, ...(params ? { params } : {}) },
  });
}
export function syncEmployees() {
  return req("/admin/employee-service/sync/", { method: "POST" });
}
// {running, local_total, local_with_face} — sonlar MAHALLIY nusxaniki,
// BnpzId'dagi haqiqiy son emas (davriy sinxron yo'q, nusxa orqada qolishi mumkin).
export function syncEmployeesStatus() {
  return req("/admin/employee-service/sync-status/");
}
export function listTsexOptions() {
  return req("/admin/tsex-list/");
}

// {results, bnpz_ok, stale, total, truncated}.
//   `bnpz_ok=false` — BnpzId javob bermadi; `stale=true` bilan birga keladi,
//     ya'ni ro'yxat mahalliy nusxadan (buni foydalanuvchiga aytish SHART).
//   `truncated=true` — BnpzId `total` ta topdi, lekin hammasi kelmadi;
//     nechtasi kelgani `results.length` da. Buni ham aytish kerak: kesilgan
//     ro'yxat "bunday xodim yo'q" bo'lib ko'rinadi.
// `signal` — eskirgan qidiruv so'rovini bekor qilish uchun (AbortController).
export function searchSyncedEmployees(q, signal) {
  return req(`/admin/synced-employees/search/?q=${encodeURIComponent(q)}`, { signal });
}
export function listExpectedEmployees() {
  return req("/admin/expected-employees/");
}
export function addExpectedEmployee(syncedEmployeeId) {
  return req("/admin/expected-employees/", { method: "POST", body: { synced_employee_id: syncedEmployeeId } });
}
export function removeExpectedEmployee(id) {
  return req(`/admin/expected-employees/${id}/`, { method: "DELETE" });
}
export function clearExpectedEmployees() {
  return req("/admin/expected-employees/", { method: "DELETE" });
}

export async function uploadSyncedEmployeePhoto(id, file) {
  const token = getToken();
  const formData = new FormData();
  formData.append("photo", file);
  const res = await fetch(`${API_BASE}/admin/synced-employees/${id}/photo/`, {
    method: "POST",
    headers: { ...(token ? { Authorization: "Token " + token } : {}) },
    body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Rasmni yuklab bo'lmadi.");
  return data;
}

export function listResults() {
  return req("/admin/results/");
}
export function getResult(id) {
  return req(`/admin/results/${id}/`);
}
export function getResultProtocol(id) {
  return req(`/admin/results/${id}/protocol/`);
}
export function resultsCsvUrl() {
  return `${API_BASE}/admin/results/csv/?token=${encodeURIComponent(getToken())}`;
}
// Bitta video yozuvni o'chiradi — serverda faqat superuserga ruxsat berilgan.
// Ommaviy o'chirish (`clearResults`, `cleanupOldRecordings`) ATAYLAB yo'q:
// server ularni 403 bilan rad etadi, chunki bir bosishda butun arxivni yo'q
// qilish imkoniyati qolmasligi kerak.
export function deleteRecording(id) {
  return req(`/admin/recordings/${id}/`, { method: "DELETE" });
}
// Tanlangan yozuvlarni o'chiradi. "Shartga mos hammasi" emas, aynan tanlangan
// id'lar yuboriladi — shuning uchun superuser nima o'chayotganini ko'rib turadi.
export function deleteRecordings(ids) {
  return req("/admin/recordings/bulk-delete/", { method: "POST", body: { ids } });
}

export function getSettings() {
  return req("/settings/");
}
export function updateSettings(data) {
  return req("/settings/", { method: "PATCH", body: data });
}
export async function uploadOfferVideo(file) {
  const token = getToken();
  const formData = new FormData();
  formData.append("video", file);
  const res = await fetch(`${API_BASE}/admin/settings/offer-video/`, {
    method: "POST",
    headers: { ...(token ? { Authorization: "Token " + token } : {}) },
    body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Videoni yuklab bo'lmadi.");
  return data;
}
export function deleteOfferVideo() {
  return req("/admin/settings/offer-video/", { method: "DELETE" });
}
