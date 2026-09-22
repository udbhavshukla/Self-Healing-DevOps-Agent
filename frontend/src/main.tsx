import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./auth";
import "./styles/app.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Missing #root element");
}
createRoot(root).render(
  <AuthProvider>
    <App />
  </AuthProvider>
);
