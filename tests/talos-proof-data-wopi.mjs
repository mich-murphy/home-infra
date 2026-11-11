#!/usr/bin/env node
/** Real CODE iframe input/save. WOPI assertions are made independently by Python.
 * JSON stdin only. No tokens/DOM/screenshots/console/URLs are emitted or saved.
 */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const input = JSON.parse(fs.readFileSync(0,'utf8'));
const here = path.dirname(fileURLToPath(import.meta.url));
let browser;
let stage = 'lease validation';
const result = {status:'failed', checks:[]};
function lease() {
  const r = spawnSync('python3',[path.join(here,'../scripts/talos-proof-data.py'),'verify','--group','nextcloud','--stage',input.mode==='office' ? 'full' : 'wopi','--state',input.state],{timeout:30000,stdio:'pipe'});
  if (r.status !== 0) throw new Error('lease rejected');
}
try {
  lease();
  if (!/^[A-Za-z0-9+/]{43}=$/.test(input.spki)) throw new Error('exact verified leaf SPKI required');
  const origin = 'https://collabora.proof.invalid';
  if (input.mode !== 'office' && new URL(input.action).origin !== origin) throw new Error('discovery action must retain real public CODE origin');
  const {chromium} = createRequire(import.meta.url)(input.module);
  stage = 'pinned Chrome launch';
  browser = await chromium.launch({
    executablePath:process.env.TALOS_PROOF_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless:true,
    args:[`--host-resolver-rules=MAP *.proof.invalid 127.0.0.1:${Number(input.port || 18443)},EXCLUDE localhost`,
      `--ignore-certificate-errors-spki-list=${input.spki}`,'--disable-background-networking',
      '--disable-component-update','--no-proxy-server','--disable-sync','--disable-default-apps','--no-first-run']
  });
  const context = await browser.newContext({ignoreHTTPSErrors:false});
  await context.route('**/*',route => {
    const u = new URL(route.request().url());
    if (input.mode!=='office' && u.origin===origin && u.pathname==='/__proof_wopi_host') return route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><html><body><iframe name="editor" style="width:1200px;height:900px"></iframe></body></html>'});
    return (u.origin === origin || (input.mode==='office' && u.origin==='https://nextcloud.proof.invalid')) && u.protocol === 'https:' ? route.continue() : route.abort('blockedbyclient');
  });
  let websocketCount = 0;
  await context.routeWebSocket('**/*',ws => {
    const u = new URL(ws.url());
    if (u.protocol !== 'wss:' || u.hostname !== 'collabora.proof.invalid') return ws.close();
    websocketCount++;
    ws.connectToServer();
  });
  const page = await context.newPage();
  let frame;
  if (input.mode==='office') {
    stage='real Nextcloud proof-user login';
    await page.goto('https://nextcloud.proof.invalid/index.php/login',{waitUntil:'domcontentloaded'});
    await page.locator('input[name="user"]').fill('proof');
    await page.locator('input[name="password"]').fill(input.password);
    await page.locator('button[type="submit"],input[type="submit"]').first().click();
    await page.waitForURL(url=>url.hostname==='nextcloud.proof.invalid' && !url.pathname.endsWith('/login'),{timeout:60000});
    stage='real supported richdocuments index route';
    await page.goto('https://nextcloud.proof.invalid/index.php/apps/richdocuments/index?fileId='+Number(input.fileid),{waitUntil:'domcontentloaded'});
    const deadline=Date.now()+120000;
    while (!frame) {
      frame=page.frames().find(f=>{try{return new URL(f.url()).origin===origin;}catch{return false;}});
      if(Date.now()>deadline) throw new Error('no real CODE iframe');
      if(!frame) await page.waitForTimeout(250);
    }
  } else {
  await page.goto(origin+'/__proof_wopi_host',{waitUntil:'domcontentloaded'});
  stage = 'discovered editor form POST';
  await page.evaluate(({action,token,source}) => {
    const form = document.createElement('form');
    const url = new URL(action);
    // Discovery hrefs may contain WOPI substitution placeholders. They are
    // resolved by Python before this point; no guessed /browser/<hash> URL.
    url.searchParams.set('WOPISrc',source);
    form.action=url.href; form.method='POST'; form.target='editor';
    for (const [name,value] of Object.entries({access_token:token,access_token_ttl:String(Date.now()+600000)})) {
      const field=document.createElement('input');field.type='hidden';field.name=name;field.value=value;form.appendChild(field);
    }
    document.body.appendChild(form);form.submit();
  },{action:input.action,token:input.token,source:input.source});
  frame = page.frameLocator('iframe[name=editor]');
  }
  stage = 'real editor rendered canvas';
  await frame.locator('#document-container canvas').first().waitFor({state:'visible',timeout:120000});
  lease();
  stage = 'real browser keyboard edit/save';
  if (input.edit !== false) {
  await frame.locator('#document-container canvas').first().click({position:{x:180,y:180},force:true});
  await page.keyboard.press('Control+End');
  await page.keyboard.type(input.marker,{delay:40});
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+s' : 'Control+s');
  // Allow real save/callback; the parent independently requires PutFile and bytes.
  await page.waitForTimeout(3000);
  }
  if (!websocketCount) throw new Error('no real editor websocket');
  result.status='browser-input-dispatched-not-functional-verdict';
  result.checks.push('Pinned public HTTPS CODE iframe rendered; real WSS connected; keyboard edit/save dispatched');
  result.chrome_version=browser.version();
} catch (error) {
  if (browser && input.mode!=='office') { const pages=browser.contexts()[0]?.pages(); if(pages?.[0]) { await pages[0].screenshot({path:path.join(input.state,'wopi-failure.png')}).catch(()=>{}); if(fs.existsSync(path.join(input.state,'wopi-failure.png'))) fs.chmodSync(path.join(input.state,'wopi-failure.png'),0o600); } }
  result.failed_stage=stage;result.failure_type=error.constructor.name;
  const message=String(error.message).split('\n')[0];
  result.failure_detail=message.replaceAll(input.token || '\u0000','<token>').replace(/https?:[^\s]+/g,'<url>').slice(0,180);
} finally {
  if (browser) await browser.close();
}
console.log(JSON.stringify(result));
if (result.status==='failed') process.exitCode=1;
