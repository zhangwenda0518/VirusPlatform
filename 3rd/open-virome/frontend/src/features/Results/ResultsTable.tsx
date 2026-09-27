import React, { useState } from 'react';
import { moduleConfig, sectionConfig } from '../Module/constants.ts';
import { handleIdKeyIrregularities } from '../../common/utils/queryHelpers.ts';

import PagedTable from '../../common/PagedTable.tsx';
import { useGetResultQuery, useGetCountsQuery, useLazyGetResultQuery } from '../../api/client.ts';
import { exportToCSV } from '../../common/utils/exportHelpers.ts';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Skeleton from '@mui/material/Skeleton';

const ResultModuleMap: Record<string, string> = {};
for (const [sectionKey, section] of Object.entries(sectionConfig)) {
    for (const m of section.modules) {
        ResultModuleMap[m] = sectionKey === 'palmdb' ? 'Virome' : sectionKey.charAt(0).toUpperCase() + sectionKey.slice(1);
    }
}

const ResultsTable = ({ identifiers, moduleKey, shouldSkipFetching }) => {
    const [page, setPage] = useState(0);
    const moduleName = ResultModuleMap[moduleKey] || 'Table';

    const {
        data: resultData,
        error: resultError,
        isFetching: resultIsFetching,
    } = useGetResultQuery(
        {
            idColumn: moduleConfig[moduleKey].resultsIdColumn,
            ids: identifiers
                ? identifiers[handleIdKeyIrregularities(moduleConfig[moduleKey].resultsIdColumn)].single
                : [],
            idRanges: identifiers
                ? identifiers[handleIdKeyIrregularities(moduleConfig[moduleKey].resultsIdColumn)].range
                : [],
            table: moduleConfig[moduleKey].resultsTable,
            sortByColumn: moduleConfig[moduleKey].resultsIdColumn,
            sortByDirection: 'asc',
            pageStart: page * 10,
            pageEnd: (page + 1) * 10,
        },
        {
            skip: shouldSkipFetching,
        },
    );

    const {
        data: totalCount,
        error: totalCountError,
        isFetching: totalCountIsFetching,
    } = useGetCountsQuery(
        {
            idColumn: moduleConfig[moduleKey].resultsIdColumn,
            table: moduleConfig[moduleKey].resultsTable,
            ids: identifiers
                ? identifiers[handleIdKeyIrregularities(moduleConfig[moduleKey].resultsIdColumn)].single
                : [],
            idRanges: identifiers
                ? identifiers[handleIdKeyIrregularities(moduleConfig[moduleKey].resultsIdColumn)].range
                : [],
        },
        {
            skip: shouldSkipFetching,
        },
    );

    const [triggerFetchAll] = useLazyGetResultQuery();

    const handleExportAll = async () => {
        const idColumn = moduleConfig[moduleKey].resultsIdColumn;
        const totalRows = totalCount?.length ? totalCount[0]?.count : 0;
        if (!totalRows || shouldSkipFetching) return;

        const allData = await triggerFetchAll({
            idColumn,
            ids: identifiers
                ? identifiers[handleIdKeyIrregularities(idColumn)].single
                : [],
            idRanges: identifiers
                ? identifiers[handleIdKeyIrregularities(idColumn)].range
                : [],
            table: moduleConfig[moduleKey].resultsTable,
            sortByColumn: idColumn,
            sortByDirection: 'asc',
            pageStart: 0,
            pageEnd: totalRows,
        }).unwrap();

        if (allData?.length) {
            const exportHeaders = Object.keys(allData[0]);
            exportToCSV(allData, exportHeaders, `open-virome-${moduleName}-PagedTable.csv`);
        }
    };

    const onPageChange = (event: unknown, newPage: number) => {
        setPage(newPage);
    };

    const getTableHeaders = (data) => {
        if (data && data.length) {
            return Object.keys(data[0]);
        }
        return [];
    };

    const shouldRenderPlaceholder = () => {
        return resultError || resultIsFetching || !resultData || resultData.length === 0;
    };

    const sectionStyle = {
        mt: 2,
        mb: 2,
    };

    const renderPlaceholder = () => {
        if (resultError) {
            return (
                <Box sx={{ flex: 1 }}>
                    <Typography variant='h6' sx={{ ...sectionStyle }}>
                        Error loading data
                    </Typography>
                </Box>
            );
        }
        if (resultData && resultData.length === 0 && !resultIsFetching) {
            return (
                <Typography variant='h6' sx={{ ...sectionStyle, height: 100, minHeight: 100 }}>
                    No data available
                </Typography>
            );
        }
        return (
            <Box sx={{ flex: 1 }}>
                <Skeleton width={'80vw'} height={400} />
            </Box>
        );
    };

    return (
        <>
            {shouldRenderPlaceholder() ? (
                renderPlaceholder()
            ) : (
                <PagedTable
                    page={page}
                    onPageChange={onPageChange}
                    total={totalCount?.length ? totalCount[0]?.count : 0}
                    rows={resultData}
                    headers={getTableHeaders(resultData)}
                    onExportAll={handleExportAll}
                    module={moduleName}
                />
            )}
        </>
    );
};

export default ResultsTable;
