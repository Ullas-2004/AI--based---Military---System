"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home, Crosshair, ShieldAlert, Brain, Map, Database, Bot, Lock, Settings, X,
} from "lucide-react";

import { useAuth } from "@/lib/auth-context";

/** Navigation targets. Every href below resolves to a real route. */
const NAV_ITEMS = [
  { name: "Dashboard", href: "/dashboard", icon: Home },
  { name: "Vision Engine", href: "/detection", icon: Crosshair },
  { name: "Threat Intelligence", href: "/history", icon: ShieldAlert },
  { name: "Predictive Intel", href: "/predictive", icon: Brain },
  { name: "GIS Maps", href: "/maps", icon: Map },
  { name: "Data Hub", href: "/data", icon: Database },
  { name: "AI Assistant", href: "/assistant", icon: Bot },
  { name: "Security", href: "/security", icon: Lock },
  { name: "Settings", href: "/settings", icon: Settings },
] as const;

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { user } = useAuth();

  return (
    <>
      {/* Scrim, mobile only. */}
      <div
        className={`fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden transition-opacity duration-200 ${
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        id="primary-navigation"
        aria-label="Primary"
        className={`fixed inset-y-0 left-0 z-40 w-64 glass-panel border-r border-white/10 flex flex-col
          transition-transform duration-300 ease-out lg:translate-x-0
          ${isOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="p-6 flex items-center justify-between gap-3">
          <Link href="/" className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 shrink-0 rounded-xl bg-gradient-to-br from-aegis-accent to-aegis-accent-secondary flex items-center justify-center shadow-[0_0_20px_rgba(0,229,255,0.35)]">
              <ShieldAlert className="w-6 h-6 text-aegis-bg" aria-hidden="true" />
            </div>
            <span className="text-2xl font-bold tracking-wider text-gradient truncate">
              AegisAI
            </span>
          </Link>
          <button
            onClick={onClose}
            className="lg:hidden p-2 -mr-2 text-gray-400 hover:text-white transition-colors"
            aria-label="Close navigation"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        <nav className="flex-1 mt-2 px-4 space-y-1 overflow-y-auto pb-4">
          {NAV_ITEMS.map(({ name, href, icon: Icon }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                aria-current={isActive ? "page" : undefined}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-colors duration-200 ${
                  isActive
                    ? "bg-gradient-to-r from-aegis-accent/20 to-transparent border-l-4 border-aegis-accent text-white"
                    : "text-gray-400 hover:text-white hover:bg-white/5 border-l-4 border-transparent"
                }`}
              >
                <Icon
                  className={`w-5 h-5 shrink-0 ${isActive ? "text-aegis-accent" : ""}`}
                  aria-hidden="true"
                />
                <span className="font-medium truncate">{name}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-5 border-t border-white/10">
          {user ? (
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 shrink-0 rounded-full bg-gradient-to-br from-aegis-accent to-aegis-accent-secondary flex items-center justify-center font-bold text-aegis-bg">
                {(user.username ?? "?").charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-white truncate">
                  {user.username ?? "Analyst"}
                </p>
                <p className="text-xs text-aegis-accent capitalize">{user.role}</p>
              </div>
            </div>
          ) : (
            <Link
              href="/security"
              className="block text-center text-sm font-medium text-aegis-accent hover:text-white transition-colors"
            >
              Not signed in - authenticate
            </Link>
          )}
        </div>
      </aside>
    </>
  );
}
