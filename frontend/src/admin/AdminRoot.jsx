import { useEffect, useState } from "react";
import AdminLogin from "./AdminLogin.jsx";
import AdminDashboard from "./AdminDashboard.jsx";
import { getToken, clearToken, getMe } from "../adminApi.js";

// YAGONA kirish eshigi. Ilgari ikkita alohida manzil bor edi ("/" test
// boshqaruvi, "/tizim" tizim boshqaruvi), ya'ni bir odam ikki xil joydan
// kirardi va bo'limlar manzilga qarab bo'linardi. Endi hamma shu yerdan
// kiradi, kim nimani ko'rishini esa ROLI hal qiladi.
//
// Eski "/tizim/..." havolalar (xatcho'plar, brauzer tarixi) hech qayerga
// olib bormasligi uchun ular shu yerda oddiy manzilga o'girib yuboriladi.
const LEGACY_SYSTEM_BASE = "/tizim";

function stripLegacyPath() {
  const p = window.location.pathname;
  if (p === LEGACY_SYSTEM_BASE || p.startsWith(LEGACY_SYSTEM_BASE + "/")) {
    const rest = p.slice(LEGACY_SYSTEM_BASE.length) || "/";
    window.history.replaceState({}, "", rest);
  }
}

export default function AdminRoot() {
  stripLegacyPath();

  // `me` — {username, is_superuser, role, permissions}. Token bo'lsa ham
  // uni serverdan qayta so'raymiz: rol o'zgargan bo'lishi mumkin, va
  // ruxsatlar ro'yxatini brauzerda saqlab qo'yish faqat chalkashlik keltiradi.
  const [me, setMe] = useState(null);
  const [checking, setChecking] = useState(() => !!getToken());

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    getMe()
      .then((data) => { if (!cancelled) setMe(data); })
      .catch(() => { clearToken(); })
      .finally(() => { if (!cancelled) setChecking(false); });
    return () => { cancelled = true; };
  }, []);

  function handleLogout() {
    clearToken();
    // Manzil oxirgi ochilgan bo'limda qolib ketmasin — kirish sahifasida
    // "/amallar-tarixi" kabi manzil turishi chalkash bo'lardi.
    window.history.replaceState({}, "", "/");
    setMe(null);
  }

  if (checking) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <div className="face-status">
            <div className="spinner" />
            <p>Yuklanmoqda...</p>
          </div>
        </div>
      </div>
    );
  }

  if (me) {
    return <AdminDashboard me={me} onLogout={handleLogout} />;
  }

  return <AdminLogin onLogin={setMe} />;
}
