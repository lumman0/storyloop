/** Translate legacy command hints in saved prose into player-facing controls. */
export function playerFacingText(text: string): string {
  return text
    .replace(/输入\s*\/next\s*可以推进到下一时段[。.]?/g, "点击“推进时段”按钮，可以继续日程。")
    .replace(/\/next\b/g, "“推进时段”按钮")
    .replace(/\/rest\b/g, "“休息到次日”按钮")
    .replace(/\/continue\b/g, "“继续阅读”按钮")
    .replace(/\/choose\b/g, "剧情选择按钮");
}

export function containsStoryCommand(text: string): boolean {
  return /\/(?:next|rest|choose|continue)\b/i.test(text);
}

export function isStoryCommandInput(text: string): boolean {
  return /^\/(?:next|rest|continue)$|^\/choose\s/i.test(text.trim());
}
