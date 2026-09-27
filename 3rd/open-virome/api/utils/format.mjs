const ENABLE_REDUCED_IDS = false;

const getNumericSuffix = (str = '') => {
    const match = str.match(/\d+$/);
    return match ? parseInt(match[0]) : null;
};

const getNumericToIdMap = (ids) => {
    return ids.reduce((acc, id) => {
        const numericSuffix = getNumericSuffix(id);
        if (numericSuffix !== null) {
            if (!acc[numericSuffix]) {
                acc[numericSuffix] = [];
            }
            acc[numericSuffix].push(id);
        }
        return acc;
    }, {});
};

export const sanitizeQueryStrings = (filterValue) => {
    // escape single quotes
    return filterValue.replace(/'/g, "''");
};

const reduceConsecutiveToRange = (ids) => {
    if (ids.length === 0) {
        return [[], []];
    }

    if (!ENABLE_REDUCED_IDS || ids.length < 5000) {
        return [[], ids];
    }

    const numericToIdMap = getNumericToIdMap(ids);
    const sortedNumericSuffixes = Object.keys(numericToIdMap).sort((a, b) => a - b);

    const idSingles = [];
    const idRanges = [];

    let prevStart = sortedNumericSuffixes[0];
    let prevEnd = sortedNumericSuffixes[0];

    for (let i = 1; i < sortedNumericSuffixes.length; i++) {
        let current = sortedNumericSuffixes[i];

        if (parseInt(current) - parseInt(prevEnd) === 1) {
            prevEnd = current;
        } else {
            if (prevStart === prevEnd) {
                idSingles.push(numericToIdMap[prevStart]);
            } else {
                idRanges.push([numericToIdMap[prevStart], numericToIdMap[prevEnd]]);
            }
            prevStart = current;
            prevEnd = current;
        }
    }

    if (prevStart == prevEnd) {
        idSingles.push(numericToIdMap[prevStart]);
    } else {
        if (parseInt(prevEnd) - parseInt(prevStart) == 1) {
            idSingles.push(numericToIdMap[prevStart], numericToIdMap[prevEnd]);
        } else {
            idRanges.push([numericToIdMap[prevStart], numericToIdMap[prevEnd]]);
        }
    }

    return [idRanges, idSingles];
};

export const formatIdentifiersResponse = (result = []) => {
    let runIds = result.map((row) => row.run_id).filter((biosample) => biosample !== null);
    runIds = [...new Set(runIds)];
    const [runIdRanges, runIdSingles] = reduceConsecutiveToRange(runIds);

    let biprojects = result.map((row) => row.bioproject).filter((biosample) => biosample !== null);
    biprojects = [...new Set(biprojects)];
    const [bioprojectRanges, bioprojectSingles] = reduceConsecutiveToRange(biprojects);

    let biosamples = result.map((row) => row.biosample).filter((biosample) => biosample !== null);
    biosamples = [...new Set(biosamples)];
    const [biosampleRanges, biosampleSingles] = reduceConsecutiveToRange(biosamples);

    return {
        run: {
            single: runIdSingles,
            range: runIdRanges,
            totalCount: result.length > 0 ? runIds.length : -1,
        },
        bioproject: {
            single: bioprojectSingles,
            range: bioprojectRanges,
            totalCount: result.length > 0 ? biprojects.length : -1,
        },
        biosample: {
            single: biosampleSingles,
            range: biosampleRanges,
            totalCount: result.length > 0 ? biosamples.length : -1,
        },
    };
};

export const getRequestBody = (req) => {
    if (req.body !== undefined) {
        return req.body;
    }
    if (req?.apiGateway?.event?.body !== undefined) {
        return JSON.parse(req.apiGateway.event.body);
    }
};
