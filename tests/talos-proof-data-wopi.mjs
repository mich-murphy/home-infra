#!/usr/bin/env node
/** Real CODE iframe input/save. WOPI assertions are made independently by Python.
 * JSON stdin only. No tokens/DOM/screenshots/console/URLs are emitted or saved.
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
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
  const context = await browser.newContext({ignoreHTTPSErrors:false,serviceWorkers:'block'});
  await context.route('**/*',route => {
    const u = new URL(route.request().url());
    if (input.mode!=='office' && u.origin===origin && u.pathname==='/__proof_wopi_host') return route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><html><body><iframe name="editor" style="width:1200px;height:900px"></iframe></body></html>'});
    return (u.origin === origin || (input.mode==='office' && u.origin==='https://nextcloud.proof.invalid')) && u.protocol === 'https:' ? route.continue() : route.abort('blockedbyclient');
  });
  let websocketCount = 0;
  await context.routeWebSocket('**/*',ws => {
    const u = new URL(ws.url());
    if (u.origin !== 'wss://collabora.proof.invalid') return ws.close();
    websocketCount++;
    ws.connectToServer();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
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
  if(input.expectHostDenial) {
    stage='explicit wrong-host denial';
    const denial=frame.getByText(/unauthori[sz]ed WOPI host|WOPI host.*not allowed|not.*allowed.*WOPI host/i).first();
    await denial.waitFor({state:'visible',timeout:45000});
    result.status='explicit-wrong-host-denial';
    result.checks.push('CODE explicitly reports non-allowlisted WOPI host denial');
  } else {
  stage = 'actual document loaded/editable';
  await frame.locator('#document-container canvas').first().waitFor({state:'visible',timeout:90000});
  // Record only bounded structural state, never tokens, URLs or document text.
  async function state() {
    return frame.locator('body').evaluate(() => {
      const map=window.app?.map;
      return {docLoaded:map?._docLoaded, permission:map?._permission ?? window.app?.file?.permission,
        hasDocLayer:!!map?._docLayer,
        inputs:[...document.querySelectorAll('[contenteditable=true],textarea')].map(e=>({id:e.id,tag:e.tagName,cls:e.className})).slice(0,12),
        dialogs:[...document.querySelectorAll('[role=dialog]')].map(e=>({id:e.id,visible:!!e.getClientRects().length})),
        saveControls:[...document.querySelectorAll('button,[role=button]')].filter(e=>/save/i.test(e.getAttribute('aria-label')||e.title||e.id)).map(e=>({id:e.id,label:e.getAttribute('aria-label'),title:e.title})).slice(0,12)};
    });
  }
  result.editor_state=await state();
  // Native ODT attempt screenshot showed this exact session-warning dialog
  // above the welcome tour. Close only the observed notice, never arbitrary UI.
  const sessionNotice=frame.getByText('Your session will end in 10 minutes. Refresh the page to continue.',{exact:true});
  if(await sessionNotice.isVisible()) {
    stage='observed native session-warning Close';
    const dialog=frame.getByRole('dialog').filter({has:sessionNotice});
    await dialog.getByRole('button',{name:'Close',exact:true}).click();
    result.checks.push('Exact observed ten-minute session warning closed');
  }
  // The previous cropped screenshot showed the version-tour overlay and the
  // real Viewing selector. Dismiss only the known tour, then choose Editing UI.
  for(const candidate of page.frames()) {
    const tour=candidate.getByText(/Explore The New/i).first();
    if(!/welcome/i.test(candidate.url()) && !await tour.isVisible().catch(()=>false)) continue;
    result.welcome_frame_seen=true;
    const controls=candidate.locator('[id*="close" i], [class*="close" i], [aria-label*="close" i], [title*="close" i]');
    result.welcome_controls=await controls.evaluateAll(elements=>elements.slice(0,12).map(e=>({id:e.id,cls:e.className,tag:e.tagName})));
    let dismissed=false;
    for(let index=0;index<await controls.count();index++) {
      const close=controls.nth(index);
      if(await close.isVisible()) {await close.click();dismissed=true;break;}
    }
    if(!dismissed && await tour.isVisible()) {
      // Version-tour body is a dedicated known iframe. Previous editor-only
      // capture showed its X at top-right. Never apply this to the document body.
      if(/welcome/i.test(candidate.url())) {
        const box=await candidate.locator('body').boundingBox();
        if(box) await candidate.locator('body').click({position:{x:box.width-28,y:32}});
      }
    }
  }
  // Some CODE builds render the tour inside an iframe-dialog wrapper whose
  // close control is in the editor document rather than the nested tour frame.
  const tourWrap=frame.locator('[id*="welcome" i], [class*="welcome" i], .iframe-dialog-wrap').first();
  if(await tourWrap.isVisible().catch(()=>false)) {
    const close=frame.locator('.iframe-dialog-close, [id*="welcome" i] [class*="close" i], [class*="welcome" i] [class*="close" i]').first();
    if(await close.isVisible()) await close.click();
  }
  const viewing=frame.getByText('Viewing',{exact:true}).first();
  if(await viewing.isVisible()) {
    stage='observed real Editing Mode menu item';
    await viewing.click();
    const editing=frame.getByText('Editing Mode',{exact:true}).first();
    await editing.click();
    result.checks.push('Explicit real Viewing → Editing mode selection');
  }
  // Observed only in the seventh plain-text attempt: selecting Editing Mode
  // opens this exact format-loss confirmation. Do not dismiss arbitrary dialogs.
  if(input.mode!=='office' && (input.format || 'txt')==='txt') {
    const notice=frame.getByText('This document may contain formatting or content that cannot be saved in the current file format.',{exact:true});
    if(await notice.waitFor({state:'visible',timeout:5000}).then(()=>true).catch(()=>false)) {
      stage='observed plain-text format-warning Continue editing';
      await frame.getByRole('button',{name:'Continue editing',exact:true}).click();
      result.checks.push('Explicit observed plain-text format warning acknowledged');
    }
  }
  const deadline=Date.now()+45000;
  while(true) {
    const current=await state();result.editor_state=current;
    if(current.hasDocLayer && current.docLoaded===true && current.permission==='edit') break;
    if(Date.now()>deadline) throw new Error('actual document not loaded/editable');
    await page.waitForTimeout(250);
  }
  lease();
  if (input.edit !== false) {
    stage='real editor input focus';
    const inputBox=frame.locator('#clipboard-area, #copy-paste-container[contenteditable=true], .clipboard[contenteditable=true], textarea.clipboard').first();
    await inputBox.focus();
    const focused=await inputBox.evaluate(e=>document.activeElement===e);
    if(!focused) throw new Error('editor clipboard input did not acquire focus');
    result.checks.push('Actual loaded editable document and focused editor clipboard input');
    await page.keyboard.press('Control+End');
    await page.keyboard.type(input.marker,{delay:35});
    stage='actual editor Save control';
    const save=frame.getByRole('button',{name:/^Save(?:\s*\(|$)/i}).first();
    await save.click();
    result.checks.push('Actual editor Save button clicked; independent PutFile assertion required');
    await page.waitForTimeout(3000);
  }
  if (!websocketCount) throw new Error('no real editor websocket');
  result.status='browser-input-dispatched-not-functional-verdict';
  result.checks.push('Pinned public HTTPS CODE iframe rendered; real WSS connected; keyboard edit/save dispatched');
  }
  result.chrome_version=browser.version();
} catch (error) {
  if (browser && input.mode!=='office') {
    const page=browser.contexts()[0]?.pages()[0];
    if(page) {const target=path.join(input.state,(input.outputPrefix || 'wopi')+'-failure-'+crypto.randomUUID()+'.png');await page.locator('iframe').first().screenshot({path:target,timeout:3000}).catch(()=>{});if(fs.existsSync(target)) {fs.chmodSync(target,0o600);result.private_failure_artifact_sha256=crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex');}}
  }
  result.failed_stage=stage;result.failure_type=error.constructor.name;
  const message=String(error.message).split('\n')[0];
  result.failure_detail=message.replaceAll(input.token || '\u0000','<token>').replaceAll(input.password || '\u0000','<password>').replace(/https?:[^\s]+/g,'<url>').slice(0,180);
} finally {
  if (browser) await browser.close();
}
console.log(JSON.stringify(result));
if (result.status==='failed') process.exitCode=1;
