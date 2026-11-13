<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import { ArrowLeft, ChevronDown, ChevronRight, Copy, Eye, EyeOff, Pencil, Plus, Search, ShieldCheck, Trash2 } from "@lucide/svelte"
  import { onMount, tick } from "svelte"
  import PasswordGenerator from "./PasswordGenerator.svelte"
  import PasswordReview, { type Review } from "./PasswordReview.svelte"

  type Entry = { name: string; username: string; url: string }

  let { generation, entries = $bindable(), writing = $bindable(), onSessionEnd }: {
    generation: number
    entries: Entry[]
    writing: boolean
    onSessionEnd: (message: string) => Promise<void>
  } = $props()

  const pageSize = 100
  const revealLifetime = 10_000
  const messages: Record<string, string> = {
    busy: "The vault is busy. Try again.",
    entry_missing: "This credential no longer exists.",
    entry_duplicate: "A credential with this name already exists.",
    entry_invalid: "Enter a name and password.",
    input_too_large: "This credential is too large to save.",
    write_conflict: "The vault changed in another app. Lock and reopen it before saving.",
    write_failed: "Could not confirm the save. Reopen the vault to check whether it was applied.",
    clipboard_unavailable: "Could not copy the password to the clipboard.",
    clipboard_unsupported: "This password contains characters the system clipboard cannot preserve.",
    timed_out: "The vault process timed out. Reopen the vault to check your changes.",
  }

  let generatorOpen = $state(false)
  let reviewOpen = $state(false)
  let reviewPending = $state(false)
  let review = $state<Review>()
  let reviewError = $state("")
  let reviewButton = $state<HTMLButtonElement>()
  let search = $state("")
  let limit = $state(pageSize)
  let selected = $state<Entry>()
  let notes = $state<string>()
  let revealed = $state<string>()
  let revealTimer: ReturnType<typeof setTimeout> | undefined
  let editor = $state<"add" | "edit">()
  let confirmation = $state(false)
  let busy = $state(false)
  let conflict = $state(false)
  let notesEdited = false
  let feedback = $state("")
  let error = $state("")
  let searchInput = $state<HTMLInputElement>()
  let nameInput = $state<HTMLInputElement>()
  let passwordInput = $state<HTMLInputElement>()
  let generatorToggle = $state<HTMLButtonElement>()
  let detailHeading = $state<HTMLHeadingElement>()
  let cancelDelete = $state<HTMLButtonElement>()
  let lastEntryButton: HTMLButtonElement | undefined
  let viewRevision = 0
  let secretRevision = 0

  const searchIndex = $derived(entries.map((entry) => ({
    entry, fields: [entry.name.toLowerCase(), entry.username.toLowerCase(), entry.url.toLowerCase()],
  })))
  const matches = $derived.by(() => {
    const query = search.trim().toLowerCase()
    return query ? searchIndex.filter(({ fields }) => fields.some((text) => text.includes(query))) : searchIndex
  })

  function hidePassword() {
    secretRevision++
    clearTimeout(revealTimer)
    revealTimer = undefined
    revealed = undefined
  }

  function clearView() {
    viewRevision++
    hidePassword()
    if (passwordInput) passwordInput.value = ""
    editor = undefined
    generatorOpen = false
    reviewOpen = false
    review = undefined
    reviewError = ""
    confirmation = false
    notes = undefined
    feedback = ""
    error = ""
  }

  async function focusSearch() {
    clearView()
    selected = undefined
    await tick()
    searchInput?.focus()
  }

  async function closeDetails() {
    clearView()
    selected = undefined
    await tick()
    if (lastEntryButton?.isConnected) lastEntryButton.focus()
    else searchInput?.focus()
  }

  function updateSearch(event: Event & { currentTarget: HTMLInputElement }) {
    clearView()
    selected = undefined
    search = event.currentTarget.value
    limit = pageSize
  }

  function endsSession(reason: unknown) {
    return typeof reason === "string"
      && ["locked", "write_failed", "timed_out", "communication_failed", "process_unavailable"].includes(reason)
  }

  function handleError(reason: unknown) {
    const code = typeof reason === "string" ? reason : ""
    const message = Object.hasOwn(messages, code) ? messages[code] : "Could not complete the vault request."
    if (code === "write_conflict") conflict = true
    if (endsSession(code)) {
      void onSessionEnd(message)
    } else {
      error = message
    }
  }

  async function showDetails(entry: Entry, button?: HTMLButtonElement, focusDetail = false) {
    clearView()
    selected = entry
    lastEntryButton = button
    const current = viewRevision
    busy = true
    await tick()
    if (current !== viewRevision) return
    if (focusDetail || matchMedia("(max-width: 760px)").matches) detailHeading?.focus()
    try {
      const result = await invoke<string>("vault_entry_notes", { generation, name: entry.name })
      if (current === viewRevision) notes = result
    } catch (reason) {
      if (current === viewRevision) handleError(reason)
    } finally {
      busy = false
    }
  }

  async function runReview() {
    if (busy || editor || reviewPending) return
    clearView()
    selected = undefined
    reviewOpen = true
    reviewPending = true
    const current = viewRevision
    try {
      const findings = await invoke<Review>("vault_review", { generation })
      if (current === viewRevision) review = findings
    } catch (reason) {
      if (current !== viewRevision) return
      if (endsSession(reason)) {
        handleError(reason)
      } else {
        reviewError = reason === "busy" ? messages.busy : "Could not review this vault. Try again."
      }
    } finally {
      reviewPending = false
    }
  }

  async function closeReview() {
    clearView()
    await tick()
    reviewButton?.focus()
  }

  function selectFinding(name: string) {
    const entry = entries.find((entry) => entry.name === name)
    if (entry) {
      search = ""
      limit = pageSize
      void showDetails(entry, undefined, true)
    }
  }

  async function dismissGenerator() {
    generatorOpen = false
    await tick()
    generatorToggle?.focus()
  }

  async function useGenerated(password: string) {
    if (!passwordInput) return
    passwordInput.value = password
    generatorOpen = false
    await tick()
    passwordInput?.focus()
  }

  async function revealPassword() {
    if (revealed !== undefined) {
      hidePassword()
      return
    }
    if (busy || !selected) return
    const current = viewRevision
    const request = ++secretRevision
    feedback = ""
    error = ""
    busy = true
    try {
      const value = await invoke<string>("vault_reveal", { generation, name: selected.name })
      if (request !== secretRevision || current !== viewRevision || document.hidden) return
      if (!await invoke<boolean>("vault_active", { generation })) return
      if (request !== secretRevision || current !== viewRevision || document.hidden) return
      revealed = value
      revealTimer = setTimeout(hidePassword, revealLifetime)
    } catch (reason) {
      if (current === viewRevision) handleError(reason)
    } finally {
      busy = false
    }
  }

  async function copyPassword() {
    if (busy || !selected) return
    const current = viewRevision
    feedback = ""
    error = ""
    busy = true
    try {
      await invoke("vault_copy", { generation, name: selected.name })
      if (current === viewRevision) feedback = "Password copied for 30 seconds."
    } catch (reason) {
      if (current === viewRevision) handleError(reason)
    } finally {
      busy = false
    }
  }

  async function openEditor(mode: "add" | "edit") {
    if (busy || conflict) return
    hidePassword()
    viewRevision++
    error = ""
    feedback = ""
    confirmation = false
    reviewOpen = false
    review = undefined
    editor = mode
    notesEdited = false
    if (mode === "add") {
      selected = undefined
      notes = undefined
    }
    await tick()
    nameInput?.focus()
  }

  async function closeEditor() {
    if (passwordInput) passwordInput.value = ""
    editor = undefined
    generatorOpen = false
    viewRevision++
    error = ""
    await tick()
    if (selected) detailHeading?.focus()
    else searchInput?.focus()
  }

  async function saveEntry(event: SubmitEvent & { currentTarget: HTMLFormElement }) {
    event.preventDefault()
    if (busy || conflict || !editor || !passwordInput) return
    const current = viewRevision
    const previous = editor === "edit" ? selected?.name : undefined
    const form = event.currentTarget
    const readField = (field: string) => {
      const element = form.elements.namedItem(field)
      return element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement ? element.value : ""
    }
    const updatedNotes = notesEdited || editor === "add" ? readField("notes") : notes ?? ""
    const input = passwordInput
    feedback = ""
    error = ""
    writing = busy = true
    try {
      let pending: Promise<Entry>
      try {
        pending = invoke<Entry>("vault_save", {
          generation,
          entry: {
            previous,
            name: readField("name"),
            username: readField("username"),
            url: readField("url"),
            notes: updatedNotes,
            password: input.value || undefined,
          },
        })
      } finally {
        input.value = ""
      }
      const saved = await pending
      if (current !== viewRevision) return
      entries = [...entries.filter((entry) => entry.name !== previous), saved]
        .sort((left, right) => left.name.localeCompare(right.name))
      search = ""
      limit = pageSize
      editor = undefined
      generatorOpen = false
      selected = saved
      notes = updatedNotes
      feedback = "Credential saved."
      await tick()
      detailHeading?.focus()
    } catch (reason) {
      if (current === viewRevision) handleError(reason)
    } finally {
      if (current === viewRevision) writing = false
      busy = false
    }
  }

  async function askDelete() {
    hidePassword()
    error = ""
    feedback = ""
    confirmation = true
    await tick()
    cancelDelete?.focus()
  }

  async function keepEntry() {
    confirmation = false
    await tick()
    detailHeading?.focus()
  }

  async function deleteEntry() {
    if (busy || conflict || !selected) return
    const current = viewRevision
    const name = selected.name
    feedback = ""
    error = ""
    writing = busy = true
    try {
      await invoke("vault_delete", { generation, name })
      if (current !== viewRevision) return
      entries = entries.filter((entry) => entry.name !== name)
      writing = false
      await focusSearch()
      feedback = "Credential deleted."
    } catch (reason) {
      if (current === viewRevision) handleError(reason)
    } finally {
      if (current === viewRevision) writing = false
      busy = false
    }
  }

  function shortcuts(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault()
      if (!editor && !busy) void focusSearch()
    }
    if (event.key !== "Escape") return
    if (revealed !== undefined || (busy && selected && !editor)) hidePassword()
    else if (reviewOpen) void closeReview()
    else if (generatorOpen) void dismissGenerator()
    else if (!busy && editor) void closeEditor()
    else if (!busy && confirmation) void keepEntry()
    else if (!busy && selected) void closeDetails()
  }

  onMount(() => {
    searchInput?.focus()
    return () => {
      writing = false
      clearView()
    }
  })
</script>

<svelte:window onkeydown={shortcuts} onblur={hidePassword} onpagehide={hidePassword} />
<svelte:document onvisibilitychange={hidePassword} />

<main class="credential-workspace" class:detail-open={selected || editor || reviewOpen}>
  <section class="collection" aria-labelledby="entry-list-heading">
    <div class="collection-heading entry-heading">
      <div>
        <h1 id="entry-list-heading">Vault entries</h1>
        <p class="muted" aria-live="polite">{matches.length} {matches.length === 1 ? "entry" : "entries"}</p>
      </div>
      <button class="primary" disabled={busy || conflict || reviewPending} onclick={() => openEditor("add")}><Plus size={17} /> Add entry</button>
    </div>
    <label class="search-box">
      <Search size={17} />
      <input type="search" bind:this={searchInput} value={search} oninput={updateSearch}
        readonly={Boolean(editor) || busy || reviewPending} aria-label="Search vault entries" placeholder="Search entries" />
    </label>
    <button class="text-button review-action" bind:this={reviewButton} disabled={busy || Boolean(editor) || reviewPending}
      onclick={runReview}><ShieldCheck size={17} /> Review passwords</button>
    {#if !selected && !editor && feedback}<p class="feedback" role="status">{feedback}</p>{/if}
    {#if conflict && !selected && !editor}<p class="error-note" role="alert">{messages.write_conflict}</p>{/if}
    {#if matches.length}
      <ul class="entries">
        {#each matches.slice(0, limit) as { entry } (entry.name)}
          <li>
            <button class:chosen={selected?.name === entry.name} aria-pressed={selected?.name === entry.name}
              aria-disabled={Boolean(editor) || busy || reviewPending}
              onclick={(event) => { if (!editor && !busy && !reviewPending) void showDetails(entry, event.currentTarget) }}>
              <span class="entry-mark">{entry.name.slice(0, 1).toUpperCase()}</span>
              <span class="entry-text">
                <strong>{entry.name}</strong>
                {#if entry.username || entry.url}<span>{entry.username || entry.url}</span>{/if}
              </span>
              <ChevronRight size={16} class="entry-arrow" />
            </button>
          </li>
        {/each}
      </ul>
      {#if matches.length > limit}
        <button class="secondary more" onclick={() => limit += pageSize}>Show more <ChevronDown size={16} /></button>
      {/if}
    {:else}
      <p class="empty">{entries.length ? "No matching entries." : "This vault has no entries."}</p>
    {/if}
  </section>

  <section class="detail" aria-label="Credential details">
    {#if reviewOpen}
      <PasswordReview result={review} pending={reviewPending} error={reviewError}
        onClose={closeReview} onEntry={selectFinding} />
    {:else if editor}
      <h2>{editor === "add" ? "Add credential" : "Edit credential"}</h2>
      <form class="credential-form" onsubmit={saveEntry} autocomplete="off">
        <label>Name <input name="name" value={selected?.name ?? ""} bind:this={nameInput} required /></label>
        <label>Username <input name="username" value={selected?.username ?? ""} autocomplete="off" /></label>
        <label>Website <input name="url" value={selected?.url ?? ""} inputmode="url" /></label>
        <label>
          {editor === "edit" ? "New password" : "Password"}
          <input type="password" bind:this={passwordInput} required={editor === "add"}
            autocomplete="off" autocapitalize="off" spellcheck={false} />
          {#if editor === "edit"}<small>Leave blank to keep the saved password.</small>{/if}
        </label>
        <button class="secondary generator-toggle" type="button" bind:this={generatorToggle} aria-expanded={generatorOpen}
          onclick={() => generatorOpen = !generatorOpen}>{generatorOpen ? "Hide generator" : "Open password generator"}</button>
        {#if generatorOpen}<PasswordGenerator {generation} onUse={useGenerated} />{/if}
        <label>Notes <textarea name="notes" value={notes ?? ""} rows="3" oninput={() => notesEdited = true}></textarea></label>
        <div class="detail-actions">
          <button class="primary" type="submit" disabled={busy || conflict}>Save credential</button>
          <button class="secondary" type="button" disabled={busy} onclick={closeEditor}>Cancel</button>
        </div>
      </form>
    {:else if selected}
      <button class="text-button detail-back" disabled={busy} onclick={closeDetails}><ArrowLeft size={16} /> Back to entries</button>
      <div class="detail-heading">
        <h2 tabindex="-1" bind:this={detailHeading}>{selected.name}</h2>
      </div>
      <dl>
        {#if selected.username}<div><dt>Username</dt><dd>{selected.username}</dd></div>{/if}
        {#if selected.url}<div><dt>Website</dt><dd>{selected.url}</dd></div>{/if}
        <div>
          <dt>Password</dt>
          <dd class="password-row">
            <span class="password-text" aria-label={revealed === undefined ? "Password hidden" : undefined}>{revealed ?? "••••••••••"}</span>
            <div class="detail-actions">
              <button class="icon-button" aria-label={revealed === undefined ? "Reveal password" : "Hide password"}
                disabled={busy || confirmation} onclick={revealPassword}>
                {#if revealed === undefined}<Eye size={18} />{:else}<EyeOff size={18} />{/if}
              </button>
              <button class="icon-button" aria-label="Copy password" disabled={busy || confirmation} onclick={copyPassword}><Copy size={17} /></button>
            </div>
          </dd>
        </div>
        {#if notes}<div><dt>Notes</dt><dd class="notes">{notes}</dd></div>{/if}
      </dl>
      {#if confirmation}
        <div class="delete-confirmation">
          <p>Delete this credential from the vault?</p>
          <div class="detail-actions">
            <button class="secondary" bind:this={cancelDelete} disabled={busy} onclick={keepEntry}>Keep credential</button>
            <button class="danger" disabled={busy || conflict} onclick={deleteEntry}>Delete credential</button>
          </div>
        </div>
      {:else}
        <div class="detail-actions">
          <button class="secondary" disabled={busy || conflict || notes === undefined} onclick={() => openEditor("edit")}><Pencil size={15} /> Edit</button>
          <button class="text-button delete-link" disabled={busy || conflict} onclick={askDelete}><Trash2 size={16} /> Delete</button>
        </div>
      {/if}
    {:else}
      <p class="detail-empty">Select a credential to view its details.</p>
    {/if}
    {#if error || (conflict && (selected || editor))}
      <p class="error-note entry-feedback" role="alert">{error || messages.write_conflict}</p>
    {/if}
    {#if (selected || editor) && feedback}<p class="feedback" role="status">{feedback}</p>{/if}
  </section>
</main>

<style>
  .credential-workspace {
    display: grid;
    grid-template-columns: minmax(300px, .9fr) minmax(320px, 1fr);
    min-height: calc(100vh - 68px);
  }
  .entry-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .entry-heading .primary { flex: none; }
  .review-action { margin-bottom: 8px; }
  .generator-toggle { justify-self: start; }
  .credential-form { display: grid; gap: 13px; margin-top: 20px; }
  .credential-form label { display: grid; gap: 5px; font-weight: 600; }
  .credential-form small { color: var(--muted); font-weight: 400; }
  .credential-form input, .credential-form textarea {
    width: 100%; min-width: 0; font: inherit; font-weight: 400; color: var(--text);
    background: var(--surface); border: 1px solid var(--line); border-radius: 9px; padding: 9px 11px;
  }
  .credential-form textarea { resize: vertical; }
  .password-text, .notes { white-space: pre-wrap; overflow-wrap: anywhere; }
  .password-text { font-family: ui-monospace, monospace; }
  .detail-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .password-row .detail-actions { flex-wrap: nowrap; flex: none; }
  .more, .entry-feedback { margin-top: 13px; }
  .entry-feedback { position: sticky; bottom: 12px; }
  .delete-confirmation { display: grid; gap: 10px; }
  .delete-link { color: var(--error-text); }
  .danger { color: var(--error-text); background: var(--error-bg); border: 1px solid transparent; border-radius: 10px; padding: 9px 14px; min-height: 43px; }
  button:disabled { cursor: default; opacity: .65; }
  @media (max-width: 760px) {
    .credential-workspace { grid-template-columns: minmax(0, 1fr); }
  }
</style>
