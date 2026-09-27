import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { toggleSidebar, selectSidebarOpen, toggleDarkMode, selectDarkMode } from './slice.ts';
import { useTheme } from '@mui/material/styles';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import { toggleChat, selectChatOpen } from '../features/LLM/slice.ts';

import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import FilterTags from '../features/Query/FilterTags.tsx';
import IconButton from '@mui/material/IconButton';
import TuneIcon from '@mui/icons-material/Tune';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import ChatOutlinedIcon from '@mui/icons-material/ChatOutlined';
import Tooltip from '@mui/material/Tooltip';

const AppToolbar = () => {
    const dispatch = useDispatch();
    const isFilterOpen = useSelector(selectSidebarOpen);
    const isChatOpen = useSelector(selectChatOpen);
    const darkMode = useSelector(selectDarkMode);
    const theme = useTheme();
    const drawerWidth = 100;
    const iconBtnBg = 'rgba(255, 255, 255, 0.14)';

    const getAppBarStyles = () => ({
        // 顶栏圆形按钮在深绿 AppBar 上的对比度：浅色圆底 + 浅色 glyph
        '& .MuiIconButton-root': {
            color: '#eef3ee',
            '&:hover': { backgroundColor: 'rgba(255, 255, 255, 0.26)' },
        },
        'transition': theme.transitions.create(['margin', 'width'], {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.leavingScreen,
        }),
        '& .MuiToolbar-root': { padding: 0 },
        ...(isFilterOpen && {
            'width': `calc(100% - ${drawerWidth}px)`,
            'marginLeft': `${drawerWidth}px`,
            'transition': theme.transitions.create(['margin', 'width'], {
                easing: theme.transitions.easing.easeOut,
                duration: theme.transitions.duration.enteringScreen,
            }),
            'zIndex': 1400,
            '& .MuiToolbar-root': { paddingLeft: 4 },
        }),
    });

    const handleFilterClick = () => {
        if (isChatOpen) {
            dispatch(toggleChat());
        }
        dispatch(toggleSidebar());
    };

    const handleChatClick = () => {
        if (isFilterOpen) {
            dispatch(toggleSidebar());
        }
        dispatch(toggleChat());
    };

    return (
        <AppBar position='fixed' sx={getAppBarStyles()}>
            <Toolbar sx={{ width: '100%', pl: 0 }}>
                {!isFilterOpen ? (
                    <Tooltip title='Filters' placement='bottom'>
                        <IconButton
                            aria-label='open drawer'
                            onClick={handleFilterClick}
                            edge='start'
                            sx={{
                                backgroundColor: iconBtnBg,
                                mr: 2,
                                ml: '3%',
                            }}
                        >
                            <TuneIcon fontSize='medium' />
                        </IconButton>
                    </Tooltip>
                ) : null}
                {/* OV */}
                <Box sx={{ minWidth: 150, ml: 2 }}>
                    <Typography variant='h5' noWrap sx={{ display: isFilterOpen ? 'none' : 'block' }}>
                        Open Virome
                    </Typography>
                </Box>
                <FilterTags />
                {!isChatOpen ? (
                    <Tooltip title='LLM Research Assistant' placement='bottom'>
                        <IconButton
                            aria-label='open drawer'
                            onClick={handleChatClick}
                            edge='start'
                            sx={{
                                backgroundColor: iconBtnBg,
                                position: 'absolute',
                                right: '3%',
                                ...(isChatOpen && { display: 'none' }),
                            }}
                        >
                            <ChatOutlinedIcon fontSize='medium' />
                        </IconButton>
                    </Tooltip>
                ) : null}
                <Tooltip title={darkMode ? 'Light mode' : 'Dark mode'} placement='bottom'>
                    <IconButton
                        onClick={() => dispatch(toggleDarkMode())}
                        edge='start'
                        sx={{
                            backgroundColor: iconBtnBg,
                            position: 'absolute',
                            right: isChatOpen ? '120px' : '120px',
                        }}
                    >
                        {darkMode ? <LightModeIcon fontSize='medium' /> : <DarkModeIcon fontSize='medium' />}
                    </IconButton>
                </Tooltip>
            </Toolbar>
        </AppBar>
    );
};

export default AppToolbar;
