import type { FastifyReply,FastifyRequest } from 'fastify';
import { SignJWT,jwtVerify } from 'jose';
import type { AdminRole } from '@jheliz/shared';
const secret=()=>new TextEncoder().encode(process.env.AUTH_SECRET||'');
export type Session={sub:string;email:string;role:AdminRole};
export async function issue(reply:FastifyReply,session:Session){const token=await new SignJWT({...session}).setProtectedHeader({alg:'HS256'}).setIssuedAt().setExpirationTime('8h').sign(secret());reply.setCookie('jheliz_admin',token,{httpOnly:true,secure:process.env.NODE_ENV==='production',sameSite:'strict',path:'/',maxAge:28800});}
export async function requireSession(request:FastifyRequest,reply:FastifyReply){try{const token=request.cookies.jheliz_admin;if(!token)throw new Error();const {payload}=await jwtVerify(token,secret());request.admin=payload as unknown as Session;}catch{reply.code(401).send({error:'UNAUTHORIZED'});}}
export function allow(...roles:AdminRole[]){return async(request:FastifyRequest,reply:FastifyReply)=>{await requireSession(request,reply);if(reply.sent)return;if(!roles.includes(request.admin.role))reply.code(403).send({error:'FORBIDDEN'});};}
declare module 'fastify'{interface FastifyRequest{admin:Session}}
