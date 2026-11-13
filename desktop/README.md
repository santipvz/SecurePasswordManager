# Desktop prototype

This Tauri and Svelte prototype uses fictional credentials. Its unlock and key interactions simulate the desktop flows. Use the Python application for real vaults until desktop integration lands.

Install Node.js 22.12 or later in the 22 series, a stable Rust toolchain, and the native packages listed in the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/). From this directory, run:

```sh
npm ci
npm run tauri dev
```

To review the frontend in a browser, run `npm run dev` and open `http://127.0.0.1:1420`. `npm run check` checks Svelte and TypeScript, and `npm run build` bundles the local frontend assets.
