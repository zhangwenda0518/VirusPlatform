import React, { useState, useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { selectActiveQueryModule } from '../../app/slice.ts';
import { moduleConfig } from '../Module/constants.ts';
import { useGetCountsQuery, useGetIdentifiersQuery } from '../../api/client.ts';
import { addFilter, removeFilter, selectAllFilters, selectFiltersByType } from './slice.ts';
import { getFilterQuery } from '../../common/utils/queryHelpers.ts';
import { formatNumber } from '../../common/utils/textFormatting.ts';

import SearchBar from '../../common/SearchBar.tsx';
import VirtualizedTable from '../../common/VirtualizedTable.tsx';
import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import CircularProgress from '@mui/material/CircularProgress';
import FormHelperText from '@mui/material/FormHelperText';
import QuerySummaryText from './QuerySummaryText.tsx';
import PalmprintOnlyToggle from './PalmprintOnlyToggle.tsx';

const FilterTable = ({ palmprintOnly }) => {
    const dispatch = useDispatch();
    const [searchString, setSearchString] = useState('');
    const [isTypingInterval, setIsTypingInterval] = useState(0);
    const activeQueryModule = useSelector(selectActiveQueryModule);
    const filters = useSelector(selectAllFilters);
    const moduleFilters = useSelector((state) => selectFiltersByType(state, activeQueryModule));

    useEffect(() => {
        setIsTypingInterval(0);
        setSearchString('');
    }, [activeQueryModule]);

    const {
        data: identifiersData,
        error: identifiersError,
        isFetching: identifiersFetching,
    } = useGetIdentifiersQuery({
        filters: getFilterQuery({ filters }),
        palmprintOnly,
        maxRetries: 3,
    });

    const {
        data: countData,
        error: countError,
        isFetching: countIsFetching,
    } = useGetCountsQuery(
        {
            filters: getFilterQuery({ filters, excludeType: activeQueryModule }),
            groupBy: moduleConfig[activeQueryModule].groupByKey,
            sortByColumn: 'count',
            sortByDirection: 'desc',
            pageStart: 0,
            pageEnd: 100000,
            searchString: searchString,
            palmprintOnly,
        },
        {
            skip: isTypingInterval > 0,
        },
    );

    useEffect(() => {
        const isTypingDelay = setTimeout(async () => {
            setIsTypingInterval(0);
        }, 500);
        return () => clearTimeout(isTypingDelay);
    }, [isTypingInterval]);

    const handleSearchInput = (query) => {
        setSearchString(query);
        setIsTypingInterval(isTypingInterval + 1);
    };

    const onRowClick = (row) => {
        if (row.selected) {
            dispatch(removeFilter(`${activeQueryModule}-${row.name}`));
            return;
        } else {
            dispatch(
                addFilter({
                    filterId: `${activeQueryModule}-${row.name}`,
                    filterType: activeQueryModule,
                    filterValue: row.name,
                }),
            );
        }
    };

    const getRows = (countData, searchString, moduleFilters) => {
        const addFilterState = (rows) => {
            return rows.map((row) => {
                const filterState = moduleFilters.find((filter) => filter.filterValue === row.name);
                return {
                    ...row,
                    selected: !!filterState,
                };
            });
        };
        if (!countData) {
            return [];
        }
        let rows = addFilterState(countData);

        // If search string is present, sort rows by search term match count
        if (searchString.length > 0) {
            const searchTerms = searchString.split(/[\s,]+/);
            rows = rows.sort((a, b) => {
                if (!a.name || !b.name) {
                    return 0;
                }
                const aScore = searchTerms.reduce((acc, term) => {
                    return acc + (a.name.toLowerCase().includes(term.toLowerCase()) ? 1 : 0);
                }, 0);
                const bScore = searchTerms.reduce((acc, term) => {
                    return acc + (b.name.toLowerCase().includes(term.toLowerCase()) ? 1 : 0);
                }, 0);
                return bScore - aScore;
            });
        }
        return rows;
    };

    return (
        <>
            <Box>
                {(countIsFetching || !countData) && searchString.length === 0 ? (
                    <Box sx={{ position: 'relative' }}>
                        <Skeleton variant='rounded' height={'75vh'} />
                        <Box
                            sx={{
                                position: 'absolute',
                                top: 0, left: 0, right: 0, bottom: 0,
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: 2,
                                pointerEvents: 'none',
                            }}
                        >
                            <CircularProgress size={36} />
                            <FormHelperText sx={{ fontSize: 14, textAlign: 'center' }}>
                                {countData
                                    ? `Updating filters… 筛选更新中`
                                    : `Loading filter options… 筛选项首次加载可能需要 1–2 分钟`}
                            </FormHelperText>
                        </Box>
                    </Box>
                ) : (
                    <VirtualizedTable
                        rows={getRows(countData, searchString, moduleFilters)}
                        onRowClick={onRowClick}
                        searchBar={
                            <Box>
                                <SearchBar
                                    placeholder={`Search ${moduleConfig[activeQueryModule].title}`}
                                    query={searchString}
                                    setQuery={handleSearchInput}
                                />
                                <FormHelperText sx={{ mb: -1, ml: 2 }}>
                                    {`Enter search terms seperated by comma or whitespace`}
                                </FormHelperText>
                            </Box>
                        }
                    />
                )}
            </Box>
            <Box sx={{ mb: 2, mt: 2, ml: 2, mr: 1 }}>
                {!identifiersData || identifiersFetching || countIsFetching ? (
                    <Skeleton variant='rounded' height={20} width={'80%'} />
                ) : (
                    <>
                        <Box
                            sx={{
                                display: 'flex',
                                flexDirection: 'row',
                                alignItems: 'flex-start',
                                justifyContent: 'space-between',
                                width: '100%',
                            }}
                        >
                            <FormHelperText component={'span'} sx={{ textAlign: 'left' }}>
                                {`Total rows: ${countData && countData?.length >= 100000 ? '≥' : ''}${countData ? formatNumber(countData.length) : ''}`}
                            </FormHelperText>
                            <PalmprintOnlyToggle />
                        </Box>
                        <QuerySummaryText />
                    </>
                )}
            </Box>
        </>
    );
};

export default FilterTable;
