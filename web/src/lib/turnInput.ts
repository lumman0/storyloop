export const TURN_INPUT_LIMIT = 10000;

// Python len(str) counts Unicode code points; DOM maxLength counts UTF-16 units.
export function limitTurnInput(text: string, limit = TURN_INPUT_LIMIT): string {
  return Array.from(text).slice(0, Math.max(0, limit)).join("");
}

export function isTurnInputTooLong(text: string): boolean {
  return Array.from(text).length > TURN_INPUT_LIMIT;
}

export function choiceCommand(optionId: string, note: string): string {
  const trimmed = note.trim();
  return `/choose ${optionId}${trimmed ? ` ${trimmed}` : ""}`;
}

export function limitChoiceNote(optionId: string, note: string): string {
  return limitTurnInput(note, TURN_INPUT_LIMIT - Array.from(`/choose ${optionId} `).length);
}
