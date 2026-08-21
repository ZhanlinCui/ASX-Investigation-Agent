import type { Report } from "./types";

export const apiBase =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function loadVersionReport(
  caseId: string,
  versionId: string,
  fetcher: typeof fetch = fetch,
): Promise<Report | null> {
  const response = await fetcher(
    `${apiBase}/api/v1/investigations/${caseId}/versions/${versionId}`,
  );
  return response.ok ? ((await response.json()) as Report) : null;
}
