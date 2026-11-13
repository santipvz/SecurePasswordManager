<script lang="ts" module>
  export type Review = {
    total: number
    short: string[]
    reused: string[][]
    minimum_length: number
  }
</script>

<script lang="ts">
  import { ArrowLeft, ChevronRight, ShieldCheck } from "@lucide/svelte"
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

  onMount(() => heading.focus())
</script>

<button class="text-button review-back" onclick={onClose}><ArrowLeft size={16} /> Back to entries</button>
<h2 tabindex="-1" bind:this={heading}>Password review</h2>
{#if pending}
  <p class="feedback" role="status"><span class="spinner"></span> Reviewing passwords…</p>
{:else if error}
  <p class="error-note" role="alert">{error}</p>
{:else if result}
  {#if result.total === 0}
    <p class="empty">This vault has no credentials to review.</p>
  {:else if !affected.length}
    <p class="feedback"><ShieldCheck size={18} /> All passwords are unique and at least {result.minimum_length} characters long.</p>
  {:else}
    <p class="feedback">{affected.length} of {result.total} credentials have short or reused passwords.</p>
    <ul class="entries">
      {#each affected.slice(0, limit) as entry (entry.name)}
        <li>
          <button onclick={() => onEntry(entry.name)}>
            <span class="entry-text">
              <strong>{entry.name}</strong>
              <span>
                {entry.short ? `Fewer than ${result.minimum_length} characters` : ""}
                {entry.short && entry.reused ? " · " : ""}{entry.reused ? "Reused password" : ""}
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
  .review-back { margin: 0 0 12px -8px; }
  .entries { margin-block: 12px; }
  .error-note { margin-top: 12px; }
</style>
