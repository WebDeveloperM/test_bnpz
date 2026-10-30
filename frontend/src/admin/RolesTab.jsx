import { useEffect, useState } from "react";
import {
  listRoles, createRole, updateRole, deleteRole, listPermissionCatalog,
} from "../adminApi.js";
import { IconShield, IconPlus, IconEdit, IconTrash } from "./icons.jsx";

// Rollar va ularning ruxsatlari. Faqat superuser ko'radi — shu yerda u har
// bir rol uchun qaysi bo'limlar ochiq ekanini belgilaydi.
//
// Ruxsatlar ro'yxati SERVERDAN olinadi (`/admin/permissions/`), bu yerga
// ko'chirib yozilmagan: aks holda yangi bo'lim qo'shilganda ikkita joyni
// yangilash kerak bo'lar va ular jimgina bir-biridan farq qila boshlardi.

const EMPTY = { name: "", description: "", permissions: [] };

export default function RolesTab() {
  const [roles, setRoles] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState(null); // null | {id?, name, description, permissions}
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    Promise.all([listRoles(), listPermissionCatalog()])
      .then(([r, c]) => { setRoles(r); setCatalog(c); })
      .catch((e) => setError(e.message))
      .finally(() => setLoaded(true));
  }

  useEffect(() => { load(); }, []);

  const labels = Object.fromEntries(catalog.map((p) => [p.key, p.label]));
  // Katalog o'z guruhlari bilan keladi — shu tartibni saqlab qolamiz.
  const groups = [];
  for (const p of catalog) {
    const g = groups.find((x) => x.name === p.group);
    if (g) g.items.push(p);
    else groups.push({ name: p.group, items: [p] });
  }

  function togglePerm(key) {
    setEditing((e) => ({
      ...e,
      permissions: e.permissions.includes(key)
        ? e.permissions.filter((k) => k !== key)
        : [...e.permissions, key],
    }));
  }

  async function save() {
    setBusy(true);
    setError("");
    try {
      const body = {
        name: editing.name,
        description: editing.description,
        permissions: editing.permissions,
      };
      if (editing.id) await updateRole(editing.id, body);
      else await createRole(body);
      setEditing(null);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(role) {
    // Rol o'chsa, undagi administratorlar hisobi qolaveradi, lekin rolsiz
    // qolgani uchun panelga kira olmaydi — buni oldindan ochiq aytamiz.
    const warn = role.user_count
      ? `\n\nDiqqat: bu rolda ${role.user_count} ta administrator bor. Rol o'chirilsa, ular yangi rol berilmaguncha panelga kira olmaydi.`
      : "";
    if (!window.confirm(`"${role.name}" roli o'chirilsinmi?${warn}`)) return;
    setError("");
    try {
      await deleteRole(role.id);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-card2">
          <div>
            <div className="stat-card2-label">Rollar</div>
            <div className="stat-card2-num">{roles.length}</div>
          </div>
          <div className="icon-square blue"><IconShield /></div>
        </div>
      </div>

      <div className="adm-card">
        <div className="adm-title-row">
          <h2>Rollar va ruxsatlar</h2>
          <div className="adm-toolbar-btns">
            <button className="btn2 primary" onClick={() => setEditing({ ...EMPTY })}>
              <IconPlus width={16} height={16} /> Yangi rol
            </button>
          </div>
        </div>

        <div className="hint" style={{ marginBottom: 14 }}>
          Rolga qaysi bo'limlar ochiq bo'lsa, shu roldagi administrator panelda faqat o'sha
          bo'limlarni ko'radi. Superuserga rol berilmaydi — unga har doim hamma narsa ochiq.
        </div>

        {error && <div className="alert" style={{ marginBottom: 12 }}>{error}</div>}

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-num">№</th>
                <th style={{ width: 220 }}>Rol</th>
                <th>Ochiq bo'limlar</th>
                <th style={{ width: 130 }}>Administratorlar</th>
                <th style={{ width: 110 }}>Amallar</th>
              </tr>
            </thead>
            <tbody>
              {roles.map((r, i) => (
                <tr key={r.id}>
                  <td className="col-num">{i + 1}</td>
                  <td>
                    <b>{r.name}</b>
                    {r.description && <div className="muted" style={{ fontSize: 12 }}>{r.description}</div>}
                  </td>
                  <td>
                    {r.permissions.length ? (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {r.permissions.map((k) => (
                          <span key={k} className="badge done">{labels[k] || k}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="badge danger">hech qanday bo'lim</span>
                    )}
                  </td>
                  <td>{r.user_count}</td>
                  <td className="nowrap">
                    <button className="adm-icon-btn" title="Tahrirlash"
                      onClick={() => setEditing({
                        id: r.id, name: r.name,
                        description: r.description || "",
                        permissions: [...r.permissions],
                      })}>
                      <IconEdit width={15} height={15} />
                    </button>
                    <button className="adm-icon-btn danger" title="O'chirish" onClick={() => remove(r)}>
                      <IconTrash width={15} height={15} />
                    </button>
                  </td>
                </tr>
              ))}
              {!roles.length && loaded && (
                <tr><td colSpan={5} className="empty">Hali rol yaratilmagan</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {editing && (
        <div className="modal-backdrop" onClick={() => !busy && setEditing(null)}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <h3>{editing.id ? "Rolni tahrirlash" : "Yangi rol"}</h3>

            <label>Rol nomi</label>
            <input
              className="field" autoFocus
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
              placeholder="Masalan: Uchebniy administrator"
            />

            <label>Izoh</label>
            <input
              className="field"
              value={editing.description}
              onChange={(e) => setEditing({ ...editing, description: e.target.value })}
              placeholder="Bu rol nima uchun ishlatilishi (majburiy emas)"
            />

            <label style={{ marginTop: 16, display: "block" }}>Ochiq bo'limlar</label>
            {groups.map((g) => (
              <div key={g.name}>
                <div className="fg-section">{g.name}</div>
                {g.items.map((p) => (
                  <label key={p.key} className="perm-row">
                    <input
                      type="checkbox"
                      checked={editing.permissions.includes(p.key)}
                      onChange={() => togglePerm(p.key)}
                    />
                    <span>
                      <b>{p.label}</b>
                      <span className="hint" style={{ display: "block", marginTop: 2 }}>{p.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            ))}

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
