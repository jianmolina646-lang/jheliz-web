import { z } from 'zod';

export const roles = ['OWNER', 'ADMIN', 'SUPPORT'] as const;
export type AdminRole = typeof roles[number];
export const productInput = z.object({sku:z.string().trim().min(2).max(40).regex(/^[A-Z0-9_-]+$/),name:z.string().trim().min(2).max(120),category:z.string().trim().max(80).default('General'),description:z.string().trim().max(1500).default(''),priceCents:z.number().int().nonnegative(),currency:z.string().length(3).default('PEN'),minimumStock:z.number().int().nonnegative().default(2),whatsappText:z.string().trim().max(2000).default(''),imageUrl:z.string().url().max(1000).nullable().optional(),sortOrder:z.number().int().default(0),active:z.boolean().default(true)});
export const commandInput = z.object({name:z.string().trim().min(1).max(40),description:z.string().trim().max(200),response:z.string().trim().min(1).max(4000),enabled:z.boolean().default(true),permission:z.enum(['PUBLIC','CUSTOMER','ADMIN']).default('PUBLIC'),sortOrder:z.number().int().default(0)});
export const rechargeInput = z.object({customerId:z.string().uuid(),amountCents:z.number().int().positive(),note:z.string().trim().max(500).optional()});
export type ConnectionSnapshot={status:'DISCONNECTED'|'CONNECTING'|'QR_READY'|'CONNECTED'|'ERROR';jid?:string;displayName?:string;qr?:string;connectedAt?:string;lastError?:string};
