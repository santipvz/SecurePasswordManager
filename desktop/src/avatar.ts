export function avatarLetter(name: string): string {
  return Array.from(name.trim())[0]?.toUpperCase() ?? "?"
}
