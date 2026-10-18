import pg from 'pg';
export const db = new pg.Pool({connectionString: process.env.DATABASE_URL, max: 8});
export const rows = async (sql, values=[]) => (await db.query(sql, values)).rows;
export async function audit(actor, action, ip, details={}) {
  await db.query('INSERT INTO audit(actor,action,ip,details) VALUES($1,$2,$3,$4)',[actor,action,ip,details]);
}
export async function event(instance, level, message) {
  await db.query('INSERT INTO events(instance_id,level,message) VALUES($1,$2,$3)',[instance,level,message]);
}
