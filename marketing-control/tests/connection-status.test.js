import test from 'node:test';
import assert from 'node:assert/strict';
import {connectionStatus} from '../public/connection-status.js';
test('inactive connection is not an error and QR differs from a failure',()=>{
 assert.deepEqual(connectionStatus({desired:false,status:'ERROR',worker_online:true}),{label:'Desactivado',tone:''});
 assert.equal(connectionStatus({desired:true,status:'QR_READY',worker_online:true}).tone,'warn');
 assert.equal(connectionStatus({desired:true,status:'CONNECTED',worker_online:true}).label,'Conectado');
 assert.equal(connectionStatus({desired:true,status:'CONNECTED',worker_online:false}).tone,'bad');
 assert.equal(connectionStatus({desired:true,status:'ERROR',worker_online:true}).tone,'bad');
});
