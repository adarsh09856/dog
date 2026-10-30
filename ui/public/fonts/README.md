# Bundled Geist fonts

These unmodified Latin variable WOFF2 assets were copied from the installed
Next.js 15.5.20 distribution (`next/dist/next-devtools/server/font/`). The root
layout uses `next/font/local`, so compiling the application does not fetch
fonts from Google. The existing sans/mono CSS variables and 100–900 weight
ranges are preserved.

Upstream: https://github.com/vercel/geist-font
License: SIL Open Font License 1.1; the copyright notice and complete license
are distributed alongside the fonts in `OFL.txt`.

SHA-256:

- `geist-latin.woff2`: `1b5ebfb3a01a97343ac96873e6d59a8cb285c66012b6a1ac509cb2765e995ba8`
- `geist-mono-latin.woff2`: `b7ac144b394cbd81052d6397ec0c33397977b1d7e9bc095e744e652a378c6fb3`

When updating these assets, preserve the font license and update the recorded
origin and hashes. Application source uses the checked-in copies and does not
depend on Next.js's internal asset paths at build time.
