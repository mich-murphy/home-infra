/** SID equality gate. Values never appear in errors or results. */
export function authenticatedSID(cookies, origin) {
  const host=new URL(origin).hostname;
  const matches=cookies.filter(c=>c.name==='SID' && c.domain.replace(/^\./,'')===host && c.path==='/' && c.secure && c.value.length>0);
  if(matches.length!==1) throw new Error('authenticated SID missing or ambiguous');
  return matches[0].value;
}
export function sameSID(header, expected) {
  if(typeof expected!=='string' || !expected.length) return false;
  const matches=(header || '').split(';').map(x=>x.trim()).filter(x=>x.startsWith('SID='));
  return matches.length===1 && matches[0].slice(4).length>0 && matches[0].slice(4)===expected;
}
