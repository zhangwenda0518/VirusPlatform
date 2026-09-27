import { runCypherQuery } from '../clients/neo4j.mjs';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';

const s5cmdPath = !!process.env.IS_LOCAL ? 's5cmd' : './bin/s5cmd';

const csvToArray = (text) => {
    let p = '',
        row = [''],
        ret = [row],
        i = 0,
        r = 0,
        s = !0,
        l;
    for (l of text) {
        if ('"' === l) {
            if (s && l === p) row[i] += l;
            s = !s;
        } else if (',' === l && s) l = row[++i] = '';
        else if ('\n' === l && s) {
            if ('\r' === p) row[i] = row[i].slice(0, -1);
            row = ret[++r] = [(l = '')];
            i = 0;
        } else row[i] += l;
        p = l;
    }
    return ret;
};

const cleanMWASData = (rows) => {
    const dateFields = [
        'date',
        'when',
        'update',
        'time',
        'day',
        'month',
        'year',
        'hour',
        'minute',
        'second',
        'timestamp',
        'created',
        'modified',
        'added',
        'deleted',
        'uploaded',
        'downloaded',
        'accessed',
        'start',
        'end',
        'duration',
        'elapsed',
    ];
    const nullUnknownValues = [
        'unknown',
        'n/a',
        'na',
        'null',
        'none',
        'not available',
        'not applicable',
        'not specified',
        'not provided',
        'not reported',
        'not recorded',
        'not collected',
        'not determined',
        'not known',
        'not measured',
        'not observed',
        'not performed',
        'not requested',
        'not required',
        'not stated',
        'not tested',
    ];
    const blackListFields = [
        ...dateFields,
        'age',
        'paragraph',
        'title',
        'lab',
        'location',
        'geo',
        'latitude',
        'longitude',
        'lat-lon',
        'lat_lon',
        'contact',
        'email',
    ];
    const blackListValues = [
        ...nullUnknownValues,
        'http',
        'missing',
        'unspecified',
        'unavailable',
        'unknown',
        'na',
        'n/a',
    ];

    const isValidNumber = (value) => {
        const parsedValue = parseFloat(value);
        if (isNaN(parsedValue)) {
            return false;
        }

        if (value === 'inf' || value === '-inf') {
            return false;
        }
        if (Number.isNaN(value)) {
            return false;
        }
        if (value <= 0 || value > 50) {
            return false;
        }
        return true;
    };

    return rows
        .filter((row) => row.metadata_field && row.metadata_value && row.p_value && row.fold_change)
        .filter((row) => isValidNumber(row.p_value) && isValidNumber(row.fold_change))
        .filter(
            (row) =>
                !blackListFields.some(
                    (field) => row.metadata_field && row.metadata_field.toLowerCase().includes(field),
                ),
        )
        .filter(
            (row) =>
                !blackListValues.some(
                    (value) => row.metadata_value && row.metadata_value.toLowerCase().includes(value),
                ),
        )
        .sort((a, b) => a.p_value - b.p_value);
};

const availableFamilyDirs = [
    'Alphaflexiviridae',
    'Alphatetraviridae',
    'Alvernaviridae',
    'Amalgaviridae',
    'Amnoonviridae',
    'Aspiviridae',
    'Astroviridae',
    'Barnaviridae',
    'Benyviridae',
    'Birnaviridae',
    'Botourmiaviridae',
    'Bromoviridae',
    'Bunyaviridae',
    'Caliciviridae',
    'Carmotetraviridae',
    'Chrysoviridae',
    'Chuviridae',
    'Closteroviridae',
    'Coronaviridae',
    'Cystoviridae',
    'Deltavirus',
    'Dicistroviridae',
    'Endornaviridae',
    'Feraviridae',
    'Filoviridae',
    'Fimoviridae',
    'Flaviviridae',
    'Flexiviridae',
    'Fusarividae',
    'Gammaflexiviridae',
    'Gresnaviridae',
    'Hantaviridae',
    'Hepeviridae',
    'Hypoviridae',
    'Iflaviridae',
    'Jonviridae',
    'Kitaviridae',
    'Leviviridae',
    'Lispiviridae',
    'Marnaviridae',
    'Matonaviridae',
    'Medioniviridae',
    'Megabirnaviridae',
    'Megabirnavirus',
    'Mitoviridae',
    'Mononiviridae',
    'Mymonaviridae',
    'Mypoviridae',
    'Nairoviridae',
    'Nanghoshaviridae',
    'Nanhypoviridae',
    'Narnaviridae',
    'Nidovirales',
    'Nodaviridae',
    'Nyamiviridae',
    'Olifoviridae',
    'Ophioviridae',
    'Orthomyxoviridae',
    'Paramyxoviridae',
    'Partitiviridae',
    'Peribunyaviridae',
    'Permutotetraviridae',
    'Phenuiviridae',
    'Picobirnaviridae',
    'Picornaviridae',
    'Pneumoviridae',
    'Polycipiviridae',
    'Potyviridae',
    'Qinviridae',
    'Quadriviridae',
    'Quenyaviridae',
    'Reoviridae',
    'Rhabdoviridae',
    'Secoviridae',
    'Sinhaliviridae',
    'Solemoviridae',
    'Sunviridae',
    'Togaviridae',
    'Tombusviridae',
    'Tospoviridae',
    'Totiviridae',
    'Tymoviridae',
    'Virgaviridae',
    'Yueviridae',
];

export const getMWASResults = async (bioprojects, targetVirusFamilies, pageStart, pageEnd) => {
    const query = `
        MATCH (n:BioProject)<-[:HAS_BIOPROJECT]-(r:SRA)-[:HAS_SOTU]->(s:SOTU)
        WHERE n.bioProject IN [${bioprojects.map((bioproject) => `'${bioproject}'`).join(', ')}]
        AND n:OpenVirome AND s:OpenVirome AND r:OpenVirome
        with n.bioProject as bioProject, s.taxFamily as virusFamily, collect(DISTINCT r.bioSample) as bioSamples, collect(DISTINCT s.sotu) as sotus, collect(DISTINCT s.taxSpecies) as taxSpecies
        RETURN bioProject, virusFamily, bioSamples, sotus, taxSpecies
        LIMIT 5000
    `;

    const records = await runCypherQuery(query);
    if (records.error) {
        return { error: records.error };
    }

    const serializedRecords = records.reduce((acc, record) => {
        if (!record || !record.bioProject || !record.virusFamily || !record.bioSamples) {
            return acc;
        }
        if (!acc[record.bioProject]) {
            acc[record.bioProject] = {};
        }
        if (!acc[record.bioProject][record.virusFamily]) {
            acc[record.bioProject][record.virusFamily] = [];
        }
        acc[record.bioProject][record.virusFamily] = {
            sotus: record.sotus,
            taxSpecies: record.taxSpecies,
            bioSamples: record.bioSamples,
        };
        return acc;
    }, {});

    let catCommands = [];
    for (const bioProject in serializedRecords) {
        const virusFamilies = Object.keys(serializedRecords[bioProject]);
        for (const familyDir of availableFamilyDirs) {
            if (virusFamilies.includes(familyDir) && targetVirusFamilies.includes(familyDir)) {
                const objKey = `${familyDir}/${bioProject}.csv`;
                const s3Path = `s3://serratus-mwas/${objKey}`;
                catCommands.push(`cat --concurrency 100 ${s3Path}`);
            }
        }
    }

    const chunkSize = 100;
    const chunkedCommands = [];
    catCommands = catCommands.slice(0, 1000);
    for (let i = 0; i < catCommands.length; i += chunkSize) {
        chunkedCommands.push(catCommands.slice(i, i + chunkSize));
    }

    let output = '';
    for (const chunk of chunkedCommands) {
        const catMWASData = spawn('sh', [
            '-c',
            `echo '${chunk.join('\n')}' | ${s5cmdPath} --numworkers 10 --no-sign-request run`,
        ]);
        for await (const line of createInterface({
            input: catMWASData.stdout,
            terminal: false,
        })) {
            output += line;
            output += '\n';
        }
    }

    const lines = output.split('\n');
    const mwasData = [];
    const header =
        'bioproject_id,family,metadata_field,metadata_value,num_true,num_false,mean_rpm_true,mean_rpm_false,sd_rpm_true,sd_rpm_false,fold_change,test_statistic,p_value';

    for (const line of lines) {
        if (!line || line.length === 0 || line.includes('ERROR') || line === header) {
            continue;
        }
        const fields = csvToArray(line)[0];
        const [
            bioproject,
            family,
            metadata_field,
            metadata_value,
            num_true,
            num_false,
            mean_rpm_true,
            mean_rpm_false,
            sd_rpm_true,
            sd_rpm_false,
            fold_change,
            test_statistic,
            p_value,
        ] = fields;

        let familyName = '';
        let biosamples = [];
        let sotus = [];
        let taxSpecies = [];

        if (family) {
            familyName = family.split('-')[0];
            if (bioproject) {
                biosamples = serializedRecords?.[bioproject]?.[familyName]?.bioSamples ?? [];
                sotus = serializedRecords?.[bioproject]?.[familyName]?.sotus ?? [];
                taxSpecies = serializedRecords?.[bioproject]?.[familyName]?.taxSpecies ?? [];
            }
        }
        mwasData.push({
            bioproject,
            family: familyName,
            metadata_field,
            metadata_value,
            num_true,
            num_false,
            mean_rpm_true,
            mean_rpm_false,
            sd_rpm_true,
            sd_rpm_false,
            fold_change,
            test_statistic,
            p_value,
            biosamples,
            sotus,
            taxSpecies,
        });
    }
    const mwasDataClean = cleanMWASData(mwasData);
    const pagedData = mwasDataClean.slice(pageStart, pageEnd);
    console.log(`MWAS done fetching data. Total: ${mwasDataClean.length}, paged: ${pagedData.length}`);
    return pagedData;
};
