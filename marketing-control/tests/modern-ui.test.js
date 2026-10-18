import test from 'node:test';
import assert from 'node:assert/strict';
import {brandKey} from '../public/modern-ui.js';
import {readFileSync} from 'node:fs';
test('platform brand key recognizes supported product names only',()=>{
 assert.equal(brandKey('Netflix · cuenta completa'),'netflix');
 assert.equal(brandKey('Prime Video'),'prime');
 assert.equal(brandKey('Disney+'),'disney');
 assert.equal(brandKey('HBO Max'),'max');
 assert.equal(brandKey('Otra plataforma'),null);
});
test('brand aliases recognize existing names without changing product codes',()=>{
 for(const label of ['prime video',' PRIME VIDEO ','prime','Amazon Prime Video','prime_video','primevideo'])assert.equal(brandKey(label),'prime');
 for(const label of ['crunchyroll','Crunchyroll · cuenta completa','CRUNCHYROLL','crunchy roll'])assert.equal(brandKey(label),'crunchyroll');
 for(const label of ['primefake','crunchyrollfake','',null])assert.equal(brandKey(label),null);
});
test('every recognized platform has a real local PNG asset',()=>{
 for(const brand of ['netflix','prime','crunchyroll','disney','max']){
  const asset=readFileSync(new URL('../public/brands/'+brand+'.png',import.meta.url));
  assert.deepEqual([...asset.subarray(0,8)],[137,80,78,71,13,10,26,10],brand);
  assert.ok(asset.length>100,brand);
 }
});
