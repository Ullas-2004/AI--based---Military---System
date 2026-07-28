"use client";
/**
 * Application chrome: sidebar + navbar + main region.
 *
 * The sidebar is a fixed rail from `lg` upwards and an off-canvas drawer below
 * it. Previously it was an unconditional `w-64`, which consumed 256px of a
 * 375px phone viewport and left the content unusable.
 */
import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import AlertFeed from "./AlertFeed";
import Navbar from "./Navbar";
import Sidebar from "./Sidebar";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [isDrawerOpen, setDrawerOpen] = useState(false);
  const pathname = usePathname();
  const [lastPathname, setLastPathname] = useState(pathname);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  // Navigating on mobile dismisses the drawer. Adjusting state during render is
  // React's sanctioned pattern for deriving from a prop change; an effect here
  // would render the stale open drawer for one frame first.
  if (pathname !== lastPathname) {
    setLastPathname(pathname);
    setDrawerOpen(false);
  }

  // Escape closes the drawer, and body scroll is locked while it is open.
  useEffect(() => {
    if (!isDrawerOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeDrawer();
    };
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [isDrawerOpen, closeDrawer]);

  return (
    <div className="relative z-10 flex min-h-screen">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      <Sidebar isOpen={isDrawerOpen} onClose={closeDrawer} />

      <div className="flex flex-1 flex-col min-w-0 lg:pl-64">
        <Navbar onMenuClick={() => setDrawerOpen(true)} />
        <main
          id="main-content"
          className="flex-1 p-4 sm:p-6 max-w-[1600px] w-full mx-auto"
        >
          {children}
        </main>
      </div>

      {/* Live alerts float above every page. */}
      <AlertFeed />
    </div>
  );
}
