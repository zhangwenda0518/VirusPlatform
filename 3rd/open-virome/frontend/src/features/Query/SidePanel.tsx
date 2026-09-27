import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { setActiveQueryModule, toggleSidebar, selectSidebarOpen, selectActiveQueryModule, selectDarkMode } from '../../app/slice.ts';
import { moduleConfig, sectionConfig } from '../Module/constants.ts';

import MenuList from '@mui/material/MenuList';
import MenuItem from '@mui/material/MenuItem';
import ListItemText from '@mui/material/ListItemText';
import Drawer from '@mui/material/Drawer';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';

const SidePanel = () => {
    const dispatch = useDispatch();
    const sidebarOpen = useSelector(selectSidebarOpen);
    const sectionLayout = useSelector(selectActiveQueryModule);
    const darkMode = useSelector(selectDarkMode);

    const onItemClick = (moduleKey: string) => {
        dispatch(setActiveQueryModule(moduleKey));
    };

    const drawerWidth = 240;

    const handleDrawerClose = () => {
        dispatch(toggleSidebar());
    };

    return (
        <Drawer
            open={sidebarOpen}
            anchor={'left'}
            variant='persistent'
            onClose={handleDrawerClose}
            sx={{
                'zIndex': sidebarOpen ? 1400 : -1,
                'width': drawerWidth,
                'flexShrink': 0,
                '& .MuiDrawer-paper': {
                    width: drawerWidth,
                    boxSizing: 'border-box',
                    backgroundColor: darkMode ? '#1E1E1E' : '#FFF',
                    backgroundImage: 'none',
                    boxShadow: 'none',
                    border: 'none',
                    overflow: 'hidden',
                },
            }}
        >
        >
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', mt: 0.5 }}>
                <IconButton onClick={handleDrawerClose}>
                    <ChevronLeftIcon fontSize='large' />
                </IconButton>
            </Box>
            {Object.keys(sectionConfig).map((sectionKey) => (
                <Box key={sectionKey}>
                    <Typography sx={{ mt: 1, ml: 2 }} variant='body1' component='div'>
                        {sectionConfig[sectionKey].title}
                    </Typography>
                    <MenuList dense>
                        {sectionConfig[sectionKey].modules.map((moduleKey) => (
                            <MenuItem
                                key={moduleKey}
                                onClick={() => onItemClick(moduleKey)}
                                selected={moduleKey === sectionLayout}
                            >
                                <ListItemText inset>{moduleConfig[moduleKey].title}</ListItemText>
                            </MenuItem>
                        ))}
                    </MenuList>
                </Box>
            ))}
        </Drawer>
    );
};

export default SidePanel;
