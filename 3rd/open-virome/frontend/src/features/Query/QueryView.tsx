import React from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { selectSidebarOpen, toggleSidebar, selectActiveQueryModule, selectPalmprintOnly, selectDarkMode } from '../../app/slice.ts';
import { moduleConfig } from '../Module/constants.ts';

import Box from '@mui/material/Box';
import Modal from '@mui/material/Modal';
import Slide from '@mui/material/Slide';
import FilterTable from './FilterTable.tsx';
import SRAIdsInput from './SRAIdsInput.tsx';

const QueryView = () => {
    const dispatch = useDispatch();
    const activeQueryModule = useSelector(selectActiveQueryModule);
    const sidebarOpen = useSelector(selectSidebarOpen);
    const palmprintOnly = useSelector(selectPalmprintOnly);
    const darkMode = useSelector(selectDarkMode);

    return (
        <Modal
            open={sidebarOpen}
            sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
            }}
            onClose={() => dispatch(toggleSidebar())}
            closeAfterTransition={false}
        >
            <Box>
                <Slide direction='right' in={sidebarOpen} mountOnEnter unmountOnExit>
                    <Box
                        sx={{
                            width: 700,
                            height: '100%',
                            position: 'absolute',
                            top: 60,
                            left: 240,
                            backgroundColor: darkMode ? '#252427' : '#FFF',
                        }}
                    >
                        {moduleConfig[activeQueryModule].queryBuilderDisplay === 'input' ? (
                            <SRAIdsInput palmprintOnly={palmprintOnly} />
                        ) : (
                            <FilterTable palmprintOnly={palmprintOnly} />
                        )}
                    </Box>
                </Slide>
            </Box>
        </Modal>
    );
};

export default QueryView;
