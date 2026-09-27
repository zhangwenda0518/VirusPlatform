import { sanitizeQueryStrings } from './format.mjs';

const TABLE_TO_SELECT_COLUMNS = {
    ov_identifiers: ['run_id', 'bioproject', 'biosample', 'has_virus'],
    sra: ['acc', 'bioproject', 'biosample', 'organism', 'assay_type'],
    sra_stat: ['run_id', 'stat_host_order'],
    palm_virome: ['run', 'sotu', 'tax_species', 'tax_family'],
    biosample_tissue: ['biosample_id', 'tissue'],
    biosample_sex: ['biosample', 'sex'],
    biosample_geographical_location: ['accession', 'geo_attribute_value'],
    bgl_gm4326_gp4326: ['accession', 'biome_attribute_value'],
    biosample_disease: ['biosample', 'do_label'],
    virome_community: ['run', 'community_id'],
};

const TABLE_TO_JOIN_KEY = {
    ov_identifiers: 'run_id',
    sra: 'run_id',
    sra_stat: 'run_id',
    palm_virome: 'run_id',
    biosample_tissue: 'biosample',
    biosample_sex: 'biosample',
    biosample_geographical_location: 'biosample',
    bgl_gm4326_gp4326: 'biosample',
    biosample_disease: 'biosample',
    virome_community: 'run_id',
};

const TABLE_TO_UNIFIED_JOIN_KEY = {
    sra: {
        run: 'acc',
    },
    sra_stat: {
        run_id: 'run',
        stat_host_order: 'name',
    },
    biosample_tissue: {
        biosample: 'biosample_id',
    },
    biosample_geographical_location: {
        biosample: 'accession',
        geo_attribute_value: 'attribute_value',
    },
    bgl_gm4326_gp4326: {
        biosample: 'accession',
        biome_attribute_value: 'gp4326_wwf_tew_id',
    },
    palm_virome: {
        run_id: 'run',
    },
    virome_community: {
        run_id: 'run',
    },
};

const GROUP_BY_KEY_TO_COUNTS_MATERIALIZED_VIEW = {
    organism: 'ov_counts_sra_organism',
    bioproject: 'ov_counts_sra_bioproject',
    assay_type: 'ov_counts_sra_assay_type',
    tax_species: 'ov_counts_palm_virome_tax_species',
    tax_family: 'ov_counts_palm_virome_tax_family',
    sotu: 'ov_counts_palm_virome_sotu',
    tissue: 'ov_counts_biosample_tissue',
    geo_attribute_value: 'ov_counts_biosample_geographical_location',
    biome_attribute_value: 'ov_counts_bgl_gm4326_gp4326',
    stat_host_order: 'ov_counts_sra_stat',
    sex: 'ov_counts_biosample_sex',
    do_label: 'ov_counts_biosample_disease',
    community_id: 'ov_counts_virome_community',
};

export const handleIdKeyIrregularities = (key, table) => {
    if (TABLE_TO_UNIFIED_JOIN_KEY[table] && TABLE_TO_UNIFIED_JOIN_KEY[table][key]) {
        return TABLE_TO_UNIFIED_JOIN_KEY[table][key];
    }
    return key;
};

export const getFilterClauses = (filters, table) => {
    let filterClauses = [];

    if (Object.keys(filters).length > 0) {
        let groupByKeys = filters.map((filter) => filter.groupByKey);
        groupByKeys = [...new Set(groupByKeys)];
        groupByKeys.forEach((groupByKey) => {
            const groupByValues = filters
                .filter((filter) => filter.groupByKey === groupByKey)
                .map((filter) => filter.filterValue);

            filterClauses = [
                ...filterClauses,
                `${handleIdKeyIrregularities(groupByKey, table)} IN (${groupByValues.map((groupByValue) => `'${sanitizeQueryStrings(groupByValue)}'`).join(', ')})`,
            ];
        });
    }
    return `${filterClauses.join(' AND ')}`;
};

export const getIdClauses = (ids, idRanges, idColumn, table = 'sra') => {
    const idColumnRemap = handleIdKeyIrregularities(idColumn, table);
    const clauses = [];
    if (ids.length > 0) {
        clauses.push(`${idColumnRemap} IN (${ids.map((id) => `'${id}'`).join(',')})`);
    }
    if (idRanges.length > 0) {
        idRanges.forEach((range) => {
            const [start, end] = range;
            clauses.push(`${idColumnRemap} BETWEEN '${start}' AND '${end}'`);
        });
    }
    return clauses;
};

export const getTotalCountsQuery = ({ ids, idRanges, idColumn, table }) => {
    let clauses = getIdClauses(ids, idRanges, idColumn, table);
    clauses = `${clauses.length > 0 ? `WHERE ${clauses.join(' OR ')}` : ''}`;
    return `
        SELECT COUNT(*) as count
        FROM ${table}
        ${clauses}
    `;
};

export const getGroupedCountsByIdentifiers = ({ ids, idRanges, idColumn, groupBy, table }) => {

    let clauses = getIdClauses(ids, idRanges, idColumn, table);
    let remappedGroupBy = handleIdKeyIrregularities(groupBy, table);
    const btoIdSelect = remappedGroupBy === 'tissue' ? "STRING_AGG(DISTINCT bto_id, ', ') AS bto_ids," : "";
    clauses = `${clauses.length > 0 ? `WHERE ${clauses.join(' OR ')}` : ''}`;
    return `
        SELECT ${remappedGroupBy} as name, ${btoIdSelect} COUNT(*) as count ${table === 'sra' ? ', SUM(mbases)/POWER(10,3) as gbp' : ''}
        FROM ${table}
        ${clauses}
        GROUP BY ${remappedGroupBy}
    `;
};

export const hasNoGroupByFilters = (filters, groupBy) => {
    return !filters.filter((filter) => filter.groupByKey !== groupBy).length > 0;
};

export const getCachedCountsQuery = (groupBy, searchStringQuery, palmprintOnly) => {
    const palmprintOnlyClause = `${searchStringQuery.length > 0 ? 'AND' : 'WHERE'} virus_only = ${palmprintOnly ? 'true' : 'false'}`;
    return `
        SELECT * FROM ${GROUP_BY_KEY_TO_COUNTS_MATERIALIZED_VIEW[groupBy]}
        ${searchStringQuery}
        ${palmprintOnlyClause}
    `;
};

export const getSearchStringClause = (searchString, filters, groupBy) => {
    if (searchString === undefined || searchString === '') {
        return '';
    }
    const searchStrings = searchString
        .split(/[,\s]/)
        .map((substring) => substring.trim())
        .filter(Boolean);
    const columnName = hasNoGroupByFilters(filters, groupBy) ? 'name' : groupBy;
    const likeStatements = searchStrings.map((searchString) => {
        return `LOWER(${columnName}) LIKE LOWER('%${sanitizeQueryStrings(searchString)}%')`;
    });
    return `WHERE (${likeStatements.join(' OR ')})`;
};

export const getGroupedCountsByFilters = ({ filters, groupBy, searchStringQuery, palmprintOnly }) => {
    const tableJoin = getMinimalJoinSubQuery(filters, palmprintOnly, groupBy);
    return `
        SELECT ${groupBy} as name, COUNT(*) as count
        FROM (${tableJoin}) as open_virome
        ${searchStringQuery}
        GROUP BY ${groupBy}
    `;
};

export const getMinimalJoinSubQuery = (filters, palmprintOnly, groupBy = undefined) => {
    const filterTypes = filters.map((filter) => filter.groupByKey);

    const tableToInnerSelect = {
        ov_identifiers: 'run_id, bioproject, biosample, has_virus',
        sra: 'acc as run_id, bioproject as bioproject, biosample as biosample, organism as organism, assay_type',
        sra_stat: 'run as run_id, name as stat_host_order',
        palm_virome: 'run as run_id, sotu, tax_species, tax_family',
        biosample_tissue: 'biosample_id as biosample, tissue',
        biosample_sex: 'biosample, sex',
        biosample_geographical_location: 'accession as biosample, attribute_value as geo_attribute_value',
        bgl_gm4326_gp4326: 'accession as biosample, gp4326_wwf_tew_id as biome_attribute_value',
        biosample_disease: 'biosample, do_label',
        virome_community: 'run as run_id, community_id',
    };

    // Helper function to get tables based on filters or groupBy
    const getRelevantTables = (keys) => {
        // only return first table that contains the key
        return keys.map((key) =>
            Object.keys(TABLE_TO_SELECT_COLUMNS).find((table) => TABLE_TO_SELECT_COLUMNS[table].includes(key)),
        );
    };

    // Determine relevant tables from filters and groupBy
    let tables = filters.length ? getRelevantTables(filterTypes) : [];
    if (groupBy !== undefined) {
        tables = [...tables, ...getRelevantTables([groupBy])];
    }

    // Default join order has sra table first, remove duplicate tables
    tables = ['ov_identifiers', ...tables.filter((table) => table !== 'ov_identifiers')];
    tables = [...new Set(tables)];

    // Helper to build join statements
    const buildJoinStatement = (table, index, selectStatement, whereStatement, tableJoinKey) => {
        if (index === 0) {
            const palmprintOnlyClause = palmprintOnly
                ? `${whereStatement.length > 0 ? 'AND' : 'WHERE'} has_virus = true`
                : '';

            return `(
                SELECT ${selectStatement} FROM ${table}
                ${whereStatement}
                ${palmprintOnlyClause}
            ) as ${table}`;
        } else {
            return `INNER JOIN (
                SELECT ${selectStatement}
                FROM ${table}
                ${whereStatement}
            ) as ${table} ON ov_identifiers.${tableJoinKey} = ${table}.${tableJoinKey}`;
        }
    };

    // Build join statements
    const joinStatements = tables.map((table, i) => {
        const columns = TABLE_TO_SELECT_COLUMNS[table];
        const tableJoinKey = TABLE_TO_JOIN_KEY[table];
        let tableFilters = filters.filter((filter) => columns.includes(filter.groupByKey));

        // Adjust filter keys to account for irregularities
        tableFilters = tableFilters.map((filter) => ({
            ...filter,
            filterKey: handleIdKeyIrregularities(filter.filterKey, table),
        }));

        const isSingleOrFirstTable = i === 0 || columns.includes(groupBy) || tableFilters.length > 0;

        const selectStatement = isSingleOrFirstTable ? tableToInnerSelect[table] : tableJoinKey;

        const whereStatement = tableFilters.length > 0 ? `WHERE ${getFilterClauses(tableFilters, table)}` : '';

        return buildJoinStatement(table, i, selectStatement, whereStatement, tableJoinKey);
    });

    // Construct select statements
    const selectStatements = [
        'ov_identifiers.run_id as run_id, ov_identifiers.biosample as biosample, ov_identifiers.bioproject as bioproject',
    ];
    if (groupBy !== undefined && !selectStatements[0].includes(groupBy)) {
        const groupByTable = tables.find((table) => TABLE_TO_SELECT_COLUMNS[table].includes(groupBy));
        selectStatements.push(`${groupByTable}.${groupBy} as ${groupBy}`);
    }

    // Final query construction
    return `
        SELECT ${selectStatements.join(', ')}
        FROM ${joinStatements.join('\n')}
    `;
};
