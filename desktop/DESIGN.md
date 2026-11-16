# Desktop visual system

The vault uses a compact collection and a reading surface. A top toolbar keeps Vault, Review, Generator, Settings, the theme switcher, and Lock vault within reach. Each pane scrolls independently in a desktop window. At 760 px and below, the toolbar wraps and the list and detail take turns filling the window. Preserve focus when moving between them.

## Identity and color

The [mark](public/mark.svg) uses two interlocking angles. Use the same geometry on the favicon, app icon, unlock screen, and toolbar. Pair it with the full name in product surfaces. Inter is bundled locally. Use 12–13 px for metadata, 14 px for controls and body text, and 24–40 px for page headings depending on the window.

| Role | Light | Dark |
| --- | --- | --- |
| Canvas | `#f3f5f9` | `#151b25` |
| Credential list | `#f2f4f8` | `#171e29` |
| Reading and form surface | `#ffffff` | `#1b2330` |
| Text | `#182334` | `#ecf2fb` |
| Secondary text | `#4c5c71` | `#a8b6cc` |
| Accent | `#2f53a6` | `#a9c1ff` |
| Selection | `#e5edfb` | `#293a59` |

Use the tokens in [styles.css](src/styles.css). Reserve the accent for primary actions and active states. Field separators use the quieter line token. Interactive fields use a higher-contrast outline, and keyboard focus uses a separate ring. Pair error and status colors with text.

## Interaction

- Group credential fields with rules and spacing. Use persistent labels in forms and place errors beside the affected workflow.
- Keep **Copy password** visible in the detail view. Quick copy is visible on the selected row, on hover, during keyboard focus, and on touch devices.
- Keep review and settings scannable with section headings and aligned actions. Use empty-state copy that identifies the current state and offers a relevant next action.

## Visual review

Launch `npm run dev` and open [the desktop preview](http://127.0.0.1:1420/preview/) using the test credentials in the [desktop README](README.md). The fixture runs in memory and simulates the Tauri bridge without using the file system, USB devices, or the clipboard. The preview entry point is excluded from the production build.

Use `?scenario=empty` for an empty vault, `?scenario=new` for first launch, or `?scenario=windows` for the system-prompt UI. Check both themes with the unlock form, credential list and detail, editor, review, generator, and settings. Check at a desktop size and again at a width below 760 px. Verify the actual system dialogs and clipboard in Tauri.

Design references include [Linear’s desktop navigation](https://linear.app/now/behind-the-latest-design-refresh), [1Password’s desktop vault](https://support.1password.com/getting-started-windows/), [Bitwarden’s desktop workflows](https://bitwarden.com/help/getting-started-desktop/), and [Proton Pass’s local app workflows](https://proton.me/support/how-to-use-proton-pass-desktop-app). The design and review used [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill), [Impeccable](https://github.com/pbakaus/impeccable), [Anthropic Frontend Design](https://github.com/anthropics/skills), and [Vercel Web Design Guidelines](https://github.com/vercel-labs/agent-skills).
