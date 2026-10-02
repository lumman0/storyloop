const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export type Game = {
  id: string;
  title: string;
  mode: "campaign" | "freeform";
  summary: string;
  genre: string;
  theme: string;
};
export type Save = {
  game_id: string;
  catalog_id: string;
  title: string;
  mode: string | null;
  available: boolean;
  tick: number;
  day: number | null;
  complete: boolean;
};
export type StorySegment = {
  kind: "narration" | "scene" | "dialogue" | "message" | "prompt" | "time";
  text: string;
  speaker_id?: string;
  speaker_name?: string;
};
export type Interaction = {
  id: string;
  kind: "choice" | "message";
  prompt: string;
  options: {
    id: string;
    label: string;
    enabled: boolean;
    requires_text: boolean;
  }[];
};
export type View = {
  game_id: string;
  catalog_id: string;
  mode: string;
  opening: string;
  body: string;
  segments?: StorySegment[];
  interaction?: Interaction | null;
  suggestions: string[];
  tick: number;
  state_version: number;
  day: number | null;
  time_of_day?: string | null;
  complete: boolean;
  turn_id: string | null;
  billing?: TurnBilling;
};
export type TurnBilling = {
  charged_milli_points: number;
  charged_points: string;
  usage_cost_milli_points: number;
  balance_milli_points: number;
  balance_points: string;
  input_tokens: number;
  output_tokens: number;
  model_calls: number;
};
export type CreditWallet = {
  balance_milli_points: number;
  balance_points: string;
  welcome_points: number;
  points_per_rmb: number;
};
export type CreditEntry = {
  entry_id: string;
  kind: "welcome" | "turn";
  game_id: string | null;
  request_id: string | null;
  delta_milli_points: number;
  delta_points: string;
  usage_cost_milli_points: number;
  balance_after_points: string;
  pricing_version: string;
  usage: {
    model: string;
    task: string;
    input_tokens: number;
    output_tokens: number;
    cached_input_tokens: number;
  }[];
  created_order: number;
};
export type History = {
  game_id: string;
  intro: View;
  turns: { request_id: string; input: string | null; response: View }[];
};
export type Session = { player_id: string; token: string };
export type TurnStreamEvent =
  | { type: "stage"; stage: string }
  | { type: "segment"; segment: StorySegment }
  | { type: "preview"; body: string; segments: StorySegment[] }
  | { type: "complete"; view: View }
  | { type: "error"; message: string };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  token?: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String(payload.detail)
        : "请求未能完成，请稍后重试。";
    throw new ApiError(detail, response.status);
  }
  return payload as T;
}

async function streamTurn(
  token: string,
  gameId: string,
  text: string,
  requestId: string,
  onEvent: (event: TurnStreamEvent) => void,
): Promise<View> {
  const response = await fetch(
    `${API_BASE}/v1/saves/${encodeURIComponent(gameId)}/turns/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ text, request_id: requestId }),
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(
      payload && typeof payload.detail === "string"
        ? payload.detail
        : "请求未能完成，请稍后重试。",
      response.status,
    );
  }
  if (!response.body) throw new ApiError("浏览器无法读取实时响应。", 0);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: View | null = null;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = frame.split("\n").filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6)).join("\n");
      if (data) {
        const event = JSON.parse(data) as TurnStreamEvent;
        if (event.type === "error") throw new ApiError(event.message, 400);
        onEvent(event);
        if (event.type === "complete") completed = event.view;
      }
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (!completed) throw new ApiError("连接中断，尚未收到完整结果。可重试这条行动。", 0);
  return completed;
}

export const api = {
  register: (username: string, password: string, inviteCode: string) =>
    request<Session>("/v1/accounts", undefined, "POST", {
      username, password, invite_code: inviteCode || undefined,
    }),
  login: (username: string, password: string) =>
    request<Session>("/v1/sessions", undefined, "POST", { username, password }),
  logout: (token: string) =>
    request<{ status: string }>("/v1/sessions/current", token, "DELETE"),
  catalog: (token: string) => request<{ games: Game[] }>("/v1/catalog", token),
  saves: (token: string) => request<{ saves: Save[] }>("/v1/saves", token),
  wallet: (token: string) => request<CreditWallet>("/v1/billing/wallet", token),
  creditLedger: (token: string) => request<{ entries: CreditEntry[] }>("/v1/billing/ledger", token),
  createSave: (token: string, catalogId: string) =>
    request<View>("/v1/saves", token, "POST", { catalog_id: catalogId }),
  resume: (token: string, gameId: string) =>
    request<View>(
      `/v1/saves/${encodeURIComponent(gameId)}/resume`,
      token,
      "POST",
    ),
  history: (token: string, gameId: string) =>
    request<History>(`/v1/saves/${encodeURIComponent(gameId)}/history`, token),
  turn: (token: string, gameId: string, text: string, requestId: string) =>
    request<View>(
      `/v1/saves/${encodeURIComponent(gameId)}/turns`,
      token,
      "POST",
      { text, request_id: requestId },
    ),
  turnStream: streamTurn,
};
