import { ApiError } from "./api";

export const SESSION_KEY = "storyloop.session";

export function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return "登录已失效，请重新登录。";
    return error.message;
  }
  return "连接服务失败。请确认后端已启动，然后重试。";
}
