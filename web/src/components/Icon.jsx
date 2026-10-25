// Thin-line icons (24 × 24, 1.8 stroke), drawn inline so the page needs nothing from the internet.
const PATHS = {
  home: <path d="M3.5 10.2 12 3.5l8.5 6.7V19a1.5 1.5 0 0 1-1.5 1.5h-4.2v-5.7H9.2v5.7H5A1.5 1.5 0 0 1 3.5 19z" />,
  chat: <path d="M20.5 11.5a8 8 0 0 1-11.7 7.1L3.5 20l1.4-4.9A8 8 0 1 1 20.5 11.5z" />,
  learn: <path d="M2.5 5.5C5 4 8.5 4 12 6c3.5-2 7-2 9.5-.5v13.2c-2.5-1.5-6-1.5-9.5.5-3.5-2-7-2-9.5-.5zM12 6v13.2" />,
  labs: <path d="M9 3h6M10 3v6.3L4.3 18.6A1.6 1.6 0 0 0 5.7 21h12.6a1.6 1.6 0 0 0 1.4-2.4L14 9.3V3M7.2 15h9.6" />,
  exam: <path d="M7 3h7l5 5v11.5a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 6 19.5v-15A1.5 1.5 0 0 1 7.5 3zM14 3v5h5M9 13h6M9 17h4" />,
  progress: <path d="M4 20V11M10 20V5M16 20v-6M2.5 20.5h19" />,
  notes: <path d="M5 3.5h14A1.5 1.5 0 0 1 20.5 5v9.5l-6 6H5A1.5 1.5 0 0 1 3.5 19V5A1.5 1.5 0 0 1 5 3.5zM14.5 20.5v-4.5a1.5 1.5 0 0 1 1.5-1.5h4.5" />,
  chevron: <path d="m6 9 6 6 6-6" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" /></>,
  moon: <path d="M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.7 6.7 0 0 0 9.7 9.7z" />,
  monitor: <path d="M3.5 4.5h17v11h-17zM8.5 20h7M12 15.5V20" />,
  target: <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><circle cx="12" cy="12" r="0.8" /></>,
  check: <><circle cx="12" cy="12" r="8.5" /><path d="m8.5 12.2 2.4 2.4 4.6-4.9" /></>,
  mic: <path d="M12 3.5a3 3 0 0 0-3 3v5.5a3 3 0 0 0 6 0V6.5a3 3 0 0 0-3-3zM6 11.5a6 6 0 0 0 12 0M12 17.5v3" />,
  paste: <path d="M9 4.5h6M9 3h6v3H9zM7 4.5H5.5A1.5 1.5 0 0 0 4 6v13.5A1.5 1.5 0 0 0 5.5 21h13a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H17M8 12h8M8 16h5" />,
  quiz: <><circle cx="12" cy="12" r="8.5" /><path d="M9.6 9.4a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.7M12 17h.01" /></>,
  info: <><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 8h.01" /></>,
  play: <path d="M8 5.5v13l10-6.5z" />,
  pin: <path d="M9 3.5h6l-1 5.5 3.5 3.5v1.5h-11V12.5L10 9zM12 14v6.5" />,
  edit: <path d="M4 20h4L19.3 8.7a2 2 0 0 0 0-2.8l-1.2-1.2a2 2 0 0 0-2.8 0L4 16zM13.5 6.5l4 4" />,
  trash: <path d="M4 7h16M10 11v6M14 11v6M5.5 7l1 12.5A1.5 1.5 0 0 0 8 21h8a1.5 1.5 0 0 0 1.5-1.5L18.5 7M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7" />,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20.5 20.5-4.5-4.5" /></>,
  bookmark: <path d="M6.5 3.5h11A1.5 1.5 0 0 1 19 5v15.5l-7-4.5-7 4.5V5a1.5 1.5 0 0 1 1.5-1.5z" />,
};

export default function Icon({ name, size = 22 }) {
  return (
    <svg className="ico" viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" fill="none"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {PATHS[name]}
    </svg>
  );
}
