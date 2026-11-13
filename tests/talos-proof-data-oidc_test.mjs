import assert from 'node:assert/strict';
import {audienceMatches} from './talos-proof-data-oidc.mjs';
const cases = [
 ['proof-client','proof-client',true],
 ['prefix-proof-client','proof-client',false],
 ['proof-client-suffix','proof-client',false],
 [['other','proof-client'],'proof-client',true],
 [['prefix-proof-client'],'proof-client',false],
 [['proof-client',123],'proof-client',false],
 [null,'proof-client',false],
 [undefined,'proof-client',false],
 [123,'proof-client',false],
 [{includes:()=>true},'proof-client',false],
 ['proof-client ','proof-client',false],
 ['','',false],
 [[], 'proof-client',false],
];
for (const [aud,client,expected] of cases) assert.equal(audienceMatches(aud,client),expected);
console.log(`${cases.length} strict OIDC audience cases passed; this is offline validation, not a new live OIDC run.`);

const {isInvalidGrant,isWrongRedirectDenial} = await import('./talos-proof-data-oidc.mjs');
const rejectedGrant = {status:400,body:{error:'invalid_grant'}};
assert.equal(isInvalidGrant(rejectedGrant),true);
for (const response of [null,{}, {status:500,body:{error:'invalid_grant'}}, {status:401,body:{error:'invalid_grant'}}, {status:400,body:{error:'invalid_client'}}, {status:200,body:{}}, ...['access_token','id_token','refresh_token'].map(key => ({status:400,body:{error:'invalid_grant',[key]:''}}))]) assert.equal(isInvalidGrant(response),false);
const deniedRedirect = {status:200,origin:'https://pocket-id.proof.invalid',path:'/interaction/error',hasError:true,errorMentionsRedirect:true,hasCode:false,callbackRequests:0};
assert.equal(isWrongRedirectDenial(deniedRedirect),true);
for (const patch of [{status:500},{origin:'https://other.invalid'},{path:'/proof-forbidden-callback'},{hasError:false},{errorMentionsRedirect:false},{hasCode:true},{callbackRequests:1}]) assert.equal(isWrongRedirectDenial({...deniedRedirect,...patch}),false);
console.log('18 strict negative-response cases passed; fake responses are not live protocol evidence.');
