# Desktop dependency patches

These copies preserve the upstream versions and license notices. Scanners that
match only the name and version may still report the advisories.

- **glib 0.18.5** is required by Tauri's GTK 3 stack on Linux. Cargo uses the
  [crates.io source](https://crates.io/crates/glib/0.18.5) with the
  [Debian backport](https://sources.debian.org/patches/rust-glib-0.18/0.18.5-7/)
  of [RUSTSEC-2024-0429](https://rustsec.org/advisories/RUSTSEC-2024-0429.html).
  The original archive's SHA-256 is
  `233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5`.
  Remove the Cargo patch once Tauri can resolve a registry version with the
  upstream fix. The Linux desktop tests exercise the string iterator in an
  optimized build.
- **deepmerge 4.3.1** is used by the Svelte Vite plugin at build time. The local
  package contains its published CommonJS entry point, types, and license. It
  rejects the `__proto__` key when copying either input, following the approach
  in the [proposed upstream fix](https://github.com/TehShrike/deepmerge/pull/274)
  for [CVE-2026-93753](https://github.com/advisories/GHSA-gcqx-w48m-w2h4).
  The original archive's npm integrity is
  `sha512-3sUqbMEc77XqpdNO7FRyRog+eW3ph+GYCbj+rK+uYyRMuwsVy0rMiVtPn+QJlKFvWP/1PYpapqYn0Me2knFn+A==`.
  Remove the local dependency when the plugin resolves a fixed release or
  drops deepmerge. The frontend tests check the entry point used by the plugin.
