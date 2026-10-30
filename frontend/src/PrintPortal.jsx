import { createPortal } from "react-dom";

export default function PrintPortal({ children }) {
  const el = document.getElementById("print-root");
  if (!el) return null;
  return createPortal(children, el);
}
