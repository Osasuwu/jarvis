// Contract check for SUPABASE_KEY role validation (#1121, decision
// 94c55c7b). Mirrors Python coverage:
// tests/reactive_core/test_supabase_key_role.py.

import { assertSupabaseKeyIsAnon, SupabaseKeyRoleError } from "./supabase-key-role.mts";

let failures = 0;
const fail = (msg: string) => {
  failures += 1;
  console.error(`FAIL: ${msg}`);
};

function b64url(obj: unknown): string {
  return Buffer.from(JSON.stringify(obj))
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function fakeJwt(role: string): string {
  return `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url({ role })}.fakesig`;
}

const anonJwt = fakeJwt("anon");
const serviceRoleJwt = fakeJwt("service_role");

// 1. New-format publishable key is accepted.
try {
  assertSupabaseKeyIsAnon("sb_publishable_abc123");
} catch {
  fail("sb_publishable_ key should be accepted");
}

// 2. New-format secret key is rejected.
try {
  assertSupabaseKeyIsAnon("sb_secret_abc123");
  fail("sb_secret_ key should be rejected");
} catch (e) {
  if (!(e instanceof SupabaseKeyRoleError)) fail("sb_secret_ rejection should raise SupabaseKeyRoleError");
}

// 3. Legacy JWT with role=anon is accepted.
try {
  assertSupabaseKeyIsAnon(anonJwt);
} catch {
  fail("JWT with role=anon should be accepted");
}

// 4. Legacy JWT with role=service_role is rejected.
try {
  assertSupabaseKeyIsAnon(serviceRoleJwt);
  fail("JWT with role=service_role should be rejected");
} catch (e) {
  if (!(e instanceof SupabaseKeyRoleError)) fail("service_role rejection should raise SupabaseKeyRoleError");
}

// 5. Garbage / malformed key is rejected, not silently accepted.
try {
  assertSupabaseKeyIsAnon("not-a-real-key");
  fail("malformed key should be rejected");
} catch (e) {
  if (!(e instanceof SupabaseKeyRoleError)) fail("malformed-key rejection should raise SupabaseKeyRoleError");
}

if (failures > 0) {
  console.error(`check-supabase-key-role: ${failures} failure(s)`);
  process.exit(1);
}
console.log("check-supabase-key-role: role validation accepts anon-equivalent keys, rejects service-role/malformed");
