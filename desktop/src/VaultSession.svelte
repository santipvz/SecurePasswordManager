<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import { KeyRound, LockKeyhole, Moon, Search, ShieldCheck, Sun } from "@lucide/svelte"
  import { onMount, tick } from "svelte"

  type Status = { exists: boolean; has_security_key: boolean; generation: number }
  type Unlocked = { generation: number }
  type Entry = { name: string; username: string; url: string }
  type Entries = { entries: Entry[] }
  type Phase = "loading" | "locked" | "unlocking" | "unlocked" | "locking"

  const messages: Record<string, string> = {
    busy: "The vault is busy. Try again in a moment.",
    input_too_large: "The master password exceeds the supported length.",
    open_failed: "Could not unlock the vault. Check the master password and try again.",
    file_error: "Could not access the default vault file.",
    process_unavailable: "Could not start the vault process.",
    timed_out: "The vault process timed out. Try again.",
  }

  let phase = $state<Phase>("loading")
  let theme = $state<"light" | "dark">("light")
  let status = $state<Status>()
  let generation = $state<number>()
  let entries = $state<Entry[]>([])
  let search = $state("")
  let feedback = $state("")
  let passwordInput = $state<HTMLInputElement>()
  let searchInput = $state<HTMLInputElement>()
  let revision = 0
  let lastActivity = -Infinity

  const matches = $derived(entries.filter((entry) =>
    [entry.name, entry.username, entry.url].some((text) =>
      text.toLowerCase().includes(search.trim().toLowerCase()),
    ),
  ))

  function errorMessage(error: unknown) {
    return typeof error === "string" && Object.hasOwn(messages, error)
      ? messages[error]
      : "The vault session ended. Unlock the vault to try again."
  }

  async function refresh() {
    const current = ++revision
    phase = "loading"
    status = undefined
    feedback = ""
    try {
      const result = await invoke<Status>("vault_status")
      if (revision === current) status = result
    } catch (error) {
      if (revision === current) feedback = errorMessage(error)
    } finally {
      if (revision === current) phase = "locked"
    }
    await tick()
    if (revision === current) passwordInput?.focus()
  }

  async function endSession(message: string) {
    const current = ++revision
    generation = undefined
    entries = []
    search = ""
    if (passwordInput) passwordInput.value = ""
    phase = "locking"
    feedback = message
    try {
      const next = await invoke<number>("vault_lock")
      if (revision === current && status) status.generation = next
    } catch {
      if (revision === current) feedback = "Could not confirm the lock. Close and reopen the app."
      return
    }
    if (revision !== current) return
    phase = "locked"
    await tick()
    if (revision === current) passwordInput?.focus()
  }

  async function unlock(event: SubmitEvent) {
    event.preventDefault()
    if (phase !== "locked" || !status || !passwordInput?.value) return
    const current = ++revision
    feedback = ""
    phase = "unlocking"
    try {
      // Pass the value directly to IPC. Clear the input before awaiting the reply.
      const input = passwordInput
      let pending: Promise<Unlocked>
      try {
        pending = invoke<Unlocked>("vault_unlock", { generation: status.generation, master: input.value })
      } finally {
        input.value = ""
      }
      const session = await pending
      if (revision !== current) return
      const metadata = await invoke<Entries>("vault_list", { generation: session.generation })
      if (revision !== current) return
      if (!await invoke<boolean>("vault_active", { generation: session.generation })) {
        throw "locked"
      }
      if (revision !== current) return
      generation = session.generation
      lastActivity = -Infinity
      entries = metadata.entries
      phase = "unlocked"
      await tick()
      if (revision === current) searchInput?.focus()
    } catch (error) {
      if (revision === current) await endSession(errorMessage(error))
    }
  }

  function activity(event: KeyboardEvent | PointerEvent) {
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
        <button class="secondary" onclick={() => endSession("")}><LockKeyhole size={16} /> Lock vault</button>
      {/if}
      <button class="icon-button" aria-label={theme === "light" ? "Use dark theme" : "Use light theme"}
        onclick={() => theme = theme === "light" ? "dark" : "light"}>
        {#if theme === "light"}<Moon size={19} />{:else}<Sun size={19} />{/if}
      </button>
    </div>
  </header>

  {#if phase === "unlocked"}
    <main class="collection live-collection">
      <div class="collection-heading">
        <h1>Vault entries</h1>
        <p class="muted">{entries.length} {entries.length === 1 ? "entry" : "entries"}</p>
      </div>
      <label class="search-box">
        <Search size={17} />
        <input type="search" bind:this={searchInput} bind:value={search} aria-label="Search vault entries" placeholder="Search entries" />
      </label>
      {#if matches.length}
        <ul class="entries live-entries">
          {#each matches as entry}
            <li>
              <strong>{entry.name}</strong>
              {#if entry.username}<span>{entry.username}</span>{/if}
              {#if entry.url}<span>{entry.url}</span>{/if}
            </li>
          {/each}
        </ul>
      {:else}
        <p class="empty">{entries.length ? "No matching entries." : "This vault has no entries."}</p>
      {/if}
    </main>
  {:else}
    <main class="welcome">
      <section class="unlock-card" aria-labelledby="vault-title">
        <div class="vault-icon"><LockKeyhole size={28} strokeWidth={1.7} /></div>
        <h1 id="vault-title">Unlock your vault</h1>
        <p class="muted welcome-copy">
          {#if status?.exists && status.has_security_key}
            A security key is registered for this vault. Use your master password to unlock it here.
          {:else if status?.exists}
            Enter the master password for your local vault.
          {:else if status}
            Use the Python app to create a vault in the default location, then check again.
          {:else}
            Secure Password Manager will check for a vault in the default location.
          {/if}
        </p>
        {#if feedback}<p class="error-note" role="alert">{feedback}</p>{/if}
        {#if phase === "loading"}
          <div class="unlock-state" role="status"><span class="spinner"></span> Checking for a vault…</div>
        {:else if phase === "locking"}
          {#if !feedback}<p role="status">Locking vault…</p>{/if}
        {:else if status?.exists}
          <form onsubmit={unlock} autocomplete="off">
            <label class="password-label" for="master-password">Master password</label>
            <input class="password-input full" id="master-password" type="password" bind:this={passwordInput}
              autocomplete="off" autocapitalize="off" spellcheck={false} required disabled={phase === "unlocking"} />
            {#if phase === "unlocking"}
              <div class="unlock-state" role="status"><span class="spinner"></span> Unlocking vault…</div>
              <button class="secondary full" type="button" onclick={() => endSession("")}>Cancel</button>
            {:else}
              <button class="primary full" type="submit"><KeyRound size={17} /> Unlock vault</button>
            {/if}
          </form>
        {:else}
          <button class="secondary full" onclick={refresh}>Check again</button>
        {/if}
      </section>
    </main>
  {/if}
</div>

<style>
  .password-label { display: block; margin-bottom: 6px; font-weight: 600; }
  .password-input {
    min-height: 43px;
    padding: 9px 12px;
    border: 1px solid var(--line);
    border-radius: 9px;
    background: var(--surface);
    color: var(--text);
  }
  .live-collection { max-width: 820px; margin-inline: auto; }
  .live-entries li {
    display: grid;
    gap: 2px;
    padding: 12px 8px;
    border-bottom: 1px solid var(--line);
    overflow-wrap: anywhere;
  }
  .live-entries li span { color: var(--muted); }
</style>
