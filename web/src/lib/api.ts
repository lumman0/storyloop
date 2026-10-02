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
  kind: "narration" | "scene" | "dialogue" | "message" | "prompt";
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
  complete: boolean;
  turn_id: string | null;
};
export type History = {
  game_id: string;
  intro: View;
  turns: { request_id: string; input: string | null; response: View }[];
};
export type Session = { player_id: string; token: string };

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

export const api = {
  register: (username: string, password: string) =>
    request<Session>("/v1/accounts", undefined, "POST", { username, password }),
  login: (username: string, password: string) =>
    request<Session>("/v1/sessions", undefined, "POST", { username, password }),
  logout: (token: string) =>
    request<{ status: string }>("/v1/sessions/current", token, "DELETE"),
  catalog: (token: string) => request<{ games: Game[] }>("/v1/catalog", token),
  saves: (token: string) => request<{ saves: Save[] }>("/v1/saves", token),
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
};
