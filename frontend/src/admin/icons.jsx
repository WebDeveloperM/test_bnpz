const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };

export const IconHome = (p) => (
  <svg {...base} {...p}><path d="M3 11.5 12 4l9 7.5" /><path d="M5.5 10v9.5a1 1 0 0 0 1 1H9a1 1 0 0 0 1-1V15a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v4.5a1 1 0 0 0 1 1h2.5a1 1 0 0 0 1-1V10" /></svg>
);
export const IconUsers = (p) => (
  <svg {...base} {...p}><circle cx="9" cy="8" r="3.2" /><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6" />
    <circle cx="17.5" cy="8.5" r="2.6" /><path d="M15.8 14.2c2.7.4 4.7 2.5 4.7 5.8" /></svg>
);
export const IconTest = (p) => (
  <svg {...base} {...p}><path d="M9 3h6v3.2l4.3 8.6a2 2 0 0 1-1.8 2.9H6.5a2 2 0 0 1-1.8-2.9L9 6.2V3Z" />
    <path d="M8.2 15h7.6" /></svg>
);
export const IconResults = (p) => (
  <svg {...base} {...p}><path d="M4 20V10M12 20V4M20 20v-7" /><path d="M2.5 20h19" /></svg>
);
export const IconSettings = (p) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="3" />
    <path d="M19.4 13a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V19a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H4a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H10a1.7 1.7 0 0 0 1-1.5V4a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V10c.1.7.6 1.3 1.5 1.5h.1a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" /></svg>
);
export const IconLogout = (p) => (
  <svg {...base} {...p}><path d="M9 20H5.5a1.5 1.5 0 0 1-1.5-1.5v-13A1.5 1.5 0 0 1 5.5 4H9" />
    <path d="M16 16.5 21 12l-5-4.5" /><path d="M21 12H9" /></svg>
);
export const IconActivity = (p) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="9" />
    <path d="M12 7.5v5l3.2 1.9" /></svg>
);
export const IconChevronDown = (p) => (
  <svg {...base} {...p}><path d="m6 9 6 6 6-6" /></svg>
);
export const IconSearch = (p) => (
  <svg {...base} {...p}><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>
);
export const IconFilter = (p) => (
  <svg {...base} {...p}><path d="M4 5h16l-6 7.5V19l-4 2v-8.5Z" /></svg>
);
export const IconPlus = (p) => (
  <svg {...base} {...p}><path d="M12 5v14M5 12h14" /></svg>
);
export const IconUpload = (p) => (
  <svg {...base} {...p}><path d="M12 15V4M8 8l4-4 4 4" /><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15" /></svg>
);
export const IconDownload = (p) => (
  <svg {...base} {...p}><path d="M12 4v11M8 11l4 4 4-4" /><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15" /></svg>
);
export const IconEye = (p) => (
  <svg {...base} {...p}><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="3" /></svg>
);
export const IconEdit = (p) => (
  <svg {...base} {...p}><path d="M12.5 5.5 18.5 11.5 8 22H2v-6Z" /><path d="M15.5 2.5 21.5 8.5" /></svg>
);
export const IconTrash = (p) => (
  <svg {...base} {...p}><path d="M4 7h16" /><path d="M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7" />
    <path d="M6 7l1 12.5A1.5 1.5 0 0 0 8.5 21h7a1.5 1.5 0 0 0 1.5-1.5L18 7" /><path d="M10 11v6M14 11v6" /></svg>
);
export const IconCheck = (p) => (
  <svg {...base} {...p}><path d="M4 12.5 9.5 18 20 6" /></svg>
);
export const IconClose = (p) => (
  <svg {...base} {...p}><path d="M5 5l14 14M19 5 5 19" /></svg>
);
export const IconInfo = (p) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5" />
    <circle cx="12" cy="7.8" r="1.1" fill="currentColor" stroke="none" /></svg>
);
export const IconCopy = (p) => (
  <svg {...base} {...p}><rect x="8.5" y="8.5" width="12" height="12" rx="2" />
    <path d="M15.5 8.5V5.5A2 2 0 0 0 13.5 3.5H5.5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3" /></svg>
);
export const IconList = (p) => (
  <svg {...base} {...p}><path d="M9 6h11M9 12h11M9 18h11" /><circle cx="4.5" cy="6" r="1.2" fill="currentColor" stroke="none" />
    <circle cx="4.5" cy="12" r="1.2" fill="currentColor" stroke="none" /><circle cx="4.5" cy="18" r="1.2" fill="currentColor" stroke="none" /></svg>
);
export const IconSync = (p) => (
  <svg {...base} {...p}><path d="M3.5 12a8.5 8.5 0 0 1 14.6-5.9L20.5 8.5" /><path d="M20.5 4.5v4h-4" />
    <path d="M20.5 12a8.5 8.5 0 0 1-14.6 5.9L3.5 15.5" /><path d="M3.5 19.5v-4h4" /></svg>
);
export const IconShield = (p) => (
  <svg {...base} {...p}><path d="M12 3l7.5 3v5.5c0 4.4-3 8.2-7.5 9.5-4.5-1.3-7.5-5.1-7.5-9.5V6L12 3Z" />
    <path d="M9 12.2l2.2 2.2L15.2 10" /></svg>
);
export const IconKey = (p) => (
  <svg {...base} {...p}><circle cx="8" cy="8" r="4.5" /><path d="M11.4 11.4 20 20" />
    <path d="M17 17l2-2M14.5 14.5l2-2" /></svg>
);
export const IconCamera = (p) => (
  <svg {...base} {...p}><path d="M4 8.5A1.5 1.5 0 0 1 5.5 7H8l1.2-1.8a1.5 1.5 0 0 1 1.25-.7h3.1a1.5 1.5 0 0 1 1.25.7L15.9 7h2.6A1.5 1.5 0 0 1 20 8.5v9A1.5 1.5 0 0 1 18.5 19h-13A1.5 1.5 0 0 1 4 17.5v-9Z" />
    <circle cx="12" cy="13" r="3.3" /></svg>
);
export const IconImage = (p) => (
  <svg {...base} {...p}><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
    <circle cx="8.5" cy="9.5" r="1.6" /><path d="M4 17l4.5-4.5 3.5 3.5 3-3L20 16.5" /></svg>
);
