import { useState } from "react";
import { startProctoring } from "../proctoring.js";

export default function ProctorGate({ session, recRef, onReady }) {
  const { test, employee } = session;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function grant() {
    setBusy(true);
    setError("");
    try {
      recRef.current = await startProctoring();
      onReady();
    } catch (e) {
      setError(
        "Ruxsat berilmadi. Bu test video nazorat ostida o'tkaziladi — davom etish uchun ekran, " +
        "kamera va mikrofonni ulashish so'rovlariga \"Ruxsat berish\" / \"Share\" deb javob bering."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card narrow">
      <h1 className="h">{test.name}</h1>
      <p className="sub">{employee}</p>

      <div className="intro-text">
        Ushbu test <b>video nazorat</b> ostida o'tkaziladi: test davomida ekraningiz, veb-kamera
        orqali yuzingiz va mikrofon orqali ovozingiz yoziladi. Davom etish uchun brauzer
        so'rovlarida ekran ulashish, kamera va mikrofondan foydalanishga ruxsat bering.
      </div>

      {error && <div className="alert">{error}</div>}

      <button className="btn gold block" onClick={grant} disabled={busy}>
        {busy ? "Kutilmoqda…" : "Ruxsat berish va davom etish"} →
      </button>
    </div>
  );
}
