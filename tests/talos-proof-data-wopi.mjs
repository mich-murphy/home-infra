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
  const r = spawnSync('python3',[path.join(here,'../scripts/talos-proof-data.py'),'verify','--group','nextcloud','--stage','wopi','--state',input.state],{timeout:30000,stdio:'pipe'});
  if (r.status !== 0) throw new Error('lease rejected');
}
try {
  lease();
  if (!/^[A-Za-z0-9+/]{43}=$/.test(input.spki)) throw new Error('exact verified leaf SPKI required');
  const origin = 'https://collabora.proof.invalid';
  if (new URL(input.action).origin !== origin) throw new Error('discovery action must retain real public CODE origin');
  const {chromium} = createRequire(import.meta.url)(input.module);
  stage = 'pinned Chrome launch';
  browser = await chromium.launch({
    executablePath:process.env.TALOS_PROOF_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless:true,
    args:[`--host-resolver-rules=MAP collabora.proof.invalid 127.0.0.1:${Number(input.port || 18443)},EXCLUDE localhost`,
      `--ignore-certificate-errors-spki-list=${input.spki}`,'--disable-background-networking',
      '--disable-component-update','--no-proxy-server','--disable-sync','--disable-default-apps','--no-first-run']
  });
  const context = await browser.newContext({ignoreHTTPSErrors:false});
  await context.route('**/*',route => {
    const u = new URL(route.request().url());
    return u.origin === origin && u.protocol === 'https:' ? route.continue() : route.abort('blockedbyclient');
  });
  let websocketCount = 0;
  await context.routeWebSocket('**/*',ws => {
    const u = new URL(ws.url());
    if (u.protocol !== 'wss:' || u.hostname !== 'collabora.proof.invalid') return ws.close();
    websocketCount++;
    ws.connectToServer();
  });
  const page = await context.newPage();
  await page.goto(origin+'/hosting/discovery',{waitUntil:'domcontentloaded'});
  stage = 'discovered editor form POST';
  await page.setContent('<html><body><iframe name="editor" style="width:1200px;height:900px"></iframe></body></html>');
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
  const frame = page.frameLocator('iframe[name=editor]');
  stage = 'real editor rendered canvas';
  await frame.locator('#document-container canvas').first().waitFor({state:'visible',timeout:120000});
  lease();
  stage = 'real browser keyboard edit/save';
  await frame.locator('#document-container').click({position:{x:180,y:180}});
  await page.keyboard.press('Control+End');
  await page.keyboard.type(input.marker,{delay:40});
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+s' : 'Control+s');
  // Allow real save/callback; the parent independently requires PutFile and bytes.
  await page.waitForTimeout(3000);
  if (!websocketCount) throw new Error('no real editor websocket');
  result.status='browser-input-dispatched-not-functional-verdict';
  result.checks.push('Pinned public HTTPS CODE iframe rendered; real WSS connected; keyboard edit/save dispatched');
  result.chrome_version=browser.version();
} catch (error) {
  result.failed_stage=stage;result.failure_type=error.constructor.name;
} finally {
  if (browser) await browser.close();
}
console.log(JSON.stringify(result));
if (result.status==='failed') process.exitCode=1;
