import { useEffect, useRef, useState } from "react";
import {
  listRecordings, deleteRecording, deleteRecordings,
  probeRecordingsArchive, recordingsArchiveUrl,
} from "../adminApi.js";
import { IconEye, IconTrash, IconFilter, IconDownload } from "./icons.jsx";
import { fixVideoDuration } from "./fixVideoDuration.js";

const PAGE = 50;

// Akkordiondagi filtrlar. Bitta obyektda turadi, chunki ular har doim BIRGA
// ishlatiladi: so'rovga ham, "tozalash" ga ham, ZIP arxiviga ham aynan shu
// to'plam uzatiladi — ya'ni yangi maydon qo'shilganda faqat shu yerni va
// akkordion razmetkasini yangilash yetadi.
const EMPTY_FILTERS = { q: "", tabel: "", tsex: "", date_from: "", date_to: "" };

export default function RecordingsTab({ me }) {
  // O'chirish tugmasi faqat superuserda ko'rinadi. Bu — ko'rinish qulayligi;
  // haqiqiy cheklov serverda (`IsSuperUser`), shuning uchun tugmani yashirish
  // aylanib o'tilsa ham hech narsa bermaydi.
  const canDelete = !!me?.is_superuser;
  const [data, setData] = useState({ rows: [], total: 0 });
  const [loaded, setLoaded] = useState(false);
  const [offset, setOffset] = useState(0);
  const [kind, setKind] = useState("");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [filterOpen, setFilterOpen] = useState(false);
  // Sex ro'yxati serverdan keladi — faqat arxivda HAQIQATAN uchraydiganlari
  // (qarang: AdminRecordingsListView, `with_options`). Bu yerda qo'lda
  // yig'ilsa, joriy sahifadagi 50 ta yozuvniki bilan cheklanib qolardi.
  const [tsexOptions, setTsexOptions] = useState([]);
  const [watch, setWatch] = useState(null); // ko'rilayotgan yozuv
  const [deletingId, setDeletingId] = useState(null);
  // Ommaviy o'chirish uchun belgilanganlar. Sahifa almashganda tanlov
  // SAQLANADI — bir necha sahifadan yig'ib, keyin birdan o'chirish mumkin.
  const [selected, setSelected] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const debounceRef = useRef(null);
  const optionsLoadedRef = useRef(false);

  // Serverga ketadigan filtr to'plami — ro'yxat uchun ham, ZIP uchun ham
  // BITTA joydan. Ikkalasi bir xil bo'lishi shart: administrator ekranda
  // ko'rgan narsasini yuklab olishi kerak.
  function filterParams() {
    return { kind, ...filters };
  }

  function load(params) {
    // Sex ro'yxatini faqat birinchi muvaffaqiyatli so'rovda olamiz — u kamdan
    // kam o'zgaradi, har qidiruv harfida qayta hisoblashning ma'nosi yo'q.
    const withOptions = optionsLoadedRef.current ? {} : { with_options: 1 };
    listRecordings({ limit: PAGE, ...params, ...withOptions })
      .then((d) => {
        if (d.tsex_options) {
          setTsexOptions(d.tsex_options);
          optionsLoadedRef.current = true;
        }
        setData(d);
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }

  useEffect(() => {
    clearTimeout(debounceRef.current);
    // Matn maydonlarida har harf uchun so'rov ketmasin. Tanlov/sana
    // maydonlari darhol qo'llanadi — u yerda kutishning sababi yo'q.
    const typing = !!(filters.q || filters.tabel);
    debounceRef.current = setTimeout(() => {
      setOffset(0);
      // Filtr o'zgarganda tanlov bekor qilinadi: ekranda ko'rinmayotgan
      // yozuvni bilmasdan o'chirib yuborish xavfi bo'lmasligi kerak.
      setSelected(new Set());
      load({ offset: 0, ...filterParams() });
    }, typing ? 350 : 0);
    return () => clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, filters]);

  function setFilter(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
  }

  function go(newOffset) {
    setOffset(newOffset);
    load({ offset: newOffset, ...filterParams() });
  }

  async function handleDelete(r) {
    // Video qaytarib bo'lmaydigan tarzda o'chadi (baza + disk), shuning uchun
    // tasdiqlashda aynan qaysi yozuv ekani to'liq ko'rsatiladi.
    const what = `${r.employee} — "${r.test_name}" (${r.created}, ${r.size_mb} MB)`;
    if (!window.confirm(`Bu video yozuv butunlay o'chirilsinmi?\n\n${what}\n\nAmalni ortga qaytarib bo'lmaydi.`)) return;
    setDeletingId(r.id);
    try {
      await deleteRecording(r.id);
      // Oxirgi sahifadagi oxirgi yozuv o'chsa, bo'sh sahifada qolib
      // ketmaslik uchun bir sahifa orqaga suramiz.
      const nextOffset = data.rows.length === 1 && offset > 0 ? offset - PAGE : offset;
      setOffset(nextOffset);
      load({ offset: nextOffset, ...filterParams() });
    } catch (e) {
      window.alert(e.message);
    } finally {
      setDeletingId(null);
    }
  }

  function toggleOne(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAllOnPage() {
    setSelected((prev) => {
      const next = new Set(prev);
      // Sahifadagi hammasi belgilangan bo'lsa — yechamiz, aks holda belgilaymiz.
      // Boshqa sahifalarda tanlanganlarga tegilmaydi.
      if (allOnPageSelected) data.rows.forEach((r) => next.delete(r.id));
      else data.rows.forEach((r) => next.add(r.id));
      return next;
    });
  }

  async function handleDeleteSelected() {
    const rows = data.rows.filter((r) => selected.has(r.id));
    const ids = [...selected];
    // Boshqa sahifada tanlangan yozuvlar ham o'chadi — buni ochiq aytamiz,
    // aks holda "men 3 tasini tanlagandim, 12 tasi o'chibdi" holati bo'lardi.
    const onOtherPages = ids.length - rows.length;
    const shownSize = rows.reduce((s, r) => s + (r.size_mb || 0), 0);
    const list = rows.slice(0, 15)
      .map((r) => `  • ${r.employee} — "${r.test_name}" (${r.created}, ${r.size_mb} MB)`)
      .join("\n");
    const more = rows.length > 15 ? `\n  … va yana ${rows.length - 15} ta` : "";
    const other = onOtherPages > 0
      ? `\n\nDiqqat: boshqa sahifalarda tanlangan yana ${onOtherPages} ta yozuv ham o'chadi.` : "";
    const msg = `${ids.length} ta video yozuv butunlay o'chirilsinmi? `
      + `(shu sahifadagilari ${shownSize.toFixed(1)} MB)\n\n${list}${more}${other}`
      + `\n\nFayllar diskdan ham o'chadi. Amalni ortga qaytarib bo'lmaydi.`;
    if (!window.confirm(msg)) return;

    setBulkBusy(true);
    try {
      const res = await deleteRecordings(ids);
      setSelected(new Set());
      // O'chirgandan keyin joriy sahifa bo'sh qolishi mumkin — birinchisiga qaytamiz.
      setOffset(0);
      load({ offset: 0, ...filterParams() });
      window.alert(`${res.deleted} ta video yozuv o'chirildi.`);
    } catch (e) {
      window.alert(e.message);
    } finally {
      setBulkBusy(false);
    }
  }

  // Filtrga mos BARCHA yozuvlarni bitta .zip da yuklab olish — joriy sahifa
  // emas, butun filtr natijasi.
  //
  // Avval `probe`: arxiv bir necha gigabayt bo'lishi mumkin, shuning uchun
  // administrator nechta fayl va qancha hajm ekanini ko'rib tasdiqlaydi.
  // Server chegaradan oshganini ham shu yerda aytadi — yuklash boshlanib,
  // o'rtada to'xtab qolgandan ko'ra, oldindan tushunarli xabar yaxshiroq.
  async function handleDownloadArchive() {
    setArchiveBusy(true);
    try {
      const params = filterParams();
      const info = await probeRecordingsArchive(params);

      if (info.too_many) {
        window.alert(
          `Filtrga ${info.max_files} tadan ko'p yozuv mos keldi.\n\n`
          + `Bir arxivda ko'pi bilan ${info.max_files} ta yozuv beriladi — `
          + `filtrni toraytiring (masalan sana oralig'ini qisqartiring).`,
        );
        return;
      }
      if (info.too_big) {
        window.alert(
          `Arxiv hajmi ${info.size_mb} MB bo'lardi — chegara ${info.max_mb} MB.\n\n`
          + `Filtrni toraytiring (masalan sana oralig'ini qisqartiring).`,
        );
        return;
      }
      if (!info.count) {
        window.alert(
          info.missing
            ? `Filtrga mos ${info.missing} ta yozuv topildi, lekin ularning fayli diskda yo'q — `
              + "yuklab oladigan narsa qolmadi."
            : "Filtrga mos video yozuv topilmadi.",
        );
        return;
      }

      // Fayli diskda topilmagan yozuvlar jimgina tushib qolmasin: administrator
      // arxivni ochib, "nega kamroq?" deb hayron bo'lmasligi kerak.
      const missing = info.missing
        ? `\n\nDiqqat: ${info.missing} ta yozuvning fayli diskda topilmadi — ular arxivga kirmaydi.`
        : "";
      const ok = window.confirm(
        `${info.count} ta video yozuv bitta .zip faylida yuklab olinadi.\n`
        + `Umumiy hajm: ${info.size_mb} MB.${missing}\n\n`
        + "Yuklash bir necha daqiqa davom etishi mumkin. Davom etilsinmi?",
      );
      if (!ok) return;

      // <a download> — `window.location` ATAYLAB emas: server chegara yoki
      // xato holatida oddiy matn qaytaradi va u holda brauzer paneldan chiqib,
      // o'sha matn sahifasiga o'tib ketardi. `download` bilan javob har doim
      // fayl sifatida qabul qilinadi, panel esa joyida qoladi.
      const a = document.createElement("a");
      a.href = recordingsArchiveUrl(params);
      a.download = ""; // nomni server beradi (Content-Disposition)
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      window.alert(e.message);
    } finally {
      setArchiveBusy(false);
    }
  }

  const from = data.total ? offset + 1 : 0;
  const to = Math.min(offset + PAGE, data.total);
  const totalSize = data.rows.reduce((s, r) => s + (r.size_mb || 0), 0);
  const allOnPageSelected = data.rows.length > 0 && data.rows.every((r) => selected.has(r.id));
  // Tugmadagi raqam — akkordion YOPIQ turganda ham nechta filtr ishlayotganini
  // ko'rsatadi. `kind` bu yerga kirmaydi: u alohida, ko'rinib turgan ro'yxat.
  const activeFilterCount = Object.values(filters).filter(Boolean).length;
  const colCount = canDelete ? 9 : 8;

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-card2">
          <div>
            <div className="stat-card2-label">Jami yozuvlar</div>
            <div className="stat-card2-num">{data.total}</div>
          </div>
          <div className="icon-square blue"><IconEye /></div>
        </div>
        <div className="stat-card2">
          <div>
            <div className="stat-card2-label">Shu sahifadagi hajm</div>
            <div className="stat-card2-num">{totalSize.toFixed(1)} MB</div>
          </div>
          <div className="icon-square yellow"><IconEye /></div>
        </div>
      </div>

      <div className="adm-card">
        <div className="adm-title-row">
          <h2>Video yozuvlar arxivi</h2>
          <div className="adm-toolbar-btns">
            {/* Tugma faqat nimadir tanlanganda paydo bo'ladi — bo'sh turgan
                "hammasini o'chirish" tugmasi tasodifan bosilishi mumkin edi. */}
            {canDelete && selected.size > 0 && (
              <button className="btn2 danger sm" onClick={handleDeleteSelected} disabled={bulkBusy}>
                <IconTrash width={14} height={14} />
                {bulkBusy ? "O'chirilmoqda…" : `Tanlanganlarni o'chirish (${selected.size})`}
              </button>
            )}
            {canDelete && selected.size > 0 && (
              <button className="btn2 sm" onClick={() => setSelected(new Set())} disabled={bulkBusy}>
                Tanlovni bekor qilish
              </button>
            )}
            <select className="field sm" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Barcha turlar</option>
              <option value="screen">Ekran</option>
              <option value="face">Yuz (kamera)</option>
            </select>
            {/* Tez qidiruv. Akkordiondagi "Ism-familiya" maydoni bilan AYNAN
                bitta qiymatni boshqaradi — ikkisi doim mos turadi. */}
            <input
              className="field sm"
              style={{ minWidth: 220 }}
              placeholder="Xodim ismi bo'yicha qidirish…"
              value={filters.q}
              onChange={(e) => setFilter("q", e.target.value)}
            />
            <button
              className={"btn2 sm" + (filterOpen || activeFilterCount ? " primary" : "")}
              onClick={() => setFilterOpen((v) => !v)}
              title="Qo'shimcha filtrlar"
            >
              <IconFilter width={15} height={15} /> Filter
              {activeFilterCount > 0 && <span className="filter-count">{activeFilterCount}</span>}
            </button>
          </div>
        </div>

        {filterOpen && (
          <div className="rec-filter">
            <div className="rec-filter-grid">
              <div className="rec-filter-field">
                <label className="fg-label">Tabel raqami</label>
                <input
                  className="field sm" autoFocus inputMode="numeric"
                  placeholder="Masalan: 9487"
                  value={filters.tabel}
                  onChange={(e) => setFilter("tabel", e.target.value)}
                />
              </div>
              <div className="rec-filter-field">
                <label className="fg-label">Ism-familiya</label>
                <input
                  className="field sm"
                  placeholder="Ism yoki familiya"
                  value={filters.q}
                  onChange={(e) => setFilter("q", e.target.value)}
                />
              </div>
              <div className="rec-filter-field">
                <label className="fg-label">Sana — dan</label>
                <input
                  type="date" className="field sm"
                  value={filters.date_from}
                  // Boshlanish sanasi tugash sanasidan keyin bo'lib qolmasin —
                  // bunday oraliq har doim bo'sh natija beradi va foydalanuvchi
                  // buni "filtr ishlamayapti" deb tushunardi.
                  max={filters.date_to || undefined}
                  onChange={(e) => setFilter("date_from", e.target.value)}
                />
              </div>
              <div className="rec-filter-field">
                <label className="fg-label">Sana — gacha</label>
                <input
                  type="date" className="field sm"
                  value={filters.date_to}
                  min={filters.date_from || undefined}
                  onChange={(e) => setFilter("date_to", e.target.value)}
                />
              </div>
              <div className="rec-filter-field">
                <label className="fg-label">Sex (tsex)</label>
                <select
                  className="field sm"
                  value={filters.tsex}
                  onChange={(e) => setFilter("tsex", e.target.value)}
                >
                  <option value="">Barcha sexlar</option>
                  {tsexOptions.map((tx) => <option key={tx} value={tx}>{tx}</option>)}
                </select>
              </div>
            </div>

            <div className="rec-filter-foot">
              <span className="hint" style={{ margin: 0 }}>
                Filtrga <b>{data.total}</b> ta yozuv mos keldi
                {activeFilterCount === 0 && " (filtr qo'yilmagan — barcha yozuvlar)"}
              </span>
              <div className="rec-filter-actions">
                {activeFilterCount > 0 && (
                  <button className="btn2 sm" onClick={() => setFilters(EMPTY_FILTERS)}>
                    Tozalash
                  </button>
                )}
                {/* Joriy sahifa emas, FILTRGA MOS HAMMASI yuklanadi. */}
                <button
                  className="btn2 sm primary"
                  onClick={handleDownloadArchive}
                  disabled={archiveBusy || !data.total}
                  title="Filtrga mos barcha video yozuvlarni bitta .zip faylida yuklab olish"
                >
                  <IconDownload width={15} height={15} />
                  {archiveBusy ? "Hisoblanmoqda…" : "ZIP yuklab olish"}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                {canDelete && (
                  <th className="col-check">
                    <input
                      type="checkbox"
                      checked={allOnPageSelected}
                      onChange={toggleAllOnPage}
                      title="Shu sahifadagi hammasini belgilash"
                    />
                  </th>
                )}
                <th className="col-num">№</th>
                <th style={{ width: 150 }}>Sana</th>
                <th>Xodim</th>
                <th>Test</th>
                <th style={{ width: 120 }}>Turi</th>
                <th style={{ width: 90 }}>Natija</th>
                <th style={{ width: 100 }}>Hajm</th>
                <th className="col-actions" />
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={r.id} className={selected.has(r.id) ? "row-selected" : undefined}>
                  {canDelete && (
                    <td className="col-check">
                      <input
                        type="checkbox"
                        checked={selected.has(r.id)}
                        onChange={() => toggleOne(r.id)}
                      />
                    </td>
                  )}
                  <td className="col-num">{offset + i + 1}</td>
                  <td className="nowrap">{r.created}</td>
                  {/* Tabel va sex alohida ustun emas, qo'shimcha qator: ular
                      filtrlanadigan qiymatlar, ya'ni ko'rinib turishi kerak,
                      lekin jadvalni ikkita ustunga kengaytirishga arzimaydi. */}
                  <td>
                    {r.employee}
                    <span className="cell-sub">Tabel: {r.tabel_number}</span>
                  </td>
                  <td>
                    {r.test_name}
                    <span className="cell-sub">{r.tsex}</span>
                  </td>
                  <td>
                    <span className={"badge " + (r.kind === "screen" ? "open" : "done")}>
                      {r.kind_label}
                    </span>
                  </td>
                  <td>{r.pct != null ? `${r.pct}%` : "—"}</td>
                  <td>{r.size_mb != null ? `${r.size_mb} MB` : "—"}</td>
                  <td className="col-actions">
                    <div className="adm-icon-row">
                      {r.url ? (
                        <button className="btn2 sm" onClick={() => setWatch(r)}>▶ Ko'rish</button>
                      ) : (
                        <span className="hint" style={{ margin: 0 }}>fayl yo'q</span>
                      )}
                      {canDelete && (
                        <button
                          className="adm-icon-btn danger"
                          title="Video yozuvni butunlay o'chirish"
                          onClick={() => handleDelete(r)}
                          disabled={deletingId === r.id}
                        >
                          <IconTrash width={15} height={15} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {!data.rows.length && loaded && (
                <tr>
                  <td colSpan={colCount} className="empty">
                    {activeFilterCount || kind
                      ? "Filtrga mos video yozuv topilmadi"
                      : "Video yozuv topilmadi"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {data.total > PAGE && (
          <div className="pager">
            <span>{from}–{to} / {data.total}</span>
            <div className="pager-btns">
              <button className="btn2 sm" disabled={offset === 0}
                onClick={() => go(Math.max(0, offset - PAGE))}>← Oldingi</button>
              <button className="btn2 sm" disabled={to >= data.total}
                onClick={() => go(offset + PAGE)}>Keyingi →</button>
            </div>
          </div>
        )}
      </div>

      {watch && (
        <div className="modal-backdrop" onClick={() => setWatch(null)}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 900 }}>
            <div className="adm-title-row" style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0 }}>
                {watch.employee} — <span style={{ fontWeight: 400 }}>{watch.kind_label}</span>
              </h3>
              <button className="btn2" onClick={() => setWatch(null)}>✕ Yopish</button>
            </div>
            <video
              src={watch.url}
              controls
              autoPlay
              onLoadedMetadata={fixVideoDuration}
              style={{ width: "100%", maxHeight: 520, background: "#111", borderRadius: 10, display: "block" }}
            />
            <div className="hint" style={{ marginTop: 10 }}>
              {watch.test_name} · {watch.created}
              {watch.size_mb != null && ` · ${watch.size_mb} MB`}
              {" · "}
              <a href={watch.url} target="_blank" rel="noopener noreferrer">Alohida oynada ochish</a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
