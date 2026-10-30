// Proktoring videosi bo'lak-bo'lak yozib olinadi (qarang: proctoring.js) va
// shu sabab sarlavhada umumiy davomiylik yo'q — pleyer buni "jonli oqim" deb
// hisoblab, davomiylikni noto'g'ri (juda qisqa) ko'rsatadi.
//
// Bu — brauzerlarda keng tanilgan aylanma yo'l: videoni juda uzoq nuqtaga
// "sakratish" brauzerni haqiqiy davomiylikni RANGE so'rovlari orqali o'zi
// hisoblashga majburlaydi (server buni qo'llab-quvvatlaydi — qarang: backend
// `_serve_video_range`), so'ng boshiga qaytariladi.
//
// `<video onLoadedMetadata={fixVideoDuration}>` sifatida ulanadi.
export function fixVideoDuration(e) {
  const video = e.currentTarget;
  if (Number.isFinite(video.duration)) return;
  const onSeeked = () => {
    video.currentTime = 0;
    video.removeEventListener("seeked", onSeeked);
  };
  video.addEventListener("seeked", onSeeked);
  video.currentTime = 1e101;
}
