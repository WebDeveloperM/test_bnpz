import { useEffect, useState } from "react";
import { getSystemStatus } from "../adminApi.js";

// Raqamlarni o'qishga qulay ko'rinishda (1 234) — "rahbariyat hisoboti" uslubi.
const nf = (n) => (n ?? 0).toLocaleString("ru-RU");

export default function SystemStatusTab() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  function load() {
    // Muvaffaqiyatda `error` TOZALANADI: aks holda bir marta tarmoq uzilib
    // `error` o'rnatilsa, keyingi muvaffaqiyatli yangilanishda ham sahifa xato
    // ekranida qotib qolar va ma'lumot yangilanmay ko'rinardi.
    getSystemStatus()
      .then((d) => { setData(d); setError(""); })
      .catch((e) => setError(e.message));
  }

  useEffect(() => {
    load();
    // Ko'rsatkichlar jonli bo'lishi uchun — panel ochiq turganda yangilanadi.
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  // Ma'lumot bor bo'lsa — vaqtincha yangilanish xatosi butun sahifani o'chirmaydi
  // (oxirgi qiymatlar ko'rinib turaveradi, keyingi sikl o'zi tuzatadi). Faqat
  // umuman ma'lumot yuklanmagan holatda xato/yuklanish ekrani ko'rsatiladi.
  if (!data) {
    return error
      ? <div className="alert">{error}</div>
      : <div className="adm-card"><div className="empty">Yuklanmoqda…</div></div>;
  }

  // --- Bugungi oqim (voronka): kutilayotgandan yakunlangangacha ---------
  const funnel = [
    { name: "Kutilayotgan", sub: "belgilangan", val: data.expected_today || 0 },
    { name: "Kutish ro'yxatida", sub: "kelgan", val: data.checkins_waiting || 0 },
    { name: "Hozir topshirmoqda", sub: "jarayonda", val: data.attempts_active || 0 },
    { name: "Bugungi natijalar", sub: "yakunlangan", val: data.results_today || 0 },
  ];
  const fMax = Math.max(1, ...funnel.map((f) => f.val));

  // --- Test bazasi (ranked barlar) --------------------------------------
  const ranked = [
    { name: "Savollar bazasi", val: data.questions || 0 },
    { name: "Video yozuvlar", val: data.recordings || 0 },
    { name: "Xodimlar", val: data.employees || 0 },
    { name: "Testlar (lavozimlar)", val: data.tests || 0 },
  ];
  const rMax = Math.max(1, ...ranked.map((r) => r.val));

  return (
    <div>
      {/* Sarlavha + jonli holat */}
      <div className="sys-head">
        <div>
          {/* <div className="sys-eyebrow">Rahbariyat hisoboti</div> */}
          <h1 className="sys-title">Tizim holati</h1>
        </div>
        <div className="sys-head-right">
          <span className="sys-pill live"><span className="sys-live-dot" /> Jonli</span>
          <span className="sys-pill dark">{data.server_time}</span>
        </div>
      </div>
      {/* KPI kartalar */}
      <div className="sys-kpi-grid">
        <div className="sys-kpi">
          <div className="sys-kpi-label">Bugungi natijalar</div>
          <div className="sys-kpi-num">{nf(data.results_today)}</div>
          <div className="sys-kpi-delta up">▲ Jami {nf(data.results_total)} ta natija</div>
        </div>
        <div className="sys-kpi">
          <div className="sys-kpi-label">Hozir topshirmoqda</div>
          <div className="sys-kpi-num">{nf(data.attempts_active)}</div>
          <div className="sys-kpi-delta">Kutishda {nf(data.checkins_waiting)} ta</div>
        </div>
        <div className="sys-kpi">
          <div className="sys-kpi-label">Video arxivi</div>
          <div className="sys-kpi-num">{nf(data.recordings)}</div>
          <div className="sys-kpi-delta">{nf(data.recordings_size_mb)} MB band</div>
        </div>
      </div>

      {/* Ikki ustun: voronka + test bazasi */}
      <div className="sys-two">
        <div className="sys-panel">
          <div className="sys-panel-head">
            <span className="sys-eyebrow">Bugungi oqim</span>
          </div>
          <div className="sys-funnel">
            {funnel.map((f, i) => {
              const pct = Math.round((f.val / fMax) * 100);
              const width = f.val > 0 ? Math.max(14, pct) : 5;
              const last = i === funnel.length - 1;
              return (
                <div className="sys-funnel-row" key={f.name}>
                  <div className="sys-funnel-info">
                    <div className="sys-funnel-name">{f.name}</div>
                    <div className="sys-funnel-sub">{f.sub}</div>
                  </div>
                  <div className={"sys-funnel-bar" + (last ? " rust" : "")} style={{ width: width + "%" }}>
                    {nf(f.val)}
                  </div>
                  <div className="sys-funnel-pct">{pct}%</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="sys-panel">
          <div className="sys-panel-head">
            <span className="sys-eyebrow">Test bazasi</span>
          </div>
          {/* Ilgari bu yerda "sinxronizatsiya foizi" va "oxirgi sinxron" bor
              edi — endi ommaviy ham, davriy ham sinxron yo'q, shuning uchun
              ikkalasi ham olib tashlandi.

              Qolgan son MAHALLIY nusxaniki, BnpzId'dagi haqiqiy son emas —
              yozuv ham aynan shunday nomlangan. Farqi bor: mahalliy nusxa
              qidiruv tekkan xodimlar bilan yangilanadi, ya'ni BnpzId'dan
              orqada qolishi mumkin. Uni "BnpzId bazasida mavjud" deb atash
              — jimgina eskirayotgan sonni jonli son qilib ko'rsatish bo'lardi.

              Ikkinchi son esa haqiqatan foydali: yuz belgisi tayyor xodim
              BnpzId o'chiq bo'lsa ham kamera orqali kira oladi. */}
          <div className="sys-hero">
            <div className="sys-hero-num">{nf(data.synced_employees)}</div>
            <div className="sys-hero-label">mahalliy nusxada saqlangan xodim</div>
            <div className="sys-hero-label">
              shundan {nf(data.synced_with_face)} tasida yuz belgisi tayyor
            </div>
          </div>
          <div className="sys-ranked">
            {ranked.map((r) => (
              <div className="sys-ranked-row" key={r.name}>
                <div className="sys-ranked-name">{r.name}</div>
                <div className="sys-ranked-track">
                  <div className="sys-ranked-fill" style={{ width: Math.max(4, Math.round((r.val / rMax) * 100)) + "%" }} />
                </div>
                <div className="sys-ranked-val">{nf(r.val)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bo'limlar kesimi jadvali */}
      <div className="sys-table-wrap">
        <div className="sys-panel-head">
          <span className="sys-eyebrow">Bo'limlar kesimi</span>
        </div>
        <table className="sys-table">
          <thead>
            <tr>
              <th>Ko'rsatkich</th>
              <th className="r">Qiymat</th>
              <th className="r">Izoh</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="name">Testlar (lavozimlar)</td>
              <td className="val r">{nf(data.tests)}</td>
              <td className="r">{nf(data.questions)} ta savol</td>
            </tr>
            <tr>
              <td className="name">Xodimlar</td>
              <td className="val r">{nf(data.employees)}</td>
              <td className="r">mahalliy nusxada {nf(data.synced_employees)} ta</td>
            </tr>
            <tr>
              <td className="name">Jami natijalar</td>
              <td className="val r">{nf(data.results_total)}</td>
              <td className="good r">bugun +{nf(data.results_today)}</td>
            </tr>
            <tr>
              <td className="name">Yakunlanmagan seanslar</td>
              <td className="val r">{nf(data.attempts_unfinished)}</td>
              <td className={"r " + (data.attempts_unfinished > 0 ? "bad" : "good")}>
                {data.attempts_unfinished > 0 ? "e'tibor bering" : "muammo yo'q"}
              </td>
            </tr>
            <tr>
              <td className="name">Video yozuvlar</td>
              <td className="val r">{nf(data.recordings)}</td>
              <td className="r">{nf(data.recordings_size_mb)} MB</td>
            </tr>
            <tr>
              <td className="name">Administratorlar</td>
              <td className="val r">{nf(data.admins_total)}</td>
              <td className="r">{nf(data.admins_system)} tizim admini</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
