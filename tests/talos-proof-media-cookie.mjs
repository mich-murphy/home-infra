/** SID equality gate. Values never appear in errors or results. */
export function authenticatedSID(cookies, origin, name='SID') {
  const host=new URL(origin).hostname;
  const matches=cookies.filter(c=>c.name===name && c.domain.replace(/^\./,'')===host && c.path==='/' && c.value.length>0);
  if(matches.length!==1) throw new Error('authenticated SID missing or ambiguous');
  return matches[0].value;
}
export function sameSID(header, expected, name='SID') {
  if(typeof expected!=='string' || !expected.length) return false;
  const matches=(header || '').split(';').map(x=>x.trim()).filter(x=>x.startsWith(name+'='));
  return matches.length===1 && matches[0].slice(name.length+1).length>0 && matches[0].slice(name.length+1)===expected;
}
