import 'dotenv/config';
import neo4j from 'neo4j-driver';

const getNeo4jClient = () => {
    const driver = neo4j.driver(
        process.env.NEO4J_URI,
        neo4j.auth.basic(process.env.NEO4J_USERNAME, process.env.NEO4J_PASSWORD),
    );
    return driver;
};

export const runCypherQuery = async (query) => {
    let session;
    let driver;
    try {
        const driver = getNeo4jClient();
        const session = driver.session();
        const result = await session.run(query);
        return result.records.map((record) => record.toObject());
    } catch (error) {
        console.error(error);
        return { error: error.message };
    } finally {
        if (session) await session.close();
        if (driver) await driver.close();
    }
};
