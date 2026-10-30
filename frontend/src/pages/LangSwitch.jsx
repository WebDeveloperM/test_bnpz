import { LANGUAGES } from "../i18n.js";

// Til almashtirish tugmalari — Intro ekranida va test davomida ko'rinadi.
// Til almashtirilganda serverga hech narsa yuborilmaydi: barcha tarjimalar
// test boshida savollar bilan birga yuklab olingan, shuning uchun matn darhol
// almashadi va xodimning javoblari (savol/variant id'lari o'zgarmagani uchun)
// joyida qoladi.
export default function LangSwitch({ lang, onChange, className = "" }) {
  return (
    <div className={"lang-switch " + className}>
      {LANGUAGES.map((l) => (
        <button
          key={l.code}
          type="button"
          className={"lang-btn" + (l.code === lang ? " active" : "")}
          onClick={() => onChange(l.code)}
          title={l.label}
        >
          {l.short}
        </button>
      ))}
    </div>
  );
}
