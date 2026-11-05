import { createRoot } from "react-dom/client";
import { LiveTestApp } from "./live-test-app.js";
import "../shared/styles.css";

createRoot(document.getElementById("root")!).render(<LiveTestApp />);
