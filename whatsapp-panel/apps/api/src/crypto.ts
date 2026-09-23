import {createCipheriv,createDecipheriv,randomBytes} from 'node:crypto';
function key(){const value=Buffer.from(process.env.ENCRYPTION_KEY||'','base64');if(value.length!==32)throw new Error('ENCRYPTION_KEY must decode to 32 bytes');return value;}
export function encrypt(value:string){const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key(),iv),data=Buffer.concat([cipher.update(value,'utf8'),cipher.final()]),tag=cipher.getAuthTag();return Buffer.concat([iv,tag,data]).toString('base64');}
export function decrypt(value:string){const raw=Buffer.from(value,'base64'),decipher=createDecipheriv('aes-256-gcm',key(),raw.subarray(0,12));decipher.setAuthTag(raw.subarray(12,28));return Buffer.concat([decipher.update(raw.subarray(28)),decipher.final()]).toString('utf8');}
export function mask(value:string){return value.length<5?'••••':`${value.slice(0,2)}••••${value.slice(-2)}`;}
