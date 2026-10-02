export function createRequestId(
  random: Pick<Crypto, "getRandomValues"> = crypto,
): string {
  const bytes = random.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
