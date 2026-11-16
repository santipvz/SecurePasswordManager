<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import { ArrowLeft, FolderOpen, HardDrive, KeyRound, LayoutList, LockKeyhole, Moon, Plus, Settings, ShieldCheck, Sun } from "@lucide/svelte"
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
    weak_master: "Use at least 15 characters for the master password.",
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
    {#if theme === "light"}<Moon size={19} />{:else}<Sun size={19} />{/if}
  </button>
{/snippet}

<div class="app desktop-app" data-theme={theme}>
  {#if phase === "unlocked" && generation !== undefined}
    <div class="vault-shell">
      <header class="vault-toolbar">
        <div class="app-brand" translate="no">
          <BrandMark size={32} />
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
            <LockKeyhole size={16} /> <span>Lock vault</span>
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
              <h1 tabindex="-1" bind:this={generatorHeading}>Password generator</h1>
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
      <aside class="welcome-identity" aria-label="Secure Password Manager">
        <div class="identity-brand" translate="no">
          <BrandMark size={64} />
          <p>Secure Password<br /> Manager</p>
        </div>
        <span class="storage-note"><HardDrive size={16} /> Local vault storage</span>
      </aside>
      <div class="welcome-main">
        <div class="welcome-header">
          {@render themeControl()}
        </div>
        <div class="welcome-body">
          {#if showGenerator}
            <section class="unlock-card" aria-labelledby="generator-title">
              <button class="text-button back-link" onclick={() => toggleGenerator(false)}><ArrowLeft size={16} /> Back to vault</button>
              <h1 id="generator-title" tabindex="-1" bind:this={generatorHeading}>Password generator</h1>
              <div class="standalone-generator"><PasswordGenerator /></div>
            </section>
          {:else}
            <section class="unlock-card" aria-labelledby="vault-title">
              <h1 id="vault-title">
                {creating ? "Create your vault" : status?.exists ? "Unlock your vault" : phase === "loading" ? "Your vault" : "Open a vault"}
              </h1>
              <p class="muted welcome-copy">
                {#if creating}
                  Choose a master password for <strong>{status?.file_name}</strong>. Keep it somewhere safe.
                {:else if status?.creating && status.exists}
                  <strong>{status.file_name}</strong> already exists. Open it or choose a new filename.
                {:else if keyReady && method === "key"}
                  {#if status?.native_key_prompt}
                    Connect your YubiKey and follow the Windows security prompt.
                  {:else}
                    Connect your YubiKey and touch it when it blinks. Leave the PIN blank if your key verifies by fingerprint.
                  {/if}
                {:else if status?.exists}
                  <strong>{status.file_name ?? "Local vault"}</strong>
                {:else}
                  Create a vault or open an existing .spm file.
                {/if}
              </p>
              {#if feedback}<p class="error-note" role="alert">{feedback}</p>{/if}
              {#if phase === "loading" || phase === "choosing" || phase === "locking"}
                <div class="unlock-state" role="status">
                  <span class="spinner"></span>
                  {phase === "loading" ? "Checking for a vault…" : phase === "choosing" ? "Waiting for file selection…" : "Locking vault…"}
                </div>
              {:else if phase === "unlocking"}
                <div class="unlock-state" role="status">
                  <span class="spinner"></span>
                  {creating ? "Creating vault…" : method === "key" ? "Waiting for your security key…" : "Unlocking vault…"}
                </div>
                {#if !creating}
                  <button class="secondary full" type="button" bind:this={cancelButton} onclick={() => endSession("")}>Cancel</button>
                {/if}
              {:else}
                {#if creating || (status?.exists && !status.creating)}
                  {#if keyReady}
                    <div class="unlock-methods" role="group" aria-label="Unlock method">
                      <button type="button" aria-pressed={method === "password"} onclick={() => switchMethod("password")}><LockKeyhole size={16} /> Password</button>
                      <button type="button" aria-pressed={method === "key"} onclick={() => switchMethod("key")}><KeyRound size={16} /> YubiKey</button>
                    </div>
                  {/if}
                  <form onsubmit={submit} autocomplete="off">
                    {#if method === "key" && keyReady}
                      {#if !status?.native_key_prompt}
                        <label class="password-label" for="key-pin">Security key PIN</label>
                        <input class="password-input full" id="key-pin" type="password" bind:this={pinInput}
                          autocomplete="off" autocapitalize="off" spellcheck={false} />
                      {/if}
                      <button class="primary full" type="submit" bind:this={keyButton}>Unlock with YubiKey</button>
                    {:else}
                      <label class="password-label" for="master-password">Master password</label>
                      <input class="password-input full" id="master-password" type="password" bind:this={passwordInput}
                        autocomplete="off" autocapitalize="off" spellcheck={false} required />
                      {#if creating}
                        <label class="password-label" for="confirm-master">Confirm master password</label>
                        <input class="password-input full" id="confirm-master" type="password" bind:this={confirmationInput}
                          autocomplete="off" autocapitalize="off" spellcheck={false} required />
                      {/if}
                      <button class="primary full" type="submit">{creating ? "Create vault" : "Unlock vault"}</button>
                    {/if}
                  </form>
                {/if}
                <div class="vault-file-actions" class:first-run={!status?.exists && !creating}>
                  <button class={status?.exists || creating ? "text-button" : "primary"} onclick={() => choose("new")}><Plus size={17} /> {creating ? "Choose new file" : "Create vault"}</button>
                  <button class={status?.exists || creating ? "text-button" : "secondary"} bind:this={openButton} onclick={() => choose("existing")}><FolderOpen size={17} /> Open vault file</button>
                </div>
                {#if status?.file_name || !status}
                  <button class="text-button default-vault" onclick={() => choose("default")}>Use default vault</button>
                {/if}
                <button class="text-button generator-link" bind:this={generatorButton} onclick={() => toggleGenerator(true)}><KeyRound size={16} /> Password generator</button>
              {/if}
            </section>
          {/if}
        </div>
      </div>
    </main>
  {/if}
</div>

<style>
  .vault-shell {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    height: 100vh;
  }
  .vault-toolbar {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
    align-items: center;
    flex: none;
    gap: 14px;
    padding: 10px 22px;
    min-height: 62px;
    background: var(--surface);
    border-bottom: 1px solid var(--line);
  }
  .app-brand { display: flex; align-items: center; gap: 10px; min-width: 0; line-height: 1.35; }
  .app-brand :global(img) { flex: none; }
  .app-brand div { min-width: 0; }
  .app-brand span, .app-brand small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .app-brand span { font-size: 13px; font-weight: 700; }
  .app-brand small { color: var(--muted); font-size: 12px; margin-top: 2px; }
  .vault-nav, .window-actions { display: flex; align-items: center; gap: 4px; }
  .vault-nav { padding: 3px; border-radius: 8px; background: var(--canvas); }
  .vault-nav button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    min-height: 33px;
    padding: 5px 10px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--muted);
    font-size: 13px;
    font-weight: 600;
  }
  .vault-nav button:hover { background: var(--soft); color: var(--text); }
  .vault-nav button[aria-current="page"] { background: var(--surface); color: var(--accent); border-color: var(--line); }
  .window-actions { justify-content: flex-end; gap: 8px; }
  .theme-control { color: var(--muted); border: 1px solid var(--line); }
  .lock-action { min-height: 38px; padding: 7px 10px; font-size: 13px; white-space: nowrap; }
  .vault-content { display: flex; flex: 1; flex-direction: column; min-width: 0; min-height: 0; }
  .vault-page { flex: 1; min-height: 0; overflow-y: auto; }
  .tool-page { width: min(100%, 670px); margin-inline: auto; padding: clamp(20px, 5vw, 45px); }
  .tool-page h1 { margin: 6px 0 23px; font-size: clamp(28px, 4vw, 36px); }
  .back-link { margin-left: -9px; color: var(--muted); }

  .desktop-welcome {
    min-height: 100vh;
    display: grid;
    grid-template-columns: minmax(295px, .77fr) minmax(0, 1.23fr);
    background: var(--surface);
  }
  .welcome-identity {
    background: var(--identity);
    color: #f1f5fc;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 40px clamp(28px, 5vw, 66px);
    position: relative;
  }
  .identity-brand p {
    margin-top: 20px;
    font-size: clamp(27px, 3.4vw, 43px);
    font-weight: 600;
    letter-spacing: -.038em;
    line-height: 1.12;
  }
  .storage-note {
    position: absolute;
    inset-inline-start: clamp(28px, 5vw, 66px);
    inset-block-end: 36px;
    display: flex;
    gap: 8px;
    align-items: center;
    color: #becce2;
    font-size: 13px;
  }
  .welcome-main { display: flex; flex-direction: column; min-width: 0; }
  .welcome-header { display: flex; justify-content: flex-end; padding: 20px 24px 0; }
  .welcome-body { display: grid; flex: 1; place-items: center; padding: 24px 30px 54px; }
  .desktop-welcome .unlock-card { width: min(100%, 400px); padding: 0; background: transparent; border: 0; box-shadow: none; }
  .unlock-card h1 { font-size: clamp(29px, 4.1vw, 40px); letter-spacing: -.04em; }
  .welcome-copy { margin: 10px 0 23px; overflow-wrap: anywhere; }
  .welcome-copy strong { color: var(--text); font-weight: 600; }
  .unlock-card .full { margin-bottom: 12px; }
  .unlock-card form > .primary { min-height: 44px; }
  .unlock-methods { display: flex; gap: 3px; margin-bottom: 18px; padding: 4px; border-radius: 8px; background: var(--canvas); }
  .unlock-methods button {
    display: flex;
    flex: 1;
    justify-content: center;
    align-items: center;
    gap: 8px;
    min-height: 37px;
    padding: 5px;
    background: none;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--muted);
    font-weight: 600;
  }
  .unlock-methods button[aria-pressed="true"] { background: var(--surface); color: var(--accent); border-color: var(--line); }
  .unlock-methods button:hover { background: var(--soft); }
  .vault-file-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-top: 10px; padding-top: 13px; border-top: 1px solid var(--line); }
  .vault-file-actions.first-run { grid-template-columns: 1fr; gap: 10px; margin: 0; padding: 0; border: 0; }
  .generator-link, .default-vault { display: flex; width: 100%; margin-top: 5px; color: var(--muted); }
  .standalone-generator { margin-top: 17px; }
  .password-label { display: block; margin-bottom: 6px; font-weight: 600; }
  .password-input { min-height: 44px; padding: 9px 12px; border: 1px solid var(--control-line); border-radius: 7px; background: var(--surface); color: var(--text); }

  @media (max-width: 920px) {
    .vault-toolbar { padding-inline: 16px; gap: 9px; }
    .vault-nav button { padding-inline: 8px; }
  }
  @media (max-width: 760px) {
    .vault-toolbar { grid-template-columns: minmax(0, 1fr) auto; padding: 10px 13px 8px; }
    .vault-nav { grid-column: 1 / -1; grid-row: 2; }
    .vault-nav button { flex: 1; min-width: 0; gap: 4px; padding-inline: 4px; }
    .vault-nav button :global(svg) { flex: none; }
    .lock-action span { display: none; }
    .lock-action { width: 38px; }
    .desktop-welcome { position: relative; grid-template-columns: minmax(0, 1fr); grid-template-rows: auto 1fr; }
    .welcome-identity { padding: 15px 66px 15px 18px; }
    .identity-brand { display: flex; align-items: center; gap: 11px; }
    .identity-brand :global(img) { width: 35px; height: 35px; }
    .identity-brand p { margin: 0; font-size: 14px; letter-spacing: -.01em; line-height: 1.27; }
    .identity-brand br { display: none; }
    .storage-note { display: none; }
    .welcome-body { padding: 20px 21px 25px; }
    .welcome-header { position: absolute; inset-block-start: 13px; inset-inline-end: 16px; padding: 0; }
    .welcome-header .theme-control { color: #e3edfc; border-color: #667e9f; }
    .welcome-header .theme-control:hover { background: #293d5e; }
    .welcome-header .theme-control:focus-visible { outline-color: #a9c1ff; }
  }
  @media (pointer: coarse) {
    .vault-nav button, .lock-action, .theme-control { min-height: 44px; }
  }
</style>
