export const categories = ["All items", "Personal", "Work", "Finance", "Developer"] as const
export type Category = (typeof categories)[number]

export type Credential = {
  id: string
  name: string
  username: string
  website: string
  category: Exclude<Category, "All items">
  mark: string
  tint: "blue" | "violet" | "green" | "amber" | "neutral"
  notes?: string
}

export const credentials: Credential[] = [
  { id: "github", name: "GitHub", username: "alex@example.test", website: "github.com",
    category: "Developer", mark: "G", tint: "neutral", notes: "Personal development account." },
  { id: "mail", name: "Personal email", username: "alex@example.test", website: "mail.example.test",
    category: "Personal", mark: "M", tint: "blue" },
  { id: "linear", name: "Linear", username: "alex@studio.example", website: "linear.app",
    category: "Work", mark: "L", tint: "violet" },
  { id: "bank", name: "Savings account", username: "alex@example.test", website: "bank.example.test",
    category: "Finance", mark: "S", tint: "green" },
  { id: "figma", name: "Figma", username: "alex@studio.example", website: "figma.com",
    category: "Work", mark: "F", tint: "amber" },
  { id: "npm", name: "npm", username: "alex-dev", website: "npmjs.com",
    category: "Developer", mark: "N", tint: "amber" },
]
