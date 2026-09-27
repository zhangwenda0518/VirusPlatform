import React from 'react';
import { useSelector } from 'react-redux';
import { selectAllFilters } from './slice.ts';
import { selectPalmprintOnly } from '../../app/slice.ts';
import { useGetIdentifiersQuery, useGetCountsQuery } from '../../api/client.ts';
import { getFilterQuery, handleIdKeyIrregularities } from '../../common/utils/queryHelpers.ts';
import { formatNumber } from '../../common/utils/textFormatting.ts';
import { moduleConfig } from '../Module/constants.ts';
import { isSummaryView } from '../../common/utils/plotHelpers.ts';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Skeleton from '@mui/material/Skeleton';

const QuerySummaryText = () => {
    const filters = useSelector(selectAllFilters);
    const palmprintOnly = useSelector(selectPalmprintOnly);

    const {
        data: identifiersData,
        error: identifiersError,
        isFetching: identifiersFetching,
    } = useGetIdentifiersQuery({
        filters: getFilterQuery({ filters }),
        palmprintOnly,
    });

    const {
        data: totalVirusContigCountData,
        error: totalVirusContigCountError,
        isFetching: totalVirusContigCountIsFetching,
    } = useGetCountsQuery(
        {
            idColumn: moduleConfig['sotu'].resultsIdColumn,
            table: moduleConfig['sotu'].resultsTable,
            ids: identifiersData
                ? identifiersData[handleIdKeyIrregularities(moduleConfig['sotu'].resultsIdColumn)].single
                : [],
            idRanges: identifiersData
                ? identifiersData[handleIdKeyIrregularities(moduleConfig['sotu'].resultsIdColumn)].range
                : [],
            palmprintOnly,
        },
        {
            skip: !identifiersData,
        },
    );

    const {
        data: sotuCountData,
        error: sotuCountError,
        isFetching: sotuCountIsFetching,
    } = useGetCountsQuery(
        {
            filters: getFilterQuery({ filters }),
            groupBy: moduleConfig['sotu'].groupByKey,
            sortByColumn: 'count',
            sortByDirection: 'desc',
            pageStart: 0,
            palmprintOnly,
        },
        {
            skip: !identifiersData || isSummaryView(identifiersData),
        },
    );

    const getQuerySummaryText = () => {
        if (!identifiersData || identifiersFetching) {
            return <Skeleton variant='text' width={400} />;
        }

        if (identifiersError) {
            return (
                <Typography paragraph variant='body1'>
                    {`Error fetching identifiers`}
                </Typography>
            );
        }

        if (isSummaryView(identifiersData)) {
            return '';
        }

        /* Current Query Selection Stats */
        /* TODO: make returned counts monospace font */
        return (
            <Typography paragraph variant='body1'>
                {`Query
                    | BioProjects: ${formatNumber(identifiersData?.bioproject?.totalCount)}
                    | Runs: ${formatNumber(identifiersData?.run?.totalCount)}
                          `}
                {sotuCountData && !sotuCountIsFetching && !sotuCountError
                    ? `
                          | Viruses (sOTU): ${sotuCountData?.length ? formatNumber(sotuCountData?.length) : 0}`
                    : ''}
                {totalVirusContigCountData && !totalVirusContigCountIsFetching && !totalVirusContigCountError
                    ? `
                          | Contigs: ${totalVirusContigCountData?.length ? formatNumber(totalVirusContigCountData[0]?.count) : 0}`
                    : ''}
            </Typography>
        );
    };

    return <Box sx={{ mt: 4, mb: 2 }}>{getQuerySummaryText()}</Box>;
};

export default QuerySummaryText;
