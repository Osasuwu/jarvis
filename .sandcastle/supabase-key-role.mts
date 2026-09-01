// SUPABASE_KEY role validation (#1121, decision 94c55c7b). Non-emptiness
// alone doesn't stop a service-role key from being forwarded into a spawned
// container — this validates by role instead:
//   - new Supabase API key formats: sb_publishable_* is accepted (anon-
//     equivalent), sb_secret_* is rejected (service-role-equivalent).
//   - legacy JWT keys: decode the unverified payload's `role` claim; "anon"
//     is accepted, "service_role" (or anything else) is rejected.
// This only classifies the key's role — it does not verify the JWT
// signature. Signature verification happens Supabase-side on every request;
// this check exists purely to stop the wrong *class* of key from being
// forwarded into a spawned container in the first place.

export class SupabaseKeyRoleError extends Error {}

function decodeJwtRole(key: string): string | null {
  const parts = key.split(".");
  if (parts.length !== 3) return null;
  try {
    const payloadB64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payloadB64 + "=".repeat((4 - (payloadB64.length % 4)) % 4);
    const payload = JSON.parse(Buffer.from(padded, "base64").toString("utf-8"));
    return typeof payload.role === "string" ? payload.role : null;
  } catch {
    return null;
  }
}

/**
 * Throws SupabaseKeyRoleError if `key` is not an anon-equivalent key.
 */
export function assertSupabaseKeyIsAnon(key: string): void {
  if (key.startsWith("sb_secret_")) {
    throw new SupabaseKeyRoleError(
      "SUPABASE_KEY is a service-role secret key (sb_secret_ prefix) — anon key only, never service-role.",
    );
  }
  if (key.startsWith("sb_publishable_")) {
    return;
  }
  const role = decodeJwtRole(key);
  if (role === "anon") {
    return;
  }
  if (role === "service_role") {
    throw new SupabaseKeyRoleError(
      "SUPABASE_KEY is a service-role JWT (role=service_role) — anon key only, never service-role.",
    );
  }
  throw new SupabaseKeyRoleError(
    "SUPABASE_KEY is not a recognized anon-role key (expected sb_publishable_* or a JWT with role=anon).",
  );
}
