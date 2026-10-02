export type StoryInlineToken = {
  kind: "text" | "emphasis" | "strong";
  text: string;
};

export function parseStoryInline(text: string): StoryInlineToken[] {
  const tokens: StoryInlineToken[] = [];
  const markers = /\\\*|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*/g;
  let cursor = 0;

  function appendText(value: string) {
    if (!value) return;
    const previous = tokens[tokens.length - 1];
    if (previous?.kind === "text") previous.text += value;
    else tokens.push({ kind: "text", text: value });
  }

  for (const match of text.matchAll(markers)) {
    const start = match.index;
    appendText(text.slice(cursor, start));
    if (match[0] === "\\*") appendText("*");
    else if (match[1] !== undefined) tokens.push({ kind: "strong", text: match[1] });
    else tokens.push({ kind: "emphasis", text: match[2] });
    cursor = start + match[0].length;
  }
  appendText(text.slice(cursor));
  return tokens;
}
