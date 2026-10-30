import logoUrl from "./assets/logo.png";

// Dastur logotipi — kirish sahifalarida (xodim va administrator) va admin
// panel yon menyusida ishlatiladi.
//
// Rasm ATAYLAB frontend ichida (`src/assets/`) turadi, `/media/...` orqali
// emas: logotip — ilovaning o'z qismi, foydalanuvchi yuklagan fayl emas.
// `media/questions/` esa savol rasmlari yuklanadigan papka — u yerdagi fayl
// tasodifan o'chirilishi yoki tozalanishi mumkin edi, kirish sahifasi esa
// xodim ko'radigan ENG BIRINCHI ekran. Endi logotip bundle ichida keladi:
// qo'shimcha so'rov ketmaydi va backend'ga umuman bog'liq emas.
//
// Logotipni almashtirish uchun `src/assets/logo.png` ni almashtirish kifoya —
// hamma joyda birdan o'zgaradi (favicon alohida: `public/favicon.png`).
export default function Logo({ className = "" }) {
  // `alt=""` — yonida "BnpzTest" matni turibdi, ya'ni logotip bezak.
  // Matn qo'yilsa, ekranni ovoz bilan o'qiydigan dastur nomni ikki marta aytardi.
  return <img src={logoUrl} alt="" className={"brand-logo " + className} />;
}
