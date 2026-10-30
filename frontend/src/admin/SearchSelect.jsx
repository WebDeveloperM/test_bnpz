import { useEffect, useRef, useState } from "react";
import { IconSearch, IconCheck } from "./icons.jsx";

export default function SearchSelect({ options, value, onChange, placeholder = "— tanlang —" }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  // Klaviatura bilan yurilayotgan element. Ro'yxat uzun (sexlar 30 dan ortiq)
  // bo'lgani uchun sichqonchasiz tanlash sezilarli tez.
  const [cursor, setCursor] = useState(0);
  const rootRef = useRef(null);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) close();
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const selected = options.find((o) => String(o.value) === String(value));
  const q = query.trim().toLowerCase();
  const filtered = q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;

  function close() {
    setOpen(false);
    setQuery("");
    setCursor(0);
  }
  function toggleOpen() {
    setOpen((o) => {
      const next = !o;
      if (next) {
        setQuery("");
        // Ochilganda kursor tanlangan elementga turadi.
        const i = options.findIndex((x) => String(x.value) === String(value));
        setCursor(i < 0 ? 0 : i);
        setTimeout(() => inputRef.current?.focus(), 0);
      }
      return next;
    });
  }
  function pick(opt) {
    onChange(opt.value);
    close();
  }

  // Kursor ko'rinib turishi uchun ro'yxatni surib qo'yamiz.
  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.children[cursor];
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor, open]);

  function onKeyDown(e) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!filtered.length) return;
      setCursor((c) => {
        const next = e.key === "ArrowDown" ? c + 1 : c - 1;
        return (next + filtered.length) % filtered.length;
      });
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[cursor]) pick(filtered[cursor]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  // Qidiruvga mos kelgan qismni ajratib ko'rsatamiz.
  function highlight(label) {
    if (!q) return label;
    const i = label.toLowerCase().indexOf(q);
    if (i < 0) return label;
    return (
      <>
        {label.slice(0, i)}
        <mark>{label.slice(i, i + q.length)}</mark>
        {label.slice(i + q.length)}
      </>
    );
  }

  return (
    <div className="search-select" ref={rootRef}>
      <button
        type="button"
        className={"field search-select-trigger" + (open ? " open" : "")}
        onClick={toggleOpen}
      >
        <span className={selected ? "" : "search-select-placeholder"}>
          {selected ? selected.label : placeholder}
        </span>
        <span className="search-select-arrow">▾</span>
      </button>

      {open && (
        <div className="search-select-panel">
          <div className="search-select-search">
            <IconSearch width={16} height={16} />
            <input
              ref={inputRef}
              className="search-select-input"
              placeholder="Qidirish…"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setCursor(0); }}
              onKeyDown={onKeyDown}
            />
            {query && (
              <button type="button" className="search-select-clear"
                onClick={() => { setQuery(""); inputRef.current?.focus(); }} title="Tozalash">✕</button>
            )}
          </div>

          <div className="search-select-list" ref={listRef}>
            {filtered.map((o, i) => {
              const isSel = String(o.value) === String(value);
              return (
                <div
                  key={o.value}
                  className={"search-select-option" + (isSel ? " active" : "") + (i === cursor ? " cursor" : "")}
                  onClick={() => pick(o)}
                  onMouseEnter={() => setCursor(i)}
                >
                  <span className="search-select-label">{highlight(o.label)}</span>
                  {isSel && <IconCheck width={15} height={15} />}
                </div>
              );
            })}
            {filtered.length === 0 && (
              <div className="search-select-empty">
                <b>“{query}”</b> bo'yicha hech narsa topilmadi
              </div>
            )}
          </div>

          <div className="search-select-foot">
            {filtered.length} ta{q && ` / ${options.length}`}
            <span className="search-select-kbd">↑↓ tanlash · Enter tasdiqlash</span>
          </div>
        </div>
      )}
    </div>
  );
}
