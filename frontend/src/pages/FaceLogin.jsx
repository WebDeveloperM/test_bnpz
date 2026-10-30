import { useEffect, useRef, useState } from "react";
import { identifyFace, checkinStatus } from "../api.js";
import Logo from "../Logo.jsx";

const CAPTURE_COUNTDOWN = 3;
const POLL_MS = 3000;

export default function FaceLogin({ onLogin, onSwitch }) {
  const [stage, setStage] = useState("intro"); // intro | camera | identifying | waiting | error
  const [error, setError] = useState("");
  const [countdown, setCountdown] = useState(CAPTURE_COUNTDOWN);
  const [waitingName, setWaitingName] = useState("");

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const pollRef = useRef(null);
  const checkinTokenRef = useRef(null);

  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }
  function stopPolling() {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
  }

  useEffect(() => () => { stopCamera(); stopPolling(); }, []);

  async function openCamera() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
      streamRef.current = stream;
      setStage("camera");
      setCountdown(CAPTURE_COUNTDOWN);
      // video elementi DOM'ga chiqqach ulaymiz
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      }, 0);
    } catch (e) {
      setError("Kameraga ruxsat berilmadi. Brauzer so'rovida \"Ruxsat berish\" tugmasini bosing.");
      setStage("error");
    }
  }

  useEffect(() => {
    if (stage !== "camera") return;
    if (countdown <= 0) {
      capture();
      return;
    }
    const id = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, countdown]);

  function capture() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    stopCamera();
    setStage("identifying");
    canvas.toBlob(async (blob) => {
      try {
        const res = await identifyFace(blob);
        checkinTokenRef.current = res.checkin_token;
        setWaitingName(res.full_name);
        setStage("waiting");
        poll();
      } catch (e) {
        setError(e.message);
        setStage("error");
      }
    }, "image/jpeg", 0.9);
  }

  function poll() {
    pollRef.current = setTimeout(async () => {
      try {
        const res = await checkinStatus(checkinTokenRef.current);
        if (res.status === "started") {
          onLogin(res);
          return;
        }
        if (res.status === "cancelled") {
          setError("Kutish bekor qilindi. Qaytadan urinib ko'ring.");
          setStage("error");
          return;
        }
        poll();
      } catch (e) {
        setError(e.message);
        setStage("error");
      }
    }, POLL_MS);
  }

  function retry() {
    stopCamera();
    stopPolling();
    setError("");
    setStage("intro");
  }

  return (
    <div className="auth-shell">
      <div className="auth-card face-login">
        <div className="auth-brand">
          <Logo className="auth-brand-logo" />
          <b>BnpzTest</b>
          {/* <small>Yuz orqali kirish</small> */}
        </div>

        {stage === "intro" && (
          <>
            <p className="auth-sub">
              Testni boshlash uchun kamera orqali yuzingiz aniqlanadi. Davom etish uchun
              quyidagi tugmani bosing va kamerani ulashishga ruxsat bering.
            </p>
            <button className="btn2 primary block" onClick={openCamera}>
              Face ID orqali →
            </button>
            {onSwitch && (
              <button className="btn2 block" onClick={onSwitch} style={{ marginTop: 10 }}>
                Ism va parol bilan kirish
              </button>
            )}
          </>
        )}

        {stage === "camera" && (
          <div className="face-camera-wrap">
            <video ref={videoRef} className="face-video" muted playsInline />
            <div className="face-countdown">{countdown > 0 ? countdown : "📷"}</div>
            <p className="auth-sub">Yuzingizni ramka ichida tuting, hozir surat olinadi…</p>
          </div>
        )}

        {stage === "identifying" && (
          <div className="face-status">
            <div className="spinner" />
            <p>Aniqlanmoqda…</p>
          </div>
        )}

        {stage === "waiting" && (
          <div className="face-status">
            <div className="spinner" />
            <p>Xush kelibsiz, <b>{waitingName}</b>!</p>
            <p className="auth-sub">Administrator sizga test tayinlab, boshlab berishini kuting…</p>
          </div>
        )}

        {stage === "error" && (
          <>
            {error && <div className="alert">{error}</div>}
            <button className="btn2 primary block" onClick={retry}>Qaytadan urinish →</button>
          </>
        )}
      </div>
    </div>
  );
}
