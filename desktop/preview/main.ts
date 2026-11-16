/// <reference types="vite/client" />

import "@fontsource/inter/latin-400.css"
import "@fontsource/inter/latin-500.css"
import "@fontsource/inter/latin-600.css"
import "@fontsource/inter/latin-700.css"
import { mount } from "svelte"
import VaultSession from "../src/VaultSession.svelte"
import "../src/styles.css"
import "./style.css"
import { createPreviewVault } from "./vault"

if ("isTauri" in window || "__TAURI_INTERNALS__" in window) {
  throw new Error("The interface preview runs in a browser.")
}

// This entry point isn't referenced by the application bundle. The fixture
// receives the same commands as the view and keeps demo data in memory.
Object.defineProperty(window, "__TAURI_INTERNALS__", {
  value: { invoke: createPreviewVault(new URL(window.location.href).searchParams.get("scenario")) },
})

mount(VaultSession, { target: document.getElementById("app")! })
