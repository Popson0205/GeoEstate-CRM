import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth";

/** The CRM's frame: the GeoEstate logo, the sections down the side, and who is signed in. */
export default function Layout() {
  const { user, can, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const links: [string, string, boolean][] = [
    ["/", "Home", true], ["/clients", "Clients", true], ["/deals", "Deals", true], ["/tasks", "Tasks", true],
    ["/staff", "Staff", true], ["/log", "Activity log", can("audit.view")],
  ];
  return (
    <div className="app">
      <header className="top">
        <Link to="/" className="brand"><img src="/logo.png" alt="" /><span>GeoEstate <strong>CRM</strong></span></Link>
        <button type="button" className="menu-btn" aria-expanded={open} aria-controls="side" onClick={() => setOpen((v) => !v)}>Menu</button>
        <div className="who">
          <Link to="/security" className="who-name">{user?.name}<span>{user?.role_name}</span></Link>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void signOut()}>Sign out</button>
        </div>
      </header>
      <nav id="side" className={`side${open ? " is-open" : ""}`} aria-label="Sections" onClick={() => setOpen(false)}>
        {links.filter(([, , show]) => show).map(([to, label]) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "is-active" : undefined)}>{label}</NavLink>
        ))}
      </nav>
      <main className="main" id="main"><Outlet /></main>
    </div>
  );
}
