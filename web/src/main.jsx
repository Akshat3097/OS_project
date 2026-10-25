import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// fonts are bundled into the page, so they work offline
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
// the archival "paper" look for theory text: display serif, book serif, typewriter mono
import "@fontsource/instrument-serif/400.css";
import "@fontsource/instrument-serif/400-italic.css";
import "@fontsource-variable/newsreader";
import "@fontsource-variable/newsreader/wght-italic.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
// chalk handwriting for the blackboard in "Explain it back"
import "@fontsource/kalam/latin-400.css";
import "@fontsource/kalam/latin-700.css";
import "./styles.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
