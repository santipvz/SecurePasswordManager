<script lang="ts">
  let { size = 32 }: { size?: number } = $props()
  const mark = `${import.meta.env.BASE_URL}mark.svg`
</script>

<img src={mark} width={size} height={size} alt="" draggable="false" />
