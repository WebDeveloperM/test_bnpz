import { useEffect, useState } from "react";
import { listTests, createTest, updateTest, deleteTest, listTsexOptions } from "../adminApi.js";
import QuestionsEditor from "./QuestionsEditor.jsx";
import { MODES } from "./TestParamsFields.jsx";
import ComboInput from "./ComboInput.jsx";
import { IconPlus, IconList, IconEdit, IconTrash } from "./icons.jsx";

const EMPTY = {
  name: "", tsex: "", mode: "oddiy", introduction: "", grading_scale: "foiz",
  pass_percent: 60, time_limit: 0, time_limit_scope: "test", shuffle_questions: true,
  shuffle_options: true, sample_count: 0, instant_feedback: false, grade_thresholds: [],
  is_common_pool: false,
};

export default function TestsTab() {
  const [tests, setTests] = useState([]);
  const [form, setForm] = useState(null);
  const [openTest, setOpenTest] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tsexFilter, setTsexFilter] = useState("");
  const [tsexOptions, setTsexOptions] = useState([]);

  async function load() {
    setTests(await listTests());
  }

  useEffect(() => {
    load();
    listTsexOptions().then(setTsexOptions).catch(() => {});
  }, []);

  // Filter faqat allaqachon lavozimlarga biriktirilgan sexlarni ko'rsatadi;
  // datalist esa BnpzId katalogidagi BARCHA sexlarni (tanlashda yozish/tanlash uchun).
  //
  // Katalog tartibi MANBADAN keladi (`sort_order` — ishlab chiqarish ketma-ketligi),
  // shuning uchun uni alifboga qayta saralamaymiz: aks holda «10-Цех» «2-Цех» dan
  // oldin turib qolardi. Testlarda uchraydigan, katalogda yo'q nomlar oxiriga
  // qo'shiladi.
  const tsexList = [...new Set(tests.map((t) => t.tsex).filter(Boolean))].sort();
  const tsexDatalistOptions = [...new Set([...tsexOptions, ...tsexList])];
  const shownTests = tsexFilter
    ? tsexFilter === "__none__"
      ? tests.filter((t) => !t.tsex)
      : tests.filter((t) => t.tsex === tsexFilter)
    : tests;


  function openNew() {
    setForm({ ...EMPTY });
    setError("");
  }
  function openEdit(test) {
    setForm({ ...EMPTY, ...test, grade_thresholds: test.grade_thresholds || [] });
    setError("");
  }
  function close() {
    setForm(null);
  }

  async function save() {
    if (!form.name.trim()) {
      setError("Test nomini kiriting.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload = { ...form };
      delete payload.id;
      delete payload.question_count;
      delete payload.created;
      if (form.id) await updateTest(form.id, payload);
      else await createTest(payload);
      await load();
      close();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(test) {
    if (!window.confirm(`"${test.name}" testi va uning barcha savollari o'chirilsinmi?`)) return;
    await deleteTest(test.id);
    load();
  }

  if (openTest) {
    return <QuestionsEditor test={openTest} onBack={() => { setOpenTest(null); load(); }} />;
  }

  return (
    <div>
      <div className="adm-card">
        <div className="adm-title-row">
          <h2>Testlar (lavozimlar)</h2>
          <div className="adm-toolbar-btns">
            <button className="btn2 primary" onClick={openNew}><IconPlus width={16} height={16} /> Test yaratish</button>
          </div>
        </div>

        <div className="adm-search-row">
          <span className="adm-count-pill">Jami: {shownTests.length}</span>
          {tsexList.length > 0 && (
            <select className="field" style={{ maxWidth: 280 }} value={tsexFilter}
              onChange={(e) => setTsexFilter(e.target.value)}>
              <option value="">Barcha sexlar</option>
              {tsexList.map((tx) => <option key={tx} value={tx}>{tx}</option>)}
              <option value="__none__">— sex belgilanmagan —</option>
            </select>
          )}
        </div>

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-num">№</th><th>Nomi</th><th>Sex/tsex</th><th>Rejim</th><th>O'tish %</th><th>Savollar</th><th className="col-actions" />
              </tr>
            </thead>
            <tbody>
              {shownTests.map((t, i) => (
                <tr key={t.id}>
                  <td className="col-num">{i + 1}</td>
                  <td>
                    {t.name}
                    {t.is_common_pool && <span className="badge done" style={{ marginLeft: 8 }}>Umumiy savollar</span>}
                  </td>
                  {/* Sex faqat KO'RSATILADI. Ilgari shu katakda to'g'ridan-to'g'ri
                      tahrirlash mumkin edi — ro'yxat bo'ylab yurganda tasodifan
                      boshqa testning sexini o'zgartirib qo'yish oson bo'lardi.
                      Endi u "Tahrirlash" oynasida, boshqa sozlamalar bilan
                      birga o'zgartiriladi. */}
                  <td>
                    {t.is_common_pool ? (
                      <span className="muted" title="Umumiy savollar to'plami biror bir sexga tegishli emas">
                        tegishli emas
                      </span>
                    ) : (
                      t.tsex || <span className="muted">—</span>
                    )}
                  </td>
                  <td>{MODES.find((m) => m.value === t.mode)?.label}</td>
                  <td>{t.pass_percent}%</td>
                  <td>{t.question_count}</td>
                  <td className="col-actions">
                    <div className="adm-icon-row">
                      <button className="adm-icon-btn" title="Savollar" onClick={() => setOpenTest(t)}>
                        <IconList width={15} height={15} />
                      </button>
                      <button className="adm-icon-btn" title="Tahrirlash" onClick={() => openEdit(t)}>
                        <IconEdit width={15} height={15} />
                      </button>
                      <button className="adm-icon-btn danger" title="O'chirish" onClick={() => remove(t)}>
                        <IconTrash width={15} height={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!shownTests.length && (
                <tr><td colSpan={7} className="empty">Testlar yo'q</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      {form && (
        <div className="modal-backdrop" onClick={close}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{form.id ? "Testni tahrirlash" : "Yangi test"}</h3>
            <label>Nomi (lavozim)</label>
            <input className="field" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <label>Sex/tsex</label>
            <ComboInput
              options={tsexDatalistOptions}
              value={form.tsex}
              placeholder="Yozing yoki ro'yxatdan tanlang"
              onChange={(v) => setForm({ ...form, tsex: v })}
            />
            <label>Kirish yo'riqnomasi</label>
            <textarea className="field" rows={3} value={form.introduction}
              onChange={(e) => setForm({ ...form, introduction: e.target.value })} />

            <label className="chk" style={{ marginTop: 14 }}>
              <input type="checkbox" checked={form.is_common_pool}
                onChange={(e) => setForm({ ...form, is_common_pool: e.target.checked })} />
              Bu — umumiy savollar to'plami
            </label>
            <div className="hint" style={{ marginTop: -6 }}>
              Rejim, o'tish foizi, vaqt chegarasi, aralashtirish va boshqa test parametrlari
              xodimni shu testga biriktirayotganda (Xodimlar bo'limida) sozlanadi.
            </div>

            {error && <div className="alert">{error}</div>}

            <div className="btnrow">
              <button className="btn2" onClick={close}>Bekor qilish</button>
              <button className="btn2 primary" onClick={save} disabled={busy}>Saqlash</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
