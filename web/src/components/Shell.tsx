import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { BookOpen, Coins, Compass, FileUp, LogOut, Menu, ShieldCheck, UserRound, X } from "lucide-react";
import { api, ApiError, type CreditWallet, type Session } from "../lib/api";
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
  const [wallet, setWallet] = useState<CreditWallet | null>(null);
  const [logoutError, setLogoutError] = useState("");
  const navigate = useNavigate();
  useEffect(() => {
    let active = true;
    const refresh = () => {
      void api.wallet().then((value) => {
        if (active) setWallet(value);
      }).catch(() => {
        if (active) setWallet(null);
      });
    };
    refresh();
    window.addEventListener("story:billing-updated", refresh);
    return () => {
      active = false;
      window.removeEventListener("story:billing-updated", refresh);
    };
  }, [session.player_id]);
  async function logout() {
    setLogoutError("");
    try {
      await api.logout();
    } catch (cause) {
      if (!(cause instanceof ApiError && cause.status === 401)) {
        setLogoutError("退出未完成，请检查网络后重试。");
        return;
      }
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
            <NavLink to="/my-scenarios" onClick={() => setMenuOpen(false)}>
              <FileUp size={17} />
              我的剧本
            </NavLink>
            <NavLink to="/credits" onClick={() => setMenuOpen(false)}>
              <Coins size={17} />
              积分明细
            </NavLink>
            {session.capabilities?.includes("review.submissions") && <NavLink to="/manage" onClick={() => setMenuOpen(false)}>
              <ShieldCheck size={17} />
              管理工作台
            </NavLink>}
            <button type="button" className="mobile-logout" onClick={logout}>
              <LogOut size={17} />
              退出登录
            </button>
          </nav>
          <div className="header-actions">
            <NavLink to="/credits" className="credit-balance" title="查看积分明细">
              <Coins size={16} />
              <span>{wallet ? `${wallet.balance_points} 积分` : "积分"}</span>
            </NavLink>
            <NavLink to="/memory" className="user-avatar" aria-label="玩家画像" title="玩家画像">
              <UserRound size={17} />
            </NavLink>
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
      {logoutError && <p className="form-error" role="alert">{logoutError}</p>}
      {children}
      <footer className="site-footer">
        <span>storyloop. 让故事继续生长。</span>
        <span>选择属于你的下一页</span>
      </footer>
    </div>
  );
}
