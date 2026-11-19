// Site password (browser login box). Any username; the password must equal SITE_PASSWORD, and if it
// is not set nobody gets in. 4 wrong passwords within 24 hours lock that connection (IP, or IPv6 /64)
// out of this site for 24 hours, even with the right password. Counts live in the GUARD D1 database
// (shared by the Nexopel sites, keyed by site and hashed IP). If GUARD is unreachable, the password
// is still required; only the lockout pauses.
const MAX_WRONG_PASSWORDS = 4;
const LOCK_MS = 24 * 60 * 60 * 1000;

// Returns a Response to send instead of the page, or null when the visitor may continue.
async function sitePasswordGate(request, env, site) {
  const header = request.headers.get('authorization') || '';
  if (!header.startsWith('Basic ')) return askForPassword();

  const key = await connectionKey(site, request);
  const now = Date.now();
  const state = await env.GUARD.prepare('SELECT locked_until FROM login_failures WHERE key = ?1')
    .bind(key).first().catch(logGuardError);
  if (state?.locked_until > now) return lockedOut(state.locked_until);

  if (isSitePassword(header, env)) {
    if (state) await env.GUARD.prepare('DELETE FROM login_failures WHERE key = ?1').bind(key).run().catch(logGuardError);
    return null;
  }

  const counted = await env.GUARD.prepare(
    `INSERT INTO login_failures (key, failures, first_failure_at) VALUES (?1, 1, ?2)
     ON CONFLICT (key) DO UPDATE SET
       failures = CASE WHEN first_failure_at > ?2 - ?3 THEN failures + 1 ELSE 1 END,
       first_failure_at = CASE WHEN first_failure_at > ?2 - ?3 THEN first_failure_at ELSE ?2 END,
       locked_until = CASE WHEN first_failure_at > ?2 - ?3 AND failures + 1 >= ?4 THEN ?2 + ?3 END
     RETURNING locked_until`,
  ).bind(key, now, LOCK_MS, MAX_WRONG_PASSWORDS).first().catch(logGuardError);
  return counted?.locked_until ? lockedOut(counted.locked_until) : askForPassword();
}

function isSitePassword(header, env) {
  if (!env.SITE_PASSWORD) return false;
  try {
    const decoded = atob(header.slice(6));
    return decoded.slice(decoded.indexOf(':') + 1) === env.SITE_PASSWORD;
  } catch {
    return false;
  }
}

// Hashed so the table never stores visitors' IP addresses
async function connectionKey(site, request) {
  const ip = request.headers.get('cf-connecting-ip') || 'unknown';
  const network = ip.includes(':') ? ipv6Network(ip) : ip;
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(network));
  return `${site}:${[...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, '0')).join('')}`;
}

// One device can switch freely between addresses inside its IPv6 /64
function ipv6Network(ip) {
  const [head, tail] = ip.split('::');
  const before = head ? head.split(':') : [];
  const after = tail ? tail.split(':') : [];
  const groups = tail === undefined ? before : [...before, ...Array(8 - before.length - after.length).fill('0'), ...after];
  return `${groups.slice(0, 4).map((group) => parseInt(group, 16).toString(16)).join(':')}::/64`;
}

function askForPassword() {
  return new Response('Password required', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Nexopel", charset="UTF-8"' },
  });
}

function lockedOut(until) {
  return new Response(`Too many wrong passwords from your connection. Try again after ${new Date(until).toUTCString()}.`, {
    status: 429,
    headers: { 'Retry-After': String(Math.ceil((until - Date.now()) / 1000)) },
  });
}

function logGuardError(error) {
  console.error('[site password] lockout check failed', error);
  return null;
}

export async function onRequest({ request, env, next }) {
  return (await sitePasswordGate(request, env, 'sawmills-poland')) ?? next();
}
