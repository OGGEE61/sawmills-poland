// Site-wide password (browser login box) for every page and CSV on the Pages site.
// Any username; the password must equal SITE_PASSWORD (Pages project setting). If it is not set, nobody gets in.
export async function onRequest({ request, env, next }) {
  const header = request.headers.get('authorization') || '';
  if (env.SITE_PASSWORD && header.startsWith('Basic ')) {
    try {
      const decoded = atob(header.slice(6));
      if (decoded.slice(decoded.indexOf(':') + 1) === env.SITE_PASSWORD) return next();
    } catch {
      // malformed header: fall through to the login box
    }
  }
  return new Response('Password required', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Nexopel", charset="UTF-8"' },
  });
}
