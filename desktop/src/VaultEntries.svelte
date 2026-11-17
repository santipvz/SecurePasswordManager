<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import {
    ArrowLeft, Check, ChevronDown, CircleAlert, Copy, Eye, EyeOff, Globe, KeyRound, Pencil, Plus, Search,
    Trash2, X,
  } from "@lucide/svelte"
  import { onMount, tick } from "svelte"
  import { avatarLetter } from "./avatar"
  import PasswordGenerator from "./PasswordGenerator.svelte"
  import PasswordReview, { type Review } from "./PasswordReview.svelte"

  type Entry = { name: string; username: string; url: string }

  let { generation, entries = $bindable(), writing = $bindable(), editing = $bindable(false),
    reviewOpen = $bindable(false), onSessionEnd }: {
    generation: number
    entries: Entry[]
    writing: boolean
    editing: boolean
    reviewOpen: boolean
    onSessionEnd: (message: string) => Promise<void>
  } = $props()

  const pageSize = 100
  const revealLifetime = 10_000
  const searchShortcut = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘ K" : "Ctrl K"
  const messages: Record<string, string> = {
    busy: "The vault is busy. Try again.",
    entry_missing: "This credential no longer exists.",
    entry_duplicate: "A credential with this name already exists.",
    entry_invalid: "Enter a name and password.",
    entry_encoding: "This credential contains invalid text. Edit the entry to replace the affected field.",
    input_too_large: "This credential is too large to save.",
    write_conflict: "The vault changed in another app. Lock and reopen it before saving.",
    write_failed: "Could not confirm the save. Reopen the vault to check whether it was applied.",
    clipboard_unavailable: "Could not copy the password to the clipboard.",
    clipboard_unsupported: "This password contains characters the system clipboard cannot preserve.",
    timed_out: "The vault process timed out. Reopen the vault to check your changes.",
  }

  let generatorOpen = $state(false)
  let reviewPending = $state(false)
  let review = $state<Review>()
  let reviewError = $state("")
  let search = $state("")
  let limit = $state(pageSize)
  let selected = $state<Entry>()
  let notes = $state<string>()
  let revealed = $state<string>()
  let revealTimer: ReturnType<typeof setTimeout> | undefined
  let copyFeedbackTimer: ReturnType<typeof setTimeout> | undefined
  let editor = $state<"add" | "edit">()
  let confirmation = $state(false)
  let busy = $state(false)
  let conflict = $state(false)
  let notesEdited = false
  let feedback = $state("")
  let error = $state("")
  let listFeedback = $state("")
  let listError = $state("")
  let searchInput = $state<HTMLInputElement>()
  let entryList = $state<HTMLUListElement>()
  let listScroll = $state<HTMLDivElement>()
  let detailPane = $state<HTMLElement>()
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
  const searchUnavailable = $derived(Boolean(editor) || busy || reviewPending)
  const revealedCharacters = $derived(revealed === undefined ? [] : Array.from(revealed).map((character) => ({
    character,
    kind: /\p{Nd}/u.test(character) ? "digit" : /[\p{L}\p{M}]/u.test(character) ? "letter" : "symbol",
  })))

  function hidePassword() {
    secretRevision++
    clearTimeout(revealTimer)
    revealTimer = undefined
    revealed = undefined
  }

  function clearView() {
    viewRevision++
    hidePassword()
    clearTimeout(copyFeedbackTimer)
    if (passwordInput) passwordInput.value = ""
    editor = undefined
    editing = false
    generatorOpen = false
    reviewOpen = false
    review = undefined
    reviewError = ""
    confirmation = false
    notes = undefined
    feedback = ""
    error = ""
    listFeedback = ""
    listError = ""
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
    if (searchUnavailable) return
    clearView()
    selected = undefined
    search = event.currentTarget.value
    limit = pageSize
    listScroll?.scrollTo(0, 0)
  }

  async function clearSearch() {
    if (searchUnavailable) return
    search = ""
    limit = pageSize
    listScroll?.scrollTo(0, 0)
    await focusSearch()
  }

  function searchKeys(event: KeyboardEvent) {
    if (event.isComposing || searchUnavailable || !["ArrowDown", "ArrowUp", "Enter"].includes(event.key)) return
    const rows = [...(entryList?.querySelectorAll<HTMLButtonElement>("[data-entry]") ?? [])]
    const current = rows.indexOf(event.currentTarget as HTMLButtonElement)
    if (event.key === "Enter" && current === -1 && rows[0]) {
      event.preventDefault()
      rows[0].click()
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault()
      if (event.key === "ArrowUp" && current <= 0) searchInput?.focus()
      else rows[current + (event.key === "ArrowDown" ? 1 : -1)]?.focus()
    }
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
    detailPane?.scrollTo(0, 0)
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

  export async function openReview() {
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

  export async function closeReview() {
    clearView()
    await tick()
    searchInput?.focus()
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

  async function copyPassword(entry: Entry, fromList = false) {
    if (busy || editor || reviewPending || confirmation) return
    hidePassword()
    clearTimeout(copyFeedbackTimer)
    const current = viewRevision
    feedback = ""
    error = ""
    listFeedback = ""
    listError = ""
    busy = true
    try {
      await invoke("vault_copy", { generation, name: entry.name })
      if (current !== viewRevision) return
      if (fromList) {
        listFeedback = "Password copied for 30 seconds."
        copyFeedbackTimer = setTimeout(() => { listFeedback = "" }, 4500)
      } else {
        feedback = "Password copied for 30 seconds."
      }
    } catch (reason) {
      if (current !== viewRevision) return
      handleError(reason)
      if (fromList) {
        listError = error
        error = ""
      }
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
    editing = true
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
    editing = false
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
      editing = false
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
    if (event.isComposing) return
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault()
      if (!searchUnavailable) void focusSearch()
    }
    if (event.key !== "Escape") return
    if (revealed !== undefined || (busy && selected && !editor)) hidePassword()
    else if (reviewOpen) void closeReview()
    else if (generatorOpen) void dismissGenerator()
    else if (!busy && editor) void closeEditor()
    else if (!busy && confirmation) void keepEntry()
    else if (!busy && selected) void closeDetails()
    else if (!busy && search && event.target === searchInput) {
      event.preventDefault()
      void clearSearch()
    }
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

<main class="credential-workspace" class:detail-open={selected || editor || reviewOpen} class:review-view={reviewOpen}>
  <section class="collection" aria-labelledby="entry-list-heading">
    <div class="collection-heading entry-heading">
      <div>
        <h1 id="entry-list-heading">Credentials</h1>
        <p class="muted entry-count" aria-live="polite">{search ? `${matches.length} of ${entries.length}` : matches.length} {entries.length === 1 ? "credential" : "credentials"}</p>
      </div>
      <button class="primary add-entry" disabled={busy || conflict || reviewPending || Boolean(editor)} onclick={() => openEditor("add")}><Plus size={16} /> Add entry</button>
    </div>
    <div class="search-box">
      <Search size={16} />
      <input type="search" bind:this={searchInput} value={search} oninput={updateSearch} onkeydown={searchKeys}
        readonly={searchUnavailable} aria-label="Search vault entries" placeholder="Search credentials…" />
      {#if search}
        <button class="icon-button clear-search" aria-label="Clear search" title="Clear search"
          disabled={searchUnavailable} onclick={clearSearch}><X size={15} /></button>
      {:else}
        <kbd>{searchShortcut}</kbd>
      {/if}
    </div>
    {#if !selected && !editor && feedback}<p class="feedback toast success" role="status"><Check size={15} /> {feedback}</p>{/if}
    {#if conflict && !selected && !editor}<p class="error-note" role="alert"><CircleAlert size={16} /> <span>{messages.write_conflict}</span></p>{/if}
    {#if listFeedback}<p class="list-status feedback toast success" role="status"><Check size={15} /> {listFeedback}</p>{/if}
    {#if listError}<p class="error-note" role="alert"><CircleAlert size={16} /> <span>{listError}</span></p>{/if}
    <div class="collection-scroll" bind:this={listScroll}>
      {#if matches.length}
        <ul class="entries credential-list" bind:this={entryList}>
          {#each matches.slice(0, limit) as { entry } (entry.name)}
            <li class:active-row={selected?.name === entry.name}>
              <button class="credential-row" data-entry aria-pressed={selected?.name === entry.name}
                aria-disabled={Boolean(editor) || busy || reviewPending}
                onkeydown={searchKeys}
                onclick={(event) => { if (!editor && !busy && !reviewPending) void showDetails(entry, event.currentTarget, event.detail === 0) }}>
                <span class="entry-mark" aria-hidden="true">{avatarLetter(entry.name)}</span>
                <span class="entry-text">
                  <strong>{entry.name}</strong>
                  {#if entry.username || entry.url}<span>{entry.username || entry.url}</span>{/if}
                </span>
              </button>
              <button class="icon-button row-copy" aria-label={`Copy password for ${entry.name}`} title="Copy password"
                aria-disabled={busy || Boolean(editor) || reviewPending || confirmation} onclick={() => copyPassword(entry, true)}><Copy size={15} />
              </button>
            </li>
          {/each}
        </ul>
        {#if matches.length > limit}
          <button class="secondary more" onclick={() => limit += pageSize}>Show more <ChevronDown size={16} /></button>
        {/if}
      {:else}
        <div class="list-empty">
          <h2>{entries.length ? "No matches" : "No credentials yet"}</h2>
          <p class="muted">{entries.length ? "Try a different name, username, or website." : "New credentials appear here."}</p>
          {#if search}<button class="secondary" disabled={searchUnavailable} onclick={clearSearch}>Clear search</button>{/if}
        </div>
      {/if}
    </div>
  </section>

  <section class="detail" aria-label="Credential details" bind:this={detailPane}>
    <div class="detail-content">
      {#if reviewOpen}
        <PasswordReview result={review} pending={reviewPending} error={reviewError}
          onClose={closeReview} onEntry={selectFinding} />
      {:else if editor}
        <button class="text-button detail-back" disabled={busy} onclick={closeEditor}><ArrowLeft size={16} /> Cancel and go back</button>
        <header class="editor-heading">
          <h2 class="panel-title">{editor === "add" ? "Add credential" : "Edit credential"}</h2>
          
        </header>
        <form class="credential-form" onsubmit={saveEntry} autocomplete="off">
          <div class="form-section">
            <label>Name <input name="name" value={selected?.name ?? ""} bind:this={nameInput} required placeholder="GitHub…" /></label>
            <div class="credential-fields">
              <label>Username <input name="username" value={selected?.username ?? ""} autocomplete="off" placeholder="name@example.com…" /></label>
              <label>Website <input name="url" value={selected?.url ?? ""} inputmode="url" placeholder="github.com…" /></label>
            </div>
          </div>
          <div class="form-section">
            <label>
              {editor === "edit" ? "New password" : "Password"}
              <input type="password" bind:this={passwordInput} required={editor === "add"}
                autocomplete="off" autocapitalize="off" spellcheck={false} />
              {#if editor === "edit"}<small>Leave blank to keep the saved password.</small>{/if}
            </label>
            <button class="text-button generator-toggle" type="button" bind:this={generatorToggle} aria-expanded={generatorOpen}
              onclick={() => generatorOpen = !generatorOpen}><KeyRound size={15} /> {generatorOpen ? "Hide generator" : "Open password generator"}</button>
            {#if generatorOpen}<div class="inline-generator"><PasswordGenerator {generation} onUse={useGenerated} /></div>{/if}
          </div>
          <div class="form-section">
            <label>Notes <textarea name="notes" value={notes ?? ""} rows="3" oninput={() => notesEdited = true} placeholder="Recovery hints…"></textarea></label>
          </div>
          <div class="detail-actions form-actions">
            <button class="secondary" type="button" disabled={busy} onclick={closeEditor}>Cancel</button>
            <button class="primary" type="submit" disabled={busy || conflict}>Save credential</button>
          </div>
        </form>
      {:else if selected}
        <button class="text-button detail-back" disabled={busy} onclick={closeDetails}><ArrowLeft size={16} /> Back to entries</button>
        <header class="detail-heading">
          <span class="entry-mark large" aria-hidden="true">{avatarLetter(selected.name)}</span>
          <div class="detail-title">
            <h2 tabindex="-1" bind:this={detailHeading}>{selected.name}</h2>
            {#if selected.url}<p class="muted detail-url"><Globe size={14} /> {selected.url}</p>{/if}
          </div>
          {#if !confirmation}
            <button class="secondary edit-action" disabled={busy || conflict || notes === undefined} onclick={() => openEditor("edit")}><Pencil size={14} /> Edit</button>
          {/if}
        </header>
        <dl class="field-group">
          {#if selected.username}<div><dt>Username</dt><dd>{selected.username}</dd></div>{/if}
          <div class="password-field">
            <dt>Password</dt>
            <dd class="password-row">
              <span class="password-text" class:revealed={revealed !== undefined}
                aria-label={revealed === undefined ? "Password hidden" : undefined}>{#if revealed === undefined}••••••••••••{:else}{#each revealedCharacters as { character, kind }}<span class={kind}>{character}</span>{/each}{/if}</span>
              <div class="detail-actions">
                <button class="icon-button" title={revealed === undefined ? "Reveal password" : "Hide password"} aria-label={revealed === undefined ? "Reveal password" : "Hide password"}
                  disabled={busy || confirmation} onclick={revealPassword}>
                  {#if revealed === undefined}<Eye size={17} />{:else}<EyeOff size={17} />{/if}
                </button>
                <button class="primary copy-detail" aria-label="Copy password" disabled={busy || confirmation}
                  onclick={() => { if (selected) void copyPassword(selected) }}><Copy size={15} /> <span>Copy</span></button>
              </div>
            </dd>
            {#if revealed !== undefined}<span class="reveal-timer" aria-hidden="true"></span>{/if}
          </div>
          {#if notes}<div><dt>Notes</dt><dd class="notes">{notes}</dd></div>{/if}
        </dl>
        {#if error || conflict}
          <p class="error-note entry-feedback" role="alert"><CircleAlert size={16} /> <span>{error || messages.write_conflict}</span></p>
        {/if}
        {#if feedback}<p class="feedback toast success entry-success" role="status"><Check size={15} /> {feedback}</p>{/if}
        {#if confirmation}
          <div class="delete-confirmation" role="group" aria-labelledby="delete-title">
            <p id="delete-title"><strong>Delete “{selected.name}”?</strong> It will be removed from this vault. Backups you saved earlier keep their copy.</p>
            <div class="detail-actions">
              <button class="secondary" bind:this={cancelDelete} disabled={busy} onclick={keepEntry}>Keep credential</button>
              <button class="danger" disabled={busy || conflict} onclick={deleteEntry}><Trash2 size={15} /> Delete credential</button>
            </div>
          </div>
        {:else}
          <div class="detail-footer">
            <button class="text-button delete-link" disabled={busy || conflict} onclick={askDelete}><Trash2 size={15} /> Delete credential</button>
          </div>
        {/if}
      {:else}
        <div class="detail-empty">
          {#if matches.length}
            <h2>Select a credential</h2>
            <p class="muted">Choose one from the list, or press <kbd>{searchShortcut}</kbd> to search.</p>
          {:else if !entries.length}
            <h2>Your vault is empty</h2>
            <p class="muted">Add a login to keep it encrypted in this vault file.</p>
            <button class="primary" disabled={busy || conflict || reviewPending} onclick={() => openEditor("add")}><Plus size={16} /> Add credential</button>
          {:else}
            <h2>Nothing selected</h2>
            <p class="muted">No credentials match the current search.</p>
          {/if}
        </div>
      {/if}
      {#if editor && (error || conflict)}
        <p class="error-note entry-feedback" role="alert"><CircleAlert size={16} /> <span>{error || messages.write_conflict}</span></p>
      {/if}
      {#if !selected && !editor && error}
        <p class="error-note entry-feedback" role="alert"><CircleAlert size={16} /> <span>{error}</span></p>
      {/if}
    </div>
  </section>
</main>

<style>
  .credential-workspace {
    flex: 1;
    display: grid;
    grid-template-columns: clamp(290px, 32vw, 360px) minmax(0, 1fr);
    min-height: 0;
  }

  /* ---------- List ---------- */

  .collection {
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding: 20px 14px 0;
    background: var(--sidebar);
    border-right: 1px solid var(--line);
  }
  .entry-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 0 4px; }
  .collection h1 { font-size: 19px; font-weight: 600; letter-spacing: -.015em; }
  .collection .entry-count { margin-top: 1px; font-size: 12.5px; font-variant-numeric: tabular-nums; }
  .add-entry { flex: none; min-height: 32px; padding: 5px 11px 5px 9px; font-size: 13px; gap: 6px; }
  .search-box { min-height: 38px; margin: 16px 4px 10px; }
  .search-box input { padding: 8px 0; }
  .search-box input::-webkit-search-cancel-button { display: none; }
  .clear-search { width: 28px; height: 28px; }
  .collection-scroll, .detail { min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
  .collection-scroll { flex: 1; padding: 4px 4px 20px; margin: 0 -4px; }
  .credential-list li {
    position: relative;
    display: flex;
    align-items: center;
    border-radius: var(--radius);
    transition: background-color .12s var(--ease);
  }
  .credential-list li + li { margin-top: 1px; }
  .credential-list li:hover { background: var(--hover); }
  .credential-list li.active-row { background: var(--soft); }
  .credential-list .credential-row {
    flex: 1;
    min-width: 0;
    min-height: 54px;
    padding: 8px 6px 8px 8px;
    background: transparent;
    border-radius: var(--radius);
  }
  .credential-list .credential-row:hover { background: transparent; }
  .credential-list .row-copy { width: 32px; height: 32px; margin-right: 8px; border-radius: var(--radius-sm); }
  .credential-list .row-copy:hover { background: var(--raised); color: var(--text); }
  .credential-list .entry-mark { width: 34px; height: 34px; font-size: 14px; }
  .active-row .entry-text strong { color: var(--soft-text); }
  .toast { margin: 0 4px 10px; font-size: 13px; font-weight: 500; }
  .toast.success { color: var(--success); }
  .collection .error-note { margin: 0 4px 10px; }
  .list-empty { display: grid; gap: 4px; justify-items: start; padding: 20px 8px; }
  .list-empty h2 { font-size: 14px; font-weight: 600; }
  .list-empty p { font-size: 13px; }
  .list-empty button { margin-top: 8px; }
  .more { width: calc(100% - 8px); margin: 10px 4px 0; }

  /* ---------- Detail ---------- */

  .detail { padding: clamp(24px, 4vw, 44px) clamp(20px, 4.5vw, 52px); background: var(--canvas); border-left: 0; }
  .detail-content { width: min(100%, 640px); margin-inline: auto; }
  .detail-heading { display: flex; align-items: center; gap: 16px; }
  .detail-title { min-width: 0; flex: 1; }
  .detail-heading h2, .panel-title { font-size: clamp(21px, 2.4vw, 25px); font-weight: 600; overflow-wrap: anywhere; }
  .detail-url { display: flex; align-items: center; gap: 6px; margin-top: 3px; font-size: 13px; overflow-wrap: anywhere; }
  .detail-url :global(svg) { flex: none; }
  .edit-action { flex: none; min-height: 34px; padding: 5px 12px; font-size: 13px; gap: 6px; }

  .detail dl.field-group {
    display: grid;
    margin: 24px 0 16px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .detail dl.field-group > div { position: relative; min-width: 0; padding: 13px 16px; border-bottom: 1px solid var(--line); }
  .detail dl.field-group > div:last-child { border-bottom: 0; }
  .field-group dt { margin-bottom: 3px; color: var(--muted); font-size: 12px; font-weight: 500; }
  .field-group dd { font-size: 14.5px; }
  .password-row { min-height: 36px; flex-wrap: wrap; gap: 6px 12px; }
  .password-text, .notes { white-space: pre-wrap; overflow-wrap: anywhere; }
  .password-text { font: 500 15px/1.5 ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace; letter-spacing: .06em; color: var(--muted); }
  .password-text.revealed { color: var(--text); letter-spacing: .02em; }
  .password-text :global(.digit) { color: var(--char-digit); }
  .password-text :global(.symbol) { color: var(--char-symbol); }
  .notes { color: var(--text); line-height: 1.6; }
  .copy-detail { min-height: 32px; padding: 5px 12px; font-size: 13px; gap: 6px; }
  .reveal-timer {
    position: absolute;
    left: 0;
    bottom: 0;
    height: 2px;
    width: 100%;
    background: var(--signal);
    transform-origin: left;
    animation: countdown 10s linear forwards;
  }
  @keyframes countdown { to { transform: scaleX(0); } }

  .detail-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .password-row .detail-actions { flex-wrap: nowrap; max-width: 100%; }
  .entry-feedback { margin-top: 12px; }
  .entry-success { margin: 0 0 12px; display: inline-flex; }
  .detail-footer { display: flex; padding-top: 4px; }
  .delete-link { margin-left: -10px; color: var(--error-text); font-size: 13px; }
  .delete-link:hover:not(:disabled) { color: var(--error-text); background: var(--error-bg); }
  .delete-confirmation {
    display: grid;
    gap: 12px;
    padding: 14px 16px;
    border-radius: var(--radius);
    background: var(--error-bg);
    border: 1px solid var(--error-line);
    animation: rise .2s var(--ease);
  }
  .delete-confirmation p { color: var(--text); font-size: 13.5px; }
  .delete-confirmation strong { font-weight: 600; }

  .detail-empty {
    display: grid;
    justify-items: center;
    gap: 6px;
    max-width: 320px;
    text-align: center;
    padding: 0;
    margin: clamp(56px, 18vh, 170px) auto 0;
  }
  .detail-empty h2 { font-size: 17px; font-weight: 600; color: var(--text); }
  .detail-empty p { font-size: 13.5px; line-height: 1.6; }
  .detail-empty button { margin-top: 14px; }

  /* ---------- Review ---------- */

  .review-view { display: block; overflow-y: auto; background: var(--canvas); }
  .review-view .collection { display: none; }
  .review-view .detail { overflow: visible; background: transparent; }
  .review-view .detail-content { width: min(100%, 720px); }

  /* ---------- Editor ---------- */

  .credential-form { display: grid; gap: 18px; margin-top: 22px; }
  .form-section { display: grid; gap: 14px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
  .form-section:last-of-type { border-bottom: 0; padding-bottom: 0; }
  .credential-fields { display: grid; gap: 14px; }
  .credential-form label { display: grid; gap: 6px; font-size: 13px; font-weight: 500; }
  .credential-form small { color: var(--muted); font-size: 12px; font-weight: 400; }
  .credential-form input, .credential-form textarea {
    width: 100%;
    min-width: 0;
    min-height: 40px;
    font: inherit;
    font-size: 14px;
    font-weight: 400;
    color: var(--text);
    background: var(--control-bg);
    border: 1px solid var(--control-line);
    border-radius: var(--radius-sm);
    padding: 8px 11px;
    transition: border-color .15s var(--ease), box-shadow .15s var(--ease);
  }
  .credential-form input::placeholder, .credential-form textarea::placeholder { color: var(--subtle); }
  .credential-form :is(input, textarea):focus-visible { outline: none; border-color: var(--focus); box-shadow: var(--focus-ring); }
  .credential-form textarea { resize: vertical; line-height: 1.55; }
  .generator-toggle { justify-self: start; margin: -4px 0 -4px -10px; color: var(--accent); font-size: 13px; }
  .generator-toggle:hover:not(:disabled) { color: var(--accent); background: var(--soft); }
  .inline-generator { padding: 14px; border-radius: var(--radius); background: var(--surface-2); border: 1px solid var(--line); }
  .form-actions { justify-content: flex-end; padding-top: 4px; }

  @media (min-width: 1020px) {
    .credential-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 760px) {
    .credential-workspace { grid-template-columns: minmax(0, 1fr); }
    .collection { padding: 16px 12px 0; border-right: 0; }
    .detail { padding: 16px; }
    .detail-back { margin-left: -10px; }
  }
  @media (hover: hover) and (pointer: fine) {
    .credential-list .row-copy { opacity: 0; transition: opacity .12s var(--ease), background-color .12s; }
    .credential-list li:hover .row-copy,
    .credential-list li:focus-within .row-copy,
    .credential-list li.active-row .row-copy { opacity: 1; }
  }
  @media (pointer: coarse) {
    .credential-list .row-copy { height: 44px; width: 44px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .reveal-timer { display: none; }
  }
</style>
