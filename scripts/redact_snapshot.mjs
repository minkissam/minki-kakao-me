/** Defense in depth for browser snapshots; never print a raw credential page. */
export function redactSnapshot(snapshot, { knownSecrets = [] } = {}) {
  if (typeof snapshot !== 'string') throw new TypeError('snapshot must be a string');
  if (!Array.isArray(knownSecrets) || knownSecrets.some(value => typeof value !== 'string')) {
    throw new TypeError('knownSecrets must contain strings');
  }

  // Hide the entire page: secrets may be short, split across DOM nodes, or use
  // an unknown alphabet. A hex-only expression cannot protect this surface.
  const credentialPage = /REST\s*API\s*(?:키|key)|클라이언트\s*시크릿|client[\s_-]*secret|access[\s_-]*token|refresh[\s_-]*token|인가\s*코드|authorization[\s_-]*code/i;
  if (credentialPage.test(snapshot)) {
    return '[REDACTED: credential page; report only verified non-secret status]';
  }

  let safe = snapshot;
  for (const secret of [...knownSecrets].filter(Boolean).sort((a, b) => b.length - a.length)) {
    safe = safe.split(secret).join('[REDACTED]');
  }
  // This fallback also covers mixed-case client secrets, URL-safe tokens,
  // Base64 and JWTs. It is deliberately conservative, not proof of safety.
  return safe.replace(/[A-Za-z0-9_+\/.=-]{24,}/g, '[REDACTED]');
}
