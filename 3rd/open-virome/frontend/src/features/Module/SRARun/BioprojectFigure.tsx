import React from 'react';
import { shouldDisableFigureView, isSummaryView } from '../../../common/utils/plotHelpers.ts';
import {
    getBioprojectSizePlotData,
    getBioprojectTargetPercentagePlotData,
    getBioprojectSizeVsPercentagePlotData,
} from './plotHelpers.ts';
import { useGetCountsQuery } from '../../../api/client.ts';
import { moduleConfig } from '../../Module/constants.ts';

import HistogramPlot from '../../../common/HistogramPlot.tsx';
import ScatterPlot from '../../../common/ScatterPlot.tsx';
import Skeleton from '@mui/material/Skeleton';
import Box from '@mui/material/Box';

const BioprojectFigure = ({ identifiers, palmprintOnly }) => {
    /* remove? */
    const {
        data: targetCountData = [],
        error: targetCountError,
        isFetching: targetCountIsFetching,
    } = useGetCountsQuery(
        {
            idColumn: 'run',
            ids: identifiers ? identifiers['run'].single : [],
            idRanges: identifiers ? identifiers['run'].range : [],
            groupBy: moduleConfig['bioproject'].groupByKey,
            pageEnd: isSummaryView(identifiers) ? 100 : undefined,
            palmprintOnly,
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
            groupBy: moduleConfig['bioproject'].groupByKey,
            pageEnd: isSummaryView(identifiers) ? 1000 : undefined,
            palmprintOnly,
        },
        {
            skip: shouldDisableFigureView(identifiers),
        },
    );

    const shouldRenderPlaceholder = (isError, isFetching, data) => {
        return isError || isFetching || !data;
    };

    const renderTotalSizePlot = () => {
        return (
            <Box sx={{ flex: 1, width: 350 }}>
                <HistogramPlot plotData={getBioprojectSizePlotData(controlCountData)} module="SRA"/>
            </Box>
        );
    };

    const renderTargetPercentagePlot = () => {
        return (
            <Box sx={{ flex: 1, width: 350 }}>
                <HistogramPlot plotData={getBioprojectTargetPercentagePlotData(controlCountData, targetCountData)} module="SRA"/>
            </Box>
        );
    };

    const handleScatterPlotEvents = {
        click: (e) => {
            const bioProjectId = e.value ? e.value[2] : null;
            if (bioProjectId) window.open(`https://www.ncbi.nlm.nih.gov/bioproject/${bioProjectId}`, '_blank');
        },
    };

    const renderSizeVsPercentagePlot = () => {
        return (
            <Box sx={{ flex: 1, width: '100%', height: '100%' }}>
                <ScatterPlot
                    plotData={getBioprojectSizeVsPercentagePlotData(controlCountData, targetCountData)}
                    styles={{ height: 600 }}
                    onEvents={handleScatterPlotEvents}
                    module="SRA"
                />
            </Box>
        );
    };

    return (
        <Box sx={{ flex: 1, width: '100%' }}>
            <Box
                sx={{
                    flex: 1,
                    width: '100%',
                    display: 'flex',
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    minWidth: 1000,
                }}
            >
                <Box
                    sx={{
                        flex: 1,
                        width: '100%',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                    }}
                >
                    {shouldRenderPlaceholder(controlCountError, controlCountIsFetching, controlCountData) ? (
                        <Skeleton variant='rectangular' width={300} height={265} sx={{ mb: 8 }} />
                    ) : (
                        renderTotalSizePlot()
                    )}
                    {shouldRenderPlaceholder(controlCountError, controlCountIsFetching, controlCountData) ||
                    shouldRenderPlaceholder(targetCountError, targetCountIsFetching, targetCountData) ? (
                        <Skeleton variant='rectangular' width={300} height={265} />
                    ) : (
                        renderTargetPercentagePlot()
                    )}
                </Box>

                <Box sx={{ flex: 1.5 }}>
                    {shouldRenderPlaceholder(controlCountError, controlCountIsFetching, controlCountData) ||
                    shouldRenderPlaceholder(targetCountError, targetCountIsFetching, targetCountData) ? (
                        <Skeleton variant='rectangular' width={600} height={600} />
                    ) : (
                        renderSizeVsPercentagePlot()
                    )}
                </Box>
            </Box>
        </Box>
    );
};

export default BioprojectFigure;
