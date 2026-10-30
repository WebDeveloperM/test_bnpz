import { useEffect, useRef, useState } from "react";
import {
  searchSyncedEmployees, listExpectedEmployees, addExpectedEmployee,
  removeExpectedEmployee, clearExpectedEmployees, uploadSyncedEmployeePhoto,
  listEmployees, createEmployee, deleteEmployee,
} from "../adminApi.js";
import { IconUsers, IconPlus, IconTrash, IconCamera, IconKey, IconClose } from "./icons.jsx";

export default function ExpectedEmployeesTab() {
  const [expected, setExpected] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const debounceRef = useRef(null);
  // Qidiruv holati. `searchedFor` — natijalar QAYSI so'rovga tegishli ekani:
  // usiz "Hech kim topilmadi" javob hali kelmasidan turib chiqib ketardi va
  // xodim aslida topilgan bo'lsa ham admin "qidiruv ishlamayapti" deb tushunardi.
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchedFor, setSearchedFor] = useState("");
  const [bnpzOk, setBnpzOk] = useState(true);
  // BnpzId javob bermaganda ro'yxat mahalliy nusxadan keladi — eskirgan
  // bo'lishi mumkin, shuning uchun buni ochiq aytish shart.
  const [stale, setStale] = useState(false);
  // Natijalar sahifa chegarasida kesilganmi va BnpzId jami nechtasini topgani.
  // Kesilgani aytilmasa, ro'yxatga tushmagan xodim "yo'q" bo'lib ko'rinadi.
  const [truncated, setTruncated] = useState(false);
  const [totalFound, setTotalFound] = useState(0);
  // Har bir so'rovga tartib raqami beriladi — javoblar boshqa tartibda kelsa
  // (sekin so'rov tezidan keyin tugasa), eskisi yangisini bosib ketmasin.
  const searchSeqRef = useRef(0);
  const abortRef = useRef(null);

  // Kamera orqali surat olish modali (qo'shishda ham, tahrirlashda ham ishlatiladi)
  const [camera, setCamera] = useState(null); // { syncedId, name, snapshot }
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const capturedBlobRef = useRef(null);

  // BnpzId'da mavjud bo'lmagan, ism/parol bilan qo'lda yaratiladigan xodimlar.
  // Nomzod kamdan-kam keladi, shuning uchun ro'yxat sahifada doim turmaydi —
  // o'ng tomondan ochiladigan yon panelda (drawer) yashiringan.
  const [manualEmployees, setManualEmployees] = useState([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  // Bo'lim so'ralmaydi — nomzodning bo'limini backend o'zi "Nomzod" qilib qo'yadi.
  const [manualForm, setManualForm] = useState({ full_name: "", password: "" });
  const [manualBusy, setManualBusy] = useState(false);
  const [manualError, setManualError] = useState("");

  function loadExpected() {
    listExpectedEmployees().then(setExpected).finally(() => setLoaded(true));
  }
  function loadManual() {
    // Faqat hali test topshirmaganlar ko'rsatiladi: nomzod testni topshirgach
    // ro'yxatdan O'Z-O'ZIDAN chiqadi (yozuvi o'chirilmaydi — natijasi "Test
    // natijalari"da turadi). Kirish sahifasidagi ro'yxat ham xuddi shunday
    // (EmployeeManualListView "completed"ni chiqarmaydi).
    listEmployees()
      .then((all) => setManualEmployees(all.filter((e) => e.is_manual && e.status !== "completed")))
      .catch(() => {});
  }

  useEffect(() => { loadExpected(); loadManual(); }, []);
  useEffect(() => () => stopCameraStream(), []);

  // Yon panel ochiqda: Escape uni yopadi, sahifaning o'zi esa aylanmaydi.
  useEffect(() => {
    if (!drawerOpen) return undefined;
    const onKey = (e) => { if (e.key === "Escape") closeDrawer(); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [drawerOpen]);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    // Ketayotgan so'rov endi keraksiz — uni to'xtatamiz va tartib raqamini
    // oshirib qo'yamiz, ya'ni javobi kelsa ham e'tiborga olinmaydi.
    abortRef.current?.abort();
    searchSeqRef.current += 1;

    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      setSearching(false);
      setSearchError("");
      setSearchedFor("");
      setStale(false);
      setTruncated(false);
      return undefined;
    }

    setSearching(true);
    setSearchError("");
    debounceRef.current = setTimeout(() => {
      const seq = searchSeqRef.current;
      const controller = new AbortController();
      abortRef.current = controller;
      searchSyncedEmployees(q, controller.signal)
        .then((data) => {
          if (seq !== searchSeqRef.current) return; // eskirgan javob
          setResults(data.results || []);
          setBnpzOk(data.bnpz_ok !== false);
          setStale(data.stale === true);
          setTruncated(data.truncated === true);
          setTotalFound(data.total || 0);
          setSearchedFor(q);
          setSearching(false);
        })
        .catch((e) => {
          if (e.name === "AbortError" || seq !== searchSeqRef.current) return;
          // Xatoni yutib yubormaymiz: ilgari `catch(() => {})` turardi va
          // qidiruv ishlamaganda ekranda "Hech kim topilmadi" chiqib, sabab
          // umuman ko'rinmasdi.
          setResults([]);
          setSearchedFor(q);
          setStale(false);
          setTruncated(false);
          setSearchError(e.message || "Qidiruvni bajarib bo'lmadi.");
          setSearching(false);
        });
    }, 350);
    return () => clearTimeout(debounceRef.current);
  }, [query]);

  function resetSearch() {
    abortRef.current?.abort();
    searchSeqRef.current += 1;
    setQuery("");
    setResults([]);
    setSearching(false);
    setSearchError("");
    setSearchedFor("");
    setBnpzOk(true);
    setStale(false);
    setTruncated(false);
    setTotalFound(0);
  }

  function openAdd() {
    setAddOpen(true);
    resetSearch();
    setError("");
  }
  function closeAdd() {
    setAddOpen(false);
    resetSearch();
  }

  async function handleAdd(syncedId, name) {
    setBusyId(syncedId);
    setError("");
    try {
      await addExpectedEmployee(syncedId);
      loadExpected();
      setResults((prev) => prev.map((r) => (r.id === syncedId ? { ...r, is_expected: true } : r)));
    } catch (e) {
      // BnpzId'da rasm topilmadi/yuz aniqlanmadi — o'sha zahoti kamera orqali
      // qo'shishni taklif qilamiz (xatoni ko'rsatib o'tirmasdan).
      if (e.code === "no_face") {
        openCamera(syncedId, name);
      } else {
        setError(e.message);
      }
    } finally {
      setBusyId(null);
    }
  }

  function stopCameraStream() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  async function openCamera(syncedId, name) {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
      streamRef.current = stream;
      capturedBlobRef.current = null;
      setCamera({ syncedId, name, snapshot: null });
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      }, 0);
    } catch {
      setError("Kameraga ruxsat berilmadi. Brauzer so'rovida \"Ruxsat berish\"ni bosing.");
    }
  }

  function closeCamera() {
    stopCameraStream();
    setCamera(null);
  }

  function capture() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    stopCameraStream();
    canvas.toBlob((blob) => {
      capturedBlobRef.current = blob;
      setCamera((c) => ({ ...c, snapshot: canvas.toDataURL("image/jpeg", 0.92) }));
    }, "image/jpeg", 0.92);
  }

  function retake() {
    if (camera) openCamera(camera.syncedId, camera.name);
  }

  async function saveCapture() {
    if (!camera || !capturedBlobRef.current) return;
    const syncedId = camera.syncedId;
    setBusyId(syncedId);
    setError("");
    try {
      await uploadSyncedEmployeePhoto(syncedId, capturedBlobRef.current);
      setResults((prev) => prev.map((r) => (r.id === syncedId ? { ...r, has_photo: true, is_expected: true } : r)));
      loadExpected();
      closeCamera();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleRemove(entryId) {
    setBusyId(entryId);
    setError("");
    try {
      await removeExpectedEmployee(entryId);
      loadExpected();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleClearAll() {
    if (!window.confirm("Kutilayotgan xodimlar ro'yxati butunlay tozalansinmi?")) return;
    setError("");
    try {
      await clearExpectedEmployees();
      loadExpected();
    } catch (e) {
      setError(e.message);
    }
  }

  function openDrawer() {
    loadManual();
    setDrawerOpen(true);
  }
  function closeDrawer() {
    setDrawerOpen(false);
    setManualOpen(false);
  }

  function openManualAdd() {
    setManualForm({ full_name: "", password: "" });
    setManualError("");
    setManualOpen(true);
  }
  function closeManualAdd() {
    setManualOpen(false);
  }
  async function saveManual() {
    if (!manualForm.full_name.trim()) {
      setManualError("Ism-familiyani kiriting.");
      return;
    }
    if (!manualForm.password.trim()) {
      setManualError("Parolni kiriting.");
      return;
    }
    setManualBusy(true);
    setManualError("");
    try {
      await createEmployee({
        full_name: manualForm.full_name.trim(),
        password: manualForm.password.trim(),
      });
      loadManual();
      closeManualAdd();
    } catch (e) {
      setManualError(e.message);
    } finally {
      setManualBusy(false);
    }
  }
  async function removeManual(id) {
    if (!window.confirm("Bu xodim o'chirilsinmi?")) return;
    setBusyId(id);
    try {
      await deleteEmployee(id);
      loadManual();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-card2">
          <div>
            <div className="stat-card2-label">Yuz orqali kiradiganlar</div>
            <div className="stat-card2-num">{expected.length}</div>
          </div>
          <div className="icon-square blue"><IconUsers /></div>
        </div>
        {/* Nomzodlar kartasi — bosilsa yon panel ochiladi. */}
        <button type="button" className="stat-card2 clickable" onClick={openDrawer}
          title="Nomzodlar ro'yxatini ochish">
          <div>
            <div className="stat-card2-label">Nomzodlar (parol bilan)</div>
            <div className="stat-card2-num">{manualEmployees.length}</div>
            <span className="stat-card2-link">Ro'yxatni ochish →</span>
          </div>
          <div className="icon-square yellow"><IconKey /></div>
        </button>
      </div>

      <div className="adm-card">
        <div className="adm-title-row">
          <h2>BnpzId orqali kiradigan xodimlar</h2>
          <div className="adm-toolbar-btns">
            <button className="btn2" onClick={openDrawer} title="BnpzId'da yo'q nomzodlar">
              <IconKey width={16} height={16} /> Nomzodlar
              {manualEmployees.length > 0 && <span className="btn-badge">{manualEmployees.length}</span>}
            </button>
            {expected.length > 0 && (
              <button className="btn2 danger sm" onClick={handleClearAll}>Barchasini tozalash</button>
            )}
            <button className="btn2 primary" onClick={openAdd}>
              <IconPlus width={16} height={16} /> BnpzId'dan tanlash
            </button>
          </div>
        </div>
        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-num">№</th><th>Ism-familiya</th><th>Tabel</th><th>Bo'lim</th><th className="col-actions" />
              </tr>
            </thead>
            <tbody>
              {expected.map((e, i) => (
                <tr key={e.id}>
                  <td className="col-num">{i + 1}</td>
                  <td>{e.full_name}</td>
                  <td>{e.tabel_number || "—"}</td>
                  <td>{e.department_name || "—"}</td>
                  <td className="col-actions">
                    <div className="adm-icon-row">
                      <button className="adm-icon-btn" title="Rasmni o'zgartirish"
                        onClick={() => openCamera(e.synced_employee_id, e.full_name)} disabled={busyId === e.id}>
                        <IconCamera width={15} height={15} />
                      </button>
                      <button className="adm-icon-btn danger" title="Olib tashlash"
                        onClick={() => handleRemove(e.id)} disabled={busyId === e.id}>
                        <IconTrash width={15} height={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!expected.length && loaded && (
                <tr><td colSpan={5} className="empty">Hozircha xodim qo'shilmagan</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* --- Nomzodlar yon paneli --- */}
      {drawerOpen && (
        <>
          <div className="drawer-backdrop" onClick={closeDrawer} />
          <aside className="drawer" role="dialog" aria-label="Nomzodlar">
            <div className="drawer-head">
              <div>
                <h3><IconKey width={17} height={17} /> Nomzodlar</h3>
                <p className="adm-card-sub">
                  BnpzId ro'yxatida bo'lmagan, ishga kirmoqchi bo'lganlar. Ular kirish sahifasida
                  ism-familiya va parol bilan kirishadi, so'ng kutish ro'yxatiga tushadi — lavozim
                  va testni o'sha yerdan odatdagidek tayinlaysiz. Nomzod testni topshirgach bu
                  ro'yxatdan o'zi chiqadi — natijasi "Test natijalari"da qoladi.
                </p>
              </div>
              <button className="drawer-close" onClick={closeDrawer} title="Yopish (Esc)">
                <IconClose width={17} height={17} />
              </button>
            </div>

            <div className="drawer-body">
              {manualOpen ? (
                <div className="drawer-form">
                  <div className="drawer-form-title">Yangi nomzod</div>
                  <label>Ism-familiya</label>
                  <input
                    className="field"
                    value={manualForm.full_name}
                    onChange={(e) => setManualForm({ ...manualForm, full_name: e.target.value })}
                    placeholder="Masalan: Karimov Aziz"
                    autoFocus
                  />
                  <label>Parol</label>
                  <input
                    className="field"
                    value={manualForm.password}
                    onChange={(e) => setManualForm({ ...manualForm, password: e.target.value })}
                    placeholder="Masalan: 1234"
                    onKeyDown={(e) => { if (e.key === "Enter") saveManual(); }}
                  />
                  <div className="hint">Bo'lim so'ralmaydi — nomzodlarning bo'limi doim "Nomzod" bo'ladi.</div>
                  {manualError && <div className="alert" style={{ marginTop: 12 }}>{manualError}</div>}
                  <div className="drawer-form-btns">
                    <button className="btn2" onClick={closeManualAdd}>Bekor qilish</button>
                    <button className="btn2 primary" onClick={saveManual} disabled={manualBusy}>
                      {manualBusy ? "Saqlanmoqda…" : "Saqlash"}
                    </button>
                  </div>
                </div>
              ) : (
                <button className="btn2 primary block" style={{ marginTop: 0, marginBottom: 18 }}
                  onClick={openManualAdd}>
                  <IconPlus width={16} height={16} /> Nomzod qo'shish
                </button>
              )}

              {manualEmployees.length > 0 ? (
                <div className="adm-table-wrap">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th className="col-num">№</th><th>Ism-familiya</th><th className="col-actions" />
                      </tr>
                    </thead>
                    <tbody>
                      {/* "Holat" ustuni yo'q: test topshirganlar ro'yxatdan avtomatik
                          chiqadi, ya'ni bu yerda faqat kutayotganlar turadi. */}
                      {manualEmployees.map((e, i) => (
                        <tr key={e.id}>
                          <td className="col-num">{i + 1}</td>
                          <td>{e.full_name}</td>
                          <td className="col-actions">
                            <div className="adm-icon-row">
                              <button className="adm-icon-btn danger" title="O'chirish"
                                onClick={() => removeManual(e.id)} disabled={busyId === e.id}>
                                <IconTrash width={15} height={15} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="drawer-empty">
                  <div className="icon-square yellow"><IconKey /></div>
                  <p>Hozircha nomzod yo'q</p>
                  <span>Ishga kirmoqchi bo'lgan, BnpzId'da hisobi bo'lmagan odam kelganda uni shu yerga qo'shasiz.</span>
                </div>
              )}
            </div>
          </aside>
        </>
      )}

      {addOpen && (
        <div className="modal-backdrop" onClick={closeAdd}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>Xodim qo'shish</h3>
            <p className="sub" style={{ marginTop: -6 }}>
              Ism yoki tabel raqamini yozing, topilgan xodimni ro'yxatga qo'shing — rasmi bo'lmasa,
              kamera orqali shu yerda surat oling.
            </p>

            <input
              className="field"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ism, familiya yoki tabel raqami"
              autoFocus
            />

            {query.trim().length > 0 && query.trim().length < 2 && (
              <div className="hint" style={{ marginTop: 10 }}>Kamida 2 ta harf/raqam yozing…</div>
            )}

            {searching && (
              <div className="hint" style={{ marginTop: 10 }}>Qidirilmoqda…</div>
            )}

            {!searching && searchError && (
              <div className="alert" style={{ marginTop: 10 }}>{searchError}</div>
            )}

            {/* BnpzId javob bermagani — "bunday xodim yo'q" degani EMAS.
                Ikkalasini aralashtirsak, admin mavjud xodimni yo'q deb o'ylab,
                uni qo'lda qayta yaratishga urinardi. Shu sabab BnpzId javob
                bermaganda ham ro'yxat bo'sh qolmaydi: mahalliy nusxadan
                ko'rsatiladi, lekin uning eskirgani ochiq aytiladi. */}
            {!searching && !searchError && searchedFor && !bnpzOk && (
              <div className="alert" style={{ marginTop: 10 }}>
                BnpzId (xodimlar bazasi) javob bermadi. Quyidagilar — mahalliy
                nusxadan, ya'ni <b>eskirgan bo'lishi mumkin</b>: yangi xodim bu
                yerda bo'lmaydi, ishdan bo'shagani esa qolib ketgan bo'lishi
                mumkin. Rasmi mahalliy saqlangan xodimni ro'yxatga qo'shsa
                bo'ladi, qolganiga kamera orqali surat oling.
              </div>
            )}

            {/* Kesilgan ro'yxat jimgina qolsa, unga tushmagan xodim "yo'q"
                bo'lib ko'rinadi — shuning uchun aniq son bilan aytiladi. */}
            {!searching && !searchError && searchedFor && truncated && (
              <div className="hint" style={{ marginTop: 10 }}>
                «{searchedFor}» bo'yicha {totalFound} ta xodim topildi, shundan
                birinchi {results.length} tasi ko'rsatilyapti. Kerakli xodim
                ro'yxatda bo'lmasa — familiyani to'liqroq yozing yoki tabel
                raqamini kiriting.
              </div>
            )}

            {/* "Topilmadi" faqat qidiruv HAQIQATAN tugagach va aynan shu
                so'rov uchun ko'rsatiladi — aks holda javob kutilayotganda ham
                chiqib, xodim bor bo'lsa ham "yo'q" bo'lib ko'rinardi.
                `searchedFor` bo'sh bo'lsa hali hech narsa qidirilmagan. */}
            {!searching && !searchError && bnpzOk && searchedFor
              && searchedFor === query.trim() && results.length === 0 && (
              <div className="hint" style={{ marginTop: 10 }}>
                «{searchedFor}» bo'yicha BnpzId'da hech kim topilmadi.
              </div>
            )}

            {!searching && !searchError && stale && searchedFor
              && searchedFor === query.trim() && results.length === 0 && (
              <div className="hint" style={{ marginTop: 10 }}>
                «{searchedFor}» bo'yicha mahalliy nusxada ham hech kim topilmadi.
              </div>
            )}

            {results.length > 0 && (
              <div className="adm-table-wrap" style={{ marginTop: 14 }}>
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th className="col-num">№</th><th>Ism-familiya</th><th>Tabel</th><th>Bo'lim</th><th className="col-actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((r, i) => (
                      <tr key={r.id}>
                        <td className="col-num">{i + 1}</td>
                        <td>{r.full_name}</td>
                        <td>{r.tabel_number || "—"}</td>
                        <td>{r.department_name || "—"}</td>
                        <td className="col-actions">
                          {r.is_expected ? (
                            <span className="badge done">✓ Ro'yxatda</span>
                          ) : r.has_photo ? (
                            <button className="btn2 sm primary"
                              onClick={() => handleAdd(r.id, r.full_name)} disabled={busyId === r.id}>
                              <IconPlus width={14} height={14} /> Ro'yxatga qo'shish
                            </button>
                          ) : (
                            <button className="btn2 sm" title="Rasmi yo'q — kamera orqali surat olib qo'shiladi"
                              onClick={() => openCamera(r.id, r.full_name)} disabled={busyId === r.id}>
                              <IconCamera width={14} height={14} /> Rasm olib qo'shish
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {error && <div className="alert" style={{ marginTop: 12 }}>{error}</div>}

            <div className="btnrow">
              <button className="btn2" onClick={closeAdd}>Yopish</button>
            </div>
          </div>
        </div>
      )}

      {camera && (
        <div className="modal-backdrop" onClick={closeCamera}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <h3 style={{ marginTop: 0 }}>Rasm olish — <span style={{ fontWeight: 400 }}>{camera.name}</span></h3>

            {camera.snapshot ? (
              <img src={camera.snapshot} alt="" style={{ width: "100%", borderRadius: 8, display: "block" }} />
            ) : (
              <video
                ref={videoRef} autoPlay playsInline muted
                style={{ width: "100%", aspectRatio: "4/3", objectFit: "cover", borderRadius: 8, background: "#000", transform: "scaleX(-1)" }}
              />
            )}

            {error && <div className="alert" style={{ marginTop: 12 }}>{error}</div>}

            <div className="btnrow">
              <button className="btn2" onClick={closeCamera}>Bekor qilish</button>
              {camera.snapshot ? (
                <>
                  <button className="btn2" onClick={retake}>Qayta olish</button>
                  <button className="btn2 primary" onClick={saveCapture} disabled={busyId === camera.syncedId}>
                    {busyId === camera.syncedId ? "Saqlanmoqda…" : "Saqlash"}
                  </button>
                </>
              ) : (
                <button className="btn2 primary" onClick={capture}>Suratga olish</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
