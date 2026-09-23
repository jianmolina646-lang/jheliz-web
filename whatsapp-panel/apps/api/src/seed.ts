import argon2 from 'argon2';import {db} from '@jheliz/db';
const email=(process.env.OWNER_EMAIL||'').trim().toLowerCase(),password=process.env.OWNER_INITIAL_PASSWORD||'';
if(!email||password.length<12)throw new Error('OWNER_EMAIL and a 12+ character OWNER_INITIAL_PASSWORD are required');
await db.admin.upsert({where:{email},update:{active:true,role:'OWNER'},create:{email,passwordHash:await argon2.hash(password),role:'OWNER'}});
await db.whatsAppSession.upsert({where:{id:'primary'},update:{},create:{id:'primary'}});
for(const command of [{name:'menu',description:'Menú principal',response:'Bienvenido. Usa .shop para ver productos.',sortOrder:1},{name:'shop',description:'Catálogo disponible',response:'DYNAMIC:SHOP',sortOrder:2},{name:'help',description:'Ayuda',response:'Usa .menu para comenzar.',sortOrder:99}])await db.botCommand.upsert({where:{name:command.name},update:{},create:command});
console.log('Owner and defaults ready');await db.$disconnect();
