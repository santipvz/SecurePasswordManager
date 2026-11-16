import "@fontsource/inter/latin-400.css"
import "@fontsource/inter/latin-500.css"
import "@fontsource/inter/latin-600.css"
import "@fontsource/inter/latin-700.css"
import { isTauri } from "@tauri-apps/api/core"
import { mount } from "svelte"
import App from "./App.svelte"
import VaultSession from "./VaultSession.svelte"
import "./styles.css"

mount(isTauri() ? VaultSession : App, { target: document.getElementById("app")! })
