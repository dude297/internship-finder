// Pure logic for the global requirement review queue (ADR-024), kept out of the page so the
// keyboard rules are unit-tested.

export type ShortcutAction = 'accept' | 'edit' | 'reject' | 'skip' | 'next' | 'previous'

const shortcuts: Record<string, ShortcutAction> = {
  a: 'accept',
  e: 'edit',
  r: 'reject',
  s: 'skip',
  j: 'next',
  k: 'previous',
}

export const shortcutHints: { key: string; label: string }[] = [
  { key: 'A', label: 'accept' },
  { key: 'E', label: 'edit and accept' },
  { key: 'R', label: 'reject' },
  { key: 'S', label: 'skip' },
  { key: 'J', label: 'next' },
  { key: 'K', label: 'previous' },
]

/** True when the event came from somewhere the owner is typing (or choosing) a value, where a
 * letter must never trigger a review action. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return (
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable
  )
}

interface KeyLike {
  key: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
  repeat: boolean
  target: EventTarget | null
}

/** The review action a keypress means, or null. Modified keys (browser/OS shortcuts), key
 * repeat (holding a key must not accept twice), and typing targets never trigger one. */
export function shortcutFor(event: KeyLike): ShortcutAction | null {
  if (event.ctrlKey || event.metaKey || event.altKey || event.repeat) return null
  if (isTypingTarget(event.target)) return null
  return shortcuts[event.key.toLowerCase()] ?? null
}

/** Moves the cursor within [0, length - 1]; 0 for an empty list. */
export function moveCursor(index: number, delta: number, length: number): number {
  if (length <= 0) return 0
  return Math.min(length - 1, Math.max(0, index + delta))
}

/** Keeps only IDs still present, so a selection never refers to an item that left the queue. */
export function pruneSelection(selected: Set<string>, present: string[]): Set<string> {
  const keep = new Set(present)
  return new Set([...selected].filter((id) => keep.has(id)))
}
