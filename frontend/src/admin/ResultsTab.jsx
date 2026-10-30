import { useEffect, useRef, useState } from "react";
import {
  listResults, resultsCsvUrl, getResult, getResultProtocol,
} from "../adminApi.js";
import ReviewList from "../ReviewList.jsx";
import Protocol from "../Protocol.jsx";
import PrintPortal from "../PrintPortal.jsx";
import { IconDownload, IconTrash, IconEye, IconResults, IconCheck, IconUsers, IconList, IconFilter } from "./icons.jsx";
import { fixVideoDuration } from "./fixVideoDuration.js";

const PAGE_SIZE = 15;

async function downloadFile(url, filename) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Faylni yuklab bo'lmadi (${res.status}).`);
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

const T = {
  your_answer: "Sizning javobingiz", correct_answer: "To'g'ri javob",
  not_answered: "belgilanmagan",
};

export default function ResultsTab() {
  const [results, setResults] = useState([]);
  const [tsexFilter, setTsexFilter] = useState("");
  const [search, setSearch] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [page, setPage] = useState(1);
  const filterRef = useRef(null);
  const [detail, setDetail] = useState(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [protocol, setProtocol] = useState(null);
  const [protocolBusy, setProtocolBusy] = useState(false);
  const [downloadingRecId, setDownloadingRecId] = useState(null);

  async function handleDownloadRecording(r) {
    setDownloadingRecId(r.id);
    try {
      const ext = r.url.split(".").pop().split("?")[0] || "webm";
      const date = new Date(r.created).toISOString().slice(0, 10);
      await downloadFile(r.url, `${detail.full_name}_${r.kind}_${date}.${ext}`);
    } catch (e) {
      window.alert(`Videoni yuklab bo'lmadi: ${e.message}`);
    } finally {
      setDownloadingRecId(null);
    }
  }

  async function load() {
    setResults(await listResults());
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!filterOpen) return;
    function onDocClick(e) {
      if (filterRef.current && !filterRef.current.contains(e.target)) setFilterOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [filterOpen]);

  useEffect(() => {
    setPage(1);
  }, [search, tsexFilter]);

  async function openDetail(r) {
    setDetailBusy(true);
    try {
      setDetail(await getResult(r.id));
    } finally {
      setDetailBusy(false);
    }
  }

  async function openProtocol(id) {
    setProtocolBusy(true);
    try {
      setProtocol(await getResultProtocol(id));
    } finally {
      setProtocolBusy(false);
    }
  }

  const tsexList = [...new Set(results.map((r) => r.tsex).filter(Boolean))].sort();
  const q = search.trim().toLowerCase();
  const shown = results.filter((r) =>
    (!tsexFilter || r.tsex === tsexFilter) &&
    (!q || r.full_name.toLowerCase().includes(q) || (r.tabel_number || "").toLowerCase().includes(q))
  );
  const activeFilterCount = (tsexFilter ? 1 : 0) + (q ? 1 : 0);

  const avgPct = shown.length ? Math.round(shown.reduce((s, r) => s + r.pct, 0) / shown.length) : 0;
  const passedShare = shown.length ? Math.round((shown.filter((r) => r.passed).length / shown.length) * 100) : 0;

  const totalPages = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages);
  const pageItems = shown.slice((pageSafe - 1) * PAGE_SIZE, pageSafe * PAGE_SIZE);

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-card2">
          <div><div className="stat-card2-label">Natijalar</div><div className="stat-card2-num">{shown.length}</div></div>
          <div className="icon-square blue"><IconResults /></div>
        </div>
        <div className="stat-card2">
          <div><div className="stat-card2-label">O'rtacha ball</div><div className="stat-card2-num">{avgPct}%</div></div>
          <div className="icon-square yellow"><IconUsers /></div>
        </div>
        <div className="stat-card2">
          <div><div className="stat-card2-label">O'tganlar ulushi</div><div className="stat-card2-num">{passedShare}%</div></div>
          <div className="icon-square purple"><IconCheck /></div>
        </div>
      </div>

      <div className="adm-card">
        <div className="adm-title-row">
          <h2>Natijalar</h2>
          <div className="results-filter" ref={filterRef}>
            {/* Barcha natijalarni Excel'da ochiladigan CSV ko'rinishida yuklab
                olish — hisobot uchun. */}
            <a className="btn2" href={resultsCsvUrl()} download="natijalar.csv"
              style={{ marginRight: 10, textDecoration: "none" }}>
              <IconDownload width={16} height={16} /> CSV
            </a>
            <button className={"btn2" + (activeFilterCount ? " primary" : "")} onClick={() => setFilterOpen((v) => !v)}>
              <IconFilter width={16} height={16} /> Filter
              {activeFilterCount > 0 && <span className="filter-count">{activeFilterCount}</span>}
            </button>
            {filterOpen && (
              <div className="results-filter-panel">
                <label className="fg-label">Tabel raqami yoki ism-familiya</label>
                <input
                  className="field sm" autoFocus
                  placeholder="Qidirish…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <label className="fg-label" style={{ marginTop: 12 }}>Tsex</label>
                <select className="field sm" value={tsexFilter}
                  onChange={(e) => setTsexFilter(e.target.value)}>
                  <option value="">Barcha tsexlar</option>
                  {tsexList.map((tx) => <option key={tx} value={tx}>{tx}</option>)}
                </select>
                {activeFilterCount > 0 && (
                  <button className="btn2 sm" style={{ marginTop: 12 }}
                    onClick={() => { setSearch(""); setTsexFilter(""); }}>
                    Tozalash
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* "N kundan eski video yozuvlarni o'chirish" tugmasi olib tashlandi:
            video yozuv va natija — qaytarib bo'lmaydigan dalil, ularni panel
            orqali o'chirish taqiqlangan (serverda ham rad etiladi). Disk
            to'lib qolsa, fayllar serverdan qo'lda arxivlanadi. */}

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-num">№</th><th>Tabel raqam</th><th>Ism-familiya</th><th>Lavozim (test)</th><th>To'g'ri</th><th>Foiz</th><th>Baho</th><th>Natija</th><th>Sana</th><th className="col-actions" />
              </tr>
            </thead>
            <tbody>
              {pageItems.map((r, i) => (
                <tr key={r.id}>
                  {/* Raqam butun ro'yxat bo'yicha — 2-sahifa 16 dan boshlanadi. */}
                  <td className="col-num">{(pageSafe - 1) * PAGE_SIZE + i + 1}</td>
                  <td>{r.tabel_number || "—"}</td>
                  <td>
                    {r.full_name}
                    {r.violations > 0 && (
                      <span className="badge danger" title="Sahifadan chiqishga urinishlar" style={{ marginLeft: 8 }}>
                        ⚠ {r.violations}
                      </span>
                    )}
                    {r.share_stopped && (
                      <span className="badge danger" title="Ekran ulashish to'xtatilgani sababli test avtomatik yakunlandi" style={{ marginLeft: 8 }}>
                        ⚠ Share o'chirildi
                      </span>
                    )}
                    {r.interrupted && (
                      <span className="badge danger" title="Test davomida sahifa yangilangani (yoki seans tashlab ketilgani) sababli test majburan yakunlandi" style={{ marginLeft: 8 }}>
                        ⚠ Sahifa yangilangan
                      </span>
                    )}
                  </td>
                  <td>{r.test_name}</td>
                  <td>{r.correct} / {r.total}</td>
                  <td>{r.pct}%</td>
                  <td>{r.grade || "—"}</td>
                  <td>
                    <span className={"badge " + (r.passed ? "done" : "danger")}>
                      {r.passed ? "O'tdi" : "O'tmadi"}
                    </span>
                  </td>
                  <td>{new Date(r.created).toLocaleString("uz-UZ")}</td>
                  <td className="col-actions">
                    <div className="adm-icon-row">
                      <button className="adm-icon-btn" title="Batafsil" onClick={() => openDetail(r)} disabled={detailBusy}>
                        <IconEye width={15} height={15} />
                      </button>
                      <button className="adm-icon-btn success" title="Protokol" onClick={() => openProtocol(r.id)} disabled={protocolBusy}>
                        <IconList width={15} height={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!shown.length && (
                <tr><td colSpan={10} className="empty">Natijalar yo'q</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {shown.length > 0 && totalPages > 1 && (
          <div className="paginator">
            <button className="btn2 sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={pageSafe <= 1}>
              ← Oldingi
            </button>
            <span className="paginator-info">Sahifa {pageSafe} / {totalPages} ({shown.length} ta natija)</span>
            <button className="btn2 sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={pageSafe >= totalPages}>
              Keyingi →
            </button>
          </div>
        )}
      </div>

      {detail && (
        <div className="modal-backdrop" onClick={() => setDetail(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="res-head">
              <div className="res-name">{detail.full_name}</div>
              <div className="res-role">{detail.test_name}</div>
            </div>

            <div className="res-score-row">
              <div className="score-block">
                <div className="score-label">Umumiy ball</div>
                <div className="score-pct">{detail.grade || detail.pct + "%"}</div>
              </div>
              <div className={"verdict-badge " + (detail.passed ? "pass" : "fail")}>
                Natija: {detail.passed ? "O'tdi" : "O'tmadi"}
              </div>
            </div>
            <div className="res-divider" />
            <div className="res-stats-grid">
              <div className="res-stat-box good">
                <div className="res-stat-num">{detail.correct}</div>
                <div className="res-stat-label">to'g'ri javob</div>
              </div>
              <div className="res-stat-box bad">
                <div className="res-stat-num">{detail.total - detail.correct}</div>
                <div className="res-stat-label">xato javob</div>
              </div>
            </div>

            {detail.violations > 0 && (
              <div className="alert" style={{ marginTop: 14 }}>
                ⚠ Sahifadan chiqishga urindi: {detail.violations} marta
              </div>
            )}
            {detail.share_stopped && (
              <div className="alert" style={{ marginTop: 14 }}>
                ⚠ Ekran ulashish (share) test davomida o'chirilgani sababli avtomatik yakunlandi
              </div>
            )}
            {detail.interrupted && (
              <div className="alert" style={{ marginTop: 14 }}>
                ⚠ Test davomida sahifa yangilangani (yoki seans tashlab ketilgani) sababli majburan
                yakunlandi. Faqat shu ongacha belgilangan javoblar hisobga olingan — qayta topshirish
                kerak bo'lsa, xodimga testni qaytadan boshlab bering.
              </div>
            )}

            {!!(detail.recordings && detail.recordings.length) && (
              <div className="rec-section">
                <h3>Video nazorat yozuvlari</h3>
                <div className="rec-grid">
                  {detail.recordings.map((r) => (
                    <div className="rec-item" key={r.id}>
                      <div className="rec-item-label">{r.kind === "screen" ? "Video (ekran + yuz)" : "Yuz (kamera)"}</div>
                      {/* preload="none": yozuv Play bosilgandagina yuklanadi.
                          "metadata" bilan "Batafsil" har ochilganda video
                          so'rov boshlanar va server butun faylni o'qib
                          chiqardi — admin javoblarni ko'rish uchun ochgan
                          bo'lsa ham. */}
                      <video src={r.url} controls preload="none" onLoadedMetadata={fixVideoDuration} />
                      <button
                        className="btn2 sm"
                        onClick={() => handleDownloadRecording(r)}
                        disabled={downloadingRecId === r.id}
                      >
                        <IconDownload width={14} height={14} />
                        {downloadingRecId === r.id ? "Yuklab olinmoqda…" : "Yuklab olish"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <ReviewList review={detail.answers || []} t={T} />

            <button className="btn2 primary block" onClick={() => setDetail(null)}>Yopish</button>
          </div>
        </div>
      )}

      {protocol && (
        <>
          <div className="modal-backdrop" onClick={() => setProtocol(null)}>
            <div className="modal wide" onClick={(e) => e.stopPropagation()}>
              <Protocol data={protocol} />
              <div className="btnrow">
                <button className="btn2" onClick={() => setProtocol(null)}>Yopish</button>
                <button className="btn2 primary" onClick={() => window.print()}>
                  <IconDownload width={16} height={16} /> Chop etish / PDF saqlash
                </button>
              </div>
            </div>
          </div>
          <PrintPortal><Protocol data={protocol} /></PrintPortal>
        </>
      )}
    </div>
  );
}
