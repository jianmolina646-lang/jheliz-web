import {db} from './db.js';
let input='';for await(const chunk of process.stdin)input+=chunk;
for(const line of input.trim().split('\n').filter(Boolean)){
 const user=JSON.parse(line);
 if(!user.active||!user.email||!user.passwordHash?.startsWith('$argon2'))continue;
 await db.query('INSERT INTO users(email,password_hash,role) VALUES($1,$2,$3) ON CONFLICT(email) DO NOTHING',[user.email.toLowerCase(),user.passwordHash,['OWNER','ADMIN'].includes(user.role)?'ADMIN':'SUPPORT']);
 console.log('Access preserved:',user.email);
}
await db.end();
