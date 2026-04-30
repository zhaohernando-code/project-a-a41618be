import { request } from "./core";
import type { AuthContextResponse } from "../types";

export function getAuthContext(): Promise<AuthContextResponse> {
  return request<AuthContextResponse>("/auth/context");
}
