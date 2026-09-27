import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { selectAllFilters, removeFilter, removeAllFilters } from './slice.ts';
import { setActiveQueryModule, selectSidebarOpen, toggleSidebar } from '../../app/slice.ts';
import { moduleConfig } from '../Module/constants.ts';

import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

const FilterTags = () => {
    const filters = useSelector(selectAllFilters);
    const sidebarOpen = useSelector(selectSidebarOpen);
    const dispatch = useDispatch();

    const getFilterDisplayText = (filter) => {
        return `${moduleConfig[filter.filterType].tag}: ${filter.filterValue}`;
    };

    const onFilterDelete = (filterId) => {
        dispatch(removeFilter(filterId));
    };

    const onFilterClick = (filterType) => {
        dispatch(setActiveQueryModule(filterType));
        if (!sidebarOpen) {
            dispatch(toggleSidebar());
        }
    };

    const onClearAllFilters = () => {
        dispatch(removeAllFilters());
    };

    return (
        <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'nowrap' }}>
            <Box
                sx={{
                    ml: 4,
                    flexGrow: 1,
                    display: 'flex',
                    justifyContent: 'left',
                    flexWrap: 'nowrap',
                    overflow: 'auto',
                    maxWidth: '50vw',
                    borderRadius: 2,
                }}
            >
                <Stack spacing={1} direction='row'>
                    {filters.map((filter) => (
                        <Chip
                            key={filter.filterId}
                            label={getFilterDisplayText(filter)}
                            onDelete={() => onFilterDelete(filter.filterId)}
                            onClick={() => onFilterClick(filter.filterType)}
                        />
                    ))}
                </Stack>
            </Box>
            {filters.length > 0 ? (
                <Button onClick={() => onClearAllFilters()} variant='text' size='small' sx={{ ml: 1 }}>
                    <Typography variant='body2'>Clear All</Typography>
                </Button>
            ) : null}
        </Box>
    );
};

export default FilterTags;
