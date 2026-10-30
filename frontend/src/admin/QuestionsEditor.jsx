import { useEffect, useRef, useState } from "react";
import {
  listQuestions, createQuestion, updateQuestion, deleteQuestion,
  uploadQuestionImage, deleteQuestionImage, importQuestions,
  uploadOptionImage, deleteOptionImage,
} from "../adminApi.js";
import { IconPlus, IconUpload, IconDownload, IconEdit, IconTrash, IconImage } from "./icons.jsx";
import { LANGUAGES } from "../i18n.js";

const BASE_LANG = "uz";

// Tarjimalardan bo'sh matnlarni olib tashlaydi: bo'sh qatorni saqlash "tarjima
// bor, lekin bo'sh" degani bo'lib qolardi va xodimga bo'sh savol ko'rsatilardi.
// Tozalangandan keyin o'sha til uchun asosiy matn ko'rsatiladi.
function pruneI18n(i18n) {
  const out = {};
  for (const [lang, values] of Object.entries(i18n || {})) {
    const kept = Object.fromEntries(
      Object.entries(values || {}).filter(([, v]) => (v || "").trim())
    );
    if (Object.keys(kept).length) out[lang] = kept;
  }
  return out;
}

// "Namuna fayl" tugmasi yuklab beradigan tayyor import shabloni.
//
// DIQQAT: bu HAQIQIY, o'zgartirmasdan import qilsa bo'ladigan fayl — parser
// har bir bo'sh qator bilan ajratilgan blokni savol deb o'qiydi, shuning uchun
// fayl ichiga "izoh" qatorlari yozib bo'lmaydi (ular savol bo'lib o'qiladi).
// Shu sabab format faqat SHU YERDA, kodda tushuntiriladi:
//   birinchi qator — savol matni ("1." raqamlash ixtiyoriy)
//   +variant — to'g'ri javob, -variant — noto'g'ri javob
//   #ru / #krill — o'sha savolning boshqa tildagi tarjimasi
//   bo'sh qator — keyingi savolning boshlanishi
//
// Namunada ATAYLAB bitta savol qoldirilgan: shablon "nusxa olib to'ldiriladigan
// bitta qolip" bo'lishi kerak. Ilgari bu yerda 6 xil turdagi savol bor edi va
// administrator ularning hammasini o'chirib chiqishga majbur bo'lardi — yoki
// e'tibordan chetda qolgan namuna savol haqiqiy testga tushib ketardi.
const TEMPLATE_TXT = `1. Kompyuterning markaziy protsessori qanday nomlanadi?
+CPU
-RAM
-HDD
#ru
Как называется центральный процессор компьютера?
+CPU
-RAM
-HDD
#krill
Компьютернинг марказий процессори қандай номланади?
+CPU
-RAM
-HDD
`;

function downloadTemplate() {
  const blob = new Blob([TEMPLATE_TXT], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "savollar_namuna.txt";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Muharrirda YARATISH mumkin bo'lgan turlar — atayin faqat 3 ta.
const QTYPES = [
  { value: "single", label: "Bir tanlovli" },
  { value: "multiple", label: "Ko'p tanlovli" },
  { value: "fillblank", label: "Bo'sh joyni to'ldirish" },
];
// Barcha turlar nomi — RO'YXATDA ko'rsatish uchun. Eski (yoki fayldan import
// qilingan) savol dropdownда yo'q turda bo'lishi mumkin — nomi baribir ko'rinsin,
// bo'sh katak qolmasin.
const QTYPE_LABELS = {
  single: "Bir tanlovli",
  multiple: "Ko'p tanlovli",
  truefalse: "To'g'ri/Noto'g'ri",
  text: "Matn/raqam kiritish",
  fillblank: "Bo'sh joyni to'ldirish",
  ordering: "Tartiblash",
  matching: "Moslashtirish",
};
const TEXT_TYPES = ["text", "fillblank"];

function emptyQuestion(testId) {
  return {
    test: testId, qtype: "single", text: "", points: 1, explanation: "", correct_text: "",
    options: [{ text: "", is_correct: true }, { text: "", is_correct: false }],
  };
}

export default function QuestionsEditor({ test, onBack }) {
  const [questions, setQuestions] = useState([]);
  const [form, setForm] = useState(null);
  const [imageFile, setImageFile] = useState(null);
  // Variantlarning yuklanishi kutilayotgan rasmlari: {variant indeksi: File}.
  // Ular savol saqlangandan KEYIN yuboriladi — variant id'si shunda ma'lum
  // bo'ladi (yangi savolda variantlar hali umuman mavjud emas).
  const [optionImages, setOptionImages] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [lang, setLang] = useState(BASE_LANG); // tahrirlanayotgan til
  const importInputRef = useRef(null);

  const isBase = lang === BASE_LANG;

  // Asosiy tilda oddiy maydonlar, tarjima tilida `i18n` ichidagi qiymat tahrirlanadi.
  const trValue = (obj, field) =>
    (isBase ? obj?.[field] : ((obj?.i18n || {})[lang] || {})[field]) || "";

  function setQField(field, value) {
    setForm((f) => (isBase
      ? { ...f, [field]: value }
      : { ...f, i18n: { ...(f.i18n || {}), [lang]: { ...((f.i18n || {})[lang] || {}), [field]: value } } }));
  }
  function setOptField(i, field, value) {
    setForm((f) => ({
      ...f,
      options: f.options.map((o, idx) => (idx !== i ? o : (isBase
        ? { ...o, [field]: value }
        : { ...o, i18n: { ...(o.i18n || {}), [lang]: { ...((o.i18n || {})[lang] || {}), [field]: value } } }))),
    }));
  }

  // Savolda qaysi tarjimalar bor — ro'yxatda ko'rsatiladi, tarjimasizlarini
  // darhol ajratib olish uchun.
  const questionLangs = (q) => LANGUAGES.filter(
    (l) => l.code !== BASE_LANG && ((q.i18n || {})[l.code] || {}).text
  );

  async function load() {
    setQuestions(await listQuestions(test.id));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openNew() {
    setForm(emptyQuestion(test.id));
    setImageFile(null);
    setLang(BASE_LANG);
    setError("");
  }
  function openEdit(q) {
    setForm({
      ...q,
      options: q.options.length ? q.options : [{ text: "", is_correct: true }, { text: "", is_correct: false }],
    });
    setImageFile(null);
    setLang(BASE_LANG);
    setError("");
  }
  function close() {
    setForm(null);
    setImageFile(null);
    setOptionImages({});
  }

  function setQtype(newType) {
    // Variantlar ro'yxati butunlay almashadi — tanlangan rasmlar ham
    // eskirgan indekslarga bog'lanib qolmasligi uchun tozalanadi.
    setOptionImages({});
    setForm((f) => {
      let options = f.options;
      const wasText = TEXT_TYPES.includes(f.qtype);
      const willBeText = TEXT_TYPES.includes(newType);
      if (newType === "truefalse") {
        options = [{ text: "To'g'ri", is_correct: true }, { text: "Noto'g'ri", is_correct: false }];
      } else if (willBeText) {
        options = [];
      } else if (newType === "ordering") {
        options = [{ text: "" }, { text: "" }, { text: "" }];
      } else if (newType === "matching") {
        options = [{ text: "", match_text: "" }, { text: "", match_text: "" }];
      } else if (f.qtype === "truefalse" || wasText || f.qtype === "ordering" || f.qtype === "matching") {
        options = [{ text: "", is_correct: true }, { text: "", is_correct: false }];
      }
      return { ...f, qtype: newType, options };
    });
  }

  function addOption() {
    setForm((f) => ({
      ...f,
      options: [...f.options, f.qtype === "matching" ? { text: "", match_text: "" } : { text: "", is_correct: false }],
    }));
  }
  function removeOption(i) {
    setForm((f) => ({ ...f, options: f.options.filter((_, idx) => idx !== i) }));
    // Tanlangan rasmlar indeks bo'yicha saqlanadi, shuning uchun o'chirilgan
    // variantdan keyingilari bir pog'ona suriladi — aks holda rasm boshqa
    // variantga tushib qolardi.
    setOptionImages((prev) => {
      const next = {};
      for (const [key, file] of Object.entries(prev)) {
        const idx = Number(key);
        if (idx < i) next[idx] = file;
        else if (idx > i) next[idx - 1] = file;
      }
      return next;
    });
  }
  function updateOptionText(i, text) {
    setForm((f) => ({ ...f, options: f.options.map((o, idx) => (idx === i ? { ...o, text } : o)) }));
  }
  function updateMatchText(i, matchText) {
    setForm((f) => ({
      ...f,
      options: f.options.map((o, idx) => (idx === i ? { ...o, match_text: matchText } : o)),
    }));
  }
  function toggleCorrect(i) {
    setForm((f) => ({
      ...f,
      options: f.options.map((o, idx) =>
        f.qtype === "multiple" ? (idx === i ? { ...o, is_correct: !o.is_correct } : o) : { ...o, is_correct: idx === i }
      ),
    }));
  }
  function moveOption(i, dir) {
    setForm((f) => {
      const j = i + dir;
      if (j < 0 || j >= f.options.length) return f;
      const options = [...f.options];
      [options[i], options[j]] = [options[j], options[i]];
      return { ...f, options };
    });
  }

  async function save() {
    if (!form.text.trim()) {
      setError("Savol matnini kiriting (asosiy til — O'zbekcha).");
      setLang(BASE_LANG);
      return;
    }
    // Variantda matn ham, rasm ham bo'lmasa xodimga bo'sh katak ko'rinardi.
    // Rasm yetarli — matn shart emas, lekin ikkalasi ham bo'sh bo'lmasin.
    if (!TEXT_TYPES.includes(form.qtype)) {
      const emptyIdx = (form.options || []).findIndex(
        (o, i) => !(o.text || "").trim() && !o.image_url && !optionImages[i],
      );
      if (emptyIdx >= 0) {
        setError(`${emptyIdx + 1}-variant bo'sh: matn kiriting yoki rasm tanlang.`);
        setLang(BASE_LANG);
        return;
      }
    }
    setBusy(true);
    setError("");
    try {
      const payload = {
        ...form,
        i18n: pruneI18n(form.i18n),
        options: (form.options || []).map((o) => {
          const clean = { ...o, i18n: pruneI18n(o.i18n) };
          // `image_url` — faqat ko'rsatish uchun (serverda read-only).
          // Variantning `id` si esa ATAYLAB yuboriladi: server shu id bo'yicha
          // mavjud variantni yangilaydi va rasmini joyida qoldiradi.
          delete clean.image_url;
          return clean;
        }),
      };
      delete payload.id;
      delete payload.image_url;
      let questionId = form.id;
      let saved;
      if (questionId) saved = await updateQuestion(questionId, payload);
      else {
        saved = await createQuestion(payload);
        questionId = saved.id;
      }
      if (imageFile) await uploadQuestionImage(questionId, imageFile);

      // Variant rasmlari: id'lar faqat saqlangandan keyin ma'lum bo'ladi.
      // Server variantlarni forma tartibida qaytaradi (`order` = indeks),
      // shuning uchun indeks bo'yicha moslashtiramiz.
      const savedOptions = saved?.options || [];
      for (const [idx, file] of Object.entries(optionImages)) {
        const opt = savedOptions[Number(idx)];
        if (opt?.id && file) await uploadOptionImage(opt.id, file);
      }

      await load();
      close();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function setOptionImage(i, file) {
    setOptionImages((prev) => {
      const next = { ...prev };
      if (file) next[i] = file;
      else delete next[i];
      return next;
    });
  }

  async function removeOptionImage(i) {
    const opt = form.options[i];
    // Hali yuklanmagan (faqat tanlangan) rasm bo'lsa — serverga bormaymiz.
    if (opt?.id && opt.image_url) await deleteOptionImage(opt.id);
    setForm((f) => ({
      ...f,
      options: f.options.map((o, idx) => (idx === i ? { ...o, image_url: null } : o)),
    }));
    setOptionImage(i, null);
  }

  async function removeImage() {
    await deleteQuestionImage(form.id);
    setForm({ ...form, image_url: null });
    setImageFile(null);
    load();
  }

  async function remove(q) {
    if (!window.confirm("Savol o'chirilsinmi?")) return;
    await deleteQuestion(q.id);
    load();
  }

  // Xatolik qatorini bitta ko'rinishda yozadi: "3-savol: ..." yoki (faylga
  // taalluqli bo'lmagan umumiy xato uchun) shunchaki matnning o'zi.
  function formatImportError(er, rowLabel) {
    return er.row === "-" || er.row == null
      ? er.error
      : `${er.row}-${rowLabel}: ${er.error}`;
  }

  async function handleImportFile(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setImportBusy(true);
    setImportResult(null);
    try {
      const res = await importQuestions(test.id, file);
      setImportResult({ ok: true, created: res.created, errors: [], rowLabel: res.row_label || "qator" });
      await load();
      window.alert(`Import muvaffaqiyatli: ${res.created} ta savol qo'shildi.`);
    } catch (err) {
      // Server "hammasi yoki hech narsa" qoidasi bilan ishlaydi: xatolik
      // bo'lsa BIRORTA ham savol qo'shilmagan bo'ladi. Shuning uchun bu yerda
      // ro'yxatni qayta yuklash shart emas — testda hech narsa o'zgarmagan.
      const rowLabel = err.rowLabel || "qator";
      const errors = err.errors?.length ? err.errors : [{ row: "-", error: err.message }];
      setImportResult({ ok: false, created: 0, errors, rowLabel, message: err.message });

      const shown = errors.slice(0, 10).map((er) => "• " + formatImportError(er, rowLabel));
      if (errors.length > 10) {
        shown.push(`… va yana ${errors.length - 10} ta xatolik (to'liq ro'yxat sahifada).`);
      }
      window.alert(
        "IMPORT BEKOR QILINDI — hech qanday savol qo'shilmadi.\n\n"
        + "Faylda quyidagi xatoliklar topildi. Ularni to'g'rilab, faylni qaytadan yuklang:\n\n"
        + shown.join("\n"),
      );
    } finally {
      setImportBusy(false);
    }
  }

  const canAddRemoveOptions = form && ["single", "multiple", "ordering", "matching"].includes(form.qtype);

  return (
    <div>
      <div className="adm-card">
        <div className="adm-title-row">
          <div className="qedit-heading">
            <button className="btn2 sm" onClick={onBack}>← Testlarga</button>
            <h2>{test.name} — savollar</h2>
          </div>
          <div className="adm-toolbar-btns">
            <button className="btn2" onClick={downloadTemplate}
              title="Bitta namuna savol (o'zbekcha, ruscha, krillcha) — shu qolipdan nusxa olib to'ldiring">
              <IconDownload width={16} height={16} /> Namuna fayl
            </button>
            <button className="btn2" onClick={() => importInputRef.current?.click()} disabled={importBusy}>
              <IconUpload width={16} height={16} /> {importBusy ? "Yuklanmoqda..." : "Fayldan import qilish"}
            </button>
            <input
              ref={importInputRef}
              type="file"
              accept=".txt,.csv,text/plain,text/csv"
              style={{ display: "none" }}
              onChange={handleImportFile}
            />
            <button className="btn2 primary" onClick={openNew}><IconPlus width={16} height={16} /> Savol qo'shish</button>
          </div>
        </div>

        {importResult && (
          <div className={"alert " + (importResult.ok ? "ok" : "")} style={{ marginBottom: 14 }}>
            {importResult.ok ? (
              <>{importResult.created} ta savol import qilindi.</>
            ) : (
              <>
                <b>Import bekor qilindi — hech qanday savol qo'shilmadi.</b>
                <div style={{ marginTop: 4 }}>
                  Quyidagi xatoliklarni faylda to'g'rilab, faylni qaytadan yuklang.
                </div>
                <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                  {importResult.errors.map((er, i) => (
                    <li key={i}>{formatImportError(er, importResult.rowLabel)}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-num">№</th><th>Savol</th><th>Turi</th><th>Ball</th><th>Tillar</th><th className="col-actions" />
              </tr>
            </thead>
            <tbody>
              {questions.map((q, i) => (
                <tr key={q.id}>
                  <td className="col-num">{i + 1}</td>
                  <td>{q.text}</td>
                  <td>{QTYPE_LABELS[q.qtype] || q.qtype}</td>
                  <td>{q.points}</td>
                  <td>
                    {questionLangs(q).length
                      ? questionLangs(q).map((l) => (
                          <span key={l.code} className="lang-chip" title={l.label}>{l.short}</span>
                        ))
                      : <span className="lang-chip muted" title="Faqat asosiy tilda">—</span>}
                  </td>
                  <td className="col-actions">
                    <div className="adm-icon-row">
                      <button className="adm-icon-btn" title="Tahrirlash" onClick={() => openEdit(q)}>
                        <IconEdit width={15} height={15} />
                      </button>
                      <button className="adm-icon-btn danger" title="O'chirish" onClick={() => remove(q)}>
                        <IconTrash width={15} height={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!questions.length && (
                <tr><td colSpan={6} className="empty">Savollar yo'q</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {form && (
        <div className="modal-backdrop" onClick={close}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <div className="adm-title-row" style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>{form.id ? "Savolni tahrirlash" : "Yangi savol"}</h3>
              <div className="lang-switch">
                {LANGUAGES.map((l) => (
                  <button
                    key={l.code}
                    type="button"
                    className={"lang-btn" + (l.code === lang ? " active" : "")}
                    onClick={() => setLang(l.code)}
                    title={l.code === BASE_LANG ? `${l.label} (asosiy til)` : `${l.label} — tarjima`}
                  >
                    {l.short}
                    {l.code !== BASE_LANG && ((form.i18n || {})[l.code] || {}).text ? " ✓" : ""}
                  </button>
                ))}
              </div>
            </div>

            {!isBase && (
              <div className="hint" style={{ marginBottom: 10 }}>
                Tarjima rejimi ({LANGUAGES.find((l) => l.code === lang)?.label}) — faqat matnlar
                tahrirlanadi. Savol turi, ballar va to'g'ri javob barcha tillar uchun umumiy,
                shuning uchun ular faqat asosiy tilda o'zgartiriladi. Bo'sh qoldirilgan matn
                o'rniga xodimga o'zbekcha matn ko'rsatiladi.
              </div>
            )}

            <div className="form-grid">
              {isBase && (
                <>
                  <div className="fg">
                    <label>Savol turi</label>
                    <select className="field" value={form.qtype} onChange={(e) => setQtype(e.target.value)}>
                      {QTYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                      {/* Eski savol dropdownда yo'q turda bo'lsa — turini
                          yo'qotib qo'ymaslik uchun uni ham ko'rsatamiz. */}
                      {!QTYPES.some((t) => t.value === form.qtype) && (
                        <option value={form.qtype}>{QTYPE_LABELS[form.qtype] || form.qtype}</option>
                      )}
                    </select>
                  </div>

                </>
              )}

              <div className="fg span2">
                <label>Savol matni</label>
                <textarea className="field" rows={2} value={trValue(form, "text")}
                  onChange={(e) => setQField("text", e.target.value)} />
                {!isBase && <div className="hint">Asosiy matn: {form.text || "—"}</div>}
              </div>

              {isBase && (
                <>
                  <div className="fg">
                    <label>Ball (og'irlik)</label>
                    <input className="field" type="number" min="1" value={form.points}
                      onChange={(e) => setForm({ ...form, points: Number(e.target.value) })} />
                  </div>

                  <div className="fg">
                    <label>Rasm (ixtiyoriy)</label>
                    {form.image_url && !imageFile && (
                      <div className="q-image-preview">
                        <img src={form.image_url} alt="" />
                        <button className="btn ghost sm danger" onClick={removeImage}>Rasmni o'chirish</button>
                      </div>
                    )}
                    <input
                      className="field"
                      type="file"
                      accept="image/*"
                      onChange={(e) => setImageFile(e.target.files[0] || null)}
                    />
                  </div>
                </>
              )}

              <div className="fg span2">
                {TEXT_TYPES.includes(form.qtype) ? (
                  <>
                    <label>To'g'ri javob (matn yoki raqam)</label>
                    <input className="field" value={trValue(form, "correct_text")}
                      onChange={(e) => setQField("correct_text", e.target.value)} />
                    {!isBase && (
                      <div className="hint">
                        Asosiy javob: {form.correct_text || "—"} — xodim istalgan tildagi to'g'ri
                        javobni yozsa qabul qilinadi.
                      </div>
                    )}
                    {form.qtype === "fillblank" && (
                      <div className="hint">Savol matnida bo'sh joy o'rnini "___" (uch tire) bilan belgilashingiz mumkin.</div>
                    )}
                  </>
                ) : form.qtype === "ordering" ? (
                  <>
                    <label>Elementlar (to'g'ri tartibda kiriting; xodimga aralashtirilgan holda ko'rsatiladi)</label>
                    {form.options.map((o, i) => (
                      <div className="option-row" key={i}>
                        <span className="order-num">{i + 1}</span>
                        <input
                          className="field"
                          value={trValue(o, "text")}
                          onChange={(e) => setOptField(i, "text", e.target.value)}
                          placeholder={isBase ? `${i + 1}-element` : o.text}
                        />
                        {isBase && <>
                          <button className="btn ghost sm" onClick={() => moveOption(i, -1)} disabled={i === 0}>↑</button>
                          <button className="btn ghost sm" onClick={() => moveOption(i, 1)} disabled={i === form.options.length - 1}>↓</button>
                          {form.options.length > 2 && (
                            <button className="btn ghost sm danger" onClick={() => removeOption(i)}>✕</button>
                          )}
                        </>}
                      </div>
                    ))}
                    {isBase && <button className="btn ghost sm" onClick={addOption}>+ Element qo'shish</button>}
                  </>
                ) : form.qtype === "matching" ? (
                  <>
                    <label>Juftlar (chap ustun ↔ mos javob)</label>
                    {form.options.map((o, i) => (
                      <div className="option-row" key={i}>
                        <input
                          className="field"
                          value={trValue(o, "text")}
                          onChange={(e) => setOptField(i, "text", e.target.value)}
                          placeholder={isBase ? `Chap ${i + 1}` : o.text}
                        />
                        <span>↔</span>
                        <input
                          className="field"
                          value={trValue(o, "match_text")}
                          onChange={(e) => setOptField(i, "match_text", e.target.value)}
                          placeholder={isBase ? `Mos javob ${i + 1}` : o.match_text}
                        />
                        {isBase && form.options.length > 2 && (
                          <button className="btn ghost sm danger" onClick={() => removeOption(i)}>✕</button>
                        )}
                      </div>
                    ))}
                    {isBase && <button className="btn ghost sm" onClick={addOption}>+ Juft qo'shish</button>}
                  </>
                ) : (
                  <>
                    <label>Variantlar {form.qtype === "multiple" ? "(bir nechtasi to'g'ri bo'lishi mumkin)" : "(bittasi to'g'ri)"}</label>
                    {form.options.map((o, i) => (
                      <div className="option-row" key={i}>
                        <input
                          type={form.qtype === "multiple" ? "checkbox" : "radio"}
                          checked={o.is_correct}
                          disabled={!isBase}
                          onChange={() => toggleCorrect(i)}
                        />
                        {/* Matn maydoni + rasm tugmasi bitta ramka ichida:
                            tugma inputning o'ng chetiga joylashadi, alohida
                            qatorda turib ko'rinishni buzmaydi. Rasm boshqaruvi —
                            struktura, shuning uchun faqat asosiy tilda ko'rinadi
                            (tarjima varag'ida savol tuzilishi o'zgarmaydi). */}
                        <div className="opt-input">
                          <input
                            className="field"
                            value={trValue(o, "text")}
                            disabled={isBase && form.qtype === "truefalse"}
                            onChange={(e) => setOptField(i, "text", e.target.value)}
                            placeholder={isBase ? `Variant ${i + 1}` : o.text}
                          />
                          {isBase && (
                            (o.image_url || optionImages[i]) ? (
                              <button
                                type="button"
                                className="opt-img-chip has-img"
                                title="Rasm biriktirilgan — o'chirish uchun bosing"
                                onClick={() => removeOptionImage(i)}
                              >
                                <img
                                  src={optionImages[i] ? URL.createObjectURL(optionImages[i]) : o.image_url}
                                  alt=""
                                />
                              </button>
                            ) : (
                              <label className="opt-img-chip" title="Rasm biriktirish">
                                <IconImage width={16} height={16} />
                                <input
                                  type="file"
                                  accept="image/*"
                                  style={{ display: "none" }}
                                  onChange={(e) => setOptionImage(i, e.target.files[0] || null)}
                                />
                              </label>
                            )
                          )}
                        </div>
                        {isBase && canAddRemoveOptions && form.options.length > 2 && (
                          <button className="btn ghost sm danger" onClick={() => removeOption(i)}>✕</button>
                        )}
                      </div>
                    ))}
                    {isBase && canAddRemoveOptions && (
                      <button className="btn ghost sm" onClick={addOption}>+ Variant qo'shish</button>
                    )}
                  </>
                )}
              </div>

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
