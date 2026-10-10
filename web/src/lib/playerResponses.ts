import { ContractError, parseStreamData, parseTurnFailure } from "./contracts.ts";
import type { TurnFailure, TurnStreamEvent, View } from "./contracts.ts";

export class ApiError extends Error {
  readonly status: number;
  readonly failure?: TurnFailure;

  constructor(message: string, status: number, failure?: TurnFailure) {
    super(message);
    this.status = status;
    this.failure = failure;
  }
}

export function responseError(status: number, payload: unknown): ApiError {
  let failure: TurnFailure | undefined;
  try {
    failure = parseTurnFailure(payload);
  } catch {
    // A response without valid execution evidence leaves the pending turn intact.
  }
  const detail = payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string"
    ? payload.detail : failure?.message || "请求未能完成，请稍后重试。";
  return new ApiError(detail, status, failure);
}

export async function readTurnStream(response: Response, onEvent: (event: TurnStreamEvent) => void): Promise<View> {
  if (!response.ok) throw responseError(response.status, await response.json().catch(() => null));
  if (!response.body) throw new ApiError("浏览器无法读取实时响应。", 0);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: View | null = null;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const dataLines = frame.split("\n").filter((line) => line === "data" || line.startsWith("data:"))
          .map((line) => {
            const value = line.slice(5);
            return value.startsWith(" ") ? value.slice(1) : value;
          });
        if (dataLines.length) {
          const event = parseStreamData(dataLines.join("\n"));
          if (event.type === "error") throw new ApiError(event.message, 400, event);
          onEvent(event);
          if (event.type === "complete") completed = event.view;
        }
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    if (buffer.trim() && !buffer.trim().startsWith(":")) throw new ContractError();
    if (!completed) throw new ApiError("连接中断，尚未收到完整结果。可重试这条行动。", 0);
    return completed;
  } catch (error) {
    if (error instanceof ContractError) throw new ApiError(error.message, 0);
    throw error;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
