import { useEffect, useState } from "react";
import {
  listAdminUsers, createAdminUser, updateAdminUser, deleteAdminUser, listRoles,
} from "../adminApi.js";
import { IconKey, IconPlus, IconEdit, IconTrash } from "./icons.jsx";

// Panel administratorlari: login, parol va rol. Faqat superuser ko'radi.
// Ilgari bu ish faqat Django admin (/it-center) orqali qilinardi — endi
// kundalik holatda u yerga kirish shart emas.

const EMPTY = { username: "", first_name: "", last_name: "", password: "", role: "", is_active: true };

export default function UsersTab() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    Promise.all([listAdminUsers(), listRoles()])
      .then(([u, r]) => { setUsers(u); setRoles(r); })
      .catch((e) => setError(e.message))
      .finally(() => setLoaded(true));
  }

  useEffect(() => { load(); }, []);

  async function save() {
    setBusy(true);
    setError("");
    try {
      const body = {
        username: editing.username,
        first_name: editing.first_name,
        last_name: editing.last_name,
        is_active: editing.is_active,
        role: editing.role === "" ? null : Number(editing.role),
      };
      // Tahrirlashda bo'sh parol "o'zgartirmaslik" degani — uni umuman
      // yubormaymiz, aks holda server bo'sh parolni saqlab qo'yishi mumkin.
      if (editing.password) body.password = editing.password;
      if (editing.id) await updateAdminUser(editing.id, body);
      else await createAdminUser(body);
      setEditing(null);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(user) {
    if (!window.confirm(`"${user.username}" hisobi butunlay o'chirilsinmi?`)) return;
    setError("");
    try {
      await deleteAdminUser(user.id);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  const activeCount = users.filter((u) => u.is_active).length;

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-card2">
          <div>
            <div className="stat-card2-label">Administratorlar</div>
            <div className="stat-card2-num">{users.length}</div>
          </div>
          <div className="icon-square blue"><IconKey /></div>
        </div>
        <div className="stat-card2">
          <div>
            <div className="stat-card2-label">Faol hisoblar</div>
            <div className="stat-card2-num">{activeCount}</div>
          </div>
          <div className="icon-square yellow"><IconKey /></div>
        </div>
      </div>

      <div className="adm-card">
        <div className="adm-title-row">
          <h2>Foydalanuvchilar</h2>
          <div className="adm-toolbar-btns">
            <button className="btn2 primary" onClick={() => setEditing({ ...EMPTY })}>
              <IconPlus width={16} height={16} /> Yangi administrator
            </button>
          </div>
        </div>

        <div className="hint" style={{ marginBottom: 14 }}>
          Har bir administrator o'z login va paroli bilan shu panelga kiradi. Nimani ko'rishini
          rol belgilaydi — rollarni "Rollar va ruxsatlar" bo'limida sozlaysiz.
        </div>

        {error && <div className="alert" style={{ marginBottom: 12 }}>{error}</div>}

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-num">№</th>
                <th style={{ width: 170 }}>Login</th>
                <th style={{ width: 200 }}>Ism-familiya</th>
                <th>Rol</th>
                <th style={{ width: 110 }}>Holat</th>
                <th style={{ width: 170 }}>Oxirgi kirish</th>
                <th style={{ width: 110 }}>Amallar</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u, i) => (
                <tr key={u.id}>
                  <td className="col-num">{i + 1}</td>
                  <td><b>{u.username}</b></td>
                  <td>{[u.first_name, u.last_name].filter(Boolean).join(" ") || "—"}</td>
                  <td>
                    {u.is_superuser ? (
                      <span className="badge open">Superuser — barcha ruxsatlar</span>
                    ) : u.role_name ? (
                      <span className="badge done">{u.role_name}</span>
                    ) : (
                      // Rolsiz hisob panelga kira olmaydi — buni ro'yxatdayoq
                      // ko'rsatamiz, aks holda sababini topish qiyin bo'ladi.
                      <span className="badge danger">rol berilmagan</span>
                    )}
                  </td>
                  <td>
                    <span className={"badge " + (u.is_active ? "done" : "danger")}>
                      {u.is_active ? "Faol" : "O'chirilgan"}
                    </span>
                  </td>
                  <td className="nowrap">{u.last_login ? new Date(u.last_login).toLocaleString("ru-RU") : "—"}</td>
                  <td className="nowrap">
                    <button className="adm-icon-btn" title="Tahrirlash"
                      onClick={() => setEditing({
                        id: u.id, username: u.username,
                        first_name: u.first_name || "", last_name: u.last_name || "",
                        password: "", role: u.role == null ? "" : String(u.role),
                        is_active: u.is_active, is_superuser: u.is_superuser,
                      })}>
                      <IconEdit width={15} height={15} />
                    </button>
                    <button className="adm-icon-btn danger" title="O'chirish" onClick={() => remove(u)}>
                      <IconTrash width={15} height={15} />
                    </button>
                  </td>
                </tr>
              ))}
              {!users.length && loaded && (
                <tr><td colSpan={7} className="empty">Administrator topilmadi</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {editing && (
        <div className="modal-backdrop" onClick={() => !busy && setEditing(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{editing.id ? "Administratorni tahrirlash" : "Yangi administrator"}</h3>

            <label>Login</label>
            <input
              className="field" autoFocus
              value={editing.username}
              onChange={(e) => setEditing({ ...editing, username: e.target.value })}
              placeholder="masalan: uchebniy1"
            />

            <div style={{ display: "flex", gap: 12 }}>
              <div style={{ flex: 1 }}>
                <label>Ism</label>
                <input className="field" value={editing.first_name}
                  onChange={(e) => setEditing({ ...editing, first_name: e.target.value })} />
              </div>
              <div style={{ flex: 1 }}>
                <label>Familiya</label>
                <input className="field" value={editing.last_name}
                  onChange={(e) => setEditing({ ...editing, last_name: e.target.value })} />
              </div>
            </div>

            <label>Parol</label>
            <input
              className="field" type="password"
              value={editing.password}
              onChange={(e) => setEditing({ ...editing, password: e.target.value })}
              placeholder={editing.id ? "O'zgartirmaslik uchun bo'sh qoldiring" : "Parol kiriting"}
            />

            <label>Rol</label>
            {editing.is_superuser ? (
              <div className="hint">
                Bu hisob — superuser. Unga barcha bo'limlar har doim ochiq, shuning uchun rol
                berilmaydi. Superuser darajasini faqat /it-center orqali o'zgartirish mumkin.
              </div>
            ) : (
              <>
                <select className="field" value={editing.role}
                  onChange={(e) => setEditing({ ...editing, role: e.target.value })}>
                  <option value="">— rol berilmagan —</option>
                  {roles.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} ({r.permissions.length} ta bo'lim)
                    </option>
                  ))}
                </select>
                <div className="hint" style={{ marginTop: 4 }}>
                  Rolsiz administrator panelga kira olmaydi.
                </div>
              </>
            )}

            <label className="perm-row" style={{ marginTop: 14 }}>
              <input type="checkbox" checked={editing.is_active}
                onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} />
              <span>
                <b>Faol</b>
                <span className="hint" style={{ display: "block", marginTop: 2 }}>
                  Belgi olib tashlansa, hisob saqlanadi, lekin panelga kira olmaydi.
                </span>
              </span>
            </label>

            {error && <div className="alert" style={{ marginTop: 12 }}>{error}</div>}

            <div className="btnrow">
              <button className="btn2 primary" onClick={save} disabled={busy}>
                {busy ? "Saqlanmoqda…" : "Saqlash"}
              </button>
              <button className="btn2" onClick={() => setEditing(null)} disabled={busy}>
                Bekor qilish
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
