import { fileURLToPath } from "node:url"
import { defineConfig, mergeConfig } from "vite"
import desktopConfig from "./vite.config.ts"

export default defineConfig(mergeConfig(desktopConfig, {
  root: fileURLToPath(new URL("./preview", import.meta.url)),
  publicDir: fileURLToPath(new URL("./public", import.meta.url)),
  base: "./",
  build: {
    outDir: "../preview-dist",
    emptyOutDir: true,
  },
  plugins: [{
    name: "preview-content-security-policy",
    transformIndexHtml() {
      return [{
        tag: "meta",
        attrs: {
          "http-equiv": "Content-Security-Policy",
          content: "default-src 'self'; connect-src 'none'; form-action 'none'; object-src 'none'; base-uri 'none'",
        },
        injectTo: "head-prepend",
      }]
    },
  }],
}))
