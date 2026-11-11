/** Strict JWT aud validation shared by the real browser flow and pure tests. */
export function audienceMatches(audience, clientId) {
  if (typeof clientId !== 'string' || clientId.length === 0) return false;
  if (typeof audience === 'string') return audience === clientId;
  return Array.isArray(audience) && audience.every(value => typeof value === 'string') && audience.includes(clientId);
}
