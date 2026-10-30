import { useEffect, useState } from "react";
import TestsTab from "./TestsTab.jsx";
import ActiveAttemptsTab from "./ActiveAttemptsTab.jsx";
import CheckinsTab from "./CheckinsTab.jsx";
import ExpectedEmployeesTab from "./ExpectedEmployeesTab.jsx";
import ResultsTab from "./ResultsTab.jsx";
import SettingsTab from "./SettingsTab.jsx";
import ActivityLogTab from "./ActivityLogTab.jsx";
import RecordingsTab from "./RecordingsTab.jsx";
import SystemStatusTab from "./SystemStatusTab.jsx";
import RolesTab from "./RolesTab.jsx";
import UsersTab from "./UsersTab.jsx";
import {
  IconUsers, IconTest, IconActivity, IconResults, IconLogout,
  IconCheck, IconSettings, IconEye, IconList, IconShield, IconKey,
} from "./icons.jsx";
import Logo from "../Logo.jsx";

// BITTA panel, bitta menyu. Bo'limlar ro'yxati hamma uchun bir xil e'lon
// qilinadi, keyin foydalanuvchining RUXSATLARI bo'yicha filtrlanadi —
// ilgari qanday manzildan kirilganiga qarab ikkita alohida ro'yxat bor edi.
//
// `perm` — `core/perms.py` dagi kalit; serverda ham xuddi shu kalit bo'yicha
// tekshiriladi. Menyudan yashirishning o'zi himoya emas.
// `sudo: true` — faqat superuser uchun (rolga berib bo'lmaydi).
//
// Har bir bo'limning O'Z MANZILI bor (`path`) — shunday qilib bo'limga
// to'g'ridan to'g'ri havola berish, uni xatcho'pga qo'shish va brauzerning
// "orqaga" tugmasini ishlatish mumkin. nginx `try_files … /index.html` bilan
// sozlangani uchun bu manzillarni to'g'ridan-to'g'ri ochish ham ishlaydi.
const ALL_TABS = [
  { key: "expected", perm: "expected", group: "Kundalik ish", path: "kutilayotgan-xodimlar", label: "Kutilayotgan xodimlar", icon: IconCheck, Comp: ExpectedEmployeesTab },
  { key: "checkins", perm: "checkins", group: "Kundalik ish", path: "kutish-royxati", label: "Kutish ro'yxati", icon: IconUsers, Comp: CheckinsTab },
  { key: "active", perm: "active", group: "Kundalik ish", path: "faol-seanslar", label: "Faol seanslar", icon: IconActivity, Comp: ActiveAttemptsTab },
  { key: "tests", perm: "tests", group: "O'quv qismi", path: "testlar", label: "Testlar", icon: IconTest, Comp: TestsTab },
  { key: "settings", perm: "settings", group: "O'quv qismi", path: "sozlamalar", label: "Sozlamalar", icon: IconSettings, Comp: SettingsTab },
  { key: "sysstatus", perm: "sysstatus", group: "Tizim", path: "tizim-holati", label: "Tizim holati", icon: IconActivity, Comp: SystemStatusTab },
  { key: "activity", perm: "activity", group: "Tizim", path: "amallar-tarixi", label: "Amallar tarixi", icon: IconList, Comp: ActivityLogTab },
  { key: "recordings", perm: "recordings", group: "Tizim", path: "video-yozuvlar", label: "Video yozuvlar", icon: IconEye, Comp: RecordingsTab },
  { key: "results", perm: "results", group: "Tizim", path: "natijalar", label: "Test natijalari", icon: IconResults, Comp: ResultsTab },
  { key: "users", sudo: true, group: "Boshqaruv", path: "foydalanuvchilar", label: "Foydalanuvchilar", icon: IconKey, Comp: UsersTab },
  { key: "roles", sudo: true, group: "Boshqaruv", path: "rollar", label: "Rollar va ruxsatlar", icon: IconShield, Comp: RolesTab },
];

// Menyu guruhlari shu tartibda chiqadi (bo'sh guruh umuman ko'rsatilmaydi).
const GROUP_ORDER = ["Kundalik ish", "O'quv qismi", "Tizim", "Boshqaruv"];

function visibleTabs(me) {
  const perms = new Set(me?.permissions || []);
  return ALL_TABS.filter((t) => (t.sudo ? me?.is_superuser : perms.has(t.perm)));
}

function initials(username) {
  return (username || "?").slice(0, 2).toUpperCase();
}

export default function AdminDashboard({ me, onLogout }) {
  const tabs = visibleTabs(me);
  // Ruxsatlar har xil bo'lgani uchun "asosiy bo'lim" ham har xil: kimdadir
  // kutish ro'yxati bor, kimdadir yo'q. Shuning uchun birinchi ochiq bo'lim.
  const defaultKey = tabs[0]?.key;

  function currentSlug() {
    return window.location.pathname.replace(/^\/+|\/+$/g, "");
  }
  const urlFor = (slug) => `/${slug}`;

  // Manzildan bo'limni aniqlaymiz. Notanish manzil ham, ruxsati yo'q bo'lim
  // manzili ham (masalan rol o'zgargandan keyin ochilgan eski havola)
  // birinchi ochiq bo'limga tushadi.
  function keyFromUrl() {
    const slug = currentSlug();
    return tabs.find((t) => t.path === slug)?.key || defaultKey;
  }

  const [tab, setTab] = useState(keyFromUrl);

  // Sahifa ochilganda manzilni bo'limga moslab qo'yamiz (masalan "/" yoki
  // noto'g'ri manzil kiritilgan bo'lsa) — `replace`, chunki bu yangi qadam emas.
  useEffect(() => {
    const want = tabs.find((t) => t.key === tab)?.path;
    if (want && currentSlug() !== want) {
      window.history.replaceState({}, "", urlFor(want));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Brauzerning "orqaga"/"oldinga" tugmalari.
  useEffect(() => {
    function onPop() { setTab(keyFromUrl()); }
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function goTab(key) {
    if (key === tab) return;
    setTab(key);
    const slug = tabs.find((t) => t.key === key)?.path;
    if (slug) window.history.pushState({}, "", urlFor(slug));
  }

  const Active = tabs.find((tb) => tb.key === tab)?.Comp;
  const groups = GROUP_ORDER
    .map((name) => ({ name, items: tabs.filter((t) => t.group === name) }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <Logo className="admin-brand-logo" />
          <div className="admin-brand-text">
            <b>BnpzTest</b>
            <small>Boshqaruv paneli</small>
          </div>
        </div>

        <nav className="admin-nav">
          {groups.map((g) => (
            <div key={g.name} className="admin-nav-group">
              <div className="admin-menu-label">{g.name}</div>
              {g.items.map((tb) => {
                const Icon = tb.icon;
                return (
                  <button
                    key={tb.key}
                    className={"admin-nav-item" + (tab === tb.key ? " active" : "")}
                    onClick={() => goTab(tb.key)}
                  >
                    <Icon />
                    {tb.label}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="admin-sidebar-spacer" />
      </aside>

      <div className="admin-main">
        <header className="admin-header">
          <div className="admin-user-box">
            <div>
              <div className="admin-user-name">{(me?.username || "").toUpperCase()}</div>
              <div className="admin-user-role">
                {me?.is_superuser ? "Superuser — barcha ruxsatlar" : (me?.role || "Rol berilmagan")}
              </div>
            </div>
            <div className={"admin-avatar" + (me?.is_superuser ? " system" : "")}>
              {initials(me?.username)}
            </div>
          </div>
          <button className="admin-logout-btn" onClick={onLogout}>
            <IconLogout width={16} height={16} />
            Chiqish
          </button>
        </header>

        <div className="admin-content">
          {/* `me` barcha bo'limlarga uzatiladi — ba'zilari foydalanuvchi
              darajasiga qarab qo'shimcha amal ko'rsatadi (masalan video
              yozuvni o'chirish faqat superuserda). */}
          {Active
            ? <Active me={me} />
            : (
              // Rol berilmagan (yoki barcha ruxsatlari olib qo'yilgan) holat.
              // Server bunday hisobga token ham bermaydi, lekin rol panel
              // ochiq turganda o'zgartirilsa shu ekran ko'rinishi mumkin.
              <div className="adm-card">
                <h3>Bo'lim yo'q</h3>
                <p className="muted">
                  Hisobingizga hech qanday bo'lim ochilmagan. Superuserga murojaat qiling.
                </p>
              </div>
            )}
        </div>
      </div>
    </div>
  );
}
