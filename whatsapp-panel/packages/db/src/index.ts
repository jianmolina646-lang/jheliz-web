import { PrismaClient } from '@prisma/client';
const globalDb=globalThis as unknown as {prisma?:PrismaClient};
export const db=globalDb.prisma??new PrismaClient({log:process.env.NODE_ENV==='development'?['warn','error']:['error']});
if(process.env.NODE_ENV!=='production')globalDb.prisma=db;
export * from '@prisma/client';
