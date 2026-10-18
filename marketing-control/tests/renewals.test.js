import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseRenewal,renewalDates,approveRenewal} from '../src/renewals.js';
test('one platform and one email only',()=>{
 assert.deepEqual(parseRenewal('/renovar Netflix A@example.com'),{code:'netflix',email:'a@example.com'});
 for(const s of ['/renovar','/renovar netflix a@b.com c@d.com','/renovar netflix wrong'])assert.throws(()=>parseRenewal(s));
});
test('active renews from expiry; expired from approval',()=>{
 const now=new Date('2026-10-14T12:00:00Z');
 assert.equal(renewalDates('2026-10-20T12:00:00Z',30,now).end.toISOString(),'2026-11-19T12:00:00.000Z');
 assert.equal(renewalDates('2026-10-01T12:00:00Z',30,now).end.toISOString(),'2026-11-13T12:00:00.000Z');
});
test('payment alone cannot approve renewal',async()=>{
 await assert.rejects(approveRenewal({query:()=>{throw Error('must not write');}},{},'REF','admin',false),/Confirma/);
});
