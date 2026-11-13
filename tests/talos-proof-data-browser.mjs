#!/usr/bin/env node
/** Mac-local Chrome WebAuthn/OIDC proof. Fresh virtual keys stay in private state.
 * Input: JSON on stdin {state, module, spki, port, mode}. No credentials in argv.
 * TLS is pinned to the exact independently CA-verified Gateway leaf SPKI, NOT
 * ignoreHTTPSErrors; all non-proof network requests are aborted.
 */
import fs from 'node:fs';
import {audienceMatches, isInvalidGrant, isWrongRedirectDenial} from './talos-proof-data-oidc.mjs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const result = {checks: [], status: 'failed', authenticator: 'fresh CDP ctap2 virtual authenticator; no physical/user passkey claim'};
const issuer = 'https://pocket-id.proof.invalid';
const here = path.dirname(fileURLToPath(import.meta.url));
let stage = 'lease';
let browser;
let leaseValidated = false;
function assert(condition, label) {
  if (!condition) throw new Error('assertion failed');
  result.checks.push(label);
}
function savePrivate(name, value) {
  const target = path.join(input.state, name);
  if (fs.existsSync(target) && fs.lstatSync(target).isSymbolicLink()) throw new Error('symlink state');
  const fd = fs.openSync(target, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY | fs.constants.O_NOFOLLOW, 0o600);
  fs.writeFileSync(fd, JSON.stringify(value));
  fs.closeSync(fd);
}
function validateLease() {
  const proc = spawnSync('python3', [path.join(here, '../scripts/talos-proof-data.py'), 'verify', '--group', 'pocket-id', '--state', input.state], {encoding:'utf8', timeout:30000});
  if (proc.status !== 0) throw new Error('lease verification failed');
  leaseValidated = true;
}
try {
  validateLease();
  if (!/^[A-Za-z0-9+/]{43}=$/.test(input.spki)) throw new Error('required Gateway SPKI pin');
  const require = createRequire(import.meta.url);
  const {chromium} = require(input.module);
  stage = 'Chrome launch';
  browser = await chromium.launch({
    executablePath: process.env.TALOS_PROOF_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: [
      `--host-resolver-rules=MAP *.proof.invalid 127.0.0.1:${Number(input.port || 18443)},EXCLUDE localhost`,
      `--ignore-certificate-errors-spki-list=${input.spki}`,
      '--disable-background-networking', '--disable-component-update', '--no-proxy-server',
      '--disable-sync', '--disable-default-apps', '--no-first-run'
    ]
  });
  result.chrome_version = browser.version();
  const context = await browser.newContext({ignoreHTTPSErrors:false,serviceWorkers:'block'});
  await context.route('**/*', async route => {
    const u = new URL(route.request().url());
    if (u.origin === issuer) return route.continue();
    if (u.protocol === 'data:') return route.continue();
    return route.abort('blockedbyclient');
  });
  await context.routeWebSocket('**/*', ws => ws.close());
  result.network_boundary = {http:'exact issuer origin only',websocket:'all blocked',service_workers:'blocked'};
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  const {authenticatorId} = await cdp.send('WebAuthn.addVirtualAuthenticator', {options:{protocol:'ctap2',transport:'internal',hasResidentKey:true,hasUserVerification:true,isUserVerified:true,automaticPresenceSimulation:true}});
  stage = 'verified/pinned Gateway navigation';
  await page.goto(issuer + '/login', {waitUntil:'domcontentloaded'});
  async function api(url, method='GET', data) {
    validateLease();
    return await page.evaluate(async ({url,method,data}) => {
      const response = await fetch(url, {method,credentials:'same-origin',headers:data ? {'Content-Type':'application/json'} : undefined,body:data ? JSON.stringify(data) : undefined});
      if (!response.ok) throw new Error('proof API status ' + response.status);
      return response.status === 204 ? null : response.json();
    }, {url,method,data});
  }
  const credentialFiles = fs.readdirSync(input.state).filter(name => /^pocket-virtual-authenticator(?:-[0-9a-f-]+)?\.json$/.test(name)).map(name => path.join(input.state,name));
  for (const file of credentialFiles) if(fs.lstatSync(file).isSymbolicLink() || (fs.statSync(file).mode & 0o777)!==0o600) throw new Error('unsafe private authenticator history');
  const credentialFile = credentialFiles.sort((a,b)=>fs.statSync(b).mtimeMs-fs.statSync(a).mtimeMs)[0];
  result.registered_new_credential = false;
  if (!credentialFile && input.requireExistingPasskey) throw new Error('existing passkey required');
  if (credentialFile) {
    if (fs.lstatSync(credentialFile).isSymbolicLink() || (fs.statSync(credentialFile).mode & 0o777) !== 0o600) throw new Error('unsafe private authenticator file');
    const stored = JSON.parse(fs.readFileSync(credentialFile,'utf8'));
    result.authenticator_source_sha256 = crypto.createHash('sha256').update(fs.readFileSync(credentialFile)).digest('hex');
    result.credential_ids_sha256 = crypto.createHash('sha256').update(JSON.stringify(stored.credentials.map(c=>c.credentialId).sort())).digest('hex');
    for (const credential of stored.credentials) await cdp.send('WebAuthn.addCredential', {authenticatorId,credential});
  } else {
    result.registered_new_credential = true;
    stage = 'fresh initial administrator signup';
    await api('/api/signup/setup', 'POST', {username:'proof',firstName:'Synthetic',lastName:'Proof',email:'proof@example.invalid'});
    stage = 'fresh WebAuthn registration';
    const options = await api('/api/webauthn/register/start');
    const registration = await page.evaluate(async data => {
      const publicKey = PublicKeyCredential.parseCreationOptionsFromJSON(data.publicKey || data);
      const credential = await navigator.credentials.create({publicKey});
      return credential.toJSON();
    }, options);
    await api('/api/webauthn/register/finish', 'POST', registration);
    assert(true, 'Fresh administrator and real navigator.credentials.create WebAuthn registration through pinned TLS Gateway');
    savePrivate('pocket-virtual-authenticator-'+crypto.randomUUID()+'.json', await cdp.send('WebAuthn.getCredentials', {authenticatorId}));
  }
  // Clear all authentication cookies: subsequent identity MUST come from the
  // registered virtual passkey, not bootstrap/session cookies or one-time tokens.
  await context.clearCookies();
  stage = 'WebAuthn passkey authentication';
  const options = await api('/api/webauthn/login/start');
  const authentication = await page.evaluate(async data => {
    const publicKey = PublicKeyCredential.parseRequestOptionsFromJSON(data.publicKey || data);
    const credential = await navigator.credentials.get({publicKey});
    return credential.toJSON();
  }, options);
  await api('/api/webauthn/login/finish', 'POST', authentication);
  const user = await api('/api/users/me');
  assert(user.username === 'proof' && user.isAdmin === true, 'Fresh-cookie passkey authentication resolves persistent proof administrator');
  savePrivate('pocket-virtual-authenticator-'+crypto.randomUUID()+'.json', await cdp.send('WebAuthn.getCredentials', {authenticatorId}));
  result.user_id = user.id;
  stage = 'isolated public PKCE OIDC client creation';
  const callback = issuer + '/proof-callback';
  const client = await api('/api/oidc/clients', 'POST', {name:'Proof ' + crypto.randomUUID().slice(0,8),callbackURLs:[callback],logoutCallbackURLs:[],isPublic:true,pkceEnabled:true,requiresReauthentication:false,requiresPushedAuthorizationRequests:false,skipConsent:false,isGroupRestricted:false});
  await page.route('**/proof-callback?**', route => route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><title>Isolated proof callback</title>'}));
  async function authorizeCode() {
    validateLease();
    const verifier = crypto.randomBytes(32).toString('base64url');
    const nonce = crypto.randomBytes(24).toString('base64url');
    const state = crypto.randomBytes(24).toString('base64url');
    const params = new URLSearchParams({client_id:client.id,response_type:'code',redirect_uri:callback,scope:'openid profile email',code_challenge:crypto.createHash('sha256').update(verifier).digest('base64url'),code_challenge_method:'S256',nonce,state});
    const callbackPromise = page.waitForRequest(req => new URL(req.url()).pathname === '/proof-callback', {timeout:45000}).then(req => new URL(req.url()));
    await page.goto(issuer + '/authorize?' + params, {waitUntil:'domcontentloaded'});
    const callbackURL = await Promise.race([callbackPromise, (async () => {
      await page.getByRole('button', {name:/^sign in$/i}).click({timeout:30000});
      return callbackPromise;
    })()]);
    assert(callbackURL.searchParams.get('state') === state && callbackURL.searchParams.has('code'), 'OIDC fresh browser authorization-code callback has matching random state');
    await page.waitForURL(url => url.pathname === '/proof-callback', {waitUntil:'domcontentloaded',timeout:15000});
    return {verifier,nonce,params,code:callbackURL.searchParams.get('code')};
  }
  async function exchangeCode(data) {
    validateLease();
    return page.evaluate(async data => {
      const response = await fetch('/api/oidc/token', {method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(data)});
      return {ok:response.ok,status:response.status,body:await response.json()};
    },data);
  }
  stage = 'OIDC authorization/consent';
  const authorized = await authorizeCode();
  const {nonce} = authorized;
  const grant = {grant_type:'authorization_code',client_id:client.id,redirect_uri:callback,code_verifier:authorized.verifier,code:authorized.code};
  stage = 'OIDC code exchange and signed ID token validation';
  const exchange = await exchangeCode(grant);
  result.token_exchange_status = exchange.status;
  if (!exchange.ok) {
    result.token_exchange_error = ['invalid_client','invalid_grant','invalid_request','unsupported_grant_type','unauthorized_client'].includes(exchange.body.error) ? exchange.body.error : 'withheld';
    throw new Error('token exchange rejected');
  }
  const token = exchange.body;
  const jwt = token.id_token.split('.');
  const header = JSON.parse(Buffer.from(jwt[0],'base64url'));
  const claims = JSON.parse(Buffer.from(jwt[1],'base64url'));
  const discovery = await api('/.well-known/openid-configuration');
  const jwks = await api(new URL(discovery.jwks_uri).pathname);
  const jwk = jwks.keys.find(key => key.kid === header.kid);
  const key = crypto.createPublicKey({key:jwk,format:'jwk'});
  const algorithm = {RS256:'RSA-SHA256',ES256:'sha256',EdDSA:null}[header.alg];
  assert(['RS256','ES256','EdDSA'].includes(header.alg), 'OIDC token uses an explicitly supported signing algorithm');
  assert(crypto.verify(algorithm,Buffer.from(jwt[0]+'.'+jwt[1]),header.alg==='ES256'?{key,dsaEncoding:'ieee-p1363'}:key,Buffer.from(jwt[2],'base64url')), 'OIDC ID token signature validates against issuer public JWKS');
  assert(claims.iss===issuer && audienceMatches(claims.aud,client.id) && claims.nonce===nonce && claims.sub===user.id && claims.exp > Date.now()/1000, 'OIDC ID token issuer/audience/nonce/subject/expiry validated');
  const info = await page.evaluate(async accessToken => {
    const response = await fetch('/api/oidc/userinfo',{headers:{Authorization:'Bearer '+accessToken}});
    if(!response.ok) throw new Error('userinfo failed');
    return response.json();
  }, token.access_token);
  assert(info.sub===user.id && info.preferred_username==='proof', 'OIDC access token returns matching userinfo identity');
  // Replay only after successful signature/userinfo checks: providers may revoke
  // tokens minted from a replayed code. Never let this disturb the positive proof.
  result.protocol_negatives = {};
  const safeGrant = value => ({status:value.status,error:['invalid_grant','invalid_request','invalid_client'].includes(value.body?.error) ? value.body.error : 'withheld',tokens_returned:['access_token','id_token','refresh_token'].some(key => Object.hasOwn(value.body || {},key))});
  stage = 'negative reused authorization code';
  const replay = await exchangeCode(grant);
  result.protocol_negatives.replay = safeGrant(replay);
  assert(isInvalidGrant(replay), 'OIDC actual previously redeemed code replay denied400 invalid_grant with no tokens');
  stage = 'negative wrong PKCE verifier for fresh real code';
  const wrongPKCE = await authorizeCode();
  const invalidVerifier = crypto.randomBytes(32).toString('base64url');
  assert(invalidVerifier !== wrongPKCE.verifier && /^[A-Za-z0-9_-]{43}$/.test(invalidVerifier),'Wrong PKCE verifier differs but has valid43-character syntax');
  const wrong = await exchangeCode({...grant,code:wrongPKCE.code,code_verifier:invalidVerifier});
  result.protocol_negatives.wrong_pkce = safeGrant(wrong);
  assert(isInvalidGrant(wrong), 'OIDC fresh real authorization code with wrong S256 PKCE verifier denied400 invalid_grant with no tokens');
  stage = 'negative unregistered redirect URI';
  let forbiddenCallbacks = 0;
  await page.route('**/proof-forbidden-callback**', route => { forbiddenCallbacks++; return route.abort('blockedbyclient'); });
  const invalidRedirect = new URLSearchParams(wrongPKCE.params);
  invalidRedirect.set('redirect_uri',issuer+'/proof-forbidden-callback');
  validateLease();
  const redirectDenial = await page.evaluate(async query => {
    const response = await fetch('/authorize?'+query,{redirect:'follow'});
    const url = new URL(response.url);
    return {status:response.status,origin:url.origin,path:url.pathname,hasError:url.searchParams.has('error'),hasCode:url.searchParams.has('code'),errorMentionsRedirect:/redirect|callback/i.test(url.searchParams.get('error') || '')};
  },invalidRedirect.toString());
  result.protocol_negatives.wrong_redirect = {status:redirectDenial.status,path:redirectDenial.path,callback_requests:forbiddenCallbacks};
  assert(isWrongRedirectDenial({...redirectDenial,callbackRequests:forbiddenCallbacks}), 'OIDC actual unregistered redirect refused on issuer error route without code or callback request');
  stage = 'negative unknown OIDC client';
  const denied = await page.evaluate(async () => {
    const response = await fetch('/api/oidc/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'client_credentials',client_id:'nonexistent-proof-client',client_secret:'synthetic-invalid'})});
    const body=await response.json();
    return {status:response.status,error:body.error};
  });
  assert([400,401].includes(denied.status) && denied.error==='invalid_client','OIDC token endpoint rejects unknown client credentials');
  await api('/api/oidc/clients/' + encodeURIComponent(client.id),'DELETE');
  result.status = 'passed';
} catch(error) {
  // Never emit exception messages, browser traces, token URLs or key material.
  result.failure_stage = stage;
  result.failure_type = error.constructor.name;
  if(error.message?.includes('Execution context was destroyed')) result.safe_failure_code='navigation_context_destroyed';
  if(error.message?.includes('Failed to fetch')) result.safe_failure_code='browser_fetch_failed';
} finally {
  if(browser) await browser.close();
  if(leaseValidated) savePrivate('pocket-browser-'+crypto.randomUUID()+'.json',result);
  console.log(JSON.stringify(result,null,2));
}
if(result.status !== 'passed') process.exitCode = 1;
