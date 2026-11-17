export type ActiveRole = "tenant" | "landlord";

export type Profile = {
  id: string;
  display_name: string | null;
  whatsapp: string | null;
  active_role: ActiveRole | null;
  created_at: string;
};

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

function apiUrl(path: string): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!baseUrl) throw new Error("Set NEXT_PUBLIC_API_URL in apps/web/.env.");
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

async function parseApiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as {
      detail?: { message?: string } | string;
      message?: string;
    };
    if (typeof body.detail === "object" && body.detail?.message) return body.detail.message;
    if (typeof body.detail === "string") return body.detail;
    if (body.message) return body.message;
  } catch {
    // Use the status-based message when the API response is not JSON.
  }
  return `The API request failed (${response.status}).`;
}

export async function getMyProfile(accessToken: string): Promise<Profile> {
  const response = await fetch(apiUrl("/me"), {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(await parseApiError(response), response.status);
  return (await response.json()) as Profile;
}

export function displayNameFromMetadata(metadata: Record<string, unknown> | null | undefined, email?: string | null): string | undefined {
  for (const key of ["full_name", "name", "display_name", "preferred_username"]) {
    const value = metadata?.[key];
    if (typeof value === "string" && value.trim()) return value.trim().slice(0, 120);
  }
  const emailName = email?.split("@")[0]?.trim();
  return emailName ? emailName.slice(0, 120) : undefined;
}

export async function updateMyProfile(
  accessToken: string,
  updates: Partial<Pick<Profile, "display_name" | "whatsapp" | "active_role">>,
): Promise<Profile> {
  const response = await fetch(apiUrl("/me"), {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(updates),
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(await parseApiError(response), response.status);
  return (await response.json()) as Profile;
}

export async function updateActiveRole(
  accessToken: string,
  activeRole: ActiveRole,
  displayName?: string,
): Promise<Profile> {
  return updateMyProfile(accessToken, {
    active_role: activeRole,
    ...(displayName ? { display_name: displayName } : {}),
  });
}
