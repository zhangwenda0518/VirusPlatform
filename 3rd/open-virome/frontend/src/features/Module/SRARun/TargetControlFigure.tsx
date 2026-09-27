import React, { useState } from 'react';
import { moduleConfig } from '../../Module/constants.ts';
import { shouldDisableFigureView, isSummaryView, isSimpleLayout } from '../../../common/utils/plotHelpers.ts';
import { getTargetControlPlotData } from './plotHelpers.ts';
import { useGetCountsQuery } from '../../../api/client.ts';
import { formatNumber } from '../../../common/utils/textFormatting.ts';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Skeleton from '@mui/material/Skeleton';
import BarPlot from '../../../common/BarPlot.tsx';
import PolarBarPlot from '../../../common/PolarBarPlot.tsx';
import RadioButtonsGroup from '../../../common/RadioButtonsGroup.tsx';

const TargetControlFigure = ({ identifiers, moduleKey, figureType, sectionLayout, palmprintOnly }) => {
    const [activeCountKey, setActiveCountKey] = useState('count');
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

    const sectionStyle = {
        mt: 2,
        mb: 2,
    };

    const countKeys = {
        count: 'Run Count (n)',
        gbp: 'Gigabasepairs (Gbp)',
        percent: 'Percent of set (%)',
    };

    const getTotalRuns = (seriesName) => {
        if (!controlCountData || !targetCountData) {
            return;
        }
        let counts;
        if (seriesName === 'Control' || isSummaryView(identifiers)) {
            counts = controlCountData.reduce((acc, curr) => acc + parseInt(curr.count), 0);
        } else {
            counts = targetCountData.reduce((acc, curr) => acc + parseInt(curr.count), 0);
        }
        return formatNumber(counts);
    };

    const renderFigure = (seriesName) => {
        const maxRows = figureType === 'polar' ? 4 : isSimpleLayout(sectionLayout) ? 9 : undefined;
        const plotData = getTargetControlPlotData(targetCountData, controlCountData, activeCountKey, maxRows);
        let totalRuns = getTotalRuns(seriesName);
        const countLabel = activeCountKey === 'gbp' ? ' (Gbp)' : activeCountKey === 'percent' ? ' (%)' : '';
        const filteredPlotData = {
            ...plotData,
            title: {
                text: `${seriesName} set${countLabel}${totalRuns ? ' (n = ' + totalRuns + ')' : ''}`,
                textStyle: {
                    color: 'white',
                    fontSize: 14,
                    fontWeight: 'normal',
                    fontStyle: 'italic',
                },
                left: 0,
                top: 5,
            },
            legend: {
                show: false,
                selected: {
                    Target: seriesName === 'Target',
                    Control: seriesName === 'Control',
                },
                textStyle: {
                    color: 'white',
                },
            },
        };
        if (figureType === 'polar') {
            return (
                <Box sx={{ minWidth: 400 }}>
                    <PolarBarPlot plotData={filteredPlotData} module="SRA"/>
                </Box>
            );
        }
        if (figureType === 'bar') {
            return (
                <Box sx={{ minWidth: 400 }}>
                    <BarPlot plotData={filteredPlotData} module="SRA"/>
                </Box>
            );
        }
    };

    const shouldRenderPlaceholder = (isError, isFetching, data) => {
        return isError || isFetching || !data;
    };

    const renderPlaceholder = () => {
        if (targetCountError || controlCountError) {
            return (
                <Box sx={{ flex: 1 }}>
                    <Typography variant='h6' sx={{ ...sectionStyle }}>
                        Error loading data
                    </Typography>
                </Box>
            );
        }
        if (
            targetCountData &&
            targetCountData.length === 0 &&
            !targetCountIsFetching &&
            controlCountData &&
            controlCountData.length === 0 &&
            !controlCountIsFetching
        ) {
            return (
                <Box sx={{ flex: 1, height: 100 }}>
                    <Typography variant='h6' sx={{ ...sectionStyle }}>
                        {`No ${moduleConfig[moduleKey].title.toLowerCase()} data available`}
                    </Typography>
                </Box>
            );
        }
        return (
            <Box sx={{ flex: 1, width: 400 }}>
                <Skeleton width='90%' height={300} />
            </Box>
        );
    };

    const onCountChange = (event) => {
        setActiveCountKey(event.target.value);
    };

    return (
        <Box sx={{ flex: 1 }}>
            <Box
                sx={{
                    flex: 1,
                    width: '80vw',
                    maxWidth: 1500,
                    display: 'flex',
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    mt: 0,
                }}
            >
                {shouldRenderPlaceholder(controlCountError, controlCountIsFetching, controlCountData) ? (
                    renderPlaceholder()
                ) : (
                    <Box sx={{ flex: 1, width: '100%' }}>{renderFigure('Control')}</Box>
                )}
                {(isSummaryView(identifiers) &&
                    shouldRenderPlaceholder(controlCountError, controlCountIsFetching, controlCountData)) ||
                (!isSummaryView(identifiers) &&
                    shouldRenderPlaceholder(targetCountError, targetCountIsFetching, targetCountData)) ? (
                    renderPlaceholder()
                ) : (
                    <Box sx={{ flex: 1, width: '100%' }}>{renderFigure('Target')}</Box>
                )}
                {isSummaryView(identifiers) || isSimpleLayout(sectionLayout) ? null : (
                    <RadioButtonsGroup items={countKeys} selected={activeCountKey} onChange={onCountChange} />
                )}
            </Box>
        </Box>
    );
};

export default TargetControlFigure;
