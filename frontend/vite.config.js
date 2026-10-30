import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// "admin" konteynerida (VITE_ADMIN_ONLY=true) /it-center yo'li Django'ning
// o'zining tayyor admin paneliga (backend:8000/it-center/) proksi qilinadi —
// dasturchi shu URL orqali to'g'ridan-to'g'ri Django admin'ga kiradi.
const isAdminOnly = process.env.VITE_ADMIN_ONLY === "true";
const backendTarget = "http://backend:8000";

// changeOrigin ATAYLAB ishlatilmaydi: Host sarlavhasi brauzer yuborgan asl
// qiymatida (masalan "localhost:2050") qolishi kerak, aks holda Django CSRF
// tekshiruvi Origin va Host mos kelmaydi deb 403 Forbidden qaytaradi.
const proxyToBackend = { target: backendTarget };

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // API va yuklangan fayllar endi NISBIY manzil orqali so'raladi ("/api"),
      // shuning uchun ishlab chiqish serveri ham ularni backend'ga uzatishi kerak.
      // Ishlab chiqarishda xuddi shu vazifani nginx bajaradi — natijada ilova
      // kodi ikkala muhitda bir xil qoladi va HTTPS'da "mixed content" muammosi
      // umuman paydo bo'lmaydi.
      "/api": proxyToBackend,
      "/media": proxyToBackend,
      // Django'ning o'z admin paneli faqat admin qurilmasida kerak.
      ...(isAdminOnly ? { "/it-center": proxyToBackend, "/static": proxyToBackend } : {}),
    },
  },
});
