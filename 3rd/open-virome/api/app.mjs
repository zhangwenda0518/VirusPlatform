import express from 'express';
import bodyParser from 'body-parser';
import cors from 'cors';
import compression from 'compression';
import awsServerlessExpressMiddleware from 'aws-serverless-express/middleware.js';

import { runPSQLQuery } from './clients/psql.mjs';
import { runCypherQuery } from './clients/neo4j.mjs';
import {
    getIdClauses,
    getMinimalJoinSubQuery,
    getTotalCountsQuery,
    getGroupedCountsByIdentifiers,
    getGroupedCountsByFilters,
    hasNoGroupByFilters,
    getCachedCountsQuery,
    getSearchStringClause,
} from './utils/queryBuilder.mjs';
import { getMWASResults } from './utils/mwas.mjs';
import { getBioprojectsSummarization, getMwasHypothesis, getGraphRAGResults, getFigureSummarization, generateFigureCaptions } from './utils/LLMTextGeneration.mjs';
import { getRequestBody, formatIdentifiersResponse } from './utils/format.mjs';

const app = express();
const port = 8000;

app.use(express.json({ limit: '100mb' }));
app.use(cors());
app.use(awsServerlessExpressMiddleware.eventContext());
app.use(bodyParser.json());
app.use(
    bodyParser.urlencoded({
        extended: true,
    }),
);
app.use(compression());

app.post('/counts', async (req, res) => {
    const body = getRequestBody(req);

    if (body === undefined) {
        return res.status(400).json({ error: 'Invalid request!' });
    }

    const idColumn = body?.idColumn ?? undefined;
    const ids = body?.ids ?? [];
    const idRanges = body?.idRanges ?? [];

    const filters = body?.filters ?? [];
    const table = body?.table ?? 'sra';
    const groupBy = body?.groupBy ?? undefined;
    const sortByColumn = body?.sortByColumn ?? undefined;
    const sortByDirection = body?.sortByDirection ?? undefined;
    const pageStart = body?.pageStart ?? 0;
    const pageEnd = body?.pageEnd ?? undefined;
    const searchString = body?.searchString ?? undefined;
    const palmprintOnly = body?.palmprintOnly ?? true;
    const tableDescription = body?.tableDescription ?? undefined;

    if (idColumn && filters.length > 0) {
        return res.status(400).json({ error: 'Cannot have both idColumn and filters!' });
    }

    let query = ``;

    const useMaterializedView = hasNoGroupByFilters(filters, groupBy) && pageEnd === 100000;

    if (!groupBy) {
        if (!idColumn) {
            return res.status(400).json({ error: 'groupBy is required!' });
        }
        // Counts for total (used by results table pagination)
        query = getTotalCountsQuery({
            ids,
            idRanges,
            idColumn,
            table: table,
        });
    } else if (idColumn && ids.length > 0) {
        // Counts for figures and plots
        query = getGroupedCountsByIdentifiers({
            ids,
            idRanges,
            idColumn,
            groupBy,
            table: table,
        });
    } else if (useMaterializedView) {
        // Counts for filters, from materialized view if no filters applied
        const searchStringQuery = getSearchStringClause(searchString, filters, groupBy);
        query = getCachedCountsQuery(groupBy, searchStringQuery, palmprintOnly);
    } else {
        // Counts for filters, from main table if filters applied
        const searchStringQuery = getSearchStringClause(searchString, filters, groupBy);
        query = getGroupedCountsByFilters({
            filters,
            groupBy,
            searchStringQuery,
            palmprintOnly,
        });
    }

    query = `
        ${query}
        ${sortByColumn !== undefined ? `ORDER BY ${sortByColumn} ${sortByDirection}` : ''}
        ${pageEnd !== undefined ? `LIMIT ${pageEnd - pageStart} OFFSET ${pageStart}` : ''}
    `;

    let result = await runPSQLQuery(query);

    if(result.length > 0 && "bto_ids" in result[0] && table == "biosample_tissue") { 
        const btoIDs = result.map(item => item.bto_ids.split(', ')).flat();
        const bestParentTissueQuery = `
            MATCH (specific:Tissue)
            WHERE specific.btoId IN [${btoIDs.map(id => `'${id}'`).join(', ')}]
            WITH specific AS ancestor, COUNT(specific) AS direct_matches

            OPTIONAL MATCH (specific:Tissue)-[:HAS_PARENT*1..5]->(ancestor)
            WHERE specific.btoId IN [${btoIDs.map(id => `'${id}'`).join(', ')}]
            WITH ancestor, 
                SUM(direct_matches) + COUNT(DISTINCT specific) AS num_bto_matches
            ORDER BY num_bto_matches DESC
            LIMIT 5
            RETURN ancestor.btoId AS common_bto, 
                ancestor.scientificName AS common_tissue, 
                num_bto_matches;
        `
        const bestParentTissue = await runCypherQuery(bestParentTissueQuery);
        const bestParentTissueObject = {};
        bestParentTissue.forEach((item, index) => {
            bestParentTissueObject[`best_${index + 1}`] = {
                btoId: item.common_bto,
                tissue: item.common_tissue,
                count: item.num_bto_matches
            };
        });

        result.push(bestParentTissueObject);
    }
    if (result.error) {
        console.error(result.error);
        console.error(query);
        return res.status(500).json({ error: result.error });
    }
    return res.json(result);
});

app.post('/identifiers', async (req, res) => {
    const body = getRequestBody(req);

    if (body === undefined) {
        return res.status(400).json({ error: 'Invalid request!' });
    }

    const filters = body?.filters ?? [];
    const palmprintOnly = body?.palmprintOnly ?? true;

    if (filters.length === 0) {
        return res.json(formatIdentifiersResponse([]));
    }
    const subquery = getMinimalJoinSubQuery(filters, palmprintOnly);
    const query = `
        SELECT DISTINCT run_id, bioproject, biosample
        FROM (${subquery}) as open_virome
    `;

    let result = await runPSQLQuery(query);

    if (result.error) {
        console.error(result.error);
        console.error(query);
        return res.status(500).json({ error: result.error });
    }

    result = formatIdentifiersResponse(result);
    return res.json(result);
});

app.post('/results', async (req, res) => {
    const body = getRequestBody(req);
    if (body === undefined) {
        return res.status(400).json({ error: 'Invalid request!' });
    }

    const idColumn = body?.idColumn ?? 'run_id';
    const ids = body?.ids ?? [];
    const idRanges = body?.idRanges ?? [];
    const table = body?.table ?? 'sra';
    const columns = body?.columns ?? '*';
    const pageStart = body?.pageStart ?? 0;
    const pageEnd = body?.pageEnd ?? undefined;

    const clauses = getIdClauses(ids, idRanges, idColumn, table);

    const query = `
        SELECT ${columns}
        FROM ${table}
        ${clauses.length > 0 ? `WHERE ${clauses.join(' OR ')}` : ''}
        ${pageEnd !== undefined ? `LIMIT ${pageEnd - pageStart} OFFSET ${pageStart}` : 'LIMIT 20000'}
    `;
    const result = await runPSQLQuery(query);
    if (result.error) {
        console.error(result.error);
        console.error(query);
        return res.status(500).json({ error: result.error });
    }
    return res.json(result);
});

app.post('/mwas', async (req, res) => {
    const body = getRequestBody(req);
    if (body === undefined) {
        return res.status(400).json({ error: 'Invalid request!' });
    }
    const ids = body?.ids ?? [];
    const virusFamilies = body?.virusFamilies ?? [];
    const pageStart = body?.pageStart ?? 0;
    const pageEnd = body?.pageEnd ?? undefined;
    const result = await getMWASResults(ids, virusFamilies, pageStart, pageEnd);
    if (result.error) {
        console.error(result.error);
        return res.status(500).json({ error: result.error });
    }
    return res.json(result);
});

app.post('/summary', async (req, res) => {
    const body = getRequestBody(req);
    if (body === undefined) {
        return res.status(400).json({ error: 'Invalid request!' });
    }
    const ids = body?.ids ?? [];
    const dataObj = body?.dataObj ?? [];
    const dataType = body?.idColumn ?? '';
    const figureData = body?.figureData ?? [];
    const figureDescription = body?.figureDescription ?? '';
    let result = {};
    if (dataType === 'bioproject') {
        result = await getBioprojectsSummarization(ids, dataObj);
    }
    else{
        result = await getFigureSummarization(ids, dataObj, dataType, figureDescription);
    }
    if (result?.error) {
        console.error(result.error);
        return res.status(500).json({ error: result.error });
    }
    return res.json(result);
});

app.post('/hypothesis', async (req, res) => {
    const body = getRequestBody(req);
    if (body === undefined) {
        return res.status(400).json({ error: 'Invalid request!' });
    }
    const ids = body?.ids ?? [];
    const filters = body?.filters ?? [];
    const selectedMetadata = body?.selectedMetadata ?? [];
    const result = await getMwasHypothesis(ids, filters, selectedMetadata);
    if (result.error) {
        console.error(result.error);
        return res.status(500).json({ error: result.error });
    }
    return res.json(result);
});

app.post('/globalChat', async (req, res) => {
    const body = getRequestBody(req);
    if (body === undefined) {
        return res.status(400).json({ error: 'Invalid request!' });
    }
    const conversation = body?.conversation ?? [];
    const message = body?.message ?? '';
    const result = await getGraphRAGResults(message, conversation);
    if (result.error) {
        console.error(result.error);
        return res.status(500).json({ error: result.error });
    }
    return res.json(result);
});

app.listen(port, () => console.log(`API listening on port ${port}`));

export default app;
