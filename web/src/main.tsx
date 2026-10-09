import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles/base.css";
import "./styles/catalog.css";
import "./styles/feedback.css";
import "./styles/saves.css";
import "./styles/auth.css";
import "./styles/reader.css";
import "./styles/credits.css";
import "./styles/upload.css";
import "./styles/player-memory.css";
import "./styles/manage.css";
import "./styles/responsive.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
);
