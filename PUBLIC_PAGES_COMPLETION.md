# Public pages and shared branding

Priority requested: finish these pages before returning to commercial installation controls.

## Implemented

- Rebuilt the home page with a shared header/footer, responsive navigation, platform overview, deployment choices and a clearly labeled illustrative conversation.
- Removed unsupported awards, transport timing, free-minute promises and specific unverified model-version claims from the home page.
- Rebuilt pricing around configured live offers. Exact stored currency and minor-unit prices drive the displayed amount. Annual pricing appears only when configured; there is no invented discount or exchange rate in the public page.
- Public and authenticated credit catalog reads no longer create sample commercial offers. Plan features come from the stored grants.
- Added loading, empty, failed-request and retry states to pricing, plus accessible FAQ controls.
- Connected hosted and client branding to the same public-safe schema. Admin settings now include name, logo, tagline, support email, primary color, font and browser icon.
- Connected public chrome, sign-in shell, workspace identity and admin identity to shared branding. Brand saves refresh the same tab and other open tabs; other sessions check periodically.
- Added server-rendered brand identity and metadata to avoid initially showing the default name before browser code runs.
- Public routes render immediately without waiting for the private authentication bootstrap. Pricing loads plans and credit bundles independently and bounds each public request to five seconds.
- Credit bundle links now retain the configured package ID through local login/signup, and the billing wallet renders the exact catalog price, currency, base minutes and bonus minutes before checkout. Razorpay order creation and signature verification carry that package ID; Stripe uses the existing metadata-bound checkout/verification route. Checkout remains behind a purchase confirmation. Live payment credentials and gateway settlement still require acceptance.

## Evidence so far

- Pricing follow-through fix on 26 October 2026: annual-only plans display their configured annual amount and 365-day term instead of a zero monthly price; missing currency is labeled “Price unavailable,” not “Free.” The selected plan/cycle survives local sign-in and signup and is applied only when it matches the loaded account plan catalog. Focused pricing, billing, and redirect tests pass (8 tests); affected-file ESLint and `tsc --noEmit` pass. Payment checkout and deployed catalog behavior still need acceptance.

- Theme audit on 26 October 2026 found the assistant chat bubble used a fixed light-slate border. It now uses the shared `border-border` token; both `MessageBubble` component regressions pass, and targeted ESLint plus `tsc --noEmit` passed. The real workflow editor still needs light/dark browser acceptance.
- On 26 October 2026, a fresh local preview exposed repeated Google font fetch timeouts during compilation. The root layout now uses bundled Geist sans/mono WOFF2 assets through `next/font/local`, with upstream license and provenance included. After reload, the rendered CSS uses the local font family. The in-app browser checked the home page at 1280 and 390 pixels without horizontal overflow, toggled dark/light theme and opened the phone navigation. Screenshots are saved under `artifacts/public-pages/home-local-fonts-*`. This is local visual evidence; real backend branding, catalog and audio acceptance remain open.
- Continued the shared theme rollout beyond public pages: workflow editor header, validation popover, version history and version comparison now use theme tokens instead of hard-coded dark surfaces; the sticky-tabs shell follows the selected theme. Targeted ESLint and TypeScript checks passed. This does not complete the remaining workspace screens or visual review.
- Workflow and template cards, the daily usage table, and React Flow canvas controls now use shared card/muted/border tokens instead of fixed white backgrounds. Targeted ESLint and TypeScript checks pass for the affected files; remaining screens and actual light/dark browser review are still required.
- Added theme-surface regression checks for workflow version history and comparison; the two focused test files pass all 6 tests. Targeted ESLint and a fresh TypeScript check also pass.
- Core workflow creation and editing surfaces (cards, version controls, comparison, usage table and canvas controls) now follow the selected theme. Remaining fixed white styles are limited to deliberate high-contrast auth, switch and onboarding elements; full panel-by-panel visual acceptance remains open.
- Continued the theme-token sweep: workflow upload dropzone borders, icons and helper copy; Stack sign-in loading indicators; and filter auto-refresh indicators now use shared border and muted foreground tokens. Browser visual verification remains open.
- Branding audit found the onboarding tour tooltip still used fixed blue surfaces, so its panel, arrow, close action and next action now use the admin-selected primary and foreground tokens. Its focused Vitest regression, targeted ESLint and `tsc --noEmit` pass; live theme/browser acceptance remains open.
- The public auth-handler fallback had a fixed light-gray heading on a theme-aware card; it now uses the semantic foreground token. Targeted ESLint and `tsc --noEmit` pass; browser contrast acceptance remains open.
- Workflow creation and template selection now render the neutral/slate category from `muted` and `border` theme tokens, and disabled-node status uses `muted-foreground` instead of fixed gray. Targeted ESLint and `tsc --noEmit` passed; workflow-editor light/dark browser acceptance is still open.

- Public pricing and shared branding browser-component tests passed.
- Focused public pricing and branding API tests passed.
- Final TypeScript and targeted UI lint checks passed.
- The production build completed successfully after the public redesign and shared-brand changes.
- On 26 October 2026, started the optimized standalone production server and fetched `/`, `/pricing`, `/auth/login`, and `/auth/signup`; each returned HTTP 200 with the Kodewaves document title/brand. Pricing SSR did not contain the retired fixed “High Performance Voice AI” pricing headline. This used default local branding because no local backend/catalog was connected; real admin-saved brand and configured offers remain unverified. Work settings disable browser automation, so this check did not inspect rendered pixels or interactions.
- Branding hydration audit on 26 October 2026 found that name/title were server-rendered but color and font waited for the client effect. The palette calculation is now shared by the root server layout and client refresh: dark-theme brand variables and system font are emitted in the initial HTML, and the pre-hydration theme script applies the light palette when light mode is saved. The standalone production build passed; SSR returned HTTP 200 and included the initial `--primary` style plus the light-theme palette. Branding palette/context tests (3), ESLint, and TypeScript passed. A connected database with non-default saved branding and pixel-level browser automation remain unverified.
- The focused API suite passed 23 tests for pricing, branding validation, edition-specific storage and load failures.
- The focused browser-component suite passed both pricing and shared-brand refresh regressions.
- Headless Chrome covered home, pricing, sign-in and sign-up at 1440, 390 and 320 pixels in both themes: 24 page renders with no horizontal overflow or browser runtime errors. It also checked the mobile menu and illustrative conversation control.
- Configured-price and custom-brand browser checks passed at 320, 390 and 1440 pixels, including annual price, font, brand refresh and no overflow or runtime errors.
- The current browser-component suite passes 10 tests, including independent plan loading while credits are pending.
- The latest client-flagged UI build completed with all 50 pages generated; TypeScript, targeted lint and `git diff --check` completed without errors. This host build did not run Dockerfile source filtering, so owner routes remain in its manifest and the distributable client image still needs verification.
- Recheck on 25 October 2026: 26 focused branding, pricing, edition, entitlement and auth UI tests passed; `tsc --noEmit` and targeted ESLint passed. A later isolated production-build retry was stopped before completion after the Node process consumed nearly all available system memory. The existing local UI server remained healthy (HTTP 200); use a memory-appropriate CI or Docker runner for the next build attempt.

## Acceptance still required

- Verify the brand save through the real admin screen and confirm public, workspace and admin identity update.
- Confirm public pricing against the configured catalog after integration and deployment.
- Deploy this isolated branch only after reconciling it with the voice-flow branch and verify the same pages on the live domain.
- Detailed tool and telephony explanatory copy now uses general platform wording; technical API identifiers keep their existing names for compatibility.

## Live deployment comparison — 26 October 2026

A read-only in-app browser check of `https://app.kodewaves.in/pricing` still shows the older public pricing implementation: “High Performance Voice AI. Fraction of the Cloud Cost,” fixed ROI savings, and fixed self-hosted hardware/model claims. The current isolated branch instead renders configured plan and credit offers, shows one-time 30/365-day terms, and avoids inventing ROI or infrastructure capacity. This proves the public-page work in this branch is not live on the production domain. Do not mark public-page completion as accepted until the voice-flow integration is reconciled and the reviewed public changes are deployed; then compare the live catalog, currency and terms against the owner-configured values.

This file tracks this isolated worktree. The public changes are not deployed to the production voice installation yet.


### 26 October 2026 - mobile admin and saved-brand refresh

- Browser evidence: the local production UI returned HTTP 200 with no page exceptions at 1280, 390 and 320 pixels. The admin dashboard uses the full mobile viewport without horizontal overflow; the drawer opens and closes from its backdrop. Fresh screenshots: local temp files kodewaves-client-admin-1280.png, kodewaves-client-admin-390.png and kodewaves-client-admin-320.png. The browser used controlled owner-auth and unavailable-backend fixtures, so this does not prove live authorization or database behavior.
- Brand-save browser evidence: one PUT from the real settings form updated five already-open pages (home, pricing, login, workspace and admin settings), including name, logo, browser title/icon, primary color and system font. Home tagline updated; a reload retained the fixture's saved values. Settings had no horizontal overflow at 390 or 320 pixels. There were no page exceptions. This used an in-memory HTTP service fixture, not the production API or database.
- Found a real refresh-order bug: an older branding read could complete after a successful save and restore the previous name/theme. The new deferred-request regression failed with Admin | Kodewaves instead of Admin | Saved Brand. The provider now applies only its latest refresh. The focused branding/admin suite passed 6/6; TypeScript, affected-file ESLint and git diff --check passed. The browser results above used the preceding production build; the refresh-order correction is covered by the regression test.
- Browser tooling correction: bundled Node Playwright is available through the workspace dependency runtime. Local headless UI acceptance is possible; in-app browser control remains disabled. This supersedes earlier claims that all browser testing was unavailable.
- Voice integration remains open: an immediate snapshot confirmed the other chat is active, narrowing advertised STT languages to installed reply voices and refreshing its own STT/API/model UI. No completion handoff or integration was received.

- Live deployment recheck on 26 October 2026 confirms the production pricing route still shows the older fixed ROI/price claims while the isolated worktree has removed them. This confirms that reviewed public-page changes still need branch reconciliation and deployment before production acceptance. The check was read-only; no live settings or content were changed.


- Public pricing now excludes active owner-only plans from the website and both free and paid self-service checkout. Owners can keep an active plan private while assigning it directly. Existing plans migrate as public by default; visibility is persisted for future edits. UI verification passed; backend regression tests and applying the new migration to PostgreSQL are still pending.
