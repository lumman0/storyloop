import type { Route } from "@playwright/test";

export async function commonApi(route: Route): Promise<boolean> {
  const path = new URL(route.request().url()).pathname;
  if (path === "/v1/sessions/current") {
    await route.fulfill({ json: { player_id: "reader", roles: ["reviewer"], capabilities: ["review.submissions"] } });
    return true;
  }
  if (path === "/v1/billing/wallet") {
    await route.fulfill({ json: { balance_points: "500.000", balance_milli_points: 500000 } });
    return true;
  }
  return false;
}

export const view = {
  game_id: "game", catalog_id: "test", mode: "freeform", opening: "故事开始。", body: "",
  suggestions: [], action_options: [], tick: 0, state_version: 0, day: null, complete: false, turn_id: null,
};
