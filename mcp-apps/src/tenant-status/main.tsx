import { createRoot } from "react-dom/client";
import { TenantStatusApp } from "./tenant-status-app.js";
import "../shared/styles.css";

createRoot(document.getElementById("root")!).render(<TenantStatusApp />);
