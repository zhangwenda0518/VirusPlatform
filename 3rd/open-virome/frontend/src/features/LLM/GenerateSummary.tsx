import React from 'react';
import { useLazyGetSummaryTextQuery } from '../../api/client.ts';
import { formatLLMGeneratedText } from './textFormatting.tsx';

import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import CheckIcon from '@mui/icons-material/Check';
import { useTheme } from '@mui/material/styles';
import GenerateButton from './GenerateButton.tsx';

import { useSelector } from 'react-redux';
import { selectAllFilters } from '../Query/slice.ts';
import { useGetResultQuery, useGetCountsQuery } from '../../api/client.ts';
import { moduleConfig } from '../Module/constants.ts';
import { isSummaryView } from '../../common/utils/plotHelpers.ts';
import { handleIdKeyIrregularities } from '../../common/utils/queryHelpers.ts';
import { useState } from 'react';
import { shouldDisableFigureView, isSimpleLayout } from '../../common/utils/plotHelpers.ts';

const GenerateSummary = ({ identifiers, dataType, palmprintOnly }) => {
     const theme = useTheme();
     const resultBg = theme.palette.mode === 'dark' ? '#484848' : '#f5f5f5';
     // figure data
     const sraFigureData = (identifiers) => {
        const [activeCountKey, setActiveCountKey] = useState('count');
        const moduleKey = 'label';
        const {
            data: targetCountData,
            error: targetCountError,
            isFetching: targetCountIsFetching,
        } = useGetCountsQuery(
            {
                idColumn: 'run',
                ids: identifiers ? identifiers['run'].single : [],
                idRanges: identifiers ? identifiers['run'].range : [],
                groupBy: moduleConfig[moduleKey].groupByKey,
                palmprintOnly,
                tableDescription: {type: 'bar', title: 'Run Count Target Set (n)'},
            },
            {
                skip: shouldDisableFigureView(identifiers) || isSummaryView(identifiers),
            },
        );
        const {
            data: controlCountData,
            error: controlCountError,
            isFetching: controlCountIsFetching,
        } = useGetCountsQuery(
            {
                idColumn: 'bioproject',
                ids: identifiers ? identifiers['bioproject'].single : [],
                idRanges: identifiers ? identifiers['bioproject'].range : [],
                groupBy: moduleConfig[moduleKey].groupByKey,
                pageStart: isSummaryView(identifiers) ? 0 : undefined,
                pageEnd: isSummaryView(identifiers) ? (moduleKey === 'label' ? 10 : 4) : undefined,
                sortBy: isSummaryView(identifiers) ? activeCountKey : undefined,
                palmprintOnly,
            },
            {
                skip: shouldDisableFigureView(identifiers),
            },
        );
        return {
            targetCountData,
            controlCountData
        };
    }
    
     const viromeFigureData = (identifiers) => {
        const allFilters = useSelector(selectAllFilters);
        const [activeModule, setActiveModule] = useState('species');
    
        const {
            data: resultData,
            error: resultError,
            isFetching: resultIsFetching,
        } = useGetResultQuery(
            {
                idColumn: moduleConfig[activeModule].resultsIdColumn,
                ids: identifiers
                    ? identifiers[handleIdKeyIrregularities(moduleConfig[activeModule].resultsIdColumn)].single
                    : [],
                idRanges: identifiers
                    ? identifiers[handleIdKeyIrregularities(moduleConfig[activeModule].resultsIdColumn)].range
                    : [],
                table: moduleConfig[activeModule].resultsTable,
                pageStart: 0,
                pageEnd: isSummaryView(identifiers) ? 100 : undefined,
                sortBy: isSummaryView(identifiers) ? 'gb_pid' : undefined,
            },
            {
                skip: !identifiers,
            },
        );
    
        const getFilteredResultData = () => {
            // If virome filters are applied, we only want to plot data that matches the filters
            // (i.e. exclude all other viruses that co-occur in the matching runs)
            if (allFilters.length === 0 || !resultData) {
                return resultData;
            }
    
            const familyFilters = allFilters.filter((filter) => filter.filterType === 'family');
            const speciesFilters = allFilters.filter((filter) => filter.filterType === 'species');
            const sotuFilters = allFilters.filter((filter) => filter.filterType === 'sotu');
    
            let filteredData = resultData;
            if (familyFilters.length > 0) {
                filteredData = filteredData.filter((row) => {
                    return familyFilters.some((filter) => row['tax_family'] === filter.filterValue);
                });
            }
    
            if (speciesFilters.length > 0) {
                filteredData = filteredData.filter((row) => {
                    return speciesFilters.some((filter) => row['tax_species'] === filter.filterValue);
                });
            }
    
            if (sotuFilters.length > 0) {
                filteredData = filteredData.filter((row) => {
                    return sotuFilters.some((filter) => row['sotu'] === filter.filterValue);
                });
            }
            return filteredData;
        };
        return getFilteredResultData();
    }

    const hostFigureData = (identifiers, sectionLayout, palmprintOnly) => {
        const {
            data: tissueCountData,
            error: hostCountError,
            isFetching: tissueCountIsFetching,
        } = useGetCountsQuery(
            {
                idColumn: moduleConfig['tissue'].resultsIdColumn,
                ids: identifiers ? identifiers[moduleConfig['tissue'].resultsIdColumn].single : [],
                idRanges: identifiers ? identifiers[moduleConfig['tissue'].resultsIdColumn].range : [],
                groupBy: moduleConfig['tissue'].groupByKey,
                table: moduleConfig['tissue'].resultsTable,
                palmprintOnly,
            },
            {
                skip: shouldDisableFigureView(identifiers),
            },
        );
    
        const {
            data: diseaseCountData,
            error: diseaseCountError,
            isFetching: diseaseCountIsFetching,
        } = useGetCountsQuery(
            {
                idColumn: moduleConfig['disease'].resultsIdColumn,
                ids: identifiers ? identifiers[moduleConfig['disease'].resultsIdColumn].single : [],
                idRanges: identifiers ? identifiers[moduleConfig['disease'].resultsIdColumn].range : [],
                groupBy: moduleConfig['disease'].groupByKey,
                table: moduleConfig['disease'].resultsTable,
                palmprintOnly,
            },
            {
                skip: shouldDisableFigureView(identifiers),
            },
        );
    
        const {
            data: organismCountData,
            error: organismCountError,
            isFetching: organismCountIsFetching,
        } = useGetCountsQuery(
            {
                idColumn: moduleConfig['statOrganism'].resultsIdColumn,
                ids: identifiers ? identifiers[moduleConfig['statOrganism'].resultsIdColumn].single : [],
                idRanges: identifiers ? identifiers[moduleConfig['statOrganism'].resultsIdColumn].range : [],
                groupBy: moduleConfig['statOrganism'].groupByKey,
                table: moduleConfig['statOrganism'].resultsTable,
                palmprintOnly,
            },
            {
                skip: shouldDisableFigureView(identifiers) || isSimpleLayout(sectionLayout),
            },
        );
    
        const {
            data: sexCountData,
            error: sexCountError,
            isFetching: sexCountIsFetching,
        } = useGetCountsQuery(
            {
                idColumn: moduleConfig['sex'].resultsIdColumn,
                ids: identifiers ? identifiers[moduleConfig['sex'].resultsIdColumn].single : [],
                idRanges: identifiers ? identifiers[moduleConfig['sex'].resultsIdColumn].range : [],
                groupBy: moduleConfig['sex'].groupByKey,
                table: moduleConfig['sex'].resultsTable,
                palmprintOnly,
            },
            {
                skip: shouldDisableFigureView(identifiers) || isSimpleLayout(sectionLayout),
            },
        );
        return {
            tissueCountData,
            diseaseCountData,
            organismCountData,
            sexCountData
        };
    }

    const getIdClauses = (ids = [], idRanges = []) => {
        const clauses = [];
        const idColumn = 'accession';
        if (ids.length > 0) {
            clauses.push(`${idColumn} IN (${ids.map((id) => `'${id}'`).join(',')})`);
        }
        if (idRanges.length > 0) {
            idRanges.forEach((range) => {
                const [start, end] = range;
                clauses.push(`${idColumn} BETWEEN '${start}' AND '${end}'`);
            });
        }
        return clauses;
    };

    const getWhereClause = (palmprintOnly, identifiers) => {
        const identifierClauses = getIdClauses(identifiers?.biosample?.single, identifiers?.biosample?.range);
        const conditions = [];
        if (palmprintOnly) {
            conditions.push('palm_virome = true');
        }
        if (identifierClauses.length > 0) {
            conditions.push(`(${identifierClauses.join(' OR ')})`);
        }
        return conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    };

    const ecologyFigureData = (identifiers) => {
        const SELECT: any = {
            text: `SELECT accession, attribute_name, attribute_value, ST_Y(lat_lon) as lat, ST_X(lat_lon) as lon, elevation, gm4326_id, gp4326_wwf_tew_id
            FROM bgl_gm4326_gp4326
            ${getWhereClause(palmprintOnly, identifiers)}
            LIMIT 65536;`,
        };
        return SELECT;
    }

    var dataObj = {};
    switch (dataType) {
        case 'sra':
            dataType = 'bioproject';
            dataObj = sraFigureData(identifiers);
            break;
        case 'palmdb':
            dataType = 'virome';
            dataObj = viromeFigureData(identifiers);
            break;
        case 'ecology': // stays the same
            dataType = 'ecology';
            // dataObj = ecologyFigureData(identifiers);
            dataObj = ecologyFigureData(identifiers);
            break;
        case 'host':
            dataType = 'host';
            dataObj = hostFigureData(identifiers, "simple", palmprintOnly);
            break;
        default:
            dataType = ''; // throw err
    }
    const [getSummaryText, { data: summaryData, isFetching: isFetchingSummary, error: errorSummary }] =
        useLazyGetSummaryTextQuery();

    const [llmClicked, setLlmClicked] = useState(false);
    const [copied, setCopied] = useState(false);

    const onButtonClick = async () => {
        if (isFetchingSummary || llmClicked) {
            return;
        }
        setLlmClicked(true);
        try {
            await getSummaryText(
                {
                    idColumn: dataType,
                    ids: identifiers ? identifiers['bioproject'].single : [],
                    dataObj: dataObj,
                },
                true,
            ).unwrap();
        } finally {
            setLlmClicked(false);
        }
    };

    const renderPlaceholder = () => {
        if (isFetchingSummary) {
            return <Skeleton variant='text' width={'100%'} height={60} />;
        }
        return null;
    };

    const summaryTextIsNonEmpty = () => summaryData && summaryData?.text?.length > 0;

    const handleCopy = () => {
        const text = summaryData?.text || '';
        const caption = summaryData?.caption || '';
        const fullText = text + '\n\nFigure Caption: ' + caption;
        navigator.clipboard.writeText(fullText).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    };

    return (
        <Box
        sx={{
            display: 'flex',
            flexDirection: 'row',
            justifyContent: 'flex-start',
            alignItems: 'center',
        }}
        >
            <GenerateButton onButtonClick={onButtonClick} title={'Generate Summary'} />
            {summaryTextIsNonEmpty() && (
                <Tooltip title={copied ? 'Copied!' : 'Copy to clipboard'}>
                    <IconButton onClick={handleCopy} size="small" sx={{ ml: 1 }}>
                        {copied ? <CheckIcon fontSize="small" color="success" /> : <ContentCopyIcon fontSize="small" />}
                    </IconButton>
                </Tooltip>
            )}
            <Box
                sx={{
                    display: 'flex',
                    width: '100%',
                    justifyContent: 'space-between',
                    justifyItems: 'flex-start',
                    height: summaryTextIsNonEmpty() || isFetchingSummary ? '100%' : 0,
                    mb: summaryTextIsNonEmpty() || isFetchingSummary ? 4 : 0,
                }}
            >
                <Box
                    sx={{
                        flex: 1,
                        minWidth: '90%',
                        maxHeight: 300,
                    }}
                >
                    {renderPlaceholder()}
                    {!isFetchingSummary && summaryTextIsNonEmpty() ? (
                        <Box
                            sx={{
                                backgroundColor: resultBg,
                                p: 2,
                                borderRadius: 2,
                                overflow: 'auto',
                                maxHeight: 300,
                                scrollbarWidth: 'none',
                                '&::-webkit-scrollbar': {
                                    display: 'none',
                                },
                            }}
                        >
                            <Typography variant='body' sx={{ mt: 2, mb: 4, whiteSpace: 'pre-wrap' }}>
                                {formatLLMGeneratedText(summaryData?.text, summaryData?.conversation)}
                                <br />
                                {formatLLMGeneratedText("Figure Caption: " + summaryData?.caption, summaryData?.conversation)}
                            </Typography>
                        </Box>
                    ) : null}
                </Box>
            </Box>
        </Box>
    );
};

export default GenerateSummary;
