import { useEffect, useState } from "react";
import { listCheckins, startCheckin, listTests } from "../adminApi.js";
import TestParamsFields from "./TestParamsFields.jsx";
import SearchSelect from "./SearchSelect.jsx";
import { IconActivity } from "./icons.jsx";

const TSEX_OTHER = "__other__";

function testParamsFromTest(test) {
  return {
    mode: test.mode,
    grading_scale: test.grading_scale,
    pass_percent: test.pass_percent,
    time_limit: test.time_limit,
    time_limit_scope: test.time_limit_scope,
    sample_count: test.sample_count,
    common_question_count: test.common_question_count,
    shuffle_questions: test.shuffle_questions,
    shuffle_options: test.shuffle_options,
    instant_feedback: test.instant_feedback,
    proctoring: test.proctoring,
    grade_thresholds: test.grade_thresholds || [],
  };
}

export default function CheckinsTab() {
  const [checkins, setCheckins] = useState([]);
  const [tests, setTests] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  // Lavozim (test) tanlash + nastroykalarni belgilash modali — "Boshlash"
  // bosilganda ochiladi.
  const [startModal, setStartModal] = useState(null); // { checkinId, checkinName, testId, params }
  const [startBusy, setStartBusy] = useState(false);
  const [startError, setStartError] = useState("");

  async function load() {
    try {
      setCheckins(await listCheckins());
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    load();
    listTests().then(setTests).catch(() => {});
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, []);

  function openStartModal(checkin) {
    setStartModal({ checkinId: checkin.id, checkinName: checkin.full_name, tsex: "", testId: "", params: null });
    setStartError("");
  }

  function closeStartModal() {
    setStartModal(null);
    setStartError("");
  }

  function pickTsex(tsex) {
    setStartModal((m) => ({ ...m, tsex, testId: "", params: null }));
  }

  function pickTest(testId) {
    const t = tests.find((x) => String(x.id) === String(testId));
    setStartModal((m) => ({
      ...m,
      testId,
      params: t ? testParamsFromTest(t) : null,
    }));
  }

  async function confirmStart() {
    if (!startModal?.testId) {
      setStartError("Avval lavozim (test)ni tanlang.");
      return;
    }
    const selected = tests.find((x) => String(x.id) === String(startModal.testId));
    if (selected && !selected.question_count) {
      setStartError("Bu lavozimda hali savollar yo'q. Avval \"Testlar\" bo'limida savol qo'shing.");
      return;
    }
    setStartBusy(true);
    setStartError("");
    try {
      // Modaldagi test sozlamalari shu so'rovning o'zida saqlanadi — alohida
      // `updateTest` chaqirilmaydi (u "tests" ruxsatini talab qilardi).
      await startCheckin(startModal.checkinId, startModal.testId, startModal.params);
      listTests().then(setTests).catch(() => {});
      closeStartModal();
      await load();
    } catch (e) {
      setStartError(e.message);
    } finally {
      setStartBusy(false);
    }
  }

  const tsexList = [...new Set(tests.map((t) => t.tsex).filter(Boolean))].sort();
  const hasUntagged = tests.some((t) => !t.tsex);
  const tsexOptions = [
    ...tsexList.map((tx) => ({ value: tx, label: tx })),
    ...(hasUntagged ? [{ value: TSEX_OTHER, label: "Boshqa (sex belgilanmagan)" }] : []),
  ];
  const testsInTsex = startModal?.tsex
    ? tests.filter((t) => (startModal.tsex === TSEX_OTHER ? !t.tsex : t.tsex === startModal.tsex))
    : [];
  const selectedTest = startModal?.testId
    ? tests.find((t) => String(t.id) === String(startModal.testId))
    : null;
  const selectedTestEmpty = selectedTest && !selectedTest.question_count;

  function testLabel(t) {
    return t.question_count ? t.name : `⚠ ${t.name} (savol yo'q)`;
  }

  return (
    <div>
      <div className="stat-grid">
        <div className="stat-card2">
          <div>
            <div className="stat-card2-label">Testdagi Xodimlar</div>
            <div className="stat-card2-num">{checkins.length}</div>
          </div>
          <div className="icon-square blue"><IconActivity /></div>
        </div>
      </div>

      <div className="adm-card">
        <div className="adm-title-row">
          <h2>Testdagi xodimlar ro`yxati</h2>
          {/* <span className="adm-count-pill">Har 4 soniyada yangilanadi</span> */}
        </div>

        {error && <div className="alert" style={{ margin: "0 0 14px" }}>{error}</div>}

        <div className="adm-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th className="col-num">№</th>
                <th>Ism-familiya</th>
                <th>Bo'lim</th>
                <th>Keldi</th>
                <th>Moslik</th>
                <th className="col-actions"></th>
              </tr>
            </thead>
            <tbody>
              {checkins.map((c, i) => (
                <tr key={c.id}>
                  <td className="col-num">{i + 1}</td>
                  <td>{c.full_name}</td>
                  <td>{c.department || "—"}</td>
                  <td>{c.arrived_at}</td>
                  <td>{c.via === "password" ? "Parol orqali" : `${Math.round(c.match_score * 100)}%`}</td>
                  <td className="col-actions">
                    <button className="btn2 primary sm" onClick={() => openStartModal(c)}>
                      Boshlash
                    </button>
                  </td>
                </tr>
              ))}
              {!checkins.length && loaded && (
                <tr><td colSpan={6} className="empty">Hozircha hech kim kelmagan</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {startModal && (
        <div className="modal-backdrop" onClick={closeStartModal}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <h3>Testni boshlash — <span style={{ fontWeight: 400 }}>{startModal.checkinName}</span></h3>

            {tsexList.length > 0 ? (
              <>
                <div className="fg">
                  <label>Sex/tsex</label>
                  <SearchSelect options={tsexOptions} value={startModal.tsex} onChange={pickTsex} />
                </div>
                {startModal.tsex && (
                  <div className="fg">
                    <label>Lavozim (test)</label>
                    <SearchSelect
                      options={testsInTsex.map((t) => ({ value: String(t.id), label: testLabel(t) }))}
                      value={startModal.testId}
                      onChange={pickTest}
                    />
                  </div>
                )}
              </>
            ) : (
              <div className="fg">
                <label>Lavozim (test)</label>
                <SearchSelect
                  options={tests.map((t) => ({ value: String(t.id), label: testLabel(t) }))}
                  value={startModal.testId}
                  onChange={pickTest}
                />
              </div>
            )}

            {selectedTestEmpty && (
              <div className="alert" style={{ marginTop: 12 }}>
                Bu lavozimning o'ziga tegishli savollari yo'q (faqat "umumiy savollar"dan foydalanadi,
                bo'lsa ham). Avval "Testlar" bo'limida shu lavozimga o'ziga xos savollar qo'shing.
              </div>
            )}

            {startModal.params && (
              <>
                <div className="hint" style={{ marginTop: 14, marginBottom: 12 }}>
                  Test sozlamalari — bu sozlamalar shu testga biriktirilgan <b>barcha xodimlarga</b> tegishli
                </div>
                <TestParamsFields
                  values={startModal.params}
                  onChange={(p) => setStartModal((m) => ({ ...m, params: p }))}
                />
              </>
            )}

            {startError && <div className="alert" style={{ marginTop: 12 }}>{startError}</div>}

            <div className="btnrow">
              <button className="btn2" onClick={closeStartModal}>Bekor qilish</button>
              <button className="btn2 primary" onClick={confirmStart} disabled={startBusy}>
                {startBusy ? "Boshlanmoqda…" : "Boshlash"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
