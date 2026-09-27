import React from 'react';
import { Provider, useSelector } from 'react-redux';
import { store } from './store.ts';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { selectDarkMode, selectSidebarOpen, selectPalmprintOnly } from './slice.ts';
import { selectAllFilters } from '../features/Query/slice.ts';
import { useGetIdentifiersQuery } from '../api/client.ts';
import { getFilterQuery } from '../common/utils/queryHelpers.ts';
import { isSummaryView } from '../common/utils/plotHelpers.ts';

import SidePanel from '../features/Query/SidePanel.tsx';
import Chat from '../features/LLM/Chat.tsx';
import AppToolbar from './Toolbar.tsx';
import Box from '@mui/material/Box';
import QuerySummaryText from '../features/Query/QuerySummaryText.tsx';
import Module from '../features/Module/Module.tsx';
import QueryView from '../features/Query/QueryView.tsx';
import Toolbar from '@mui/material/Toolbar';
import Footer from './Footer.tsx';
import OnboardingMessage from '../features/Query/OnboardingMessage.tsx';
import NoResultsMessage from '../features/Query/NoResultsMessage.tsx';

const AppWrapper = () => {
    return (
        <Provider store={store}>
            <App />
        </Provider>
    );
};

const App = () => {
    const darkMode = useSelector(selectDarkMode);
    const filters = useSelector(selectAllFilters);
    const sidebarOpen = useSelector(selectSidebarOpen);
    const palmprintOnly = useSelector(selectPalmprintOnly);

    const theme = createTheme({
        palette: {
            mode: darkMode ? 'dark' : 'light',
            // 平台主题色（与 app.css 的 topnav/accent 一致）
            primary: { main: '#14532d' },
            secondary: { main: '#7dd3a8' },
            ...(darkMode ? {} : { background: { default: '#f2f4f7', paper: '#ffffff' } }),
        },
    });

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

    const getContainerStyles = () => ({
        flexGrow: 1,
        /* padding below toolbar */
        padding: theme.spacing(0),
        transition: theme.transitions.create('margin', {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.leavingScreen,
        }),
        /* left Section Margin */
        /* set to -240 to offset Sidebar "drawerWidth" in SidePanel.tsx */
        marginLeft: `-240px`,
        marginRight: `0px`,
        backgroundColor: darkMode ? 'rgba(29, 30, 32, 0.6)' : 'transparent',
    });

    const showOnboardingMessage = () => {
        return filters.length === 0;
    };
    const showNoResultsMessage = () => {
        return filters.length > 0 && !identifiersFetching && isSummaryView(identifiersData);
    };

    return (
        <ThemeProvider theme={theme}>
            {/* Main Page Layout */}
            <Box sx={{ display: 'flex' }}>
                <CssBaseline />
                <AppToolbar />
                <SidePanel />
                <Chat />
                <Box sx={getContainerStyles()}>
                    <Box
                        sx={{
                            flexGrow: 1,
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'center',
                            ml: '3%',
                        }}
                    >
                        <Toolbar />
                        {showOnboardingMessage() ? (
                            <OnboardingMessage />
                        ) : showNoResultsMessage() ? (
                            <NoResultsMessage />
                        ) : (
                            <>
                                <QuerySummaryText />
                                <Module sectionKey={'sra'} />
                                <Module sectionKey={'palmdb'} />
                                <Module sectionKey={'ecology'} />
                                <Module sectionKey={'host'} />
                            </>
                        )}
                    </Box>
                </Box>
                <QueryView />
            </Box>
            <Footer />
        </ThemeProvider>
    );
};

export default AppWrapper;
