import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseRenewal,renewalDates,approveRenewal} from '../src/renewals.js';
test('one platform and one email only',()=>{
 assert.deepEqual(parseRenewal('/renovar Netflix A@example.com'),{code:'netflix',email:'a@example.com'});
 for(const s of ['/renovar','/renovar netflix a@b.com c@d.com','/renovar netflix wrong'])assert.throws(()=>parseRenewal(s));
});
test('active renews from expiry; expired from approval',()=>{
 const now=new Date('2026-10-14T12:00:00Z');
 assert.equal(renewalDates('2026-10-22T12:00:00Z',30,now).end.toISOString(),'2026-11-22T12:00:00.000Z');
 assert.equal(renewalDates('2026-10-01T12:00:00Z',30,now).end.toISOString(),'2026-11-14T12:00:00.000Z');
});
test('calendar month ends, leap years, Peru midnight and nonmonthly plans',()=>{
 const now=new Date('2020-01-01T00:00:00Z');
 for(const [from,to] of [
  ['2026-01-31T12:00:00Z','2026-02-28T12:00:00.000Z'],
  ['2028-01-31T12:00:00Z','2028-02-29T12:00:00.000Z'],
  ['2026-12-22T12:00:00Z','2027-01-22T12:00:00.000Z'],
  ['2026-02-01T02:00:00Z','2026-03-01T02:00:00.000Z']
 ])assert.equal(renewalDates(from,30,now).end.toISOString(),to);
 assert.equal(renewalDates('2026-10-22T12:00:00Z',7,now).end.toISOString(),'2026-10-29T12:00:00.000Z');
});
test('payment alone cannot approve renewal',async()=>{
 await assert.rejects(approveRenewal({query:()=>{throw Error('must not write');}},{},'REF','admin',false),/Confirma/);
});
