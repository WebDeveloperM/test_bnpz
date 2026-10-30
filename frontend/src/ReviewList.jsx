export default function ReviewList({ review, t }) {
  return (
    <div className="rev">
      {review.map((item, i) => {
        const isMatching = item.pairs !== undefined;
        if (isMatching) {
          return (
            <div className="rev-item" key={i}>
              <div className="rev-q">
                <span className={"rev-badge " + (item.is_correct ? "good" : "wrong")}>
                  {item.is_correct ? "✓" : "✗"}
                </span>
                {i + 1}. {item.question}
              </div>
              {item.pairs.map((p, pi) => (
                <div className={"rev-line " + (p.is_correct ? "good" : "wrong")} key={pi}>
                  <b>{p.is_correct ? "✓" : "✗"}</b>{" "}
                  {p.left}: {p.chosen ? p.chosen : "— (" + t.not_answered + ")"}
                  {!p.is_correct && <> — {t.correct_answer}: {p.correct}</>}
                </div>
              ))}
              {item.explanation && <div className="rev-exp">ℹ {item.explanation}</div>}
            </div>
          );
        }

        const isOrdering = item.given_order !== undefined;
        const isText = !isOrdering && item.options === undefined;

        if (!isText && !isOrdering) {
          // Bir/ko'p tanlovli, to'g'ri/noto'g'ri — barcha variantlarni belgilab ko'rsatish
          return (
            <div className="rev-item" key={i}>
              <div className="rev-q">
                <span className={"rev-badge " + (item.is_correct ? "good" : "wrong")}>
                  {item.is_correct ? "✓" : "✗"}
                </span>
                {i + 1}. {item.question}
              </div>
              <div className="rev-opts">
                {item.options.map((o, oi) => {
                  let cls = "rev-opt";
                  let mark = "";
                  if (o.is_correct && o.chosen) { cls += " correct-chosen"; mark = "✓"; }
                  else if (o.is_correct && !o.chosen) { cls += " correct-missed"; mark = "✓"; }
                  else if (!o.is_correct && o.chosen) { cls += " wrong-chosen"; mark = "✗"; }
                  return (
                    <div className={cls} key={oi}>
                      <span className="rev-opt-mark">{mark}</span>
                      {/* Rasmli variantda faqat matnni ko'rsatish "qaysi
                          rasmni tanlagandim?" degan savolni ochiq qoldirardi. */}
                      <span className="rev-opt-body">
                        {o.image && <img className="opt-img" src={o.image} alt="" loading="lazy" />}
                        {o.text && <span>{o.text}</span>}
                      </span>
                      {o.chosen && <span className="rev-opt-tag">Siz belgiladingiz</span>}
                    </div>
                  );
                })}
              </div>
              {item.explanation && <div className="rev-exp">ℹ {item.explanation}</div>}
            </div>
          );
        }

        const yourAnswer = isOrdering ? item.given_order.join(" → ") : item.given_text;
        const correctAnswer = isOrdering ? item.correct_order.join(" → ") : item.correct_text;
        return (
          <div className="rev-item" key={i}>
            <div className="rev-q">
              <span className={"rev-badge " + (item.is_correct ? "good" : "wrong")}>
                {item.is_correct ? "✓" : "✗"}
              </span>
              {i + 1}. {item.question}
            </div>
            <div className={"rev-line " + (item.is_correct ? "good" : "wrong")}>
              <b>{item.is_correct ? "✓" : "✗"}</b>{" "}
              {t.your_answer}: {yourAnswer ? yourAnswer : "— (" + t.not_answered + ")"}
            </div>
            {!item.is_correct && (
              <div className="rev-line good">
                <b>✓</b> {t.correct_answer}: {correctAnswer}
              </div>
            )}
            {item.explanation && <div className="rev-exp">ℹ {item.explanation}</div>}
          </div>
        );
      })}
    </div>
  );
}
