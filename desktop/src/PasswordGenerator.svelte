<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import { Check, CircleAlert, RefreshCw, TextCursorInput } from "@lucide/svelte"
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
  const id = $props.id()
  const sliderMax = 64
  const bits = $derived(Number.isInteger(length) && length !== undefined && length >= 12 && length <= 256
    ? Math.floor(length * Math.log2(symbols ? 90 : 62)) : undefined)
  const rating = $derived(bits === undefined ? "" : bits < 96 ? "Strong" : bits < 128 ? "Very strong" : "Excellent")

  function slide(event: Event & { currentTarget: HTMLInputElement }) {
    length = Number(event.currentTarget.value)
    reset()
  }

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
  <legend class="visually-hidden">Generator options</legend>
  <div class="output" class:filled={Boolean(password)}>
    {#if password}
      <label class="output-label" for="{id}-output">Generated password</label>
      <input id="{id}-output" class="output-value" type="text" value={password} readonly
        onkeydown={(event) => { if (event.key === "Enter") event.preventDefault() }} bind:this={output} autocomplete="off" spellcheck={false} />
    {:else}
      <p class="output-placeholder">{busy ? "Generating…" : "Choose a length, then generate."}</p>
    {/if}
  </div>

  <div class="options">
    <div class="length-row">
      <label for="{id}-length">Length</label>
      <input class="slider" type="range" min="12" max={sliderMax} step="1" value={Math.min(length ?? 12, sliderMax)}
        style:--fill="{((Math.min(Math.max(length ?? 12, 12), sliderMax) - 12) / (sliderMax - 12)) * 100}%"
        aria-label="Password length" oninput={slide} />
      <input id="{id}-length" class="length-input" type="number" step="any" bind:value={length} oninput={reset} onkeydown={generateOnEnter} />
    </div>
    <label class="switch">
      <input type="checkbox" role="switch" bind:checked={symbols} onchange={reset} />
      <span class="track" aria-hidden="true"></span>
      Include symbols
    </label>
    {#if bits !== undefined}
      <div class="strength" data-rating={rating}>
        <span class="strength-meter" aria-hidden="true"><span style:width="{Math.min(100, bits / 160 * 100)}%"></span></span>
        <span><strong>{rating}</strong> (about {bits} bits of entropy)</span>
      </div>
    {/if}
  </div>

  <div class="actions">
    <button class="primary generate" type="button" disabled={busy} onclick={generate}>
      <RefreshCw size={15} class={busy ? "spinning" : ""} /> {password ? "Regenerate" : busy ? "Generating…" : "Generate password"}
    </button>
    {#if password}
      {#if onUse}
        <button class="secondary result-action" type="button" onclick={usePassword}><Check size={15} /> Use password</button>
      {:else}
        <button class="secondary result-action" type="button" onclick={() => { output?.focus(); output?.select() }}><TextCursorInput size={15} /> Select password</button>
      {/if}
    {/if}
  </div>
  {#if error}<p class="error-note" role="alert"><CircleAlert size={16} /> <span>{error}</span></p>{/if}
</fieldset>

<style>
  .generator { display: grid; gap: 16px; min-width: 0; margin: 0; padding: 0; border: 0; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }

  .output {
    display: grid;
    align-content: center;
    gap: 4px;
    min-height: 76px;
    padding: 12px 14px;
    border-radius: var(--radius);
    background: var(--surface-2);
    border: 1px solid var(--line);
  }
  .output.filled { background: var(--surface); }
  .output-label { color: var(--muted); font-size: 12px; font-weight: 500; }
  .output-value {
    width: 100%;
    min-width: 0;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--text);
    font: 500 17px/1.5 ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
    letter-spacing: .03em;
    text-overflow: ellipsis;
  }
  .output-value:focus-visible { outline: none; }
  .output:focus-within { border-color: var(--focus); box-shadow: var(--focus-ring); }
  .output-placeholder { color: var(--subtle); font-size: 13.5px; text-align: center; }

  .options { display: grid; gap: 14px; }
  .length-row { display: grid; grid-template-columns: auto minmax(0, 1fr) 68px; align-items: center; gap: 14px; }
  .length-row label { font-size: 13px; font-weight: 500; }
  .length-input {
    min-width: 0;
    width: 100%;
    min-height: 34px;
    padding: 5px 8px;
    color: var(--text);
    background: var(--control-bg);
    border: 1px solid var(--control-line);
    border-radius: var(--radius-sm);
    font-variant-numeric: tabular-nums;
    text-align: center;
  }
  .length-input:focus-visible { outline: none; border-color: var(--focus); box-shadow: var(--focus-ring); }
  .slider {
    --fill: 0%;
    width: 100%;
    height: 20px;
    margin: 0;
    background: transparent;
    appearance: none;
    cursor: pointer;
  }
  .slider::-webkit-slider-runnable-track {
    height: 4px;
    border-radius: 99px;
    background: linear-gradient(90deg, var(--signal) var(--fill), var(--line-strong) var(--fill));
  }
  .slider::-moz-range-track { height: 4px; border-radius: 99px; background: var(--line-strong); }
  .slider::-moz-range-progress { height: 4px; border-radius: 99px; background: var(--signal); }
  .slider::-webkit-slider-thumb {
    appearance: none;
    width: 16px;
    height: 16px;
    margin-top: -6px;
    border-radius: 50%;
    background: #fff;
    border: 0;
    box-shadow: 0 0 0 1px rgb(0 0 0 / .12), 0 1px 3px rgb(0 0 0 / .25);
  }
  .slider::-moz-range-thumb {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #fff;
    border: 0;
    box-shadow: 0 0 0 1px rgb(0 0 0 / .12), 0 1px 3px rgb(0 0 0 / .25);
  }

  .switch { display: inline-flex; align-items: center; gap: 10px; justify-self: start; font-size: 13.5px; cursor: pointer; }
  .switch input { position: absolute; opacity: 0; width: 1px; height: 1px; }
  .track {
    position: relative;
    flex: none;
    width: 32px;
    height: 18px;
    border-radius: 99px;
    background: var(--line-strong);
    transition: background-color .15s var(--ease);
  }
  .track::after {
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #fff;
    box-shadow: 0 1px 2px rgb(0 0 0 / .25);
    transition: transform .18s var(--ease);
  }
  .switch input:checked + .track { background: var(--signal); }
  .switch input:checked + .track::after { transform: translateX(14px); }
  .switch input:focus-visible + .track { outline: 2px solid var(--focus); outline-offset: 2px; }

  .strength { display: flex; align-items: center; gap: 12px; font-size: 12.5px; color: var(--muted); }
  .strength strong { color: var(--text); font-weight: 600; }
  .strength-meter { flex: 0 0 96px; height: 4px; border-radius: 99px; background: var(--line); overflow: hidden; }
  .strength-meter span { display: block; height: 100%; border-radius: inherit; background: var(--success); transition: width .2s var(--ease); }
  .strength[data-rating="Strong"] .strength-meter span { background: var(--signal); }

  .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .actions :global(.spinning) { animation: spin .7s linear infinite; }
  .error-note { margin: 0; }
</style>
