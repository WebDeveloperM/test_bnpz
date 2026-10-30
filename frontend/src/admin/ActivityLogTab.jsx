import { useEffect, useRef, useState } from "react";
import { listActivity } from "../adminApi.js";
import { IconActivity } from "./icons.jsx";

const PAGE = 50;

const ACTOR_LABEL = { admin: "Administrator", employee: "Xodim" };

export default function ActivityLogTab() {
  const [data, setData] = useState({ rows: [], total: 0, actions: [] });
  const [loaded, setLoaded] = useState(false);
  const [offset, setOffset] = useState(0);
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [q, setQ] = useState("");
  const debounceRef = useRef(null);

  function load(params) {
    listActivity({ limit: PAGE, ...params })
      .then(setData)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }

  // Qidiruvda har harf uchun so'rov yubormaslik uchun kichik kechikish.
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setOffset(0);
      load({ offset: 0, actor, action, q });
    }, q ? 350 : 0);
    return () => clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actor, action, q]);

  function go(newOffset) {
    setOffset(newOffset);
    load({ offset: newOffset, actor, action, q });
  }

  const from = data.total ? offset + 1 : 0;
  const to = Math.min(offset + PAGE, data.total);

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-card2">
          <div>
            <div className="stat-card2-label">Jami yozuvlar</div>
            <div className="stat-card2-num">{data.total}</div>
          </div>
          <div className="icon-square blue"><IconActivity /></div>
        </div>
      </div>

      <div className="adm-card">
        <div className="adm-title-row">
          <h2>Amallar tarixi</h2>
          <div className="adm-toolbar-btns">
            <select className="field sm" value={actor} onChange={(e) => setActor(e.target.value)}>
              <option value="">Barcha ishtirokchilar</option>
              <option value="admin">Administrator</option>
              <option value="employee">Xodim</option>
            </select>
            <select className="field sm" value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">Barcha amallar</option>
              {(data.actions || []).map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <input
              className="field sm"
              style={{ minWidth: 220 }}
              placeholder="Ism yoki tavsif bo'yicha qidirish…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        </div>

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-num">№</th>
                <th style={{ width: 160 }}>Vaqt</th>
                <th style={{ width: 130 }}>Kim</th>
                <th style={{ width: 180 }}>Ism</th>
                <th style={{ width: 170 }}>Amal</th>
                <th>Tavsif</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={r.id}>
                  <td className="col-num">{offset + i + 1}</td>
                  <td className="nowrap">{r.created}</td>
                  <td>
                    <span className={"badge " + (r.actor === "admin" ? "open" : "done")}>
                      {ACTOR_LABEL[r.actor] || r.actor}
                    </span>
                  </td>
                  <td>{r.actor_name || "—"}</td>
                  <td><code className="code-chip">{r.action}</code></td>
                  <td>{r.description}</td>
                </tr>
              ))}
              {!data.rows.length && loaded && (
                <tr><td colSpan={6} className="empty">Yozuv topilmadi</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {data.total > PAGE && (
          <div className="pager">
            <span>{from}–{to} / {data.total}</span>
            <div className="pager-btns">
              <button className="btn2 sm" disabled={offset === 0}
                onClick={() => go(Math.max(0, offset - PAGE))}>← Oldingi</button>
              <button className="btn2 sm" disabled={to >= data.total}
                onClick={() => go(offset + PAGE)}>Keyingi →</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
