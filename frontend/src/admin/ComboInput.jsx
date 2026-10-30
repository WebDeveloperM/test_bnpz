import { useEffect, useRef, useState } from "react";
import { IconCheck } from "./icons.jsx";

// Erkin matn kiritiladigan, lekin tayyor takliflari ham bor maydon.
//
// Ilgari bu yerda HTML'ning `<datalist>` elementi ishlatilardi. U ishlaydi,
// lekin ro'yxatni BRAUZERNING o'zi chizadi: uni CSS bilan bezab bo'lmaydi,
// tizim mavzusiga qarab qora fonli bo'lib ketadi va uzun ro'yxatda qidirilgan
// qismni ajratib ko'rsatmaydi. Shu sabab ro'yxat o'zimizda chiziladi.
export default function ComboInput({
  value, onChange, onCommit, options = [], placeholder, className = "field",
  style, disabled, title,
}) {
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  // Maydon ochilganda BARCHA variantlar ko'rsatiladi, filtr esa faqat
  // foydalanuvchi yozishni boshlagach ishlaydi. Aks holda to'ldirilgan
  // maydonni ochganda ro'yxat o'sha bitta qiymatgacha qisqarib qolardi va
  // boshqasini tanlash uchun avval matnni o'chirishga to'g'ri kelardi.
  const [typing, setTyping] = useState(false);
  const rootRef = useRef(null);
  const listRef = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const q = (value || "").trim().toLowerCase();
  const filtered = q && typing ? options.filter((o) => o.toLowerCase().includes(q)) : options;
  const exact = options.some((o) => o.toLowerCase() === q);

  useEffect(() => {
    if (!open || !listRef.current) return;
    listRef.current.children[cursor]?.scrollIntoView({ block: "nearest" });
  }, [cursor, open]);

  function pick(opt) {
    onChange(opt);
    setOpen(false);
    onCommit?.(opt);
  }

  function onKeyDown(e) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) { setOpen(true); return; }
      if (!filtered.length) return;
      setCursor((c) => {
        const next = e.key === "ArrowDown" ? c + 1 : c - 1;
        return (next + filtered.length) % filtered.length;
      });
    } else if (e.key === "Enter") {
      if (open && filtered[cursor]) {
        e.preventDefault();
        pick(filtered[cursor]);
      } else {
        setOpen(false);
        onCommit?.(value);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  function highlight(label) {
    if (!q || !typing) return label;
    const i = label.toLowerCase().indexOf(q);
    if (i < 0) return label;
    return (
      <>
        {label.slice(0, i)}
        <mark>{label.slice(i, i + q.length)}</mark>
        {label.slice(i + q.length)}
      </>
    );
  }

  return (
    <div className="combo" ref={rootRef} style={style}>
      <input
        className={className}
        value={value || ""}
        placeholder={placeholder}
        title={title}
        disabled={disabled}
        autoComplete="off"
        onChange={(e) => { onChange(e.target.value); setOpen(true); setTyping(true); setCursor(0); }}
        onFocus={() => {
          setOpen(true);
          setTyping(false);
          // Kursor joriy qiymat turgan qatorga qo'yiladi.
          const i = options.findIndex((o) => o.toLowerCase() === q);
          setCursor(i < 0 ? 0 : i);
        }}
        onKeyDown={onKeyDown}
        onBlur={(e) => {
          // Ro'yxatdagi elementga bosilgan bo'lsa, `pick` o'zi hal qiladi.
          if (rootRef.current?.contains(e.relatedTarget)) return;
          onCommit?.(e.target.value);
        }}
      />

      {open && (filtered.length > 0 || (q && typing && !exact)) && (
        <div className="combo-panel">
          <div className="combo-list" ref={listRef}>
            {filtered.map((o, i) => (
              <div
                key={o}
                className={"combo-option" + (o.toLowerCase() === q ? " active" : "") + (i === cursor ? " cursor" : "")}
                onMouseEnter={() => setCursor(i)}
                onMouseDown={(e) => e.preventDefault()}  // input blur bo'lib ketmasin
                onClick={() => pick(o)}
              >
                <span className="combo-label">{highlight(o)}</span>
                {o.toLowerCase() === q && <IconCheck width={15} height={15} />}
              </div>
            ))}
          </div>
          {q && typing && !exact && (
            <div className="combo-foot">Yangi sex sifatida saqlanadi: <b>{value}</b></div>
          )}
        </div>
      )}
    </div>
  );
}
