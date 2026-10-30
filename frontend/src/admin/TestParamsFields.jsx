import { useEffect, useRef, useState } from "react";
import { IconInfo } from "./icons.jsx";

// Rejim ikki narsani belgilaydi: savollar bo'ylab QANDAY yurish mumkinligi va
// ball QANDAY hisoblanishi. Har bir izoh aynan shu ikkisini aytadi — ilgari
// ular yarim-yorti yozilgan va administrator "Jarima" da orqaga qaytish
// mumkinmi yoki javob bermaslik ham jazolanadimi degan savolga javob topmasdi.
export const MODES = [
  {
    value: "oddiy",
    label: "Oddiy",
    short: "Ketma-ket, orqaga qaytish mumkin",
    hint: (
      <>
        Savollar ketma-ket beriladi. Xodim <b>orqaga qaytib</b> javobini o'zgartira oladi,
        lekin savoldan savolga sakrab o'tolmaydi. To'g'ri javob uchun savolning balli
        qo'shiladi, noto'g'ri javob uchun <b>hech narsa ayirilmaydi</b>.
      </>
    ),
  },
  {
    value: "erkin",
    label: "Erkin",
    short: "Istalgan savolga o'tish mumkin",
    hint: (
      <>
        Xodim savollar ro'yxatidan <b>istalgan savolga</b> o'tishi, savolni o'tkazib yuborib
        keyin qaytishi mumkin. Ball hisoblash "Oddiy" bilan bir xil — noto'g'ri javob uchun
        ball ayirilmaydi.
      </>
    ),
  },
  {
    value: "jarima",
    label: "Jarima",
    short: "Noto'g'ri javob uchun ball ayiriladi",
    hint: (
      <>
        Yurish tartibi "Oddiy" bilan bir xil (ketma-ket, orqaga qaytish mumkin), lekin ball
        boshqacha: <b>noto'g'ri javob uchun savolning balli ayiriladi</b>.
        Savolga <b>umuman javob bermaslik jazolanmaydi</b> — ya'ni bilmagan savolni bo'sh
        qoldirish tavakkal qilishdan foydaliroq. Umumiy ball manfiy bo'lib qolishi mumkin.
      </>
    ),
  },
  {
    value: "maksimal",
    label: "Maksimal",
    short: "Orqaga qaytish yo'q, javob qulflanadi",
    hint: (
      <>
        Eng qat'iy tartib: keyingi savolga o'tilgach <b>orqaga qaytib bo'lmaydi</b> va javob
        serverda <b>qulflanadi</b> — uni boshqa o'zgartirib bo'lmaydi. Ball hisoblash "Oddiy"
        bilan bir xil, noto'g'ri javob uchun ball ayirilmaydi.
      </>
    ),
  },
];
export const SCALES = [
  { value: "foiz", label: "Foiz" },
  { value: "5", label: "5 ballik" },
  { value: "100", label: "100 ballik" },
];

const DEFAULT_THRESHOLDS = {
  "5": [{ min: 90, grade: "5" }, { min: 75, grade: "4" }, { min: 60, grade: "3" }, { min: 0, grade: "2" }],
  "100": [{ min: 86, grade: "5" }, { min: 71, grade: "4" }, { min: 55, grade: "3" }, { min: 0, grade: "2" }],
};

// Maydon + sarlavha yonidagi "i" tugmasi. Tushuntirish matni odatda YASHIRIN
// bo'ladi va faqat tugma bosilganda ochiladi — forma toza ko'rinadi, izoh esa
// kerak bo'lganda qo'l ostida turadi.
//
// Izoh maydon ostiga SUZIB chiqadi (absolute), formaga qo'shilmaydi. Ilgari u
// oddiy element sifatida qo'shilardi va ochilganda maydonning o'z boshqaruvini
// pastga surardi: ikki ustunli formada yonidagi maydon joyida qolib, qator
// cho'zilib ketardi va forma "sakragandek" ko'rinardi.
function Field({ label, info, span2, children }) {
  const [open, setOpen] = useState(false);
  const [arrowX, setArrowX] = useState(16);
  const btnRef = useRef(null);
  const boxRef = useRef(null);
  const wrapRef = useRef(null);

  function toggle() {
    setOpen((o) => {
      // Uchburchak AYNAN "i" tugmasi ostida turishi uchun tugmaning joyi
      // o'lchanadi — u sarlavha uzunligiga qarab siljiydi, shuning uchun
      // qat'iy qiymat ko'pchilik maydonlarda noto'g'ri joyga tushardi.
      if (!o && btnRef.current) setArrowX(btnRef.current.offsetLeft + 6);
      return !o;
    });
  }

  // Izoh suzib turgani uchun uni yopishning aniq yo'li bo'lishi kerak:
  // tashqariga bosish yoki Esc. Aks holda u boshqa maydonlarni to'sib turardi.
  useEffect(() => {
    if (!open) return;
    function onDown(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    }
    function onKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className={(span2 ? "fg span2" : "fg") + " fg-anchor"} ref={wrapRef}>
      <div className="label-row">
        <label>{label}</label>
        {info && (
          <button
            ref={btnRef}
            type="button"
            className={"info-btn" + (open ? " active" : "")}
            onClick={toggle}
            title={open ? "Izohni yopish" : "Izohni ko'rish"}
            aria-expanded={open}
          >
            <IconInfo width={15} height={15} />
          </button>
        )}
      </div>
      {children}
      {info && open && (
        <div className="info-box" ref={boxRef} style={{ "--arrow-x": `${arrowX}px` }} role="note">
          {info}
        </div>
      )}
    </div>
  );
}

export default function TestParamsFields({ values, onChange }) {
  function set(field, value) {
    onChange({ ...values, [field]: value });
  }
  function setMany(patch) {
    onChange({ ...values, ...patch });
  }
  function setScale(scale) {
    const next = { ...values, grading_scale: scale };
    if (scale !== "foiz" && !values.grade_thresholds.length && DEFAULT_THRESHOLDS[scale]) {
      next.grade_thresholds = DEFAULT_THRESHOLDS[scale];
    }
    onChange(next);
  }
  function addThreshold() {
    set("grade_thresholds", [...values.grade_thresholds, { min: 60, grade: "" }]);
  }
  function updateThreshold(i, field, value) {
    set("grade_thresholds", values.grade_thresholds.map((th, idx) => (idx === i ? { ...th, [field]: value } : th)));
  }
  function removeThreshold(i) {
    set("grade_thresholds", values.grade_thresholds.filter((_, idx) => idx !== i));
  }

  // Vaqt chegarasi bitta tanlov bilan boshqariladi. Ilgari "0 = cheksiz" degan
  // yashirin qoida bor edi va "vaqt turi" alohida maydonda turardi — natijada
  // kiritilgan raqamning MA'NOSI boshqa maydonga bog'liq bo'lib qolardi.
  const timeMode = !values.time_limit ? "yoq" : values.time_limit_scope;
  function setTimeMode(mode) {
    if (mode === "yoq") return setMany({ time_limit: 0 });
    setMany({ time_limit: values.time_limit || 10, time_limit_scope: mode });
  }

  const limited = (values.sample_count || 0) > 0;
  const common = values.common_question_count ?? 0;
  const currentMode = MODES.find((m) => m.value === values.mode);

  return (
    <div className="form-grid">
      {/* ---------- Baholash ---------- */}
      <div className="fg span2 fg-section">Baholash</div>

      {/* "i" tugmasi yo'q: izoh pastda doimo ochiq turadi, uni yashirish
          faqat ortiqcha bir bosish qo'shardi. */}
      <Field label="Rejim">
        <select className="field" value={values.mode} onChange={(e) => set("mode", e.target.value)}>
          {/* Ro'yxatning o'zida qisqa izoh turadi — administrator tanlashdan
              OLDIN farqni ko'rishi kerak, "i" tugmasini bosib chiqmasdan. */}
          {MODES.map((m) => (
            <option key={m.value} value={m.value}>{m.label} — {m.short}</option>
          ))}
        </select>
        {/* Tanlangan rejim izohi har doim ko'rinib turadi: bu forma kunda bir
            necha marta to'ldiriladi va rejim eng ko'p chalkashtiradigan maydon. */}
        {currentMode && <div className="hint mode-hint">{currentMode.hint}</div>}
      </Field>

      <Field label="O'tish balli" info="Shundan kam ball to'plagan xodim testdan o'tmagan hisoblanadi.">
        <div className="field-row">
          <input className="field" type="number" min="0" max="100" value={values.pass_percent}
            onChange={(e) => set("pass_percent", Number(e.target.value))} />
          <span className="field-suffix">%</span>
        </div>
      </Field>

      <Field label="Baho ko'rinishi" span2>
        <select className="field" value={values.grading_scale} onChange={(e) => setScale(e.target.value)}>
          {SCALES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </Field>

      {values.grading_scale !== "foiz" && (
        <Field label="Baho chegaralari" span2 info="Necha foizdan boshlab qaysi baho qo'yilishi.">
          {values.grade_thresholds.map((th, i) => (
            <div className="threshold-row" key={i}>
              <input className="field" type="number" min="0" max="100" value={th.min}
                onChange={(e) => updateThreshold(i, "min", Number(e.target.value))}
                placeholder="min %" />
              <span>% dan yuqori →</span>
              <input className="field" value={th.grade}
                onChange={(e) => updateThreshold(i, "grade", e.target.value)}
                placeholder="baho" />
              <button className="btn ghost sm danger" onClick={() => removeThreshold(i)}>✕</button>
            </div>
          ))}
          <button className="btn ghost sm" onClick={addThreshold}>+ Chegara qo'shish</button>
        </Field>
      )}

      {/* ---------- Vaqt ---------- */}
      <div className="fg span2 fg-section">Vaqt</div>

      <Field label="Vaqt chegarasi">
        <select className="field" value={timeMode} onChange={(e) => setTimeMode(e.target.value)}>
          <option value="yoq">Cheklanmagan</option>
          <option value="test">Butun test uchun</option>
          <option value="question">Har bir savol uchun</option>
        </select>
      </Field>

      {timeMode !== "yoq" && (
        <Field label={timeMode === "question" ? "Har bir savolga" : "Butun testga"}>
          <div className="field-row">
            <input className="field" type="number" min="1" value={values.time_limit}
              onChange={(e) => set("time_limit", Number(e.target.value))} />
            <span className="field-suffix">daqiqa</span>
          </div>
        </Field>
      )}

      {/* ---------- Savollar ---------- */}
      <div className="fg span2 fg-section">Savollar</div>

      <Field label="Lavozimning o'z savollari">
        <select
          className="field"
          value={limited ? "qism" : "barchasi"}
          // Umumiy savollar soniga TEGILMAYDI: bu tanlov faqat lavozimning
          // o'z savollariga tegishli. Umumiy bankdan savol qo'shish ikkala
          // holatda ham mumkin.
          onChange={(e) => setMany(
            e.target.value === "barchasi"
              ? { sample_count: 0 }
              : { sample_count: values.sample_count || 10 },
          )}
        >
          <option value="barchasi">Barchasi beriladi</option>
          <option value="qism">Tasodifiy tanlab olinadi</option>
        </select>
      </Field>

      {limited && (
        <Field label="Nechta savol tanlansin" info="Har bir xodimga tasodifiy shuncha savol beriladi.">
          <div className="field-row">
            <input className="field" type="number" min="1" value={values.sample_count}
              onChange={(e) => set("sample_count", Number(e.target.value))} />
            <span className="field-suffix">ta</span>
          </div>
        </Field>
      )}

      <Field
        label="Texnika xavfsizligi bo'yicha savollar"
        span2
        info={
          <>
            Barcha lavozimlar uchun umumiy bo'lgan texnika xavfsizligi savollaridan shuncha savol
            qo'shiladi. <b>0</b> qo'yilsa — bunday savol umuman qo'shilmaydi.
            {common > 0 && (limited
              ? (common <= values.sample_count && (
                  <> Hozir: <b>{common}</b> ta texnika xavfsizligi + <b>{values.sample_count - common}</b> ta
                  shu lavozimdan = jami {values.sample_count} ta.</>
                ))
              : <> Hozir: lavozimning <b>barcha</b> savollari + <b>{common}</b> ta texnika xavfsizligi savoli.</>
            )}
          </>
        }
      >
        <div className="field-row">
          <input className="field" type="number" min="0" value={common}
            onChange={(e) => set("common_question_count", Number(e.target.value))} />
          <span className="field-suffix">ta</span>
        </div>
        {/* Xatolik izoh emas — u har doim ko'rinib turadi. */}
        {limited && common > values.sample_count && (
          <div className="hint" style={{ color: "var(--bad)" }}>
            Texnika xavfsizligi savollari soni ({common}) beriladigan savollar sonidan
            ({values.sample_count}) oshib ketdi — kamaytiring, aks holda saqlashda xatolik chiqadi.
          </div>
        )}
      </Field>

      <div className="fg span2 chk-row">
        <label className="chk">
          <input type="checkbox" checked={values.shuffle_questions}
            onChange={(e) => set("shuffle_questions", e.target.checked)} />
          Savollarni aralashtirish
        </label>
        <label className="chk">
          <input type="checkbox" checked={values.shuffle_options}
            onChange={(e) => set("shuffle_options", e.target.checked)} />
          Variantlarni aralashtirish
        </label>
        <label className="chk">
          <input type="checkbox" checked={values.instant_feedback}
            onChange={(e) => set("instant_feedback", e.target.checked)} />
          Har bir savoldan keyin to'g'ri javobni ko'rsatish
        </label>
      </div>

      {/* Video nazorat sozlamasi ko'rsatilmaydi — u har doim yoqilgan
          (qarang: Test.proctoring, default=True). */}
    </div>
  );
}
