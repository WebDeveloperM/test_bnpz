import { useEffect, useState } from "react";
import { listEmployees, createEmployee, updateEmployee, deleteEmployee, listTests, updateTest } from "../adminApi.js";
import TestParamsFields from "./TestParamsFields.jsx";
import { IconUsers, IconTest, IconResults, IconSearch, IconPlus, IconEdit, IconTrash, IconCheck } from "./icons.jsx";

const LANGS = [
  { value: "uz", label: "O'zbek (lotin)" },
  { value: "uz-cyrl", label: "O'zbek (kirill)" },
  { value: "ru", label: "Rus" },
];

const EMPTY = { full_name: "", password: "", department: "", assigned_test: "", language: "uz", status: "assigned" };

function testParamsFromTest(test) {
  return {
    mode: test.mode, grading_scale: test.grading_scale, pass_percent: test.pass_percent,
    time_limit: test.time_limit, time_limit_scope: test.time_limit_scope,
    sample_count: test.sample_count, common_question_count: test.common_question_count,
    shuffle_questions: test.shuffle_questions,
    shuffle_options: test.shuffle_options, instant_feedback: test.instant_feedback,
    proctoring: test.proctoring, grade_thresholds: test.grade_thresholds || [],
  };
}

export default function EmployeesTab() {
  const [employees, setEmployees] = useState([]);
  const [tests, setTests] = useState([]);
  const [form, setForm] = useState(null);
  const [testParams, setTestParams] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [bulkTest, setBulkTest] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [addMany, setAddMany] = useState(null);
  const [addManyTestParams, setAddManyTestParams] = useState(null);
  const [addManyBusy, setAddManyBusy] = useState(false);
  const [addManyResult, setAddManyResult] = useState(null);

  async function load() {
    const [emps, tsts] = await Promise.all([listEmployees(), listTests()]);
    setEmployees(emps);
    setTests(tsts);
  }

  useEffect(() => {
    load();
  }, []);

  function openEdit(emp) {
    setForm({ ...EMPTY, ...emp, password: "", assigned_test: emp.assigned_test || "" });
    const t = emp.assigned_test ? tests.find((x) => x.id === emp.assigned_test) : null;
    setTestParams(t ? testParamsFromTest(t) : null);
    setError("");
  }
  function close() {
    setForm(null);
    setTestParams(null);
  }

  function selectTest(testId) {
    setForm((f) => ({ ...f, assigned_test: testId }));
    const t = testId ? tests.find((x) => String(x.id) === String(testId)) : null;
    setTestParams(t ? testParamsFromTest(t) : null);
  }

  async function save() {
    if (!form.full_name.trim()) {
      setError("Ism-familiyani kiriting.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload = {
        full_name: form.full_name.trim(),
        department: form.department || "",
        assigned_test: form.assigned_test || null,
        language: form.language,
        status: form.status,
      };
      if (form.password) payload.password = form.password;
      await updateEmployee(form.id, payload);
      if (form.assigned_test && testParams) {
        await updateTest(form.assigned_test, testParams);
      }
      await load();
      close();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(emp) {
    if (!window.confirm(`"${emp.full_name}" o'chirilsinmi?`)) return;
    await deleteEmployee(emp.id);
    load();
  }

  async function resetStatus(emp) {
    await updateEmployee(emp.id, { status: "assigned" });
    load();
  }

  const q = search.trim().toLowerCase();
  const shown = q ? employees.filter((e) => e.full_name.toLowerCase().includes(q)) : employees;
  const allShownSelected = shown.length > 0 && shown.every((e) => selected.has(e.id));

  function toggleSelect(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function toggleSelectAll() {
    setSelected((prev) => {
      if (allShownSelected) {
        const next = new Set(prev);
        shown.forEach((e) => next.delete(e.id));
        return next;
      }
      const next = new Set(prev);
      shown.forEach((e) => next.add(e.id));
      return next;
    });
  }

  async function bulkAssign() {
    if (!bulkTest || !selected.size) return;
    setBulkBusy(true);
    try {
      await Promise.all([...selected].map((id) => updateEmployee(id, { assigned_test: bulkTest })));
      setSelected(new Set());
      setBulkTest("");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBulkBusy(false);
    }
  }

  function openAddMany() {
    setAddMany({ names: "", assigned_test: "", language: "uz", password: "1234", department: "" });
    setAddManyTestParams(null);
    setAddManyResult(null);
  }
  function closeAddMany() {
    setAddMany(null);
    setAddManyTestParams(null);
    setAddManyResult(null);
  }

  function selectAddManyTest(testId) {
    setAddMany((f) => ({ ...f, assigned_test: testId }));
    const t = testId ? tests.find((x) => String(x.id) === String(testId)) : null;
    setAddManyTestParams(t ? testParamsFromTest(t) : null);
  }

  async function submitAddMany() {
    const names = [...new Set(addMany.names.split("\n").map((s) => s.trim()).filter(Boolean))];
    if (!names.length) {
      setAddManyResult({ created: 0, errors: [{ name: "-", error: "Kamida bitta ism-familiya kiriting." }] });
      return;
    }
    setAddManyBusy(true);
    let created = 0;
    const errors = [];
    for (const name of names) {
      try {
        await createEmployee({
          full_name: name,
          password: addMany.password || "1234",
          department: addMany.department || "",
          assigned_test: addMany.assigned_test || null,
          language: addMany.language,
        });
        created++;
      } catch (e) {
        errors.push({ name, error: e.message });
      }
    }
    if (addMany.assigned_test && addManyTestParams) {
      await updateTest(addMany.assigned_test, addManyTestParams);
    }
    setAddManyResult({ created, errors });
    setAddManyBusy(false);
    await load();
  }

  const assignedCount = employees.filter((e) => e.status === "assigned").length;
  const completedCount = employees.filter((e) => e.status === "completed").length;

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-card2">
          <div><div className="stat-card2-label">Jami xodimlar</div><div className="stat-card2-num">{employees.length}</div></div>
          <div className="icon-square blue"><IconUsers /></div>
        </div>
        <div className="stat-card2">
          <div><div className="stat-card2-label">Kutilmoqda</div><div className="stat-card2-num">{assignedCount}</div></div>
          <div className="icon-square yellow"><IconTest /></div>
        </div>
        <div className="stat-card2">
          <div><div className="stat-card2-label">Topshirgan</div><div className="stat-card2-num">{completedCount}</div></div>
          <div className="icon-square purple"><IconResults /></div>
        </div>
      </div>

      <div className="adm-card">
        <div className="adm-title-row">
          <h2>Xodimlar ro'yxati</h2>
          <div className="adm-toolbar-btns">
            <button className="btn2 primary" onClick={openAddMany}><IconPlus width={16} height={16} /> Xodim qo'shish</button>
          </div>
        </div>

        <div className="adm-search-row">
          <span className="adm-count-pill">Jami: {employees.length}</span>
          <div className="adm-search-box">
            <IconSearch width={16} height={16} />
            <input
              className="field"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Ism-familiya bo'yicha qidirish..."
            />
          </div>
        </div>

        {selected.size > 0 && (
          <div className="bulk-bar">
            <span>{selected.size} ta xodim tanlandi</span>
            <select className="field sm" value={bulkTest} onChange={(e) => setBulkTest(e.target.value)}>
              <option value="">— test tanlang —</option>
              {tests.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <button className="btn2 primary" onClick={bulkAssign} disabled={!bulkTest || bulkBusy}>
              Biriktirish
            </button>
            <button className="btn2" onClick={() => setSelected(new Set())}>Bekor qilish</button>
          </div>
        )}

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-check">
                  <input type="checkbox" checked={allShownSelected} onChange={toggleSelectAll} />
                </th>
                <th>Ism-familiya</th>
                <th>Test (lavozim)</th>
                <th>Bo'lim</th>
                <th>Til</th>
                <th>Holat</th>
                <th className="col-actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((e) => (
                <tr key={e.id}>
                  <td className="col-check">
                    <input type="checkbox" checked={selected.has(e.id)} onChange={() => toggleSelect(e.id)} />
                  </td>
                  <td>
                    <div className="adm-name-cell">
                      <div className="adm-name-avatar">{e.full_name.trim().charAt(0).toUpperCase() || "?"}</div>
                      <div>
                        {e.full_name}
                        <div className="adm-name-sub">{e.assigned_test_name || "Test yo'q"}</div>
                      </div>
                    </div>
                  </td>
                  <td>{e.assigned_test_name || "—"}</td>
                  <td>{e.department || "—"}</td>
                  <td>{LANGS.find((l) => l.value === e.language)?.label || e.language}</td>
                  <td>
                    <span className={"badge " + (e.status === "completed" ? "done" : "open")}>
                      {e.status === "completed" ? "Topshirilgan" : "Tayinlangan"}
                    </span>
                  </td>
                  <td className="col-actions">
                    <div className="adm-icon-row">
                      <button className="adm-icon-btn" title="Tahrirlash" onClick={() => openEdit(e)}>
                        <IconEdit width={15} height={15} />
                      </button>
                      {e.status === "completed" && (
                        <button className="adm-icon-btn success" title="Qayta biriktirish" onClick={() => resetStatus(e)}>
                          <IconCheck width={15} height={15} />
                        </button>
                      )}
                      <button className="adm-icon-btn danger" title="O'chirish" onClick={() => remove(e)}>
                        <IconTrash width={15} height={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!shown.length && (
                <tr>
                  <td colSpan={7} className="empty">{q ? "Hech narsa topilmadi" : "Xodimlar yo'q"}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {form && (
        <div className="modal-backdrop" onClick={close}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Xodimni tahrirlash</h3>

            <div className="form-grid">
              <div className="fg span2">
                <label>Ism-familiya</label>
                <input
                  className="field"
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                />
              </div>

              <div className="fg">
                <label>Parol (bo'sh qoldirsangiz o'zgarmaydi)</label>
                <input
                  className="field"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                />
              </div>

              <div className="fg">
                <label>Til</label>
                <select
                  className="field"
                  value={form.language}
                  onChange={(e) => setForm({ ...form, language: e.target.value })}
                >
                  {LANGS.map((l) => (
                    <option key={l.value} value={l.value}>{l.label}</option>
                  ))}
                </select>
              </div>

              <div className="fg span2">
                <label>Bo'lim</label>
                {/* Bu oyna orqali yaratilgan xodim doim parol bilan kiradi (BnpzId'da yo'q),
                    ya'ni nomzod. BnpzId'dan kelgan xodimning bo'limi esa sinxronizatsiyadan
                    keladi — ikkalasi ham qo'lda kiritilmaydi. */}
                <input className="field" value={form.is_manual === false ? (form.department || "—") : "Nomzod"} disabled readOnly />
                <div className="hint">
                  {form.is_manual === false
                    ? "Bu xodim BnpzId ro'yxatidan kelgan — bo'lim sinxronizatsiya orqali yangilanadi."
                    : "Ism-familiya va parol bilan kiradigan xodimlar BnpzId ro'yxatida bo'lmaydi — "
                      + "ular nomzod hisoblanadi. Sex/bo'lim faqat BnpzId'dan kelgan xodimlarda bo'ladi."}
                </div>
              </div>

              <div className="fg span2">
                <label>Biriktirilgan test (lavozim)</label>
                <select
                  className="field"
                  value={form.assigned_test || ""}
                  onChange={(e) => selectTest(e.target.value)}
                >
                  <option value="">— tanlanmagan —</option>
                  {tests.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {testParams && (
              <div className="test-params-box">
                <div className="test-params-title">
                  Test parametrlari — bu sozlamalar shu testga biriktirilgan{" "}
                  <b>barcha xodimlarga</b> tegishli
                </div>
                <TestParamsFields values={testParams} onChange={setTestParams} />
              </div>
            )}

            {error && <div className="alert">{error}</div>}

            <div className="btnrow">
              <button className="btn2" onClick={close}>Bekor qilish</button>
              <button className="btn2 primary" onClick={save} disabled={busy}>Saqlash</button>
            </div>
          </div>
        </div>
      )}

      {addMany && (
        <div className="modal-backdrop" onClick={closeAddMany}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <h3>Xodim qo'shish</h3>
            <div className="hint" style={{ marginTop: -8 }}>
              Bitta yoki bir nechta xodimning ism-familiyasini har birini alohida qatorga
              yozing. Barchasiga bir xil parol, til va test biriktiriladi — keyinroq har
              birini alohida tahrirlash mumkin.
            </div>

            <label>Ism-familiya(lar)</label>
            <textarea
              className="field textarea-lg"
              rows={8}
              value={addMany.names}
              onChange={(e) => setAddMany({ ...addMany, names: e.target.value })}
              placeholder={"Karimov Aziz\nSoliyeva Nigora\nToshpo'latov Bekzod"}
            />

            <div className="form-grid">
              <div className="fg">
                <label>Barchasiga parol</label>
                <input
                  className="field"
                  value={addMany.password}
                  onChange={(e) => setAddMany({ ...addMany, password: e.target.value })}
                  placeholder="1234"
                />
              </div>

              <div className="fg">
                <label>Til</label>
                <select
                  className="field"
                  value={addMany.language}
                  onChange={(e) => setAddMany({ ...addMany, language: e.target.value })}
                >
                  {LANGS.map((l) => (
                    <option key={l.value} value={l.value}>{l.label}</option>
                  ))}
                </select>
              </div>

              <div className="fg">
                <label>Bo'lim</label>
                <input className="field" value="Nomzod" disabled readOnly />
                <div className="hint">Parol bilan kiradigan xodimlar nomzod hisoblanadi.</div>
              </div>

              <div className="fg span2">
                <label>Biriktiriladigan test (lavozim)</label>
                <select
                  className="field"
                  value={addMany.assigned_test}
                  onChange={(e) => selectAddManyTest(e.target.value)}
                >
                  <option value="">— tanlanmagan —</option>
                  {tests.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {addManyTestParams && (
              <div className="test-params-box">
                <div className="test-params-title">
                  Test parametrlari — bu sozlamalar shu testga biriktirilgan{" "}
                  <b>barcha xodimlarga</b> tegishli
                </div>
                <TestParamsFields values={addManyTestParams} onChange={setAddManyTestParams} />
              </div>
            )}

            {addManyResult && (
              <div className={"alert " + (addManyResult.errors.length ? "" : "ok")}>
                {addManyResult.created} ta xodim qo'shildi.
                {addManyResult.errors.length > 0 && (
                  <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                    {addManyResult.errors.map((er, i) => (
                      <li key={i}>{er.name}: {er.error}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="btnrow">
              <button className="btn2" onClick={closeAddMany}>
                {addManyResult ? "Yopish" : "Bekor qilish"}
              </button>
              <button className="btn2 primary" onClick={submitAddMany} disabled={addManyBusy}>
                {addManyBusy ? "Qo'shilmoqda..." : "Qo'shish"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
