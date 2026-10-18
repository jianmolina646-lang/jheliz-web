import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mergeAssignments} from '../src/codes-sheets.js';
test('updates without duplicating; keeps withdrawn assignments and raw text',()=>{
 const now=new Date('2026-10-14T03:00:00Z');
 const item={id:'wa:1:email:1',phone:'51911111111',name:'=unsafe()',email:'a@example.test',status:'Activo'};
 const first=mergeAssignments([], [item],now);
 assert.equal(first.length,1);assert.equal(first[0][2],'=unsafe()');
 const again=mergeAssignments(first,[{...item,status:'Inactivo'}],now);
 assert.equal(again.length,1);assert.equal(again[0][4],'Inactivo');
 const removed=mergeAssignments(again,[],now);
 assert.equal(removed.length,1);assert.equal(removed[0][8],'Retirado');
 assert.equal(removed[0][3],item.email);
});
