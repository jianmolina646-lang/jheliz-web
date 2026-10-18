import test from 'node:test';
import assert from 'node:assert/strict';
import {permitted,commandReply,commandSchema} from '../src/policy.js';
test('support cannot control a bot or edit commands',()=>{assert.equal(permitted('SUPPORT','read'),true);assert.equal(permitted('SUPPORT','control'),false);assert.equal(permitted('OPERATOR','users'),false);assert.equal(permitted('ADMIN','users'),true);});
test('private commands never return their configured private data',()=>{assert.equal(commandReply({enabled:false,response:'secret'}),null);assert.ok(!commandReply({enabled:true,private:true,response:'secret'}).includes('secret'));assert.equal(commandReply({enabled:true,private:false,response:'hola'}),'hola');});
test('command validation rejects invalid names and oversized responses',()=>{assert.equal(commandSchema.safeParse({name:'../secret',response:'hi',enabled:true}).success,false);assert.equal(commandSchema.safeParse({name:'help',response:'x'.repeat(2001),enabled:true}).success,false);});
