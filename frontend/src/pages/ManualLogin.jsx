import { useEffect, useRef, useState } from "react";
import { login, listManualEmployees, checkinStatus } from "../api.js";
import Logo from "../Logo.jsx";
import SearchSelect from "../admin/SearchSelect.jsx";

const POLL_MS = 3000;

export default function ManualLogin({ onLogin, onSwitch }) {
  const [stage, setStage] = useState("form"); // form | busy | waiting | error
  const [employees, setEmployees] = useState([]);
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [waitingName, setWaitingName] = useState("");

  const pollRef = useRef(null);
  const checkinTokenRef = useRef(null);

  useEffect(() => {
    listManualEmployees().then(setEmployees).catch(() => {});
    return () => stopPolling();
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
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

  async function submit() {
    if (!employeeId || !password) {
      setError("Ism-familiyangizni tanlang va parolni kiriting.");
      return;
    }
    setError("");
    setStage("busy");
    try {
      const res = await login(employeeId, password);
      checkinTokenRef.current = res.checkin_token;
      setWaitingName(res.full_name);
      setStage("waiting");
      poll();
    } catch (e) {
      setError(e.message);
      setStage("error");
    }
  }

  function retry() {
    stopPolling();
    setError("");
    setStage("form");
  }

  const options = employees.map((e) => ({ value: e.id, label: e.full_name }));

  return (
    <div className="auth-shell">
      <div className="auth-card face-login">
        <div className="auth-brand">
          <Logo className="auth-brand-logo" />
          <b>BnpzTest</b>
          <small>Ism va parol bilan kirish</small>
        </div>

        {stage === "form" && (
          <>
            <p className="auth-sub">
              Ism-familiyangizni ro'yxatdan tanlang va administrator bergan parolni kiriting.
            </p>
            <label>Ism-familiya</label>
            <SearchSelect
              options={options}
              value={employeeId}
              onChange={setEmployeeId}
              placeholder="— tanlang —"
            />
            <label style={{ marginTop: 14 }}>Parol</label>
            <input
              className="field"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="••••••••"
            />
            {error && <div className="alert" style={{ marginTop: 12 }}>{error}</div>}
            <button className="btn2 primary block" onClick={submit} style={{ marginTop: 16 }}>
              Kirish →
            </button>
            <button className="btn2 block" onClick={onSwitch} style={{ marginTop: 10 }}>
              ← Yuz orqali kirish
            </button>
          </>
        )}

        {stage === "busy" && (
          <div className="face-status">
            <div className="spinner" />
            <p>Tekshirilmoqda…</p>
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
