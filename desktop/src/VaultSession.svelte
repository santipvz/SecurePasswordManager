<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import { FolderOpen, KeyRound, LockKeyhole, Moon, Plus, Settings, ShieldCheck, Sun } from "@lucide/svelte"
  import { onMount, tick } from "svelte"
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
  let settingsOpen = $state(false)
  let settingsPending = $state(false)
  let settingsButton = $state<HTMLButtonElement>()
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
    settingsOpen = false
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

  async function showSettings(open: boolean) {
    settingsOpen = open
    if (!open) {
      await tick()
      settingsButton?.focus()
    }
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
    void refresh()
    const poll = window.setInterval(() => void checkSession(), 500)
    return () => window.clearInterval(poll)
  })
</script>

<svelte:window onkeydown={activity} onpointerdown={activity} onfocus={checkSession} />

<div class="app" data-theme={theme}>
  <header class="topbar">
    <div class="brand"><span class="brand-icon"><ShieldCheck size={20} /></span> Secure Password Manager</div>
    <div class="top-actions">
      {#if phase === "unlocked"}
        <button class="icon-button" aria-label="Vault settings" aria-pressed={settingsOpen} disabled={settingsPending} bind:this={settingsButton}
          onclick={() => showSettings(!settingsOpen)}><Settings size={19} /></button>
        <button class="secondary" onclick={() => endSession("")}><LockKeyhole size={16} /> Lock vault</button>
      {/if}
      <button class="icon-button" aria-label={theme === "light" ? "Use dark theme" : "Use light theme"}
        onclick={() => theme = theme === "light" ? "dark" : "light"}>
        {#if theme === "light"}<Moon size={19} />{:else}<Sun size={19} />{/if}
      </button>
    </div>
  </header>

  {#if phase === "unlocked" && generation !== undefined}
    {#if settingsOpen}
      <VaultSettings {generation} nativePrompt={Boolean(status?.native_key_prompt)} bind:hasSecurityKey bind:pending={settingsPending}
        onClose={() => showSettings(false)} onLock={endSession} onImport={addImported} />
    {:else}
      <VaultEntries {generation} bind:entries onSessionEnd={endSession} />
    {/if}
  {:else}
    <main class="welcome">
      {#if showGenerator}
        <section class="unlock-card" aria-labelledby="generator-title">
          <h1 id="generator-title" tabindex="-1" bind:this={generatorHeading}>Generate a password</h1>
          <div class="standalone-generator"><PasswordGenerator /></div>
          <button class="text-button full" onclick={() => toggleGenerator(false)}>Back to vault</button>
        </section>
      {:else}
        <section class="unlock-card" aria-labelledby="vault-title">
          <div class="vault-icon"><LockKeyhole size={28} strokeWidth={1.7} /></div>
          <h1 id="vault-title">
            {creating ? "Create a vault" : method === "key" && keyReady ? "Unlock with YubiKey" : "Unlock your vault"}
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
              Enter the master password for <strong>{status.file_name ?? "your default vault"}</strong>.
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
              <form onsubmit={submit} autocomplete="off">
                {#if method === "key" && keyReady}
                  {#if !status?.native_key_prompt}
                    <label class="password-label" for="key-pin">Security key PIN</label>
                    <input class="password-input full" id="key-pin" type="password" bind:this={pinInput}
                      autocomplete="off" autocapitalize="off" spellcheck={false} />
                  {/if}
                  <button class="primary full" type="submit" bind:this={keyButton}><KeyRound size={17} /> Use YubiKey</button>
                {:else}
                  <label class="password-label" for="master-password">Master password</label>
                  <input class="password-input full" id="master-password" type="password" bind:this={passwordInput}
                    autocomplete="off" autocapitalize="off" spellcheck={false} required />
                  {#if creating}
                    <label class="password-label" for="confirm-master">Confirm master password</label>
                    <input class="password-input full" id="confirm-master" type="password" bind:this={confirmationInput}
                      autocomplete="off" autocapitalize="off" spellcheck={false} required />
                  {/if}
                  <button class="primary full" type="submit"><KeyRound size={17} /> {creating ? "Create vault" : "Unlock vault"}</button>
                {/if}
              </form>
              {#if keyReady}
                <button class="secondary full" onclick={() => switchMethod(method === "key" ? "password" : "key")}>
                  {method === "key" ? "Use master password" : "Unlock with YubiKey"}
                </button>
              {/if}
            {/if}
            <div class="welcome-footer">
              <button class="text-button" onclick={() => choose("new")}><Plus size={16} /> {creating ? "Choose new file" : "Create vault"}</button>
              <button class="text-button" bind:this={openButton} onclick={() => choose("existing")}><FolderOpen size={16} /> Open file</button>
            </div>
            <button class="text-button full" bind:this={generatorButton} onclick={() => toggleGenerator(true)}>Password generator</button>
            {#if status?.file_name || !status}
              <button class="text-button full" onclick={() => choose("default")}>Check default location</button>
            {/if}
          {/if}
        </section>
      {/if}
    </main>
  {/if}
</div>

<style>
  .standalone-generator { margin: 16px 0; }
  .password-label { display: block; margin-bottom: 6px; font-weight: 600; }
  .password-input {
    min-height: 43px;
    padding: 9px 12px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: var(--surface);
    color: var(--text);
  }
</style>
