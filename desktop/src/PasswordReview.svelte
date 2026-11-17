<script lang="ts" module>
  export type Review = {
    total: number
    short: string[]
    reused: string[][]
    minimum_length: number
  }
</script>

<script lang="ts">
  import { ArrowLeft, ChevronRight, CircleAlert, Repeat2, Ruler, ShieldCheck } from "@lucide/svelte"
  import { avatarLetter } from "./avatar"
  import { onMount } from "svelte"

  let { result, pending, error, onClose, onEntry }: {
    result?: Review
    pending: boolean
    error: string
    onClose: () => void
    onEntry: (name: string) => void
  } = $props()

  let heading: HTMLHeadingElement
  let limit = $state(100)
  const affected = $derived.by(() => {
    if (!result) return []
    const short = new Set(result.short)
    const reused = new Set(result.reused.flat())
    return [...new Set([...short, ...reused])].sort((a, b) => a.localeCompare(b))
      .map((name) => ({ name, short: short.has(name), reused: reused.has(name) }))
  })

  const reusedCount = $derived(affected.filter((entry) => entry.reused).length)
  const shortCount = $derived(affected.filter((entry) => entry.short).length)

  onMount(() => heading.focus())
</script>

<button class="text-button review-back" onclick={onClose}><ArrowLeft size={16} /> Back to entries</button>
<header class="review-header">
  <h2 tabindex="-1" bind:this={heading}>Password review</h2>
  <p class="muted">Checks run locally on the unlocked vault and never change the file.</p>
</header>
{#if pending}
  <p class="feedback review-pending" role="status"><span class="spinner"></span> Reviewing passwords…</p>
{:else if error}
  <p class="error-note" role="alert"><CircleAlert size={16} /> <span>{error}</span></p>
{:else if result}
  {#if result.total === 0}
    <p class="empty">This vault has no credentials to review.</p>
  {:else if !affected.length}
    <p class="feedback review-clear"><ShieldCheck size={17} /> All {result.total} passwords are unique and at least {result.minimum_length} characters long.</p>
  {:else}
    <p class="summary">
      <strong>{affected.length} of {result.total}</strong> credentials need attention:
      {[shortCount ? `${shortCount} shorter than ${result.minimum_length} characters` : "", reusedCount ? `${reusedCount} reused` : ""].filter(Boolean).join(", ")}.
    </p>
    <ul class="entries findings">
      {#each affected.slice(0, limit) as entry (entry.name)}
        <li>
          <button onclick={() => onEntry(entry.name)}>
            <span class="entry-mark" aria-hidden="true">{avatarLetter(entry.name)}</span>
            <span class="entry-text">
              <strong>{entry.name}</strong>
              <span class="issue">
                {#if entry.short}<Ruler size={13} aria-hidden="true" />{:else}<Repeat2 size={13} aria-hidden="true" />{/if}
                {entry.short && entry.reused ? `Shorter than ${result.minimum_length} characters and reused`
                  : entry.short ? `Shorter than ${result.minimum_length} characters` : "Reused in another credential"}
              </span>
            </span>
            <ChevronRight size={16} class="entry-arrow" />
          </button>
        </li>
      {/each}
    </ul>
    {#if affected.length > limit}
      <button class="secondary" onclick={() => limit += 100}>Show more findings</button>
    {/if}
  {/if}
{/if}

<style>
  .review-back { margin: 0 0 10px -10px; }
  .review-header { margin-bottom: 20px; }
  h2 { font-size: clamp(21px, 2.6vw, 24px); font-weight: 600; }
  .review-header p { margin-top: 4px; font-size: 13.5px; }
  .review-pending { gap: 10px; }
  .review-clear { color: var(--success); font-weight: 500; }
  .empty { color: var(--muted); }
  .summary { margin-bottom: 12px; line-height: 1.55; }
  .summary strong { font-weight: 600; }
  .findings {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    overflow: hidden;
    margin-bottom: 14px;
  }
  .findings li + li { border-top: 1px solid var(--line); }
  .findings button { border-radius: 0; padding: 10px 14px; }
  .issue { display: flex; align-items: center; gap: 5px; color: var(--warning); }
  .issue :global(svg) { flex: none; }
  .error-note { margin-top: 12px; }
</style>
