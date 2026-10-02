import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { type Session } from "./lib/api";
import { readSession, SESSION_KEY } from "./lib/session";
import { AuthPage } from "./pages/AuthPage";
import { CatalogPage } from "./pages/CatalogPage";
import { SavesPage } from "./pages/SavesPage";
import { PlayPage } from "./pages/PlayPage";
import { CreditsPage } from "./pages/CreditsPage";
import { UploadPage } from "./pages/UploadPage";
import { Shell } from "./components/Shell";

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [pathname]);
  return null;
}

export default function App() {
  const [session, setSession] = useState<Session | null>(readSession);
  function updateSession(next: Session | null) {
    if (next) sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
    else sessionStorage.removeItem(SESSION_KEY);
    setSession(next);
  }
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
              <AuthPage onSession={(value) => updateSession(value)} />
            )
          }
        />
        <Route
          path="/*"
          element={
            session ? (
              <Shell session={session} onLogout={() => updateSession(null)}>
                <Routes>
                  <Route
                    path="/"
                    element={<CatalogPage token={session.token} />}
                  />
                  <Route
                    path="/saves"
                    element={<SavesPage token={session.token} />}
                  />
                  <Route
                    path="/play/:gameId"
                    element={<PlayPage token={session.token} />}
                  />
                  <Route path="/credits" element={<CreditsPage token={session.token} />} />
                  <Route path="/my-scenarios" element={<UploadPage token={session.token} />} />
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
