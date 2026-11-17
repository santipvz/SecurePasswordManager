<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import {
    ArrowLeft, CircleAlert, Eye, EyeOff, FileKey, FolderOpen, HardDrive, KeyRound, LayoutList,
    LockKeyhole, Moon, Plus, Settings, ShieldCheck, Sun, Usb,
  } from "@lucide/svelte"
  import { onMount, tick } from "svelte"
  import BrandMark from "./BrandMark.svelte"
  import PasswordGenerator from "./PasswordGenerator.svelte"
  import VaultEntries from "./VaultEntries.svelte"
  import VaultSettings from "./VaultSettings.svelte"

  type Status = {
    exists: boolean
    has_security_key: boolean
    generation: number
    creating: boolean
    file_name: string | null
    native_key_prompt: boolean
  }
  type Unlocked = { generation: number; has_security_key: boolean }
  type Entry = { name: string; username: string; url: string }
  type Entries = { entries: Entry[] }
  type Phase = "loading" | "choosing" | "locked" | "unlocking" | "unlocked" | "locking"
  type Selection = "default" | "existing" | "new"
  type View = "credentials" | "generator" | "settings"

  const messages: Record<string, string> = {
    busy: "The vault is busy. Try again in a moment.",
    input_too_large: "The unlock request exceeds the supported length.",
    open_failed: "Could not unlock the vault. Check the master password and vault file.",
    file_error: "Could not access the vault file.",
    invalid_file: "Choose a file with the .spm extension.",
    dialog_failed: "Could not open the file dialog. Try again.",
    create_failed: "Could not create the vault. Choose a new file in a writable folder.",
    weak_master: "Choose a less predictable master password of at least 15 characters.",
    key_disconnected: "Connect the key and check that the system can access it.",
    key_failed: "Could not unlock with this key. Check the key and vault, or use the master password.",
    key_interrupted: "The security key request timed out or was cancelled.",
    key_setup_required: "Set up a FIDO2 PIN on the key before trying again.",
    key_unsupported: "The key or system lacks the required FIDO2 features.",
    multiple_keys: "Connect only the key registered for this vault.",
    pin_required: "Enter the security key PIN.",
    pin_invalid: "The security key PIN is incorrect.",
    pin_blocked: "The security key PIN is blocked. Reconnect the key or use your master password.",
    wrong_key: "Use the security key registered for this vault.",
    process_unavailable: "Could not start the vault process.",
    timed_out: "The vault process timed out. Try again.",
  }

  let showGenerator = $state(false)
  let generatorHeading = $state<HTMLHeadingElement>()
  let generatorButton = $state<HTMLButtonElement>()
  let view = $state<View>("credentials")
  let workspace = $state<VaultEntries>()
  let reviewing = $state(false)
  let settingsPending = $state(false)
  let entryWritePending = $state(false)
  let editing = $state(false)
  let hasSecurityKey = $state(false)
  let phase = $state<Phase>("loading")
  let theme = $state<"light" | "dark">("light")
  let status = $state<Status>()
  let generation = $state<number>()
  let entries = $state<Entry[]>([])
  let feedback = $state("")
  let method = $state<"password" | "key">("password")
  let passwordInput = $state<HTMLInputElement>()
  let confirmationInput = $state<HTMLInputElement>()
  let pinInput = $state<HTMLInputElement>()
  let keyButton = $state<HTMLButtonElement>()
  let openButton = $state<HTMLButtonElement>()
  let cancelButton = $state<HTMLButtonElement>()
  let showMaster = $state(false)
  let capsLock = $state(false)
  let masterCount = $state(0)
  const minimumMaster = 15
  const keyReady = $derived(status?.exists && status.has_security_key && !status.creating)
  const creating = $derived(status?.creating && !status.exists)
  const navigationBusy = $derived(settingsPending || entryWritePending || editing)
  let revision = 0
  let lastActivity = -Infinity

  function errorMessage(error: unknown) {
    return typeof error === "string" && Object.hasOwn(messages, error)
      ? messages[error]
      : "The vault session ended. Unlock the vault to try again."
  }

  async function focusWelcome(current: number) {
    await tick()
    if (revision !== current) return
    const input = pinInput ?? keyButton ?? passwordInput ?? openButton
    input?.focus()
  }

  function clearInputs() {
    if (passwordInput) passwordInput.value = ""
    if (confirmationInput) confirmationInput.value = ""
    if (pinInput) pinInput.value = ""
    showMaster = false
    masterCount = 0
  }

  function trackCapsLock(event: KeyboardEvent) {
    capsLock = event.getModifierState?.("CapsLock") ?? false
  }

  function countMaster(event: Event & { currentTarget: HTMLInputElement }) {
    // Only the length is kept so the hint can update; the value stays in the field.
    if (creating) masterCount = Array.from(event.currentTarget.value).length
  }

  async function refresh(message = "", current = ++revision) {
    phase = "loading"
    feedback = message
    try {
      const result = await invoke<Status>("vault_status")
      if (revision === current) {
        status = result
        if (!result.has_security_key || result.creating) method = "password"
      }
    } catch (error) {
      if (revision === current) {
        status = undefined
        feedback = message || errorMessage(error)
      }
    } finally {
      if (revision === current) phase = "locked"
    }
    await focusWelcome(current)
  }

  async function toggleGenerator(show: boolean) {
    clearInputs()
    showGenerator = show
    await tick()
    if (show) generatorHeading?.focus()
    else generatorButton?.focus()
  }

  async function choose(selection: Selection) {
    if (phase !== "locked") return
    const current = ++revision
    clearInputs()
    feedback = ""
    phase = "choosing"
    try {
      // The native picker keeps the full path in Rust.
      const result = await invoke<Status | null>("vault_select", { generation: status?.generation, selection })
      if (revision !== current) return
      if (result) {
        status = result
        method = "password"
      }
      phase = "locked"
      await focusWelcome(current)
    } catch (error) {
      if (revision === current) await refresh(errorMessage(error), current)
    }
  }

  async function endSession(message: string) {
    const current = ++revision
    generation = undefined
    view = "credentials"
    reviewing = false
    entries = []
    clearInputs()
    phase = "locking"
    feedback = message
    try {
      await invoke("vault_lock")
    } catch {
      if (revision === current) feedback = "Could not confirm the lock. Close and reopen the app."
      return
    }
    if (revision === current) await refresh(message, current)
  }

  async function switchMethod(next: "password" | "key") {
    if (method === next) return
    clearInputs()
    method = next
    feedback = ""
    await focusWelcome(revision)
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault()
    if (phase !== "locked" || !status) return
    if (method === "password") {
      if (!passwordInput?.value) return
      if (creating && (Array.from(passwordInput.value).length < 15 || !passwordInput.value.trim())) {
        clearInputs()
        feedback = messages.weak_master
        passwordInput.focus()
        return
      }
      if (creating && passwordInput.value !== confirmationInput?.value) {
        if (confirmationInput) confirmationInput.value = ""
        feedback = "The master passwords do not match."
        confirmationInput?.focus()
        return
      }
    }
    const current = ++revision
    feedback = ""
    phase = "unlocking"
    try {
      const args = { generation: status.generation }
      let pending: Promise<Unlocked>
      try {
        pending = method === "key"
          ? invoke<Unlocked>("vault_unlock_key", { ...args, pin: pinInput?.value || undefined })
          : invoke<Unlocked>("vault_unlock", { ...args, master: passwordInput?.value })
      } finally {
        clearInputs()
      }
      void tick().then(() => {
        if (revision === current) cancelButton?.focus()
      })
      const session = await pending
      if (revision !== current) return
      const metadata = await invoke<Entries>("vault_list", { generation: session.generation })
      if (revision !== current) return
      if (!await invoke<boolean>("vault_active", { generation: session.generation })) {
        throw "locked"
      }
      if (revision !== current) return
      generation = session.generation
      hasSecurityKey = session.has_security_key
      lastActivity = -Infinity
      entries = metadata.entries
      phase = "unlocked"
    } catch (error) {
      if (revision === current) await endSession(errorMessage(error))
    }
  }

  async function navigate(next: View) {
    if (phase !== "unlocked" || navigationBusy) return
    if (next !== "credentials") reviewing = false
    view = next
    await tick()
    if (phase !== "unlocked" || view !== next) return
    if (next === "credentials" && reviewing) await workspace?.closeReview()
    if (next === "generator") generatorHeading?.focus()
  }

  async function showReview() {
    if (phase !== "unlocked" || navigationBusy || reviewing) return
    view = "credentials"
    await tick()
    if (phase === "unlocked" && view === "credentials") void workspace?.openReview()
  }

  function addImported(imported: Entry[]) {
    entries = [...entries, ...imported].sort((a, b) => a.name.localeCompare(b.name))
  }

  function activity(event: KeyboardEvent | PointerEvent) {
    if (event.isTrusted && event instanceof KeyboardEvent && event.key === "Escape" && showGenerator) {
      void toggleGenerator(false)
      return
    }
    if (event.isTrusted && event instanceof KeyboardEvent && event.key === "Escape" && phase === "unlocking") {
      if (!creating) void endSession("")
      return
    }
    if (event.isTrusted && event instanceof KeyboardEvent && phase === "unlocked" && view !== "credentials") {
      if (!event.isComposing && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        void navigate("credentials")
      } else if (event.key === "Escape" && view === "generator") {
        void navigate("credentials")
      }
    }
    if (!event.isTrusted || generation === undefined || performance.now() - lastActivity < 250) return
    lastActivity = performance.now()
    void invoke("vault_activity", { generation }).catch(() => {})
  }

  async function checkSession() {
    if (generation === undefined) return
    const current = revision
    try {
      if (await invoke<boolean>("vault_active", { generation })) return
    } catch {
      // A failed IPC call also ends the visible session.
    }
    if (revision === current) await endSession("The vault locked. Unlock it to continue.")
  }

  onMount(() => {
    if (matchMedia("(prefers-color-scheme: dark)").matches) theme = "dark"
    void refresh()
    const poll = window.setInterval(() => void checkSession(), 500)
    return () => window.clearInterval(poll)
  })
</script>

<svelte:window onkeydown={activity} onpointerdown={activity} onfocus={checkSession} />

{#snippet themeControl()}
  <button class="icon-button theme-control" aria-label={theme === "light" ? "Use dark theme" : "Use light theme"}
    title={theme === "light" ? "Use dark theme" : "Use light theme"}
    onclick={() => theme = theme === "light" ? "dark" : "light"}>
    {#if theme === "light"}<Moon size={18} />{:else}<Sun size={18} />{/if}
  </button>
{/snippet}

<div class="app desktop-app" data-theme={theme}>
  {#if phase === "unlocked" && generation !== undefined}
    <div class="vault-shell">
      <header class="vault-toolbar">
        <div class="app-brand" translate="no">
          <BrandMark size={30} />
          <div><span>Secure Password Manager</span><small>{status?.file_name ?? "Local vault"}</small></div>
        </div>
        <nav class="vault-nav" aria-label="Vault navigation">
          <button aria-label="Credentials" title="Credentials" aria-current={view === "credentials" && !reviewing ? "page" : undefined}
            disabled={navigationBusy} onclick={() => navigate("credentials")}><LayoutList size={16} /> <span>Vault</span></button>
          <button aria-label="Password review" title="Password review" aria-current={reviewing ? "page" : undefined}
            disabled={navigationBusy} onclick={showReview}><ShieldCheck size={16} /> <span>Review</span></button>
          <button aria-label="Password generator" title="Password generator" aria-current={view === "generator" ? "page" : undefined}
            disabled={navigationBusy} onclick={() => navigate("generator")}><KeyRound size={16} /> <span>Generator</span></button>
          <button aria-label="Vault settings" title="Vault settings" aria-current={view === "settings" ? "page" : undefined}
            disabled={navigationBusy} onclick={() => navigate("settings")}><Settings size={16} /> <span>Settings</span></button>
        </nav>
        <div class="window-actions">
          {@render themeControl()}
          <button class="secondary lock-action" aria-label="Lock vault" title="Lock vault" onclick={() => endSession("")}>
            <LockKeyhole size={15} /> <span>Lock vault</span>
          </button>
        </div>
      </header>
      <div class="vault-content">
        {#if view === "settings"}
          <div class="vault-page">
            <VaultSettings {generation} nativePrompt={Boolean(status?.native_key_prompt)} bind:hasSecurityKey bind:pending={settingsPending}
              onClose={() => navigate("credentials")} onLock={endSession} onImport={addImported} />
          </div>
        {:else if view === "generator"}
          <div class="vault-page">
            <main class="tool-page">
              <button class="text-button back-link" onclick={() => navigate("credentials")}><ArrowLeft size={16} /> Back to credentials</button>
              <header class="page-header">
                <h1 tabindex="-1" bind:this={generatorHeading}>Password generator</h1>
                <p class="muted">Random passwords drawn on this device. Generated values clear after 30 seconds.</p>
              </header>
              <PasswordGenerator {generation} />
            </main>
          </div>
        {:else}
          <VaultEntries {generation} bind:this={workspace} bind:entries bind:writing={entryWritePending}
            bind:editing bind:reviewOpen={reviewing} onSessionEnd={endSession} />
        {/if}
      </div>
    </div>
  {:else}
    <main class="desktop-welcome">
      <header class="welcome-header">
        <div class="app-brand" translate="no"><BrandMark size={24} /> <span>Secure Password Manager</span></div>
        {@render themeControl()}
      </header>
      <div class="welcome-main">
        <div class="welcome-body">
          {#if showGenerator}
            <section class="unlock-card generator-card" aria-labelledby="generator-title">
              <button class="text-button back-link" onclick={() => toggleGenerator(false)}><ArrowLeft size={16} /> Back to vault</button>
              <h1 id="generator-title" tabindex="-1" bind:this={generatorHeading}>Password generator</h1>
              <p class="muted welcome-copy">Create a strong password without unlocking a vault.</p>
              <div class="standalone-generator"><PasswordGenerator /></div>
            </section>
          {:else}
            <section class="unlock-card" aria-labelledby="vault-title">
              <h1 id="vault-title">
                {creating ? "Create your vault" : status?.exists ? "Unlock your vault" : phase === "loading" ? "Your vault" : "Open a vault"}
              </h1>
              <p class="muted welcome-copy">
                {#if creating}
                  Choose a master password for <span class="file-chip"><FileKey size={14} /><strong>{status?.file_name}</strong></span>.
                  You'll need it to open the vault, so keep it somewhere safe.
                {:else if status?.creating && status.exists}
                  <span class="file-chip"><FileKey size={14} /><strong>{status.file_name}</strong></span> already exists. Open it or choose a new filename.
                {:else if keyReady && method === "key"}
                  {#if status?.native_key_prompt}
                    Connect your YubiKey and follow the Windows security prompt.
                  {:else}
                    Connect your YubiKey and touch it when it blinks. Leave the PIN blank if your key verifies by fingerprint.
                  {/if}
                {:else if status?.exists}
                  <span class="file-chip"><FileKey size={14} /><strong>{status.file_name ?? "Local vault"}</strong></span>
                {:else if phase === "loading"}
                  Looking for your vault…
                {:else}
                  Create a new vault or open an existing <code>.spm</code> file.
                {/if}
              </p>
              {#if feedback}<p class="error-note" role="alert"><CircleAlert size={17} /> <span>{feedback}</span></p>{/if}
              {#if phase === "loading" || phase === "choosing" || phase === "locking"}
                <div class="unlock-state" role="status">
                  <span class="spinner"></span>
                  {phase === "loading" ? "Checking for a vault…" : phase === "choosing" ? "Waiting for file selection…" : "Locking vault…"}
                </div>
              {:else if phase === "unlocking"}
                {#if method === "key" && !creating}
                  <div class="key-wait" role="status">
                    <span class="spinner"></span>
                    <span><strong>Waiting for your security key</strong>{status?.native_key_prompt ? "Follow the system prompt." : "Touch the key when it blinks."}</span>
                  </div>
                {:else}
                  <div class="unlock-state" role="status">
                    <span class="spinner"></span>
                    {creating ? "Creating vault…" : "Unlocking vault…"}
                  </div>
                {/if}
                {#if !creating}
                  <button class="secondary full" type="button" bind:this={cancelButton} onclick={() => endSession("")}>Cancel</button>
                {/if}
              {:else}
                {#if creating || (status?.exists && !status.creating)}
                  {#if keyReady}
                    <div class="unlock-methods" role="group" aria-label="Unlock method">
                      <button type="button" aria-pressed={method === "password"} onclick={() => switchMethod("password")}><LockKeyhole size={15} /> Password</button>
                      <button type="button" aria-pressed={method === "key"} onclick={() => switchMethod("key")}><KeyRound size={15} /> YubiKey</button>
                    </div>
                  {/if}
                  <form class="unlock-form" onsubmit={submit} autocomplete="off">
                    {#if method === "key" && keyReady}
                      {#if !status?.native_key_prompt}
                        <div class="field">
                          <label class="password-label" for="key-pin">Security key PIN <span class="optional">Optional</span></label>
                          <input class="password-input" id="key-pin" type="password" bind:this={pinInput} inputmode="numeric"
                            autocomplete="off" autocapitalize="off" spellcheck={false} />
                        </div>
                      {/if}
                      <button class="primary submit" type="submit" bind:this={keyButton}><Usb size={16} /> Unlock with YubiKey</button>
                    {:else}
                      <div class="field">
                        <label class="password-label" for="master-password">{creating ? "New master password" : "Master password"}</label>
                        <div class="password-field">
                          <input class="password-input" id="master-password" type={showMaster ? "text" : "password"} bind:this={passwordInput}
                            autocomplete="off" autocapitalize="off" spellcheck={false} required
                            aria-describedby={creating ? "master-hint" : undefined}
                            onkeydown={trackCapsLock} onkeyup={trackCapsLock} oninput={countMaster} onblur={() => capsLock = false} />
                          <button class="icon-button reveal-toggle" type="button" aria-pressed={showMaster}
                            aria-label={showMaster ? "Hide master password" : "Show master password"}
                            title={showMaster ? "Hide master password" : "Show master password"}
                            onclick={() => showMaster = !showMaster}>
                            {#if showMaster}<EyeOff size={17} />{:else}<Eye size={17} />{/if}
                          </button>
                        </div>
                        {#if creating}
                          <div class="length-hint" class:met={masterCount >= minimumMaster} id="master-hint">
                            <span class="meter" aria-hidden="true"><span style:width="{Math.min(100, masterCount / minimumMaster * 100)}%"></span></span>
                            <span>{masterCount >= minimumMaster ? "Length requirement met" : `At least ${minimumMaster} characters`}</span>
                          </div>
                        {/if}
                      </div>
                      {#if creating}
                        <div class="field">
                          <label class="password-label" for="confirm-master">Confirm master password</label>
                          <input class="password-input" id="confirm-master" type="password" bind:this={confirmationInput}
                            autocomplete="off" autocapitalize="off" spellcheck={false} required
                            onkeydown={trackCapsLock} onkeyup={trackCapsLock} onblur={() => capsLock = false} />
                        </div>
                      {/if}
                      {#if capsLock}<p class="caps-hint" role="status"><CircleAlert size={14} /> Caps Lock is on</p>{/if}
                      <button class="primary submit" type="submit">{creating ? "Create vault" : "Unlock vault"}</button>
                    {/if}
                  </form>
                {/if}
                <div class="vault-file-actions" class:first-run={!status?.exists && !creating}>
                  <button class={status?.exists || creating ? "text-button" : "primary"} onclick={() => choose("new")}><Plus size={16} /> {creating ? "Choose new file" : "Create vault"}</button>
                  <button class={status?.exists || creating ? "text-button" : "secondary"} bind:this={openButton} onclick={() => choose("existing")}><FolderOpen size={16} /> Open vault file</button>
                </div>
                <div class="welcome-links">
                  <button class="text-button generator-link" bind:this={generatorButton} onclick={() => toggleGenerator(true)}><KeyRound size={15} /> Password generator</button>
                  {#if status?.file_name || !status}
                    <button class="text-button default-vault" onclick={() => choose("default")}><HardDrive size={15} /> Use default vault</button>
                  {/if}
                </div>
              {/if}
            </section>
          {/if}
        </div>
      </div>
    </main>
  {/if}
</div>

<style>
  .desktop-app { display: flex; flex-direction: column; height: 100vh; min-height: 0; }

  /* ---------- Toolbar ---------- */

  .vault-shell { display: flex; flex: 1; flex-direction: column; min-height: 0; }
  .vault-toolbar {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
    align-items: center;
    flex: none;
    gap: 14px;
    padding: 9px 16px 9px 18px;
    min-height: 58px;
    background: var(--surface);
    border-bottom: 1px solid var(--line);
  }
  .app-brand { display: flex; align-items: center; gap: 10px; min-width: 0; line-height: 1.3; }
  .app-brand :global(img) { flex: none; border-radius: 22%; }
  .app[data-theme="dark"] .app-brand :global(img) { box-shadow: 0 0 0 1px var(--line-strong); }
  .app-brand div { min-width: 0; }
  .app-brand span, .app-brand small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .app-brand span { font-size: 13px; font-weight: 600; letter-spacing: -.01em; }
  .app-brand small { color: var(--muted); font-size: 12px; }
  .vault-nav, .window-actions { display: flex; align-items: center; gap: 2px; }
  .vault-nav { padding: 3px; border-radius: 10px; background: var(--canvas); border: 1px solid var(--line); }
  .vault-nav button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    min-height: 32px;
    padding: 5px 12px;
    background: transparent;
    border: 0;
    border-radius: 7px;
    color: var(--muted);
    font-size: 13px;
    font-weight: 500;
    transition: background-color .15s var(--ease), color .15s var(--ease), box-shadow .15s var(--ease);
  }
  .vault-nav button:hover:not(:disabled) { color: var(--text); }
  .vault-nav button[aria-current="page"] {
    background: var(--raised);
    color: var(--text);
    box-shadow: var(--shadow-sm), 0 0 0 1px var(--line);
  }
  .vault-nav button[aria-current="page"] :global(svg) { color: var(--accent); }
  .window-actions { justify-content: flex-end; gap: 6px; }
  .lock-action { min-height: 34px; padding: 6px 12px; font-size: 13px; }
  .vault-content { display: flex; flex: 1; flex-direction: column; min-width: 0; min-height: 0; }
  .vault-page { flex: 1; min-height: 0; overflow-y: auto; }
  .tool-page { width: min(100%, 640px); margin-inline: auto; padding: clamp(20px, 5vw, 44px) clamp(18px, 4vw, 32px); }
  .page-header { margin: 4px 0 24px; }
  .page-header h1 { font-size: clamp(24px, 3vw, 28px); }
  .page-header p { margin-top: 6px; }
  .back-link { margin-left: -10px; }

  /* ---------- Welcome ---------- */

  .desktop-welcome { flex: 1; min-height: 0; display: flex; flex-direction: column; background: var(--surface); overflow: auto; }
  .welcome-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px 14px 20px; }
  .welcome-header .app-brand { gap: 9px; font-size: 13px; font-weight: 600; color: var(--muted); }
  .welcome-header .app-brand :global(img) { border-radius: 6px; }
  .welcome-main { display: flex; flex: 1; flex-direction: column; min-width: 0; }
  .welcome-body { display: grid; flex: 1; place-items: center; padding: 24px 24px 12vh; }
  .desktop-welcome .unlock-card { width: min(100%, 360px); padding: 0; background: transparent; border: 0; box-shadow: none; }
  .unlock-card h1 { font-size: 24px; font-weight: 600; letter-spacing: -.015em; }
  .welcome-copy { margin: 8px 0 22px; overflow-wrap: anywhere; line-height: 1.55; }
  .welcome-copy strong { color: var(--text); font-weight: 600; }
  .welcome-copy code { font: 500 12.5px ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--text); }
  .file-chip { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; vertical-align: bottom; }
  .file-chip :global(svg) { flex: none; color: var(--muted); }
  .file-chip strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .unlock-methods {
    display: flex;
    gap: 2px;
    margin-bottom: 20px;
    padding: 3px;
    border-radius: 10px;
    background: var(--canvas);
    border: 1px solid var(--line);
  }
  .unlock-methods button {
    display: flex;
    flex: 1;
    justify-content: center;
    align-items: center;
    gap: 7px;
    min-height: 34px;
    padding: 5px;
    background: none;
    border: 0;
    border-radius: 7px;
    color: var(--muted);
    font-weight: 500;
    transition: background-color .15s var(--ease), color .15s var(--ease);
  }
  .unlock-methods button:hover { color: var(--text); }
  .unlock-methods button[aria-pressed="true"] { background: var(--raised); color: var(--text); box-shadow: var(--shadow-sm), 0 0 0 1px var(--line); }
  .unlock-methods button[aria-pressed="true"] :global(svg) { color: var(--accent); }

  .unlock-form { display: grid; gap: 16px; }
  .field { display: grid; gap: 7px; }
  .password-label { display: flex; justify-content: space-between; font-size: 13px; font-weight: 500; }
  .optional { color: var(--subtle); font-weight: 400; }
  .password-input {
    width: 100%;
    min-height: 42px;
    padding: 9px 12px;
    border: 1px solid var(--control-line);
    border-radius: var(--radius-sm);
    background: var(--control-bg);
    color: var(--text);
    transition: border-color .15s var(--ease), box-shadow .15s var(--ease);
  }
  .app .password-input:focus-visible { outline: none; border-color: var(--focus); box-shadow: var(--focus-ring); }
  .password-field { position: relative; }
  .password-field .password-input { padding-right: 44px; }
  .reveal-toggle { position: absolute; top: 3px; right: 3px; }
  .length-hint { display: flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--muted); }
  .meter { flex: 1; height: 4px; border-radius: 99px; background: var(--line); overflow: hidden; }
  .meter span { display: block; height: 100%; border-radius: inherit; background: var(--signal); transition: width .2s var(--ease), background-color .2s; }
  .length-hint.met { color: var(--success); }
  .length-hint.met .meter span { background: var(--success); }
  .caps-hint { display: flex; align-items: center; gap: 6px; margin-top: -6px; color: var(--warning); font-size: 12.5px; font-weight: 500; }
  .submit { min-height: 42px; width: 100%; }
  .unlock-card .full { margin-bottom: 0; }
  .key-wait {
    display: flex;
    gap: 14px;
    align-items: center;
    margin-bottom: 16px;
    padding: 14px;
    border-radius: var(--radius);
    background: var(--surface-2);
    border: 1px solid var(--line);
  }
  .key-wait strong { display: block; font-weight: 600; }
  .key-wait > span:last-child { color: var(--muted); font-size: 13px; }
  .vault-file-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid var(--line);
  }
  .vault-file-actions.first-run { grid-template-columns: 1fr; gap: 10px; margin: 0; padding: 0; border: 0; }
  .vault-file-actions.first-run :global(button) { min-height: 42px; }
  .welcome-links { display: flex; flex-wrap: wrap; justify-content: center; gap: 2px; margin-top: 10px; }
  .welcome-links .text-button { font-size: 13px; }
  .standalone-generator { margin-top: 4px; }

  @media (max-width: 920px) {
    .vault-toolbar { padding-inline: 12px; gap: 9px; }
    .vault-nav button { padding-inline: 9px; }
  }
  @media (max-width: 760px) {
    .vault-toolbar { grid-template-columns: minmax(0, 1fr) auto; padding: 8px 12px; }
    .vault-nav { grid-column: 1 / -1; grid-row: 2; }
    .vault-nav button { flex: 1; min-width: 0; gap: 5px; padding-inline: 4px; }
    .vault-nav button :global(svg) { flex: none; }
    .lock-action span { display: none; }
    .lock-action { width: 36px; padding: 0; }
    .welcome-body { padding: 24px 20px; place-items: start center; }
  }
  @media (max-width: 420px) {
    .vault-nav button :global(svg) { display: none; }
  }
  @media (pointer: coarse) {
    .vault-nav button, .lock-action, .theme-control { min-height: 44px; }
  }
</style>
