import React, { useState, useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { selectAllFilters } from '../Query/slice.ts';
import {
    selectSectionLayoutBySection,
    setSectionLayout,
    selectSidebarOpen,
    selectPalmprintOnly,
} from '../../app/slice.ts';
import { sectionConfig } from './constants.ts';
import { getFilterQuery } from '../../common/utils/queryHelpers.ts';
import { shouldDisableFigureView } from '../../common/utils/plotHelpers.ts';
import { useGetIdentifiersQuery } from '../../api/client.ts';
import { capitalize } from '../../common/utils/textFormatting.ts';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import SRARunLayout from '../Module/SRARun/SRARunLayout.tsx';
import EcologyLayout from '../Module/Ecology/EcologyLayout.tsx';
import ViromeLayout from '../Module/Virome/ViromeLayout.tsx';
import HostLayout from '../Module/Host/HostLayout.tsx';
import IconButton from '@mui/material/IconButton';
import TableIcon from '@mui/icons-material/TableRows';
import PlotIcon from '@mui/icons-material/InsertChart';
import ResultsTable from '../Results/ResultsTable.tsx';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import Tooltip from '@mui/material/Tooltip';
import Skeleton from '@mui/material/Skeleton';
import QuestionMarkIcon from '@mui/icons-material/HelpCenter';
import Button from '@mui/material/Button';
import ArrowRightIcon from '@mui/icons-material/ChevronRight';
import GenerateSummary from '../LLM/GenerateSummary.tsx';

const Module = ({ sectionKey }) => {
    const dispatch = useDispatch();
    const filters = useSelector(selectAllFilters);
    const sectionLayout = useSelector((state) => selectSectionLayoutBySection(state, sectionKey));
    const sidebarOpen = useSelector(selectSidebarOpen);
    const palmprintOnly = useSelector(selectPalmprintOnly);
    const [moduleDisplay, setModuleDisplay] = useState(sectionConfig[sectionKey].defaultDisplay);
    const [customDropDownOpen, setCustomDropDownOpen] = useState(false);

    const isTableView = () => moduleDisplay === 'table';
    const isFigureView = () => moduleDisplay === 'figure';

    const {
        data: identifiersData,
        error: identifiersError,
        isFetching: identifiersFetching,
    } = useGetIdentifiersQuery(
        {
            filters: getFilterQuery({ filters }),
            palmprintOnly,
        },
        {
            skip: sidebarOpen, // Skip fetching when sidebar is open
        },
    );

    useEffect(() => {
        if (!identifiersFetching && shouldDisableFigureView(identifiersData, sectionKey)) {
            setModuleDisplay('table');
        } else {
            setModuleDisplay(sectionConfig[sectionKey].defaultDisplay);
        }
    }, [identifiersData]);

    const onViewChange = (view) => {
        setModuleDisplay(view);
    };

    const getModuleFigureLayout = () => {
        if (!identifiersData || identifiersFetching) {
            return (
                <Box sx={{ height: '70vh', width: '100%' }}>
                    <Skeleton variant='rectangular' width={'100%'} height={'100%'} />
                </Box>
            );
        }
        if (sectionKey === 'sra') {
            return (
                <SRARunLayout
                    identifiers={identifiersData}
                    sectionLayout={sectionLayout}
                    palmprintOnly={palmprintOnly}
                />
            );
        }
        if (sectionKey === 'palmdb') {
            return <ViromeLayout identifiers={identifiersData} sectionLayout={sectionLayout} />;
        }
        if (sectionKey === 'ecology') {
            return (
                <EcologyLayout
                    identifiers={identifiersData}
                    sectionLayout={sectionLayout}
                    palmprintOnly={palmprintOnly}
                />
            );
        }
        if (sectionKey === 'host') {
            return (
                <HostLayout identifiers={identifiersData} sectionLayout={sectionLayout} palmprintOnly={palmprintOnly} />
            );
        }
        return (
            <Box sx={{ height: 500, width: 400 }}>
                <Typography variant='h6' sx={{ mt: 8 }}>
                    Coming soon!
                </Typography>
            </Box>
        );
    };

    const onLayoutChange = (event) => {
        dispatch(setSectionLayout({ sectionKey, sectionValue: event.target.value }));
    };

    const onHelpClick = () => {
        window.open(sectionConfig[sectionKey]?.wikiUrl, '_blank');
    };

    const getSectionLayoutDisplayName = (sectionLayoutType) => {
        return `${sectionConfig[sectionKey]?.title} (${sectionLayoutType == 'advanced' ? capitalize(sectionLayoutType) : 'Summary'})`;
    };

    // This custom handler is to keep MUI styles on select component while behaving like a button
    const handleDropdownClick = () => {
        setCustomDropDownOpen(false);
        const newSectionLayout = sectionLayout === 'simple' ? 'advanced' : 'simple';
        onLayoutChange({ target: { value: newSectionLayout } });
    };

    return (
        /* Section Layout */
        /* Control Global Figure width on page here " */
        <Box sx={{ width: '88vw', maxWidth: '100%', mt: 1, mb: 4, flexGrow: 1 }}>
            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    mb: 2,
                }}
            >
                <Box
                    sx={{
                        display: 'flex',
                        flexDirection: 'row',
                        justifyContent: 'flex-start',
                        alignItems: 'center',
                    }}
                >
                    <Box sx={{ mb: 0 }}>
                        {' '}
                        {/* Pull-down Menu Module Select */}
                        <Button
                            disableRipple
                            color='inherit'
                            onClick={() => {
                                handleDropdownClick();
                            }}
                            sx={{
                                'color': 'inherit',
                                'backgroundColor': 'transparent',
                                'padding': 0,
                                'textTransform': 'none',
                                'fontSize': 30,
                                'fontWeight': 500,
                                'borderRadius': 0,
                                'cursor': 'pointer',
                                '&:hover': {
                                    backgroundColor: 'transparent',
                                },
                            }}
                        >
                            <Select
                                sx={{
                                    'fontSize': 30,
                                    '.MuiOutlinedInput-notchedOutline': {
                                        borderColor: '#40a9ff',
                                    },
                                    '&:hover .MuiOutlinedInput-notchedOutline': {
                                        borderColor: '#40a9ff',
                                        borderWidth: '0.15rem',
                                    },
                                    'borderColor': '#40a9ff',
                                    '&:before': {
                                        borderColor: '#40a9ff',
                                    },
                                    '&:after': {
                                        borderColor: '#40a9ff',
                                    },
                                    'paddingRight': 0,
                                }}
                                value={sectionLayout}
                                onChange={onLayoutChange}
                                onClick={() => handleDropdownClick()}
                                variant='standard'
                                open={customDropDownOpen}
                                IconComponent={() => (
                                    <ArrowRightIcon sx={{ ml: -3, cursor: 'pointer', fontSize: 24 }} />
                                )}
                            >
                                {['simple', 'advanced'].map((sectionLayout) => {
                                    return (
                                        <MenuItem key={sectionLayout} value={sectionLayout} sx={{ pr: 10 }}>
                                            {getSectionLayoutDisplayName(sectionLayout)}
                                        </MenuItem>
                                    );
                                })}
                            </Select>
                        </Button>
                    </Box>
                    <GenerateSummary identifiers={identifiersData} dataType={sectionKey} palmprintOnly={palmprintOnly}/>
                </Box>

                <Box>
                    <Tooltip
                        placement='top'
                        title={
                            shouldDisableFigureView(identifiersData, sectionKey)
                                ? 'Figure view disabled. Add more filters.'
                                : 'Figures'
                        }
                    >
                        {/* Module View Icons */}
                        <IconButton
                            sx={{ mt: -0.5, height: 10, width: 30 }}
                            color={isFigureView() ? 'primary' : 'default'}
                            onClick={() => onViewChange('figure')}
                            disabled={shouldDisableFigureView(identifiersData, sectionKey)}
                        >
                            <PlotIcon fontSize='medium' />
                        </IconButton>
                    </Tooltip>
                    <Tooltip title='Table' placement='top'>
                        <IconButton
                            sx={{ mt: -0.5, height: 10, width: 30 }}
                            color={isTableView() ? 'primary' : 'default'}
                            onClick={() => onViewChange('table')}
                        >
                            <TableIcon fontSize='medium' />
                        </IconButton>
                    </Tooltip>
                    <Tooltip title='Wiki' placement='top'>
                        <IconButton sx={{ mt: -0.5, height: 10, width: 30 }} onClick={onHelpClick}>
                            <QuestionMarkIcon fontSize='medium' />
                        </IconButton>
                    </Tooltip>
                </Box>
            </Box>
            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'flex-start',
                    alignItems: 'flex-start',
                    flexWrap: 'wrap',
                    mt: 1,
                }}
            >
                {isTableView() ? (
                    <ResultsTable
                        identifiers={identifiersData}
                        moduleKey={sectionConfig[sectionKey].modules[0]}
                        shouldSkipFetching={identifiersFetching || !isTableView() || sidebarOpen}
                    />
                ) : (
                    getModuleFigureLayout()
                )}
            </Box>
        </Box>
    );
};

export default Module;
