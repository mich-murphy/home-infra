/** Strict JWT aud validation shared by the real browser flow and pure tests. */
export function audienceMatches(audience, clientId) {
  if (typeof clientId !== 'string' || clientId.length === 0) return false;
  if (typeof audience === 'string') return audience === clientId;
  return Array.isArray(audience) && audience.every(value => typeof value === 'string') && audience.includes(clientId);
}

/** Reject only a real token-endpoint OAuth denial, never a transport/server error. */
export function isInvalidGrant(response) {
  return response?.status === 400 && response?.body?.error === 'invalid_grant' &&
    !['access_token', 'id_token', 'refresh_token'].some(key => key in response.body);
}

export function isWrongRedirectDenial(response) {
  return response?.status === 200 && response.origin === 'https://pocket-id.proof.invalid' &&
    response.path === '/interaction/error' && response.hasError === true &&
    response.errorMentionsRedirect === true && response.hasCode === false && response.callbackRequests === 0;
}
