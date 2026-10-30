import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import AdminRoot from "./admin/AdminRoot.jsx";
import "./styles.css";

const isAdmin = import.meta.env.VITE_ADMIN_ONLY === "true";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {isAdmin ? <AdminRoot /> : <App />}
  </React.StrictMode>
);
