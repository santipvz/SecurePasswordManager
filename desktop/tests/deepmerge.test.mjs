import assert from "node:assert/strict"
import { createRequire } from "node:module"
import test from "node:test"

const requireFromSvelte = createRequire(import.meta.resolve("@sveltejs/vite-plugin-svelte"))
const merge = requireFromSvelte("deepmerge")

test("Svelte's deepmerge discards own __proto__ keys from both inputs", () => {
  const payload = JSON.parse('{"__proto__":{"injected":true},"keep":1}')
  const nested = merge({ session: null }, { session: payload }).session
  const cases = [
    nested,
    merge(Object.create(null), payload),
    merge(payload, { enabled: true }),
    merge({ list: [] }, { list: [payload] }).list[0],
  ]

  for (const result of cases) {
    assert.equal(Object.getPrototypeOf(result), Object.prototype)
    assert.equal(result.injected, undefined)
    assert.equal(result.keep, 1)
  }
  assert.equal(cases[2].enabled, true)
})
