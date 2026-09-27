import React from 'react';
import { useGetCountsQuery } from '../../../api/client.ts';
import { shouldDisableFigureView, isSimpleLayout, chooseFigure } from '../../../common/utils/plotHelpers.ts';
import { moduleConfig } from '../../Module/constants.ts';
import { getBarPlotData } from './plotHelpers.ts';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import BarPlot from '../../../common/BarPlot.tsx';
import PolarBarPlot from '../../../common/PolarBarPlot.tsx';
import Skeleton from '@mui/material/Skeleton';

const HostLayout = ({ identifiers, sectionLayout, palmprintOnly }) => {
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

    const getEmptyResultsMessage = () => {
        return (
            <Typography variant='body' sx={{ ml: 4 }}>
                {`No data available`}
            </Typography>
        );
    };



    const getTissuePlot = () => {
        if (tissueCountIsFetching) {
            return <Skeleton variant='rectangular' height={400} width={'80%'} />;
        }
        if (tissueCountData && tissueCountData.length > 0) {
            const maxRows = isSimpleLayout(sectionLayout) ? 9 : undefined;
            let imagePath = "";
            if(tissueCountData){
                imagePath = chooseFigure(tissueCountData.at(-1));
            }
            return <BarPlot plotData={getBarPlotData(tissueCountData, maxRows, imagePath)} imagePath={imagePath} title="Tissue" module="Host"/>;
        }
        return getEmptyResultsMessage();
    };

    const getDiseasePlot = () => {
        if (diseaseCountIsFetching) {
            return <Skeleton variant='rectangular' height={400} width={'80%'} />;
        }

        if (diseaseCountData && diseaseCountData.length > 0) {
            const maxRows = isSimpleLayout(sectionLayout) ? 9 : undefined;
            return <BarPlot plotData={getBarPlotData(diseaseCountData, maxRows)} title="Disease" module="Host"/>;
        }
        return getEmptyResultsMessage();
    };

    const getOrganismPlot = () => {
        if (organismCountIsFetching) {
            return <Skeleton variant='rectangular' height={400} width={'80%'} />;
        }

        if (organismCountData && organismCountData.length > 0) {
            const maxRows = isSimpleLayout(sectionLayout) ? 9 : undefined;
            return <BarPlot plotData={getBarPlotData(organismCountData, maxRows)} title="STAT Organism" module="Host"/>;
        }
        return getEmptyResultsMessage();
    };

    const getSexPlot = () => {
        if (sexCountIsFetching) {
            return <Skeleton variant='rectangular' height={400} width={'80%'} />;
        }

        if (sexCountData && sexCountData.length > 0) {
            const maxRows = isSimpleLayout(sectionLayout) ? 9 : undefined;
            return <PolarBarPlot plotData={getBarPlotData(sexCountData, maxRows)} title="Sex" module="Host"/>;
        }
        return getEmptyResultsMessage();
    };

    return (
        <Box sx={{ display: 'flex', flexDirection: 'column', width: '100%', width: '80vw', maxWidth: 1500 }}>
            <Box sx={{ display: 'flex', flexDirection: 'row', width: '100%', mb: 2, gap: 2 }}>
                <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', width: '50%' }}>
                    {getTissuePlot()}
                </Box>
                <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', width: '50%' }}>
                    {getDiseasePlot()}
                </Box>
            </Box>
            {isSimpleLayout(sectionLayout) ? null : (
            <>
                <Box sx={{ display: 'flex', flexDirection: 'row', width: '100%', mb: 2, gap: 2 }}>
                    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', width: '50%' }}>
                        {getOrganismPlot()}
                    </Box>
                    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', width: '50%' }}>
                        {getSexPlot()}
                    </Box>
                </Box>
            </>
            )}
        </Box>
    );
};

export default HostLayout;
