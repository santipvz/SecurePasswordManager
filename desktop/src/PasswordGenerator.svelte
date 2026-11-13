<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import { RefreshCw } from "@lucide/svelte"
  import { onDestroy } from "svelte"

  let { generation, onUse }: {
    generation?: number
    onUse?: (password: string) => void
  } = $props()

  let length = $state<number | undefined>(24)
  let symbols = $state(true)
  let password = $state("")
  let busy = $state(false)
  let error = $state("")
  let output = $state<HTMLInputElement>()
  let expiry: ReturnType<typeof setTimeout> | undefined
  let revision = 0

  function clear() {
    revision++
    clearTimeout(expiry)
    password = ""
  }

  function reset() {
    clear()
    error = ""
  }

  async function generate() {
    if (busy) return
    reset()
    if (!Number.isInteger(length) || length === undefined || length < 12 || length > 256) {
      error = "Choose a length from 12 to 256 characters."
      return
    }
    const current = revision
    busy = true
    try {
      const result = await invoke<string>("vault_generate", { generation, length, symbols })
      if (current !== revision || document.hidden) return
      if (generation !== undefined && !await invoke<boolean>("vault_active", { generation })) return
      if (current !== revision || document.hidden) return
      password = result
      expiry = setTimeout(clear, 30_000)
    } catch (reason) {
      if (current === revision) {
        error = reason === "generator_length"
          ? "Choose a length from 12 to 256 characters."
          : "Could not generate a password. Try again."
      }
    } finally {
      busy = false
    }
  }

  function generateOnEnter(event: KeyboardEvent) {
    if (event.key !== "Enter") return
    event.preventDefault()
    void generate()
  }

  function usePassword() {
    if (!password) return
    onUse?.(password)
    clear()
  }

  onDestroy(clear)
</script>

<svelte:window onblur={clear} onpagehide={clear} />
<svelte:document onvisibilitychange={clear} />

<fieldset class="generator">
  <legend>Password generator</legend>
  <div class="settings">
    <label>Length <input type="number" step="any" bind:value={length} oninput={reset} onkeydown={generateOnEnter} /></label>
    <label class="symbols"><input type="checkbox" bind:checked={symbols} onchange={reset} /> Include symbols</label>
  </div>
  <button class="secondary" type="button" disabled={busy} onclick={generate}>
    <RefreshCw size={16} /> Generate password
  </button>
  {#if password}
    <label class="output">
      Generated password
      <input type="text" value={password} readonly onkeydown={(event) => { if (event.key === "Enter") event.preventDefault() }} bind:this={output} autocomplete="off" spellcheck={false} />
    </label>
    {#if onUse}
      <button class="primary" type="button" onclick={usePassword}>Use password</button>
    {:else}
      <button class="secondary" type="button" onclick={() => { output?.focus(); output?.select() }}>Select password</button>
    {/if}
  {/if}
  {#if error}<p class="error-note" role="alert">{error}</p>{/if}
</fieldset>

<style>
  .generator { display: grid; gap: 12px; min-width: 0; margin: 0; padding: 12px; border: 1px solid var(--line); border-radius: 10px; }
  legend { padding-inline: 5px; font-weight: 600; }
  .settings { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
  .settings label { display: flex; gap: 7px; align-items: center; }
  .settings input { accent-color: var(--accent); }
  input[type="number"], input[type="text"] {
    min-width: 0; padding: 6px 8px; color: var(--text); background: var(--surface);
    border: 1px solid var(--line); border-radius: 7px;
  }
  input[type="number"] { width: 72px; }
  input[type="text"] { width: 100%; font-family: ui-monospace, monospace; }
  .output { display: grid; gap: 5px; }
  .error-note { margin: 0; }
</style>
