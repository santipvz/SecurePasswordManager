<script lang="ts">
  import { invoke } from "@tauri-apps/api/core"
  import { ArrowLeft, ChevronDown, Copy, Eye, EyeOff, KeyRound, Pencil, Plus, Search, Trash2, X } from "@lucide/svelte"
  import { onMount, tick } from "svelte"
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

  function entryTint(name: string) {
    return (name.codePointAt(0) ?? 0) % 4
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
        <p class="muted" aria-live="polite">{matches.length} {matches.length === 1 ? "credential" : "credentials"}</p>
      </div>
      <button class="primary" disabled={busy || conflict || reviewPending || Boolean(editor)} onclick={() => openEditor("add")}><Plus size={17} /> Add entry</button>
    </div>
    <div class="search-box">
      <Search size={17} />
      <input type="search" bind:this={searchInput} value={search} oninput={updateSearch} onkeydown={searchKeys}
        readonly={searchUnavailable} aria-label="Search vault entries" placeholder="Search your vault" />
      {#if search}
        <button class="icon-button clear-search" aria-label="Clear search" title="Clear search"
          disabled={searchUnavailable} onclick={clearSearch}><X size={16} /></button>
      {:else}
        <kbd>{searchShortcut}</kbd>
      {/if}
    </div>
    {#if !selected && !editor && feedback}<p class="feedback" role="status">{feedback}</p>{/if}
    {#if conflict && !selected && !editor}<p class="error-note" role="alert">{messages.write_conflict}</p>{/if}
    {#if listFeedback}<p class="list-status feedback" role="status">{listFeedback}</p>{/if}
    {#if listError}<p class="error-note" role="alert">{listError}</p>{/if}
    <div class="collection-scroll" bind:this={listScroll}>
      {#if matches.length}
        <ul class="entries credential-list" bind:this={entryList}>
          {#each matches.slice(0, limit) as { entry } (entry.name)}
            <li class:active-row={selected?.name === entry.name}>
              <button class="credential-row" data-entry aria-pressed={selected?.name === entry.name}
                aria-disabled={Boolean(editor) || busy || reviewPending}
                onkeydown={searchKeys}
                onclick={(event) => { if (!editor && !busy && !reviewPending) void showDetails(entry, event.currentTarget, event.detail === 0) }}>
                <span class="entry-mark" data-color={entryTint(entry.name)} aria-hidden="true">{Array.from(entry.name)[0]?.toUpperCase()}</span>
                <span class="entry-text">
                  <strong>{entry.name}</strong>
                  {#if entry.username || entry.url}<span>{entry.username || entry.url}</span>{/if}
                </span>
              </button>
              <button class="icon-button row-copy" aria-label={`Copy password for ${entry.name}`} title="Copy password"
                aria-disabled={busy || Boolean(editor) || reviewPending || confirmation} onclick={() => copyPassword(entry, true)}><Copy size={16} />
              </button>
            </li>
          {/each}
        </ul>
        {#if matches.length > limit}
          <button class="secondary more" onclick={() => limit += pageSize}>Show more <ChevronDown size={16} /></button>
        {/if}
      {:else}
        <div class="list-empty">
          <Search size={24} aria-hidden="true" />
          <h2>{entries.length ? "No matches" : "No credentials yet"}</h2>
          <p class="muted">{entries.length ? "Try a different name, username, or website." : "Add your first credential to this vault."}</p>
          {#if search}<button class="secondary" disabled={searchUnavailable} onclick={clearSearch}>Clear search</button>{/if}
        </div>
      {/if}
    </div>
  </section>

  <section class="detail" aria-label="Credential details" bind:this={detailPane}>
    {#if reviewOpen}
      <PasswordReview result={review} pending={reviewPending} error={reviewError}
        onClose={closeReview} onEntry={selectFinding} />
    {:else if editor}
      <button class="text-button detail-back" disabled={busy} onclick={closeEditor}><ArrowLeft size={16} /> Cancel and go back</button>
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
        <span class="entry-mark large" data-color={entryTint(selected.name)} aria-hidden="true">{Array.from(selected.name)[0]?.toUpperCase()}</span>
        <div>
          <h2 tabindex="-1" bind:this={detailHeading}>{selected.name}</h2>
          {#if selected.url}<p class="muted detail-url">{selected.url}</p>{/if}
        </div>
        {#if !confirmation}
          <button class="secondary edit-action" disabled={busy || conflict || notes === undefined} onclick={() => openEditor("edit")}><Pencil size={15} /> Edit</button>
        {/if}
      </div>
      <dl>
        {#if selected.username}<div><dt>Username</dt><dd>{selected.username}</dd></div>{/if}
        <div>
          <dt>Password</dt>
          <dd class="password-row">
            <span class="password-text" aria-label={revealed === undefined ? "Password hidden" : undefined}>{revealed ?? "••••••••••"}</span>
            <div class="detail-actions">
              <button class="icon-button" title={revealed === undefined ? "Reveal password" : "Hide password"} aria-label={revealed === undefined ? "Reveal password" : "Hide password"}
                disabled={busy || confirmation} onclick={revealPassword}>
                {#if revealed === undefined}<Eye size={18} />{:else}<EyeOff size={18} />{/if}
              </button>
              <button class="primary copy-detail" aria-label="Copy password" disabled={busy || confirmation}
                onclick={() => { if (selected) void copyPassword(selected) }}><Copy size={16} /> <span>Copy</span></button>
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
          <button class="text-button delete-link" disabled={busy || conflict} onclick={askDelete}><Trash2 size={16} /> Delete credential</button>
        </div>
      {/if}
    {:else}
      <div class="detail-empty">
        <span class="detail-empty-icon"><KeyRound size={29} strokeWidth={1.5} /></span>
        <h2>Select a credential</h2>
        <p>Choose an entry to view or edit its details.</p>
      </div>
    {/if}
    {#if error || (conflict && (selected || editor))}
      <p class="error-note entry-feedback" role="alert">{error || messages.write_conflict}</p>
    {/if}
    {#if (selected || editor) && feedback}<p class="feedback" role="status">{feedback}</p>{/if}
  </section>
</main>

<style>
  .credential-workspace {
    flex: 1;
    display: grid;
    grid-template-columns: minmax(280px, .81fr) minmax(310px, 1fr);
    min-height: 0;
  }
  .collection, .detail { padding: 31px clamp(17px, 2.8vw, 38px); }
  .collection { display: flex; flex-direction: column; min-height: 0; padding-bottom: 0; background: var(--canvas); }
  .collection-scroll, .detail { min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
  .collection-scroll { padding: 4px 5px 23px 4px; margin: -4px -5px 0 -4px; }
  .collection h1 { font-size: clamp(26px, 3vw, 35px); }
  .collection-heading p { margin-top: 6px; }
  .entry-heading { display: flex; align-items: center; justify-content: space-between; gap: 9px; }
  .entry-heading .primary { flex: none; min-height: 38px; padding: 7px 12px; }
  .search-box { min-height: 44px; margin: 22px 0 16px; border-radius: 10px; }
  .search-box input::-webkit-search-cancel-button { display: none; }
  .clear-search { width: 30px; height: 30px; margin-right: -4px; }
  .credential-list {
    padding: 4px;
    border: 1px solid var(--line);
    border-radius: 13px;
    background: var(--surface);
  }
  .credential-list li {
    display: flex; align-items: center; gap: 2px; border: 1px solid transparent;
    border-radius: 9px;
  }
  .credential-list li + li { margin-top: 1px; }
  .credential-list li:hover { background: var(--canvas); }
  .credential-list li.active-row { background: var(--soft); border-color: var(--line); }
  .credential-list .credential-row { flex: 1; min-width: 0; min-height: 62px; background: transparent; }
  .credential-list .row-copy {
    flex: none; width: 35px; min-height: 35px; height: 35px; margin-right: 6px;
    padding: 0; justify-content: center; color: var(--muted);
  }
  .credential-list .row-copy:hover { background: var(--soft); color: var(--accent); }
  .entry-mark { color: #50369f; background: #eee8ff; }
  .entry-mark[data-color="1"] { color: #185474; background: #dff1ff; }
  .entry-mark[data-color="2"] { color: #20604b; background: #dbf1e8; }
  .entry-mark[data-color="3"] { color: #844724; background: #f9e8dc; }
  .entry-text strong { font-weight: 600; }
  .entry-text span { font-size: 12px; }
  .list-status { margin: 0 0 10px; color: var(--accent); }
  .list-empty {
    display: grid; gap: 10px; justify-items: center; padding: 37px 14px;
    text-align: center; border: 1px dashed var(--line); border-radius: 13px;
  }
  .list-empty > :global(svg) { color: var(--accent); }
  .list-empty h2 { font-size: 19px; }
  .detail-heading { gap: 14px; }
  .detail-heading > div { min-width: 0; }
  .detail-heading h2 { font-size: clamp(22px, 3vw, 34px); }
  .detail-heading .detail-url { margin-top: 5px; font-size: 13px; overflow-wrap: anywhere; }
  .edit-action { margin-left: auto; min-height: 36px; flex: none; }
  .detail dl { display: grid; gap: 13px; margin: 28px 0 16px; }
  .detail dl > div {
    min-width: 0; padding: 13px 14px; border: 1px solid var(--line);
    background: var(--canvas); border-radius: 10px;
  }
  .detail dl dt { margin-bottom: 4px; font-weight: 600; }
  .detail-empty {
    display: grid; justify-items: center; gap: 9px; text-align: center;
    padding: 0; margin: clamp(70px, 16vh, 165px) auto 0;
  }
  .detail-empty-icon {
    display: grid; place-items: center; width: 60px; height: 60px; margin-bottom: 8px;
    background: var(--soft); color: var(--accent); border-radius: 17px;
  }
  .detail-empty h2 { font-size: 22px; color: var(--text); }
  .copy-detail { min-height: 35px; padding: 6px 10px; }
  .review-view { display: block; overflow-y: auto; }
  .review-view .collection { display: none; }
  .review-view .detail {
    max-width: 730px; margin-inline: auto; border: 0; background: transparent; overflow: visible;
  }
  .generator-toggle { justify-self: start; }
  .credential-form { display: grid; gap: 13px; margin-top: 20px; }
  .credential-form label { display: grid; gap: 5px; font-weight: 600; }
  .credential-form small { color: var(--muted); font-weight: 400; }
  .credential-form input, .credential-form textarea {
    width: 100%; min-width: 0; font: inherit; font-weight: 400; color: var(--text);
    background: var(--canvas); border: 1px solid var(--line); border-radius: 9px; padding: 11px 12px;
  }
  .credential-form textarea { resize: vertical; }
  .password-text, .notes { white-space: pre-wrap; overflow-wrap: anywhere; }
  .password-text { font-family: ui-monospace, monospace; }
  .detail-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .password-row .detail-actions { flex-wrap: nowrap; flex: none; }
  .more, .entry-feedback { margin-top: 13px; }
  .delete-confirmation { display: grid; gap: 10px; }
  .delete-link { color: var(--error-text); }
  .danger { color: var(--error-text); background: var(--error-bg); border: 1px solid transparent; border-radius: 10px; padding: 9px 14px; min-height: 43px; }
  @media (max-width: 760px) {
    .credential-workspace { grid-template-columns: minmax(0, 1fr); min-height: calc(100vh - 108px); }
    .collection, .detail { padding-block: 22px; }
    .collection-scroll, .detail, .review-view { overflow: visible; }
    .detail-heading .entry-mark.large { width: 44px; height: 44px; font-size: 17px; }
  }
</style>
