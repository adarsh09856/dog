"use client";

import { ArrowRight, Menu, Moon, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { useClientBranding } from "@/context/ClientBrandingContext";

import styles from "./PublicSiteChrome.module.css";

const links = [
  { href: "/platform", label: "Platform" },
  { href: "/#scenarios", label: "Use cases" },
  { href: "/deployment", label: "Deployment" },
  { href: "/pricing", label: "Pricing" },
];

export function PublicHeader() {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  const isClientEdition = process.env.NEXT_PUBLIC_KODEWAVES_EDITION === "client";
  const visibleLinks = isClientEdition
    ? links.filter((link) => link.href !== "/pricing")
    : links;
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => setMounted(true), []);
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      menuButtonRef.current?.focus();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  return (
    <header className={`${styles.header} public-header sticky top-0 z-50`}>
      <a
        href="#main-content"
        className="sr-only rounded-lg bg-background px-4 py-3 focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50"
      >
        Skip to content
      </a>
      <div className={`${styles.headerInner} mx-auto flex h-[76px] max-w-[1480px] items-center justify-between gap-4 px-5 sm:px-8 lg:px-10`}>
        <Link href="/" aria-label="Home" className={`${styles.brand} min-w-0 max-w-[55%] sm:max-w-none`}>
          <BrandLogo className="h-8" />
        </Link>
        <nav
          aria-label="Main navigation"
          className={`${styles.nav} hidden items-center gap-8 text-sm lg:flex`}
        >
          {visibleLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href ? "page" : undefined}
              className={`${styles.navLink} text-muted-foreground transition-colors hover:text-foreground aria-[current=page]:text-foreground`}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            type="button"
            aria-label="Toggle color theme"
            onClick={() =>
              setTheme(resolvedTheme === "dark" ? "light" : "dark")
            }
            className={`${styles.themeButton} rounded-lg p-2.5 text-muted-foreground hover:bg-muted hover:text-foreground`}
          >
            {mounted && resolvedTheme === "dark" ? (
              <Sun className="size-4" />
            ) : (
              <Moon className="size-4" />
            )}
          </button>
          <Link
            href="/auth/login"
            className="hidden text-sm font-medium lg:inline-flex"
          >
            Sign in
          </Link>
          <Link
            href="/auth/login"
            className={`${styles.consoleLink} hidden items-center gap-2 rounded-lg bg-cta px-4 py-2.5 text-sm font-semibold text-cta-foreground hover:bg-cta/90 lg:inline-flex`}
          >
            Open console <ArrowRight className="size-4" />
          </Link>
          <button
            ref={menuButtonRef}
            type="button"
            aria-label={open ? "Close navigation" : "Open navigation"}
            aria-expanded={open}
            aria-controls="public-mobile-navigation"
            onClick={() => setOpen(!open)}
            className={`${styles.menuButton} rounded-lg p-2 lg:hidden`}
          >
            {open ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>
      {open && (
        <nav
          id="public-mobile-navigation"
          aria-label="Mobile navigation"
          className={`${styles.mobileMenu} space-y-1 border-t border-border px-5 py-4 lg:hidden`}
        >
          {visibleLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href ? "page" : undefined}
              onClick={() => setOpen(false)}
              className={`${styles.mobileLink} block rounded-lg px-3 py-3 text-sm hover:bg-muted`}
            >
              {link.label}
            </Link>
          ))}
          <Link
            href="/auth/login"
            onClick={() => setOpen(false)}
            className={`${styles.mobileWorkspaceLink} mt-3 flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold`}
          >
            Open workspace <ArrowRight aria-hidden className="size-4" />
          </Link>
        </nav>
      )}
    </header>
  );
}

export function PublicFooter() {
  const branding = useClientBranding();
  const isClientEdition = process.env.NEXT_PUBLIC_KODEWAVES_EDITION === "client";
  return (
    <footer className={`${styles.footer} border-t border-border`}>
      <div className="mx-auto grid max-w-7xl grid-cols-[minmax(0,1fr)] gap-8 px-5 py-12 sm:px-8 md:grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0 space-y-4">
          <Link href="/" aria-label="Home">
            <BrandLogo inverse className="h-7" />
          </Link>
          <p className="max-w-sm text-sm leading-6 text-muted-foreground">
            {branding.tagline}
          </p>
        </div>
        <nav
          aria-label="Footer navigation"
          className="flex flex-wrap content-start gap-x-7 gap-y-4 text-sm text-muted-foreground"
        >
          <Link href="/platform" className="hover:text-foreground">
            Platform
          </Link>
          <Link href="/#scenarios" className="hover:text-foreground">
            Use cases
          </Link>
          <Link href="/deployment" className="hover:text-foreground">
            Deployment
          </Link>
          {!isClientEdition && (
            <Link href="/pricing" className="hover:text-foreground">
              Pricing
            </Link>
          )}
          <Link href="/auth/login" className="hover:text-foreground">
            Sign in
          </Link>
          {branding.support_email && (
            <a
              href={`mailto:${branding.support_email}`}
              className="hover:text-foreground"
            >
              Contact support
            </a>
          )}
        </nav>
        <p className="text-xs text-muted-foreground md:col-span-2">
          © {new Date().getFullYear()} {branding.company_name}. Voice agents
          for your business.
        </p>
      </div>
    </footer>
  );
}
