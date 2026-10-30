import { useEffect, useState } from "react";
import { listActiveAttempts } from "../adminApi.js";
import { IconActivity } from "./icons.jsx";
import LiveViewModal from "./LiveViewModal.jsx";

function fmtElapsed(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export default function ActiveAttemptsTab() {
  const [attempts, setAttempts] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [liveView, setLiveView] = useState(null); // { attemptId, name }

  async function load() {
    try {
      setAttempts(await listActiveAttempts());
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-card2">
          <div>
            <div className="stat-card2-label">Hozir topshirmoqda</div>
            <div className="stat-card2-num">{attempts.length}</div>
          </div>
          <div className="icon-square blue"><IconActivity /></div>
        </div>
      </div>

      <div className="adm-card">
        <div className="adm-title-row">
          <h2>Imtixondagi Xodimlar</h2>
          {/* <span className="adm-count-pill">Har 5 soniyada yangilanadi</span> */}
        </div>

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-num">№</th>
                <th>Ism-familiya</th>
                <th>Bo'lim</th>
                <th>Test</th>
                <th>Boshlangan</th>
                <th>O'tgan vaqt</th>
                <th>Savollar</th>
                <th className="col-actions"></th>
              </tr>
            </thead>
            <tbody>
              {attempts.map((a, i) => (
                <tr key={a.id}>
                  <td className="col-num">{i + 1}</td>
                  <td>{a.full_name}</td>
                  <td>{a.department || "—"}</td>
                  <td>{a.test_name}</td>
                  <td>{a.started_at}</td>
                  <td>{fmtElapsed(a.elapsed_seconds)}{a.time_limit ? ` / ${a.time_limit}:00` : ""}</td>
                  <td>{a.total_questions}</td>
                  <td className="col-actions">
                    {a.proctoring ? (
                      <button
                        className="btn2 sm"
                        title="Jonli ekranni ko'rish"
                        onClick={() => setLiveView({ attemptId: a.id, name: a.full_name })}
                      >
                        📺 Ko'rish
                      </button>
                    ) : (
                      <span
                        className="btn2 sm"
                        style={{ opacity: 0.4, cursor: "default" }}
                        title="Bu testda video nazorat yoqilmagan — test sozlamalarida yoqing"
                      >
                        📺 Ko'rish
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {!attempts.length && loaded && (
                <tr><td colSpan={8} className="empty">Hozircha hech kim test topshirmayapti</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {liveView && (
        <LiveViewModal
          attemptId={liveView.attemptId}
          name={liveView.name}
          onClose={() => setLiveView(null)}
        />
      )}
    </div>
  );
}
