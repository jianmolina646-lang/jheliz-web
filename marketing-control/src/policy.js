import {z} from 'zod';
export const loginSchema=z.object({email:z.string().email().max(254),password:z.string().min(1).max(256)}).strict();
export const commandSchema=z.object({name:z.string().regex(/^[a-z][a-z0-9_]{0,29}$/),response:z.string().trim().min(1).max(2000),enabled:z.boolean(),private:z.boolean().default(false)}).strict();
export function permitted(role, capability){return ({ADMIN:['read','control','commands','users'],OPERATOR:['read','control','commands'],SUPPORT:['read']}[role]||[]).includes(capability);}
export function commandReply(command){if(!command?.enabled)return null;if(command.private)return 'Por seguridad, esta consulta requiere el módulo de clientes verificados. Contacta con un operador.';return command.response;}
