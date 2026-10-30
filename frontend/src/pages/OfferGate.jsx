import { useEffect, useState } from "react";
import { getSettings, acceptOffer } from "../api.js";

export default function OfferGate({ session, onAccept }) {
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState(null);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getSettings()
      .then((s) => {
        if (!s.offer_text && !s.offer_video_url) {
          onAccept();
          return;
        }
        setSettings(s);
        setLoading(false);
      })
      .catch(() => onAccept());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleContinue() {
    setBusy(true);
    try {
      await acceptOffer(session.token);
    } catch {
      // Rozilikni qayd etish muvaffaqiyatsiz bo'lsa ham testni to'xtatmaymiz
    }
    onAccept();
  }

  if (loading) return null;

  return (
    <div className="card">
      <h2 className="h">Ommaviy oferta</h2>
      <p className="sub">Davom etishdan oldin quyidagi shartlar bilan tanishib chiqing.</p>

      {settings.offer_video_url && (
        <video className="offer-video" src={settings.offer_video_url} controls />
      )}

      {settings.offer_text && <div className="intro-text">{settings.offer_text}</div>}

      <label className="chk" style={{ marginTop: 18 }}>
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
        Men ommaviy oferta shartlari bilan tanishib chiqdim va roziman
      </label>

      <button className="btn block" onClick={handleContinue} disabled={!agreed || busy} style={{ marginTop: 16 }}>
        {busy ? "Yuklanmoqda..." : "Davom etish →"}
      </button>
    </div>
  );
}
