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
