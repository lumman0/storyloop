/** Translate legacy command hints in saved prose into player-facing controls. */
export function playerFacingText(text: string): string {
  return text
    .replace(/输入\s*\/next\s*可以推进到下一时段[。.]?/g, "行动会让时间自然流逝。")
    .replace(/\/next\b/g, "继续行动")
    .replace(/\/rest\b/g, "休息一晚")
    .replace(/\/continue\b/g, "“继续阅读”按钮")
    .replace(/\/choose\b/g, "剧情选择按钮");
}

/** Some structured model responses contain escaped line breaks as literal text. */
export function storyLineBreaks(text: string): string {
  return text.replace(/\\r\\n|\\n|\\r/g, "\n");
}

export function containsStoryCommand(text: string): boolean {
  return /\/(?:next|rest|choose|continue)\b/i.test(text);
}

export function isStoryCommandInput(text: string): boolean {
  return /^\/(?:next|rest|continue)$|^\/choose\s/i.test(text.trim());
}
