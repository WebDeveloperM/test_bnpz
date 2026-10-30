import { useEffect, useState } from "react";
import { getSettings, updateSettings, uploadOfferVideo, deleteOfferVideo } from "../adminApi.js";
import { IconUpload, IconTrash } from "./icons.jsx";

export default function SettingsTab() {
  const [settings, setSettings] = useState(null);
  const [offerText, setOfferText] = useState("");
  const [busy, setBusy] = useState(false);
  const [videoBusy, setVideoBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  function load() {
    getSettings().then((s) => {
      setSettings(s);
      setOfferText(s.offer_text || "");
    });
  }

  useEffect(() => { load(); }, []);

  async function save() {
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const s = await updateSettings({ offer_text: offerText });
      setSettings(s);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleVideoUpload(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setVideoBusy(true);
    setError("");
    try {
      const res = await uploadOfferVideo(file);
      setSettings((s) => ({ ...s, offer_video_url: res.offer_video_url }));
    } catch (e2) {
      setError(e2.message);
    } finally {
      setVideoBusy(false);
    }
  }

  async function handleVideoRemove() {
    if (!window.confirm("Oferta videosi o'chirilsinmi?")) return;
    setVideoBusy(true);
    setError("");
    try {
      await deleteOfferVideo();
      setSettings((s) => ({ ...s, offer_video_url: null }));
    } catch (e) {
      setError(e.message);
    } finally {
      setVideoBusy(false);
    }
  }

  if (!settings) return null;

  return (
    <div className="set-wrap">
      <div className="set-head">
        <div className="set-eyebrow">Boshqaruv</div>
        <h1 className="set-title">Sozlamalar</h1>
      </div>

      {error && <div className="alert" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="set-grid">
      {/* Oferta matni */}
      <div className="set-section">
        <h3>Ommaviy oferta matni</h3>
        <p className="set-desc">
          Xodim testni boshlashdan oldin shu matnni (video bilan birga) ko'radi va roziligini
          bildiradi. Bo'sh qoldirilsa (video ham bo'lmasa) — bu qadam butunlay o'tkazib yuboriladi.
        </p>
        <textarea
          className="set-textarea"
          value={offerText}
          onChange={(e) => setOfferText(e.target.value)}
          placeholder="Ommaviy oferta shartlari matnini shu yerga yozing…"
        />
        <div className="set-actions">
          <button className="btn2 primary" onClick={save} disabled={busy}>
            {busy ? "Saqlanmoqda…" : "Saqlash"}
          </button>
          {saved && <span className="set-saved">✓ Saqlandi</span>}
        </div>
      </div>

      {/* Video instruksiya */}
      <div className="set-section">
        <h3>Oferta video instruksiyasi</h3>
        <p className="set-desc">
          Ixtiyoriy. Matn bilan birga ko'rsatiladi — masalan test qoidalari bo'yicha qisqa video.
        </p>
        {settings.offer_video_url ? (
          <div className="set-video">
            <video src={settings.offer_video_url} controls />
            <button className="btn2 danger sm set-video-remove" onClick={handleVideoRemove} disabled={videoBusy}>
              <IconTrash width={14} height={14} /> Videoni o'chirish
            </button>
          </div>
        ) : (
          <label className="set-drop">
            <span className="set-drop-icon"><IconUpload width={20} height={20} /></span>
            <b>{videoBusy ? "Yuklanmoqda…" : "Video yuklash"}</b>
            <span>MP4 yoki WebM · bosib faylni tanlang</span>
            <input type="file" accept="video/*" style={{ display: "none" }} onChange={handleVideoUpload} disabled={videoBusy} />
          </label>
        )}
      </div>
      </div>
    </div>
  );
}
