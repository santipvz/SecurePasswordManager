<script lang="ts" module>
  export type ImportedEntry = { name: string; username: string; url: string }
</script>

<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import { ArrowLeft, Archive, FolderOpen, KeyRound, Upload } from "@lucide/svelte"
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
    weak_master: "Use at least 15 characters for the new master password.",
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
  <button class="text-button back" disabled={pending} onclick={onClose}><ArrowLeft size={16} /> Back to entries</button>
  <h1 tabindex="-1" bind:this={heading}>Vault settings</h1>

  {#if notice}<p class="feedback" role="status">{notice}</p>{/if}
  {#if error}<p class="error-note" role="alert">{error}</p>{/if}

  <section aria-labelledby="vault-files-heading">
    <h2 id="vault-files-heading">Backups and import</h2>
    <p class="muted">Open a backup as its own vault. Backups keep the master password and any YubiKey registration they had when saved.</p>
    <div class="actions">
      <button class="secondary" disabled={pending || Boolean(method)} onclick={() => manageFile("save_backup")}><Archive size={17} /> Save encrypted backup</button>
      <button class="secondary" disabled={pending || Boolean(method)} onclick={() => manageFile("open_backup")}><FolderOpen size={17} /> Open backup</button>
    </div>
    <p class="muted">Import legacy .key files as a batch. The original files remain on disk in plaintext.</p>
    <button class="secondary" disabled={pending || Boolean(method)} onclick={() => manageFile("import_legacy")}><Upload size={17} /> Import .key files</button>
  </section>

  <section aria-labelledby="unlock-heading">
    <h2 id="unlock-heading">Unlock methods</h2>
    <p class="muted">
      {hasSecurityKey ? "A YubiKey is registered for this vault." : "This vault uses its master password."}
      Keep your master password for recovery.
    </p>
    {#if method}
      <form onsubmit={updateMethod} autocomplete="off">
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
        <div class="actions">
          <button class="primary" type="submit" disabled={pending}>{labels[method]}</button>
          {#if !pending}
            <button class="secondary" type="button" onclick={resetMethod}>Cancel</button>
          {:else if method === "register_key"}
            <button class="secondary" type="button" onclick={() => onLock("Unlock the vault to continue.")}>Cancel and lock</button>
          {/if}
        </div>
        {#if pending}<p class="feedback" role="status"><span class="spinner"></span> {method === "register_key" ? "Waiting for your security key…" : "Saving changes…"}</p>{/if}
      </form>
    {:else}
      <div class="actions">
        <button class="secondary" disabled={pending} onclick={(event) => chooseMethod("change_master", event.currentTarget)}>Change master password</button>
        <button class="secondary" disabled={pending} onclick={(event) => chooseMethod(hasSecurityKey ? "remove_key" : "register_key", event.currentTarget)}>
          <KeyRound size={17} /> {hasSecurityKey ? "Remove YubiKey" : "Register YubiKey"}
        </button>
      </div>
    {/if}
  </section>
</main>

<style>
  .settings-page { width: min(100%, 780px); margin-inline: auto; padding: 24px; }
  .back { margin: 0 0 8px -8px; }
  h1 { font-size: 30px; margin-bottom: 18px; }
  h2 { font-size: 22px; }
  h3 { margin: 0; font-size: 16px; }
  section { display: grid; justify-items: start; gap: 12px; margin-top: 16px; padding: 20px; background: var(--surface); border: 1px solid var(--line); border-radius: 14px; }
  form { display: grid; width: min(100%, 430px); gap: 12px; }
  label { display: grid; gap: 5px; font-weight: 600; }
  input { width: 100%; font: inherit; font-weight: 400; padding: 8px 10px; color: var(--text); background: var(--surface); border: 1px solid var(--line); border-radius: 9px; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  button:disabled { cursor: default; opacity: .65; }
</style>
