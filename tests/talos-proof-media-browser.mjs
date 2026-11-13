#!/usr/bin/env node
/** Real native qBit5.3 browser authentication/CSRF, not a manual Origin probe.
 * Private JSON stdin. No traces, HAR, storage state, DOM or credentials saved.
 */
import fs from 'node:fs';
import {randomUUID} from 'node:crypto';
import path from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const here=path.dirname(fileURLToPath(import.meta.url));
const result={status:'FAIL',checks:[]};
let browser,stage='lease';
const mediaDiagnostics=[];
function lease() {
  const source='import sys,importlib;sys.path.insert(0,sys.argv[1]);b=importlib.import_module("talos-proof-media-browser");b.check_lease(sys.argv[2],sys.argv[3])';
  const check=spawnSync('python3',['-c',source,path.join(here,'../scripts'),input.service,input.group || input.service],{timeout:30000,stdio:'pipe'});
  if(check.status!==0) throw new Error('lease');
}
function requireCheck(ok,name) {if(!ok) throw new Error(name);result.checks.push(name);}
try {
  lease();
  if(!['qbittorrent','plex','jellyfin'].includes(input.service) || !/^[A-Za-z0-9+/]{43}=$/.test(input.spki)) throw new Error('input');
  const origin=`https://${input.service}.proof.invalid`;
  const hostile='https://hostile.proof.invalid';
  const {chromium}=createRequire(import.meta.url)(input.module);
  stage='Chrome launch';
  browser=await chromium.launch({
    executablePath:process.env.TALOS_PROOF_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless:true,args:[
      '--host-resolver-rules=MAP *.proof.invalid 127.0.0.1:18443,EXCLUDE localhost',
      `--ignore-certificate-errors-spki-list=${input.spki}`,'--disable-background-networking',
      '--disable-component-update','--no-proxy-server','--disable-sync','--disable-default-apps','--no-first-run']});
  const context=await browser.newContext({ignoreHTTPSErrors:false,serviceWorkers:'block'});
  // Both guards are installed BEFORE creating pages/navigation. Hostile document
  // is locally fulfilled, never a network destination. No origin/header rewrite.
  await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(input.service!=='qbittorrent' && url.href===origin+'/__proof_decoder') return route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><title>Local proof decoder (not native UI)</title>'});
    if(input.service==='qbittorrent' && url.href===hostile+'/__proof_attack') return route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><title>Local hostile-origin CSRF fixture</title>'});
    if(url.protocol!=='https:' || url.origin!==origin) return route.abort('blockedbyclient');
    if(input.service!=='qbittorrent') {
      if(url.pathname+url.search!==input.mediaPath) return route.abort('blockedbyclient');
      return route.continue({headers:{...route.request().headers(),...input.headers}});
    }
    return route.continue();
  });
  await context.routeWebSocket('**/*',ws=>ws.close()); // qBit WebUI needs no WSS
  async function wireHeaders(page) {
    const cdp=await context.newCDPSession(page), requests=new Map(), extra=new Map();
    cdp.on('Network.requestWillBeSent',e=>requests.set(e.requestId,{url:e.request.url,method:e.request.method}));
    cdp.on('Network.requestWillBeSentExtraInfo',e=>extra.set(e.requestId,e.headers));
    await cdp.send('Network.enable');
    return async response=>{
      for(let i=0;i<30;i++) {
        for(const [id,request] of requests) if(request.url===response.url() && request.method===response.request().method() && extra.has(id))
          return Object.fromEntries(Object.entries(extra.get(id)).map(([k,v])=>[k.toLowerCase(),v]));
        await new Promise(resolve=>setTimeout(resolve,100));
      }
      throw new Error('actual wire headers unavailable');
    };
  }
  const page=await context.newPage();page.setDefaultTimeout(15000);
  if(input.service!=='qbittorrent') {
    page.on('response',r=>{if(mediaDiagnostics.length<40) mediaDiagnostics.push({status:r.status(),path:new URL(r.url()).pathname});});
    page.on('requestfailed',r=>{if(mediaDiagnostics.length<40) mediaDiagnostics.push({failed:r.failure()?.errorText,path:new URL(r.url()).pathname});});
  }
  const actualHeaders=await wireHeaders(page);
  if(input.service!=='qbittorrent') {
    stage='actual server MP4 browser decode';
    await page.goto(origin+'/__proof_decoder');
    const {decode}=await import('./talos-proof-media-player.mjs');
    if(input.bridge) await page.exposeFunction('proofTimeline',async event=>{
      lease();
      const child=spawnSync('python3',[path.join(here,'../scripts/talos-proof-media-playback.py')],
        {input:JSON.stringify({bridge:input.bridge,event}),timeout:60000,encoding:'utf8'});
      if(child.status!==0) throw new Error('timeline callback failed');
      return JSON.parse(child.stdout);
    });
    result.decoder=await decode(page,input.mediaPath,Boolean(input.bridge),input.bridge?.resume_seconds || 0);
    result.checks.push('real server H264 video frames decoded/presented; clock advanced; target seek frame decoded');
    result.scope='custom muted Chrome decoder only; app resume/ACL/recovery and native UI require separate gates';
  } else {
  stage='native WebUI login';
  await page.goto(origin+'/',{waitUntil:'domcontentloaded'});
  await page.locator('#username').fill(input.username);
  await page.locator('#password').fill(input.password);
  const login=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v2/auth/login' && r.request().method()==='POST');
  await page.locator('#loginButton').click();
  const response=await login;
  const sent=await actualHeaders(response);
  result.login_transport={sec_fetch_site:sent['sec-fetch-site'] || 'absent',origin_expected:sent.origin===origin};
  requireCheck(response.status()===204,'native form login HTTP204');
  requireCheck(sent['sec-fetch-site']==='same-origin','native login Sec-Fetch-Site same-origin');
  requireCheck(!sent.origin || sent.origin===origin,'native Origin retained without transport port');
  await page.waitForFunction(()=>!document.querySelector('#loginButton'));
  await page.waitForLoadState('networkidle');
  async function preferences() {
    return page.evaluate(async()=>{const r=await fetch('/api/v2/app/preferences');return {status:r.status,body:await r.json()};});
  }
  stage='browser authenticated preferences';
  const before=await preferences();
  requireCheck(before.status===200,'browser session preferences HTTP200');
  const {authenticatedSID,sameSID}=await import('./talos-proof-media-cookie.mjs');
  const cookies=await context.cookies();
  const cookieName='QBT_SID_8080'; // observed exact5.3 native session cookie, not legacy SID
  result.sid_cookie_metadata=cookies.filter(c=>c.name===cookieName).map(c=>({exact_host:c.domain.replace(/^\./,'')===new URL(origin).hostname,path_root:c.path==='/',secure:c.secure,nonempty:c.value.length>0}));
  const validSID=authenticatedSID(cookies,origin,cookieName);
  result.secure_cookie_proved=cookies.find(c=>c.name===cookieName)?.secure===true;
  result.production_ready_auth=false;
  if(input.requireSecureCookie) requireCheck(cookies.find(c=>c.name===cookieName)?.secure===true,'native authenticated session cookie has actual Secure attribute');
  lease();
  stage='hostile origin CSRF';
  const attacker=await context.newPage();
  const attackHeaders=await wireHeaders(attacker);
  await attacker.goto(hostile+'/__proof_attack');
  const denied=attacker.waitForResponse(r=>new URL(r.url()).pathname==='/api/v2/app/setPreferences' && r.request().method()==='POST');
  await attacker.evaluate(({target,value})=>{
    const form=document.createElement('form');form.method='POST';form.action=target;
    const field=document.createElement('input');field.type='hidden';field.name='json';
    field.value=JSON.stringify({max_active_downloads:value});form.appendChild(field);document.body.appendChild(form);form.submit();
  },{target:origin+'/api/v2/app/setPreferences',value:Number(before.body.max_active_downloads)===7?8:7});
  const rejection=await denied;
  const hostileHeaders=await attackHeaders(rejection);
  requireCheck(hostileHeaders.origin===hostile,'real browser hostile Origin retained');
  // Without the authenticated cookie a401 proves only auth, not CSRF. Fail closed.
  requireCheck(sameSID(hostileHeaders.cookie,validSID,cookieName),'hostile request carried real authenticated SID');
  requireCheck(rejection.status()===401 || rejection.status()===403,'hostile authenticated mutation denied');
  const after=await preferences();
  requireCheck(after.status===200 && after.body.max_active_downloads===before.body.max_active_downloads,'preference unchanged after hostile mutation');
  }
  result.chrome_version=browser.version();result.status='PASS';
} catch(error) {
  result.failed_stage=stage;result.failure_type=error.constructor.name;
  fs.writeFileSync(path.join(input.state,`browser-private-failure-${randomUUID()}.log`),String(error.stack || error)+'\n'+JSON.stringify(mediaDiagnostics),{mode:0o600,flag:'wx'});
  // Deliberately do not emit error.message: Playwright errors can embed secrets.
} finally {if(browser) await browser.close();}
console.log(JSON.stringify(result));
if(result.status!=='PASS') process.exitCode=1;
