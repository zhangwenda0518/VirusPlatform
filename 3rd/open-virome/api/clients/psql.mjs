import 'dotenv/config';
import pg from 'pg';

const { Pool } = pg;

const pool = new Pool({
    database: process.env.PG_DATABASE_LOGAN,
    host: process.env.PG_HOST,
    password: process.env.PG_PASSWORD_LOGAN,
    port: process.env.PG_PORT,
    user: process.env.PG_USER_LOGAN,
});

export const runPSQLQuery = async (text, params) => {
    try {
        const start = Date.now();
        const res = await pool.query(text, params);
        const duration = Date.now() - start;
        console.log('executed query', { text, duration, rows: res.rowCount });
        return res.rows;
    } catch (e) {
        return { error: JSON.stringify(e) };
    }
};
