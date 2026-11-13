<script lang="ts">
  import { tick } from "svelte"
  import {
    ArrowLeft, ArrowRight, BriefcaseBusiness, Check, ChevronRight, CodeXml,
    Copy, Eye, EyeOff, FolderOpen, KeyRound, LayoutGrid, LockKeyhole, Moon,
    Plus, Search, ShieldCheck, Sun, UserRound, Wallet,
  } from "@lucide/svelte"
  import { categories, credentials, type Category } from "./demo"

  const categoryIcons = {
    "All items": LayoutGrid, Personal: UserRound, Work: BriefcaseBusiness,
    Finance: Wallet, Developer: CodeXml,
  }
  const demoPassword = "example-only-vault-password"
  let theme = $state<"light" | "dark">("light")
  let view = $state<"welcome" | "vault">("welcome")
  let mode = $state<"existing" | "create" | "file">("existing")
  let phase = $state<"idle" | "waiting" | "error">("idle")
  let category = $state<Category>("All items")
  let search = $state("")
  let selected = $state(credentials[0])
  let showDetail = $state(false)
  let reveal = $state(false)
  let feedback = $state("")
  let searchInput = $state<HTMLInputElement>()
  let detailHeading = $state<HTMLHeadingElement>()
  let unlockButton = $state<HTMLButtonElement>()
  let lastEntryButton: HTMLButtonElement | undefined

  const matches = $derived(credentials.filter((entry) =>
    (category === "All items" || entry.category === category)
    && [entry.name, entry.username, entry.website].some((value) =>
      value.toLowerCase().includes(search.trim().toLowerCase()),
    ),
  ))
  const current = $derived(matches.find((entry) => entry.id === selected.id) ?? matches[0])

  async function openVault() {
    phase = "idle"
    category = "All items"
    search = ""
    selected = credentials[0]
    view = "vault"
    await tick()
    searchInput?.focus()
  }

  async function lockVault() {
    showDetail = false
    reveal = false
    feedback = ""
    lastEntryButton = undefined
    mode = "existing"
    phase = "idle"
    view = "welcome"
    await tick()
    unlockButton?.focus()
  }

  function setCategory(next: Category) {
    category = next
    showDetail = false
    reveal = false
    feedback = ""
  }

  async function openDetail(entry: (typeof credentials)[number], event: MouseEvent) {
    selected = entry
    lastEntryButton = event.currentTarget as HTMLButtonElement
    showDetail = true
    reveal = false
    feedback = ""
    await tick()
    if (matchMedia("(max-width: 760px)").matches) detailHeading?.focus()
  }

  async function backToItems() {
    showDetail = false
    reveal = false
    feedback = ""
    await tick()
    if (lastEntryButton?.isConnected) lastEntryButton.focus()
    else searchInput?.focus()
  }

  async function copyDemo() {
    try {
      await navigator.clipboard.writeText(demoPassword)
      feedback = "Sample password copied."
    } catch {
      feedback = "Clipboard unavailable."
    }
  }

  function shortcuts(event: KeyboardEvent) {
    if (view === "vault" && (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault()
      void backToItems().then(() => searchInput?.focus())
    }
    if (event.key === "Escape") {
      if (view === "vault" && showDetail) void backToItems()
      else if (phase !== "idle") phase = "idle"
      else if (mode !== "existing") mode = "existing"
    }
  }
</script>

<svelte:window onkeydown={shortcuts} />

<div class="app" data-theme={theme}>
  <header class="topbar">
    <div class="brand"><span class="brand-icon"><ShieldCheck size={20} /></span> Secure Password Manager</div>
    <div class="top-actions">
      <span class="sample-label">Demo vault</span>
      <button class="icon-button" aria-label={theme === "light" ? "Use dark theme" : "Use light theme"}
        onclick={() => theme = theme === "light" ? "dark" : "light"}>
        {#if theme === "light"}<Moon size={19} />{:else}<Sun size={19} />{/if}
      </button>
    </div>
  </header>

  {#if view === "welcome"}
    <main class="welcome">
      <section class="unlock-card" aria-labelledby="welcome-title">
        <div class="vault-icon"><LockKeyhole size={28} strokeWidth={1.7} /></div>
        <h1 id="welcome-title">
          {mode === "create" ? "Create a vault" : mode === "file" ? "Open a vault file" : "Unlock your vault"}
        </h1>
        {#if mode === "existing"}
          <p class="muted welcome-copy">Demo vault · YubiKey registered</p>
          {#if phase === "waiting"}
            <div class="unlock-state" role="status"><span class="spinner"></span> Waiting for the demo key…</div>
            <button class="primary full" onclick={openVault}>Simulate touch <ArrowRight size={17} /></button>
            <button class="text-button full" onclick={() => phase = "error"}>Simulate a disconnected key</button>
            <button class="text-button full" onclick={() => phase = "idle"}>Cancel</button>
          {:else}
            {#if phase === "error"}
              <p class="error-note" role="alert">The demo key was disconnected. Try again or open the sample vault.</p>
            {/if}
            <button class="primary full" bind:this={unlockButton} onclick={() => phase = "waiting"}>
              <KeyRound size={18} /> Use YubiKey <ArrowRight size={17} class="action-arrow" />
            </button>
            <button class="secondary full" onclick={openVault}>Open demo vault</button>
          {/if}
          <div class="welcome-footer">
            <button class="text-button" onclick={() => { mode = "create"; phase = "idle" }}><Plus size={16} /> Create vault</button>
            <button class="text-button" onclick={() => { mode = "file"; phase = "idle" }}><FolderOpen size={16} /> Open file</button>
          </div>
        {:else}
          <p class="muted welcome-copy">This preview opens a sample vault with fictional credentials.</p>
          <button class="primary full" onclick={openVault}>Open demo vault <ArrowRight size={17} /></button>
          <button class="text-button full" onclick={() => mode = "existing"}><ArrowLeft size={16} /> Back</button>
        {/if}
      </section>
    </main>
  {:else}
    <div class="workspace" class:detail-open={showDetail && current}>
      <aside class="sidebar">
        <nav aria-label="Credential categories">
          <span class="nav-label">Vault</span>
          {#each categories as item}
            {@const Icon = categoryIcons[item]}
            <button class:active={category === item} aria-pressed={category === item} onclick={() => setCategory(item)}>
              <Icon size={17} /> <span>{item}</span>
              {#if item === "All items"}<small>{credentials.length}</small>{/if}
            </button>
          {/each}
        </nav>
        <button class="lock-button" onclick={lockVault}><LockKeyhole size={16} /> Lock vault</button>
      </aside>

      <main class="collection">
        <div class="collection-heading">
          <h1>{category}</h1>
          <p class="muted" aria-live="polite">{matches.length} {matches.length === 1 ? "credential" : "credentials"}</p>
        </div>
        <div class="search-box">
          <Search size={18} />
          <input type="search" aria-label="Search credentials" placeholder="Search credentials…" bind:this={searchInput}
            bind:value={search} oninput={() => { reveal = false; feedback = "" }} />
          <kbd>Ctrl K</kbd>
        </div>
        <ul class="entries">
          {#each matches as entry (entry.id)}
            <li>
              <button class:chosen={current?.id === entry.id} aria-pressed={current?.id === entry.id}
                onclick={(event) => openDetail(entry, event)}>
                <span class="entry-mark" data-tint={entry.tint}>{entry.mark}</span>
                <span class="entry-text"><strong>{entry.name}</strong><span>{entry.username}</span></span>
                <ChevronRight size={16} class="entry-arrow" />
              </button>
            </li>
          {:else}
            <li class="empty">No credentials match your search.</li>
          {/each}
        </ul>
      </main>

      <section class="detail" aria-label="Credential details">
        {#if current}
          <button class="text-button detail-back" onclick={backToItems}><ArrowLeft size={17} /> Back to credentials</button>
          <div class="detail-heading">
            <span class="entry-mark large" data-tint={current.tint}>{current.mark}</span>
            <div><span class="muted">{current.category}</span><h2 bind:this={detailHeading} tabindex="-1">{current.name}</h2></div>
          </div>
          <dl>
            <div><dt>Username</dt><dd>{current.username}</dd></div>
            <div><dt>Website</dt><dd>{current.website}</dd></div>
            <div class="password-row">
              <div><dt>Sample password</dt><dd>{reveal ? demoPassword : "••••••••••••"}</dd></div>
              <button class="icon-button" aria-label={reveal ? "Hide password" : "Show sample password"}
                onclick={() => reveal = !reveal}>
                {#if reveal}<EyeOff size={19} />{:else}<Eye size={19} />{/if}
              </button>
            </div>
            {#if current.notes}<div><dt>Notes</dt><dd>{current.notes}</dd></div>{/if}
          </dl>
          <button class="primary" onclick={copyDemo}><Copy size={17} /> Copy password</button>
          <p class="feedback" role="status">{#if feedback}<Check size={15} />{feedback}{/if}</p>
        {:else}
          <div class="detail-empty"><KeyRound size={24} /><p>Select a credential to see its details.</p></div>
        {/if}
      </section>
    </div>
  {/if}
</div>
