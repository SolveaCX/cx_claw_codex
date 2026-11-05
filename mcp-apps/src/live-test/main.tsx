import { createRoot } from "react-dom/client";
import { LiveTestApp } from "./live-test-app.js";
import "../shared/styles.css";
import "./live-test.css";

createRoot(document.getElementById("root")!).render(<LiveTestApp />);
