import { useState } from "react";
import { adminLogin } from "../adminApi.js";
import Logo from "../Logo.jsx";

// Barcha administratorlar uchun YAGONA kirish sahifasi — test administratori,
// o'quv qismi administratori va superuser bir xil formadan kiradi. Kim nimani
// ko'rishini roli hal qiladi, shuning uchun bu yerda hech qanday "qaysi panel"
// tanlovi yo'q.
export default function AdminLogin({ onLogin }) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    if (!login || !password) {
      setError("Login va parolni kiriting.");
      return;
    }
    setBusy(true);
    try {
      // Javobda token bilan birga rol va ruxsatlar keladi — panelni darhol
      // shu ma'lumot bilan ochamiz, qo'shimcha so'rov kutmasdan.
      const me = await adminLogin(login, password);
      onLogin(me);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-brand">
          <Logo className="auth-brand-logo" />
          <b>BnpzTest</b>
          <small>Boshqaruv paneli</small>
        </div>
        <p className="auth-sub">Kirish uchun login va parolni kiriting</p>

        <label>Login</label>
        <input
          className="field"
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="admin"
          autoFocus
        />

        <label>Parol</label>
        <input
          className="field"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="••••••••"
        />

        {error && <div className="alert">{error}</div>}

        <button className="btn2 primary block" onClick={submit} disabled={busy}>
          {busy ? "Yuklanmoqda..." : "Kirish"} →
        </button>
      </div>
    </div>
  );
}
