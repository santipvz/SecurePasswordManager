<script lang="ts" module>
  export type ImportedEntry = { name: string; username: string; url: string }
</script>

<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import { ArrowLeft, Archive, Check, CircleAlert, FolderOpen, KeyRound, Upload } from "@lucide/svelte"
  import { onMount, tick } from "svelte"

  type FileAction = "save_backup" | "open_backup" | "import_legacy"
  type FileResult = { action: "saved" | "selected_backup" } | { action: "imported"; entries: { entries: ImportedEntry[] } }
  type UnlockAction = "change_master" | "register_key" | "remove_key"

  let { generation, nativePrompt, hasSecurityKey = $bindable(), pending = $bindable(), onClose, onLock, onImport }: {
    generation: number
    nativePrompt: boolean
    hasSecurityKey: boolean
    pending: boolean
    onClose: () => void
    onLock: (message: string) => Promise<void>
    onImport: (entries: ImportedEntry[]) => void
  } = $props()

  const labels: Record<UnlockAction, string> = {
    change_master: "Change master password",
    register_key: "Register YubiKey",
    remove_key: "Remove YubiKey",
  }
  const errors: Record<string, string> = {
    busy: "The vault is busy. Try again.",
    invalid_file: "Choose a valid .spm file.",
    dialog_failed: "Could not open the file dialog.",
    input_too_large: "The request is too large. Try selecting fewer files or using a shorter password.",
    backup_failed: "Could not save the backup. Choose a new filename in a writable folder.",
    invalid_import: "Select .key files.",
    import_count: "Select up to 64 .key files at a time.",
    import_failed: "Could not read all selected .key files. Check their format and permissions.",
    entry_duplicate: "An imported name conflicts with another credential. Rename the .key file and retry.",
    write_conflict: "The vault changed in another app. Lock and reopen it before trying again.",
    incorrect_master: "The current master password is incorrect.",
    weak_master: "Choose a less predictable master password of at least 15 characters.",
    already_registered: "A YubiKey is already registered.",
    no_registered_key: "There is no YubiKey registered for this vault.",
    key_disconnected: "Connect your YubiKey and check that the system can access it.",
    key_failed: "Could not register the key. Check the connection and try again.",
    key_interrupted: "The security key request timed out or was cancelled.",
    key_setup_required: "Set a FIDO2 PIN on the key before trying again.",
    key_unsupported: "The key or system lacks the required FIDO2 features.",
    multiple_keys: "Connect only the key you want to register.",
    pin_invalid: "The security key PIN is incorrect.",
    pin_required: "Enter your security key PIN.",
    pin_blocked: "The key PIN is blocked. Reconnect the key or check its PIN settings.",
  }
  const failedSession = ["locked", "write_failed", "timed_out", "communication_failed", "process_unavailable"]

  let method = $state<UnlockAction>()
  let notice = $state("")
  let error = $state("")
  let heading: HTMLHeadingElement
  let master = $state<HTMLInputElement>()
  let replacement = $state<HTMLInputElement>()
  let confirm = $state<HTMLInputElement>()
  let pin = $state<HTMLInputElement>()
  let returnButton: HTMLButtonElement | undefined
  let revision = 0

  function clearInputs() {
    for (const field of [master, replacement, confirm, pin]) {
      if (field) field.value = ""
    }
  }

  function fail(reason: unknown) {
    const code = typeof reason === "string" ? reason : ""
    if (failedSession.includes(code)) {
      void onLock("The vault session ended. Reopen it to verify any pending changes.")
    } else {
      error = Object.hasOwn(errors, code) ? errors[code] : "Could not complete the vault request."
    }
  }

  async function manageFile(action: FileAction) {
    if (pending || method) return
    const current = ++revision
    pending = true
    notice = error = ""
    try {
      const result = await invoke<FileResult | null>("vault_manage_files", { generation, action })
      if (current !== revision || !result) return
      switch (result.action) {
        case "saved":
          notice = "Encrypted backup saved."
          break
        case "selected_backup":
          await onLock("Unlock the selected backup to open it.")
          break
        case "imported":
          onImport(result.entries.entries)
          const count = result.entries.entries.length
          notice = `Imported ${count} ${count === 1 ? "credential" : "credentials"}.`
          break
      }
    } catch (reason) {
      if (current === revision) fail(reason)
    } finally {
      if (current === revision) pending = false
    }
  }

  async function chooseMethod(action: UnlockAction, button: HTMLButtonElement) {
    if (pending) return
    returnButton = button
    method = action
    notice = error = ""
    await tick()
    master?.focus()
  }

  async function resetMethod() {
    clearInputs()
    method = undefined
    await tick()
    if (returnButton?.isConnected) returnButton.focus()
    else heading?.focus()
  }

  function validReplacement() {
    const value = replacement?.value ?? ""
    return Array.from(value).length >= 15 && Boolean(value.trim())
  }

  async function updateMethod(event: SubmitEvent) {
    event.preventDefault()
    if (pending || !method || !master?.value) return
    const action = method
    if (action === "change_master" && !validReplacement()) {
      error = errors.weak_master
      replacement?.focus()
      return
    }
    if (action === "change_master" && replacement?.value !== confirm?.value) {
      error = "The new master passwords do not match."
      confirm?.focus()
      return
    }

    const current = ++revision
    pending = true
    notice = error = ""
    try {
      let operation: Promise<{ has_security_key: boolean }>
      try {
        operation = sendUnlockChange(action)
      } finally {
        clearInputs()
      }
      const result = await operation
      if (current !== revision) return
      hasSecurityKey = result.has_security_key
      if (action === "change_master") {
        await onLock("Master password changed. Unlock with your new password.")
      } else {
        notice = action === "register_key" ? "YubiKey registered." : "YubiKey removed from this vault."
        await resetMethod()
      }
    } catch (reason) {
      if (current === revision) fail(reason)
    } finally {
      if (current === revision) {
        pending = false
        await tick()
        if (method) master?.focus()
      }
    }
  }

  function sendUnlockChange(action: UnlockAction) {
    const currentMaster = master?.value
    const request = action === "change_master"
      ? { action, master: currentMaster, new_master: replacement?.value }
      : action === "register_key"
        ? { action, master: currentMaster, pin: pin?.value || undefined }
        : { action, master: currentMaster }
    return invoke<{ has_security_key: boolean }>("vault_manage_unlock", { generation, request })
  }

  function shortcuts(event: KeyboardEvent) {
    if (event.key !== "Escape" || pending) return
    event.preventDefault()
    event.stopImmediatePropagation()
    if (method) void resetMethod()
    else onClose()
  }

  onMount(() => {
    heading.focus()
    return () => { revision++; clearInputs(); pending = false }
  })
</script>

<svelte:window onkeydown={shortcuts} />

<main class="settings-page">
  <button class="text-button back" disabled={pending} onclick={onClose}><ArrowLeft size={16} /> Back to credentials</button>
  <header class="page-header">
    <h1 tabindex="-1" bind:this={heading}>Vault settings</h1>
    <p class="muted">Manage backups, imports, and how this vault unlocks.</p>
  </header>

  {#if notice}<p class="feedback notice" role="status"><Check size={15} /> {notice}</p>{/if}
  {#if error}<p class="error-note" role="alert"><CircleAlert size={16} /> <span>{error}</span></p>{/if}

  <section aria-labelledby="vault-files-heading">
    <h2 id="vault-files-heading">Backups and import</h2>
    <div class="card">
      <div class="setting-row">
        <div class="row-text"><h3>Encrypted backups</h3><p class="muted">Backups keep the master password and YubiKey registration used when they were saved.</p></div>
        <div class="actions">
          <button class="secondary" disabled={pending || Boolean(method)} onclick={() => manageFile("save_backup")}><Archive size={15} /> Save backup</button>
          <button class="secondary" disabled={pending || Boolean(method)} onclick={() => manageFile("open_backup")}><FolderOpen size={15} /> Open backup</button>
        </div>
      </div>
      <div class="setting-row">
        <div class="row-text"><h3>Legacy credentials</h3><p class="muted">The original .key files remain on disk in plaintext after import.</p></div>
        <div class="actions">
          <button class="secondary" disabled={pending || Boolean(method)} onclick={() => manageFile("import_legacy")}><Upload size={15} /> Import .key files</button>
        </div>
      </div>
    </div>
  </section>

  <section aria-labelledby="unlock-heading">
    <h2 id="unlock-heading">Unlock methods</h2>
    <div class="card">
      {#if method}
        <form onsubmit={updateMethod} autocomplete="off">
          <div class="form-intro">
            <h3>{labels[method]}</h3>
            {#if method === "change_master"}
              <p class="muted">
                Use at least 15 characters. Changing the master password removes any YubiKey registration from the active vault.
                Older backups still use their previous unlock methods.
              </p>
            {:else if method === "remove_key"}
              <p class="muted">After removal, use your master password for this vault. Older backups can still accept their registered key.</p>
            {:else}
              <p class="muted">
                {nativePrompt ? "Connect the YubiKey and follow the Windows security prompts."
                  : "Connect the YubiKey and touch it when it blinks. Registration may ask for a second touch."}
              </p>
            {/if}
          </div>
          <label>Current master password
            <input type="password" bind:this={master} required disabled={pending} autocomplete="off" spellcheck={false} />
          </label>
          {#if method === "change_master"}
            <label>New master password
              <input type="password" bind:this={replacement} required disabled={pending} autocomplete="off" spellcheck={false} />
            </label>
            <label>Confirm new master password
              <input type="password" bind:this={confirm} required disabled={pending} autocomplete="off" spellcheck={false} />
            </label>
          {:else if method === "register_key" && !nativePrompt}
            <label>Security key PIN
              <input type="password" bind:this={pin} disabled={pending} autocomplete="off" spellcheck={false} />
            </label>
          {/if}
          {#if pending}<p class="feedback" role="status"><span class="spinner"></span> {method === "register_key" ? "Waiting for your security key…" : "Saving changes…"}</p>{/if}
          <div class="actions">
            {#if !pending}
              <button class="secondary" type="button" onclick={resetMethod}>Cancel</button>
            {:else if method === "register_key"}
              <button class="secondary" type="button" onclick={() => onLock("Unlock the vault to continue.")}>Cancel and lock</button>
            {/if}
            <button class={method === "remove_key" ? "danger" : "primary"} type="submit" disabled={pending}>{labels[method]}</button>
          </div>
        </form>
      {:else}
        <div class="setting-row">
          <div class="row-text"><h3>Master password</h3><p class="muted">Keep your master password for recovery.</p></div>
          <div class="actions">
            <button class="secondary" disabled={pending} onclick={(event) => chooseMethod("change_master", event.currentTarget)}>Change master password</button>
          </div>
        </div>
        <div class="setting-row">
          <div class="row-text">
            <h3>YubiKey</h3>
            <p class="muted">{hasSecurityKey ? "Registered. You can unlock this vault with the key." : "Use a security key to unlock this vault."}</p>
          </div>
          <div class="actions">
            <button class="secondary" disabled={pending} onclick={(event) => chooseMethod(hasSecurityKey ? "remove_key" : "register_key", event.currentTarget)}>
              <KeyRound size={15} /> {hasSecurityKey ? "Remove YubiKey" : "Register YubiKey"}
            </button>
          </div>
        </div>
      {/if}
    </div>
  </section>
</main>

<style>
  .settings-page { width: min(100%, 760px); margin-inline: auto; padding: clamp(20px, 5vw, 44px) clamp(18px, 4vw, 32px) 48px; }
  .back { margin: 0 0 4px -10px; }
  .page-header { margin: 4px 0 26px; }
  h1 { font-size: clamp(24px, 3vw, 28px); }
  .page-header p { margin-top: 6px; }
  h2 { margin: 0 0 10px; font-size: 15px; font-weight: 600; letter-spacing: -.01em; }
  h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 14px; font-weight: 600; }
  section + section { margin-top: 28px; }
  .card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .setting-row { display: flex; align-items: center; flex-wrap: wrap; gap: 12px 14px; padding: 16px; }
  .setting-row + .setting-row { border-top: 1px solid var(--line); }
  .row-text { flex: 1 1 260px; min-width: 0; }
  .row-text p { margin-top: 2px; font-size: 13px; line-height: 1.5; }
  .notice { margin-bottom: 16px; color: var(--success); font-weight: 500; }
  form { display: grid; gap: 14px; padding: 18px; max-width: 480px; }
  .form-intro p { margin-top: 4px; font-size: 13px; line-height: 1.55; }
  label { display: grid; gap: 6px; font-size: 13px; font-weight: 500; }
  input {
    min-width: 0;
    width: 100%;
    min-height: 40px;
    font: inherit;
    font-weight: 400;
    padding: 8px 11px;
    color: var(--text);
    background: var(--control-bg);
    border: 1px solid var(--control-line);
    border-radius: var(--radius-sm);
    transition: border-color .15s var(--ease), box-shadow .15s var(--ease);
  }
  form input:focus-visible { outline: none; border-color: var(--focus); box-shadow: var(--focus-ring); }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  form .actions { justify-content: flex-end; margin-top: 4px; }
</style>
