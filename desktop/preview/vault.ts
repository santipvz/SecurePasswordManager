type Metadata = { name: string; username: string; url: string }
type Credential = Metadata & { password: string; notes: string }
type Request = {
  generation?: number
  name?: string
  selection?: "default" | "existing" | "new"
  action?: "save_backup" | "open_backup" | "import_legacy"
  master?: string
  pin?: string
  length?: number
  symbols?: boolean
  entry?: Metadata & { previous?: string; password?: string; notes?: string }
  request?: { action: "change_master" | "register_key" | "remove_key"; master?: string; new_master?: string; pin?: string }
}

const sampleEntries: Credential[] = [
  { name: "Fastmail", username: "alex@studio.example", url: "app.fastmail.com", password: "example-fastmail-41", notes: "" },
  { name: "Figma", username: "alex@studio.example", url: "figma.com", password: "example-figma-89", notes: "" },
  { name: "GitHub", username: "alex-dev", url: "github.com", password: "example-github-17", notes: "Personal developer account. Recovery codes are stored separately." },
  { name: "Hetzner Cloud", username: "ops@studio.example", url: "console.hetzner.cloud", password: "example-hetzner-24", notes: "" },
  { name: "Home router", username: "admin", url: "192.168.1.1", password: "demo123", notes: "" },
  { name: "Linear", username: "alex@studio.example", url: "linear.app", password: "example-linear-36", notes: "Workspace for the product design team." },
  { name: "Proton Mail", username: "alex@example.test", url: "account.proton.me", password: "example-mail-72", notes: "" },
]

const metadata = ({ name, username, url }: Credential): Metadata => ({ name, username, url })

export function createPreviewVault(scenario: string | null) {
  let entries = (scenario === "empty" || scenario === "new") ? [] : sampleEntries.map((entry) => ({ ...entry }))
  let master = "preview-password"
  let generation = 1
  let unlocked = false
  let creating = false
  let exists = scenario !== "new"
  let hasSecurityKey = exists && scenario !== "empty"
  let fileName: string | null = null

  const status = () => ({
    generation, creating, exists, has_security_key: hasSecurityKey,
    file_name: fileName, native_key_prompt: scenario === "windows",
  })
  const findEntry = (name?: string) => {
    const entry = entries.find((item) => item.name === name)
    if (!entry) throw "entry_missing"
    return entry
  }

  return async function invoke(command: string, args: Request = {}): Promise<unknown> {
    switch (command) {
      case "vault_status": return status()
      case "vault_active": return unlocked && args.generation === generation
      case "vault_activity": return
      case "vault_lock":
        unlocked = false
        generation++
        return
      case "vault_select":
        creating = args.selection === "new"
        exists = !creating
        fileName = creating ? "new-vault.spm" : args.selection === "existing" ? "example.spm" : null
        generation++
        return status()
      case "vault_unlock":
      case "vault_unlock_key":
        if (args.generation !== generation) throw "locked"
        if (command === "vault_unlock_key") {
          if (!hasSecurityKey || (scenario !== "windows" && args.pin !== "123456")) throw "pin_invalid"
        } else if (creating && args.master) {
          master = args.master
          creating = false
          exists = true
          hasSecurityKey = false
          entries = []
        } else if (!exists || args.master !== master) {
          throw "open_failed"
        }
        unlocked = true
        return { generation, has_security_key: hasSecurityKey }
      case "vault_generate": {
        if (args.generation !== undefined && (!unlocked || args.generation !== generation)) throw "locked"
        const length = args.length ?? 0
        if (!Number.isInteger(length) || length < 12 || length > 256) throw "generator_length"
        const sample = args.symbols ? "Example7!onlyG3v@" : "Example7OnlyG3va"
        return sample.repeat(Math.ceil(length / sample.length)).slice(0, length)
      }
    }

    if (!unlocked || args.generation !== generation) throw "locked"

    switch (command) {
      case "vault_list": return { entries: entries.map(metadata) }
      case "vault_entry_notes": return findEntry(args.name).notes
      case "vault_reveal": return findEntry(args.name).password
      case "vault_copy": findEntry(args.name); return
      case "vault_save": {
        const input = args.entry
        if (!input?.name?.trim()) throw "entry_invalid"
        if (entries.some((entry) => entry.name === input.name && entry.name !== input.previous)) throw "entry_duplicate"
        const password = input.password || (input.previous ? findEntry(input.previous).password : "")
        if (!password) throw "entry_invalid"
        const saved = { ...metadata({ ...input, password, notes: "" }), password, notes: input.notes ?? "" }
        entries = [...entries.filter((entry) => entry.name !== input.previous), saved]
          .sort((a, b) => a.name.localeCompare(b.name))
        return metadata(saved)
      }
      case "vault_delete":
        findEntry(args.name)
        entries = entries.filter((entry) => entry.name !== args.name)
        return
      case "vault_review":
        return {
          total: entries.length, minimum_length: 12,
          short: entries.filter((entry) => entry.password.length < 12).map((entry) => entry.name),
          reused: [],
        }
      case "vault_manage_files":
        if (args.action === "save_backup") return { action: "saved" }
        if (args.action === "open_backup") {
          fileName = "example-backup.spm"
          return { action: "selected_backup" }
        }
        return { action: "imported", entries: { entries: [] } }
      case "vault_manage_unlock": {
        const request = args.request
        if (!request || request.master !== master) throw "incorrect_master"
        if (request.action === "change_master" && request.new_master) master = request.new_master
        if (request.action === "register_key" && scenario !== "windows" && request.pin !== "123456") throw "pin_invalid"
        hasSecurityKey = request.action === "register_key"
        return { has_security_key: hasSecurityKey }
      }
      default: throw new Error("Unknown preview command: " + command)
    }
  }
}
