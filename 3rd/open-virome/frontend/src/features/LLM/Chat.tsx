import React, { useState } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { selectChatOpen, selectChatMessages, toggleChat, addChatMessage, clearChatMessages } from './slice.ts';
import { selectAllFilters } from '../Query/slice.ts';
import { addFilter } from '../Query/slice.ts';
import { formatLLMGeneratedText } from './textFormatting.tsx';

import IconButton from '@mui/material/IconButton';
import Box from '@mui/material/Box';
import Drawer from '@mui/material/Drawer';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import CloseIcon from '@mui/icons-material/Close';
import SendIcon from '@mui/icons-material/Send';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import InputAdornment from '@mui/material/InputAdornment';
import DeleteIcon from '@mui/icons-material/Delete';
import Toolbar from '@mui/material/Toolbar';
import FormHelperText from '@mui/material/FormHelperText';
import Link from '@mui/material/Link';

export const Chat = () => {
    const dispatch = useDispatch();
    const isChatOpen = useSelector(selectChatOpen);
    const chatMessages = useSelector(selectChatMessages);
    const filters = useSelector(selectAllFilters);

    const [inputValue, setInputValue] = useState('');

    const handleDrawerClose = () => {
        dispatch(toggleChat());
    };

    const handleSendMessage = () => {
        if (inputValue.trim() !== '') {
            setInputValue('');
            dispatch(
                addChatMessage({
                    text: inputValue,
                    role: 'user',
                }),
            );
        }
    };

    const handleClearMessages = () => {
        dispatch(clearChatMessages());
    };

    const handleKeyDown = (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            handleSendMessage();
        }
    };

    const onFilterTextClick = (filterText) => {
        const filterType = filterText.split(':')[0].trim();
        const filterValue = filterText.split(':')[1].trim();
        dispatch(
            addFilter({
                filterId: `${filterType}-${filterValue}`,
                filterType,
                filterValue,
            }),
        );
        dispatch(toggleChat());
    };

    const renderChatBubble = (messageObj, index) => {
        return messageObj.role === 'user' ? (
            <Box
                key={index}
                sx={{
                    bgcolor: 'cornflowerblue',
                    p: 1,
                    border: 'rounded',
                    borderRadius: '16px 16px 0 16px',
                    ml: 'auto',
                    mb: 2,
                }}
            >
                <Typography variant='body'>{messageObj.text}</Typography>
            </Box>
        ) : (
            <Box sx={{ p: 1, border: 'rounded', borderRadius: '16px 16px 16px 0', mb: 2 }} key={index}>
                <Typography sx={{ display: 'block', fontSize: '0.8em' }}>
                    {formatLLMGeneratedText(messageObj.text, messageObj.conversation, onFilterTextClick)}
                </Typography>
            </Box>
        );
    };

    const isGlobalChat = () => filters.length === 0;

    return (
        <>
            <Drawer
                anchor='right'
                open={isChatOpen}
                onClose={handleDrawerClose}
                sx={{
                    'zIndex': 1000,
                    '& .MuiDrawer-paper': {
                        width: '400px',
                        padding: '16px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        backgroundColor: 'background.paper',
                        backgroundImage: 'unset',
                    },
                }}
            >
                <Toolbar />
                <Box sx={{ width: '100%', display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                    <IconButton onClick={handleDrawerClose}>
                        <CloseIcon />
                    </IconButton>
                    <IconButton onClick={handleClearMessages}>
                        <DeleteIcon />
                    </IconButton>
                </Box>

                {/* Chat Messages */}
                <Box sx={{ flexGrow: 1 }}>
                    <List>
                        {chatMessages.map((message, index) => (
                            <ListItem key={index}>{renderChatBubble(message, index)}</ListItem>
                        ))}
                    </List>
                </Box>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <TextField
                        fullWidth
                        multiline
                        rows={2}
                        autoFocus
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        placeholder={
                            isGlobalChat()
                                ? 'Query the global virome (coming soon)'
                                : 'Query the local virome (coming soon)'
                        }
                        disabled={true}
                        onKeyDown={handleKeyDown}
                        sx={{
                            '& .MuiInputBase-root': {
                                borderRadius: 2,
                                backgroundColor: 'action.hover',
                            },
                            '& .MuiOutlinedInput-root': {
                                '& fieldset': {
                                    borderColor: 'transparent',
                                },
                                '&:hover fieldset': {
                                    borderColor: 'transparent',
                                },
                                '&.Mui-focused fieldset': {
                                    borderColor: 'transparent',
                                },
                            },
                        }}
                        InputProps={{
                            endAdornment: (
                                <InputAdornment position='end'>
                                    <IconButton onClick={handleSendMessage}>
                                        <SendIcon />
                                    </IconButton>
                                </InputAdornment>
                            ),
                        }}
                    />
                    <FormHelperText sx={{ ml: 2 }}>
                        <Link
                            href={'https://github.com/serratus-bio/open-virome/wiki/LLM-Integration'}
                            target='_blank'
                            rel='noreferrer'
                        >
                            GraphRAG LLMs
                        </Link>
                        {` may make mistakes. Check important info.`}
                    </FormHelperText>
                </Box>
            </Drawer>
        </>
    );
};

export default Chat;
