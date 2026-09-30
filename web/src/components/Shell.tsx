import { useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { BookOpen, Compass, LogOut, Menu, UserRound, X } from "lucide-react";
import { api, type Session } from "../lib/api";
import { Brand } from "./Brand";

export function Shell({
  children,
  session,
  onLogout,
}: {
  children: ReactNode;
  session: Session;
  onLogout: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  async function logout() {
    try {
      await api.logout(session.token);
    } catch {
      /* clear the local session even when offline */
    }
    onLogout();
    navigate("/login", { replace: true });
  }
  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="header-inner">
          <Brand />
          <nav
            className={menuOpen ? "main-nav open" : "main-nav"}
            aria-label="主导航"
          >
            <NavLink to="/" end onClick={() => setMenuOpen(false)}>
              <Compass size={17} />
              探索故事
            </NavLink>
            <NavLink to="/saves" onClick={() => setMenuOpen(false)}>
              <BookOpen size={17} />
              我的存档
            </NavLink>
            <button type="button" className="mobile-logout" onClick={logout}>
              <LogOut size={17} />
              退出登录
            </button>
          </nav>
          <div className="header-actions">
            <span className="user-avatar" title="已登录玩家">
              <UserRound size={17} />
            </span>
            <button
              type="button"
              className="icon-action logout"
              onClick={logout}
              aria-label="退出登录"
              title="退出登录"
            >
              <LogOut size={18} />
            </button>
            <button
              type="button"
              className="icon-action mobile-menu"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label={menuOpen ? "关闭菜单" : "打开菜单"}
            >
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </header>
      {children}
      <footer className="site-footer">
        <span>storyloop. 让故事继续生长。</span>
        <span>选择属于你的下一页</span>
      </footer>
    </div>
  );
}
