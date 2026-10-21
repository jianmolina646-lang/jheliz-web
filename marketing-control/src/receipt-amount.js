import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
export async function readReceiptAmount(data){return (await readReceiptDetails(data))?.amount_cents??null;}
export function readReceiptDetails(data){
 return new Promise(resolve=>{
  const child=spawn('python3',[fileURLToPath(new URL('./receipt-amount.py',import.meta.url))],{stdio:['pipe','pipe','ignore']});
  let output='',finished=false;
  const finish=value=>{if(finished)return;finished=true;clearTimeout(timer);resolve(value);};
  const timer=setTimeout(()=>{child.kill('SIGKILL');finish(null);},30000);
  child.on('error',()=>finish(null));child.stdin.on('error',()=>finish(null));
  child.stdout.on('data',chunk=>{output+=chunk;if(output.length>1024){child.kill('SIGKILL');finish(null);}});
  child.on('close',code=>{
   try{const r=JSON.parse(output);finish(code===0?{
    amount_cents:Number.isSafeInteger(r.amount_cents)&&r.amount_cents>0?r.amount_cents:null,
    operation_minute:typeof r.operation_minute==='string'&&Number.isFinite(Date.parse(r.operation_minute))?r.operation_minute:null
   }:null);}
   catch{finish(null);}
  });
  child.stdin.end(data);
 });
}
