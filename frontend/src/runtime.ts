// Runtime transport config. In the packaged desktop app, Electron's preload injects
// window.desktop with the live backend URL + per-launch token. On the plain web build
// these are undefined → empty base, so the existing Vite "/api" dev proxy keeps working
// unchanged. This is the single place that knows whether we're in Electron or the browser.

declare global {
  interface Window {
    desktop?: { apiBase: string; token: string };
  }
}

export const API_BASE = window.desktop?.apiBase ?? "";
export const AUTH_TOKEN = window.desktop?.token ?? "";

/** Absolute URL for an API path: prefixed with the backend origin in desktop, relative on web. */
export const apiUrl = (path: string): string => `${API_BASE}${path}`;

/** fetch() that targets the live backend and carries the auth token (no-op header on web). */
export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (AUTH_TOKEN) headers.set("x-dielectric-token", AUTH_TOKEN);
  return fetch(apiUrl(path), { ...init, headers });
}

export {};
