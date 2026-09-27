import { streamLLMCompletion } from '../clients/oai.mjs';
import { runCypherQuery } from '../clients/neo4j.mjs';
import { runPSQLQuery } from '../clients/psql.mjs';
import {
    getMwasHypothesisSystemPrompt,
    getBioProjectsSummarizationPrompt,
    getViromeSummarizationPrompt,
    getEcologySummarizationPrompt,
    getHostSummarizationPrompt,
    getSummaryPrompt,
    getGraphRAGMapSystemPrompt,
    getGraphRAGReduceSystemPrompt,
    getGraphRAGMwasSystemPrompt,
    allowGeneralKnowledgeSystemPrompt,
    noDataFoundMessage,
    getCaptionPrompt,
    getCaptionJudgementPrompt,
    getSRAFigureDescription,
    getEcologyFigureDescription,
    getHostFigureDescription,
    getViromeFigureDescription,
} from './prompts.mjs';
const INCLUDE_MWAS_IN_GRAPH_RAG = true;

const getBioprojectContext = async (bioprojects) => {
    const maxTotalLength = 10000;

    const bioprojectRecords = await runCypherQuery(
        `MATCH (n:BioProject)
        WHERE n.bioProject IN [${bioprojects.map((id) => `'${id}'`).join(', ')}]
        AND n:OpenVirome
        RETURN n
        ORDER BY size(n.description) DESC
        LIMIT 5000
        `,
    );

    // Try serializing full bioproject details first
    // fallback to only including titles if the total length exceeds the limit
    const serializeBioprojectRecord = (record, includeFullDetails) => {
        if (!record?.n) {
            return {};
        }
        const { bioProject: id, name, title, description } = record.n.properties;
        if (includeFullDetails) {
            return JSON.stringify({ id, name, title, description });
        }
        return JSON.stringify({ id, title });
    };

    const serializeAllBioprojects = (bioprojectRecords, includeFullDetails) => {
        let totalLength = 0;
        const serializedBioprojects = [];
        const serializedIterator = bioprojectRecords.map((record) =>
            serializeBioprojectRecord(record, includeFullDetails),
        );
        for (const serialized of serializedIterator) {
            const isExceedingMax = totalLength + serialized.length > maxTotalLength;
            if (isExceedingMax && includeFullDetails) {
                return undefined;
            }
            if (isExceedingMax) {
                break;
            }
            totalLength += serialized.length;
            serializedBioprojects.push(serialized);
        }
        return serializedBioprojects.join('\n');
    };

    let serializedBioprojects = serializeAllBioprojects(bioprojectRecords, false);
    if (serializedBioprojects === undefined) {
        serializedBioprojects = serializeAllBioprojects(bioprojectRecords, true);
    }
    return serializedBioprojects;
};

const getFilterQueryContext = (filters) => {
    const filterContext = filters.map((filter) => {
        const { filterType, filterValue } = filter;
        return `${filterType}: ${filterValue}`;
    });
    return filterContext.join('\n');
};

export const getBioprojectsSummarization = async (bioprojects, dataObj) => {
    const bioprojectContext = await getBioprojectContext(bioprojects);
    const context = getBioProjectsSummarizationPrompt();
    const model = chooseModel('bioproject');
    const role = 'system';
    const figureDescription = getSRAFigureDescription();
    let conversation = [
        {
            role: role,
            content: context,
        },
        {
            role: 'user',
            content: `Please provide a brief overview of the following bioprojects: \n ${bioprojectContext}`,
        },
    ];
    const result = await streamLLMCompletion(conversation, model);

    conversation.push({
        role: role,
        content: result.text,
    });

    const captionResults = await generateFigureCaptions(figureDescription, dataObj);
    const jsonString = captionResults.text.replace(/^```json\s*|\s*```$/g, '');
    const captions = JSON.parse(jsonString);
    const improvedCaption = captions["Improved Caption"];
    return { text: result.text, conversation: conversation, caption: improvedCaption };
};

export const getFigureSummarization = async (bioprojects, dataObj, dataType, figureDescription) => {
    let exceedTokenLimit = false;
    if(dataType === 'ecology'){
        dataObj = await runPSQLQuery(dataObj.text);
    }
    const model = chooseModel(dataType);
    const role = 'system';
    const bioprojectContext = await getBioprojectContext(bioprojects);
    const maxTotalLength = dataType === 'ecology' ? 90000 : 110000;
    const dataObjSummaries = [];
    let content = `Please provide a brief overview of the following ${dataType} data: \n ${JSON.stringify(dataObj, null, 2)} \n bioproject context: \n ${bioprojectContext}`
    if(JSON.stringify(dataObj, null, 2).length / 4 > maxTotalLength){
        const splitDataObj = split_data(dataObj, maxTotalLength);
        const summaryPrompt = getSummaryPrompt();
        for (const obj of splitDataObj){
            let summaryConversation = [
                {
                    role: role,
                    content: summaryPrompt,
                },
                {
                    role: 'user',
                    content: `Please provide a contextual summary of the following data: ${obj}`,
                },
            ];
            const summaryResult = await streamLLMCompletion(summaryConversation, model);
            dataObjSummaries.push({text: summaryResult.text});
        }
    }
    if(dataObjSummaries.length > 0){
        exceedTokenLimit = true;
        console.log("Data object too large, splitting into multiple summaries");
        content = `Please provide a brief overview of the following pre-summarized ${dataType} data: \n ${JSON.stringify(dataObjSummaries)} \n bioproject context: \n ${bioprojectContext}`
    }

    let prompt = ''
    switch (dataType) {
        case 'virome':
            prompt = getViromeSummarizationPrompt();
            figureDescription = getViromeFigureDescription();
            break;
        case 'ecology':
            prompt = getEcologySummarizationPrompt();
            figureDescription = getEcologyFigureDescription();
            break;
        case 'host':
            prompt = getHostSummarizationPrompt();
            figureDescription = getHostFigureDescription();
            break;
    }
    let conversation = [
        {
            role: role,
            content: prompt,
        },
        {
            role: 'user',
            content: content,
        },
    ];
    const result = await streamLLMCompletion(conversation, model);
    conversation.push({
        role: role,
        content: result.text,
    });
    if (exceedTokenLimit) {
        return { text: result.text, conversation: conversation, caption: 'Token Limit Exceeded' };
    }
    const captionResults = await generateFigureCaptions(figureDescription, dataObj);
    const jsonString = captionResults.text.replace(/^```json\s*|\s*```$/g, '');
    const captions = JSON.parse(jsonString);
    const improvedCaption = captions["Improved Caption"];
    return { text: result.text, conversation: conversation, caption: improvedCaption};
};

export const getMwasHypothesis = async (bioprojects, filters, selectedMetadata) => {
    const model = chooseModel('virome');
    const role = 'system';

    const filterQueryContext = getFilterQueryContext(filters);

    const contextBioprojects = bioprojects.filter((bioproject) => bioproject !== selectedMetadata['bioproject']);
    const backgroundBioprojectContext = await getBioprojectContext(contextBioprojects);
    const targetBioprojectContext = await getBioprojectContext([selectedMetadata['bioproject']]);

    const taxSpecies = Array.from(new Set(selectedMetadata['taxSpecies'])).join(', ');
    const changeInViralLoad = selectedMetadata['mean_rpm_true'] - selectedMetadata['mean_rpm_false'];

    const target_mwas_prompt = `
        - Query: ${filterQueryContext}
        - Virus Family: ${selectedMetadata['family']}
        - Virus Species: ${taxSpecies}
        - Significant metadata term: ${selectedMetadata['metadata_field']}
        - Significant metadata value: ${selectedMetadata['metadata_value']}
        - Mean change in viral reads per million (RPM) between positive and negative samples: ${changeInViralLoad}
        - P-value: ${selectedMetadata['p_value']}
        - Fold change: ${selectedMetadata['fold_change']}
    `;

    const instructionsPrompt = `
    ${getMwasHypothesisSystemPrompt(filterQueryContext, backgroundBioprojectContext)}

    ${allowGeneralKnowledgeSystemPrompt()}
    `;

    const documentsPrompt = `
    <documents>
    Target Metadata Association:
    ${target_mwas_prompt}

    Target BioProject:
    ${targetBioprojectContext}
    </documents>
    `;
    let conversation = [
        {
            role: role,
            content: instructionsPrompt,
        },
        {
            role: 'user',
            content: documentsPrompt,
        },
    ];
    const result = await streamLLMCompletion(conversation, model);

    conversation.push({
        role: role,
        content: result.text,
    });
    return { text: result.text, conversation: conversation };
};

export const getGraphRAGResults = async (message, conversation = []) => {
    // See https://github.com/microsoft/graphrag for map and reduce functionality
    let communitySummaries;
    try {
        communitySummaries = await import('./virome_community_summaries.json', {
            assert: { type: 'json' },
        });
        communitySummaries = communitySummaries.default;
    } catch (e) {
        console.error(e);
        return { text: noDataFoundMessage, conversation: conversation };
    }

    let mapModel = 'gpt4oMini';
    const reduceModel = 'gpt4o';
    const role = 'system';
    const promises = [];
    const maxTokenLimit = 128000;

    let index = 0;
    for (const community of communitySummaries) {
        let communityData = { ...community };
        delete communityData.mwas;
        delete communityData.max_biosafety;

        const communityPrompt = getGraphRAGMapSystemPrompt(JSON.stringify(communityData));
        const communityConversation = [
            ...conversation,
            {
                role: role,
                content: communityPrompt,
            },
            {
                role: 'user',
                content: message,
            },
        ];

        // Use model with high sensitivity content filters for high biosafety level communities
        const maxBioSafetyLevel = community.max_biosafety;
        if (maxBioSafetyLevel === 'RG4') {
            mapModel = 'gpt4oMini2';
        } else {
            mapModel = 'gpt4oMini';
        }

        const result = streamLLMCompletion(communityConversation, mapModel);
        promises.push(result);
        index++;
    }
    const results = await Promise.allSettled(promises);

    let parsedResults = results.map((result) => {
        try {
            return JSON.parse(result?.value?.text);
        } catch (e) {
            return {};
        }
    });

    parsedResults = parsedResults.filter((result) => result.points && result.points.length > 0);
    parsedResults = parsedResults.map((result) => {
        result.points = result.points.filter((point) => point.description && point.score && point.score >= 0);
        return result;
    });
    parsedResults = parsedResults.filter((result) => result.points && result.points.length > 0);
    parsedResults = parsedResults.sort((a, b) => b.score - a.score);

    if (parsedResults.length === 0) {
        return { text: noDataFoundMessage, conversation: conversation };
    }

    let content = JSON.stringify(parsedResults);
    if (content.length > maxTokenLimit) {
        console.log(`GraphRAG content length exceeds ${maxTokenLimit} characters. ${content.length}`);
        parsedResults = parsedResults.slice(0, 100);
        content = JSON.stringify(parsedResults);
        console.log(`GraphRAG content length after truncation: ${content.length}`);
    }

    const reducerConversation = [
        ...conversation,
        {
            role: role,
            content: getGraphRAGReduceSystemPrompt(JSON.stringify(parsedResults)),
        },
    ];
    const reducerResult = await streamLLMCompletion(reducerConversation, reduceModel);

    const displayedConversation = [
        {
            role: 'user',
            content: message,
        },
        ...reducerConversation,
        {
            role: role,
            content: reducerResult.text,
        },
    ];

    if (INCLUDE_MWAS_IN_GRAPH_RAG) {
        const mwasResponse = await getGraphRAGMWASResults(message, communitySummaries, reducerResult);
        if (mwasResponse.text) {
            reducerResult.text = `${reducerResult.text}\n\n---\n\n### Supporting MWAS Results\n${mwasResponse.text}`;
            displayedConversation.push(...mwasResponse.conversation);
        }
    }

    return { text: reducerResult.text, conversation: displayedConversation };
};

// Additional GraphRAG prompt to get relevant MWAS results for GraphRAG output
const getGraphRAGMWASResults = async (message, communitySummaries, reducerResult) => {
    const model = 'gpt4o';
    const temperature = 1;
    const role = 'system';

    const referencedMWAS = [];
    const communityIds = reducerResult.text.match(/{{community: (\d+)}}/g);
    if (!communityIds) {
        return [];
    }
    communityIds.forEach((id) => {
        const communityId = id.match(/(\d+)/)[0];
        const community = communitySummaries.find((summary) => summary.community === parseInt(communityId));
        if (community && community.mwas) {
            referencedMWAS.push(community.mwas);
        }
    });

    if (referencedMWAS.length === 0) {
        return '';
    }
    const instructionsPrompt = `
    ${getGraphRAGMwasSystemPrompt(message, reducerResult.text)}

    ${allowGeneralKnowledgeSystemPrompt()}
    `;

    const documentsPrompt = `
    <documents>
    ---User query---

    ${message}

    ---Metadata Association---

    ${JSON.stringify(referencedMWAS)}

    </documents>
    `;
    let mwasConversation = [
        {
            role: role,
            content: instructionsPrompt,
        },
        {
            role: 'user',
            content: documentsPrompt,
        },
    ];
    const mwasResult = await streamLLMCompletion(mwasConversation, model, temperature);

    mwasConversation.push({
        role: role,
        content: mwasResult.text,
    });

    if (mwasResult.text.includes('###')) {
        return { text: '', conversation: mwasConversation };
    }
    return { text: mwasResult.text, conversation: mwasConversation };
};

const chooseModel = (dataType) => {
    switch (dataType) {
        case 'bioproject':
            return 'gpt4o';
        case 'virome':
            return 'gpt4o';
        // case 'mwas':
        //     return 'o1';
        case 'ecology':
            return 'gpt4o';
        case 'host':
            return 'gpt4o';
        case 'caption':
            return 'gpt4o';
        default:
            return 'gpt4o';
    }
};

const split_data = (data, maxTotalLength) => {
    let batches  = [];
    let currentBatch = [];
    let currentSize = 0;

    for(const entry of data){
        if (currentSize + (JSON.stringify(entry).length / 4) > maxTotalLength){
            batches.push(currentBatch);
            currentBatch = [];
            currentSize = 0;
        }
        currentBatch.push(entry);
        currentSize += JSON.stringify(entry).length / 4;
    }
    if (currentBatch.length > 0){
        batches.push(currentBatch);
    };
    return batches;
};

export const generateFigureCaptions = async (figureDescription, figureData) => {
    const prompt = getCaptionPrompt(figureDescription);

    const model = chooseModel('caption');
    const role = 'system';
    let conversation = [
        {
            role: role,
            content: prompt,
        },
        {
            role: 'user',
            content: JSON.stringify(figureData),
        },
    ];
    const captionResults = await streamLLMCompletion(conversation, model);
    const jsonString = captionResults.text.replace(/^```json\s*|\s*```$/g, '');
    const captions = JSON.parse(jsonString);
    const judgePrompt = getCaptionJudgementPrompt(JSON.stringify(figureData), JSON.stringify(captions, null, 2));
    let judgeConversation = [
        {
            role: role,
            content: judgePrompt,
        },
    ];
    const result = await streamLLMCompletion(judgeConversation, model);
    return { text: result.text, conversation: conversation };
}