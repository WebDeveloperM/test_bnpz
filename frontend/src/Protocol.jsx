const QUESTIONS_PER_ROW = 10;

function chunk(arr, size) {
  const out = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

export default function Protocol({ data }) {
  if (!data) return null;
  return (
    <div className="protocol">
      <h2 className="protocol-title">Bayonnoma</h2>

      <div className="protocol-info">
        <div>Test topshiruvchining ism-familiyasi: <b>{data.full_name}</b>.</div>
        <div>Bo'lim, sex: {data.department || "—"}</div>
        <div>Test topshirilgan sana: {data.date}.</div>
        <div>Boshlangan vaqti: {data.started_at || "—"}. Tugagan vaqti: {data.finished_at}.</div>
        <div>Davomiyligi: {data.duration || "—"}.</div>
        <div>Test (lavozim) nomi: {data.test_name}</div>
        <div>Testdagi jami savollar soni: {data.total}. Bajarilgan savollar: {data.attempted}.</div>
        <div>Shundan to'g'ri: {data.correct} (bajarilgan savollarning {data.correct_pct}%.)</div>
        <div>Shundan xato: {data.wrong} (bajarilgan savollarning {data.wrong_pct}%).</div>
        <div>Natijadorlik: {data.correct_pct}%.</div>
        <div>Tekshirishdan foydalanildi: {data.hints_used} marta.</div>
        <div>To'plangan ball: {data.points_earned},0 / mumkin bo'lgan {data.points_total},0 balldan. Natija: {data.result_pct}%.</div>
        <div className="protocol-grade">Baho: {data.grade}.</div>
      </div>

      <h3 className="protocol-h3">Natijalar jadvali</h3>
      <div className="protocol-table-wrap">
        {chunk(data.per_question, QUESTIONS_PER_ROW).map((group, gi) => (
          <table className="protocol-qtable" key={gi}>
            <tbody>
              <tr>
                <th>Savol №</th>
                {group.map((q) => <td key={q.index}>{q.index}</td>)}
              </tr>
              <tr>
                <th>Natija</th>
                {group.map((q) => (
                  <td key={q.index} className={q.is_correct ? "good" : "wrong"}>{q.is_correct ? "+" : "−"}</td>
                ))}
              </tr>
              <tr>
                <th>Vaqt</th>
                {group.map((q) => <td key={q.index}>{q.time}</td>)}
              </tr>
            </tbody>
          </table>
        ))}
      </div>

      <h3 className="protocol-h3">Mavzular bo'yicha natijalar jadvali</h3>
      <table className="protocol-table">
        <thead>
          <tr>
            <th>Mavzu</th><th>To'g'ri</th><th>Xato</th><th>Natijadorlik</th><th>O'rt. vaqt</th><th>O'rt. ball</th>
          </tr>
        </thead>
        <tbody>
          {data.by_topic.map((t, i) => (
            <tr key={i}>
              <td>{t.name}</td><td>{t.correct}</td><td>{t.wrong}</td>
              <td>{t.result_pct}</td><td>{t.avg_time}</td><td>{t.avg_points}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="protocol-footer">
        <div>Sana: {data.generated_at}.</div>
        <div className="protocol-sign">Test administratori: ____________________</div>

        <div className="protocol-sign-row">
          {/* Sana avtomatik to'ldiriladi (test topshirilgan sana) — yuqoridagi
              "Sana:" kabi. Imzo esa qo'lda qo'yiladi, shu sabab bo'sh chiziq. */}
          <span>Sana: {data.date}</span>
          <span>Imzo: ______________</span>
          <span>Test topshiruvchi xodim: <b>{data.full_name}</b></span>
        </div>

        <div className="protocol-objection">
          <div>Xodimning e'tirozi (bo'lsa, qo'lda yoziladi):</div>
          <div className="protocol-objection-line" />
          <div className="protocol-objection-line" />
          <div className="protocol-objection-line" />
        </div>
      </div>
    </div>
  );
}
