import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, ApiError, type Session } from "./lib/api";
import { SESSION_KEY } from "./lib/session";
import { AuthPage } from "./pages/AuthPage";
import { CatalogPage } from "./pages/CatalogPage";
import { SavesPage } from "./pages/SavesPage";
import { PlayPage } from "./pages/PlayPage";
import { CreditsPage } from "./pages/CreditsPage";
import { UploadPage } from "./pages/UploadPage";
import { PlayerMemoryPage } from "./pages/PlayerMemoryPage";
import { Shell } from "./components/Shell";
import { Loading, Notice } from "./components/Feedback";

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname]);
  return null;
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [authError, setAuthError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    try { sessionStorage.removeItem(SESSION_KEY); } catch { /* old storage may be blocked */ }
    let active = true;
    const expired = () => { if (active) setSession(null); };
    window.addEventListener("story:session-expired", expired);
    setChecking(true);
    api.currentSession()
      .then((value) => { if (active) setSession(value); })
      .catch((cause) => {
        if (!active) return;
        if (cause instanceof ApiError && cause.status === 401) setSession(null);
        else setAuthError("无法确认登录状态，请检查网络后重试。");
      })
      .finally(() => { if (active) setChecking(false); });
    return () => {
      active = false;
      window.removeEventListener("story:session-expired", expired);
    };
  }, [retry]);

  if (checking) return <Loading label="正在恢复登录状态…" />;
  if (authError) return <Notice message={authError} onRetry={() => {
    setAuthError("");
    setRetry((value) => value + 1);
  }} />;
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route
          path="/login"
          element={
            session ? (
              <Navigate to="/" replace />
            ) : (
              <AuthPage onSession={setSession} />
            )
          }
        />
        <Route
          path="/*"
          element={
            session ? (
              <Shell session={session} onLogout={() => setSession(null)}>
                <Routes>
                  <Route
                    path="/"
                    element={<CatalogPage />}
                  />
                  <Route
                    path="/saves"
                    element={<SavesPage />}
                  />
                  <Route
                    path="/play/:gameId"
                    element={<PlayPage />}
                  />
                  <Route path="/credits" element={<CreditsPage />} />
                  <Route path="/my-scenarios" element={<UploadPage />} />
                  <Route path="/memory" element={<PlayerMemoryPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Shell>
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
      </Routes>
    </>
  );
}
