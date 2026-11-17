# Desktop visual system

The vault uses a compact collection and a reading surface. A top toolbar keeps Vault, Review, Generator, Settings, the theme switcher, and Lock vault within reach. Each pane scrolls independently in a desktop window. At 760 px and below, the toolbar wraps and the list and detail take turns filling the window. Preserve focus when moving between them.

## Identity and color

The [mark](public/mark.svg) is a 3×3 grid of blocks on a graphite tile. The centre block is signal orange and the bottom-right block is missing, which keeps the mark recognizable at 16 px. Use the same file on the favicon, the app icon in `src-tauri/icons`, the unlock screen, and the toolbar. Pair it with the full name in product surfaces. Regenerate the app icons with `npx tauri icon public/mark.svg` and keep `icon.png` (128 px) and `icon.ico`.

Inter is bundled locally in 400, 500, 600, and 700 weights. Use 12–13 px for metadata, 13–14 px for controls and body text, and 19–25 px for pane and page headings.

The palette is graphite with one signal colour. Neutrals carry the interface; primary buttons are ink on light and near-white on dark. Orange marks selection, focus, and progress (sliders, switches, the reveal countdown) and nothing else.

| Role | Light | Dark |
| --- | --- | --- |
| Canvas and reading pane | `#f5f5f4` | `#111113` |
| Credential list | `#fafaf9` | `#141416` |
| Cards and toolbar | `#ffffff` | `#18181b` |
| Text | `#18181b` | `#fafafa` |
| Secondary text | `#5f5f68` | `#a1a1aa` |
| Primary button | `#18181b` | `#f4f4f5` |
| Accent text (selection, links) | `#c2410c` | `#ff8a50` |
| Signal fill (focus, progress) | `#ff6a2b` | `#ff6a2b` |
| Selection | `#fdeee6` | `#2e1b12` |

Use the tokens in [styles.css](src/styles.css). Warnings use amber and errors use red so they stay distinct from the signal orange. Group related fields in one bordered card with a 10 px radius and never nest cards; controls use a 7 px radius. Prefer borders over shadows. Field separators use the quieter line token. Interactive fields use a higher-contrast outline, and keyboard focus uses a separate ring. Pair error, warning, and success colours with text and an icon.

Credential avatars are neutral letter tiles. Revealed passwords use a monospace face and colour digits and symbols so similar characters are easier to tell apart.

## Interaction

- Group credential fields in a card. Use persistent labels in forms and place errors beside the affected workflow.
- Keep **Copy** visible beside the password in the detail view. Quick copy is visible on the selected row, on hover, during keyboard focus, and on touch devices.
- A revealed password shows a bar that counts down the 10-second reveal.
- The master password field offers a show/hide toggle and warns when Caps Lock is on. Creating a vault shows progress toward the 15-character minimum without storing the value.
- Ask for deletion in an inline danger callout that names the credential.
- Keep review and settings scannable with section headings, summary figures, and aligned actions. Use empty-state copy that identifies the current state and offers a relevant next action.
- Use motion only as feedback to an action, such as a confirmation or status message. Do not animate view entrances. Remove motion under `prefers-reduced-motion`.

## Avoid

The lock screen is a tool, not a landing page. Do not add marketing copy, feature lists, gradient text, glows, or decorative backgrounds. Avoid icon tiles above headings, metric-card rows, accent stripes on list rows, all-caps section labels, and arrows on buttons. These patterns follow the [Impeccable slop catalog](https://impeccable.style/slop) and the [Vercel web interface guidelines](https://github.com/vercel-labs/web-interface-guidelines).

## Visual review

Launch `npm run dev` and open [the desktop preview](http://127.0.0.1:1420/preview/) using the test credentials in the [desktop README](README.md). The fixture runs in memory and simulates the Tauri bridge without using the file system, USB devices, or the clipboard. The preview entry point is excluded from the production build.

Use `?scenario=empty` for an empty vault, `?scenario=new` for first launch, or `?scenario=windows` for the system-prompt UI. Check both themes with the unlock form, credential list and detail, editor, review, generator, and settings. Check at a desktop size and again at a width below 760 px. Verify the actual system dialogs and clipboard in Tauri.

Design references include [Linear’s desktop navigation](https://linear.app/now/behind-the-latest-design-refresh), [1Password’s desktop vault](https://support.1password.com/getting-started-windows/), [Bitwarden’s desktop workflows](https://bitwarden.com/help/getting-started-desktop/), and [Proton Pass’s local app workflows](https://proton.me/support/how-to-use-proton-pass-desktop-app). The design and review used [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill), [Impeccable](https://github.com/pbakaus/impeccable), [Anthropic Frontend Design](https://github.com/anthropics/skills), and [Vercel Web Design Guidelines](https://github.com/vercel-labs/agent-skills).
