import ReviewList from "../ReviewList.jsx";

export default function ResultView({ result, t, onHome }) {
  const r = result.result;
  const review = result.review || [];
  const wrong = r.total - r.correct;

  return (
    <div className="card res-card">
      <div className="res-head">
        <div className="res-name">{r.full_name}</div>
        <div className="res-role">{r.test_name}</div>
      </div>

      <div className="res-body">
        {/* Test o'z-o'zidan yopilgan bo'lsa, sababini aytamiz — aks holda
            xodim "men hali tugatmagan edim-ku?" deb hayron qoladi. */}
        {r.interrupted && (
          <div className="alert" style={{ marginBottom: 16 }}>
            <b>{t.interrupted_title}</b> {t.interrupted_text}
          </div>
        )}
        <div className="res-score-row">
          <div className="score-block">
            <div className="score-label">{t.overall_score}</div>
            <div className="score-pct">{r.grade || r.pct + "%"}</div>
          </div>
          <div className={"verdict-badge " + (r.passed ? "pass" : "fail")}>
            {t.result}: {r.passed ? t.passed_word : t.failed_word}
          </div>
        </div>
        <div className="res-divider" />
        <div className="res-stats-grid">
          <div className="res-stat-box good">
            <div className="res-stat-num">{r.correct}</div>
            <div className="res-stat-label">{t.correct_answers}</div>
          </div>
          <div className="res-stat-box bad">
            <div className="res-stat-num">{wrong}</div>
            <div className="res-stat-label">{t.wrong_answers}</div>
          </div>
        </div>
      </div>

      <h3 className="rev-h">{t.review}</h3>
      <ReviewList review={review} t={t} />

      <button className="btn block" onClick={onHome}>{t.home}</button>
    </div>
  );
}
