import React, { useEffect, useState } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { toggleSidebar } from '../../app/slice.ts';
import { addManyFilters } from './slice.ts';
import { selectChatMessages, addChatMessage, clearChatMessages } from '../LLM/slice.ts';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import Typography from '@mui/material/Typography';
import LabelIcon from '@mui/icons-material/Description';
import GeoIcon from '@mui/icons-material/TravelExplore';
import BlurOnIcon from '@mui/icons-material/BlurOn';
import Logo from '../../common/assets/ov_hex_dark.png';
import OnboardingChat from '../LLM/OnboardingChat.tsx';

const OnbaordingMessage = () => {
    const dispatch = useDispatch();
    const chatMessages = useSelector(selectChatMessages);
    const [promptList, setPromptList] = useState([]);
    const [currentPromptIndex, setCurrentPromptIndex] = useState(0);

    useEffect(() => {
        window.scrollTo(0, 0);
    }, []);

    const getRandomizedPromptList = () => {
        const randomPrompts = [
            'What human tissue show the most viral diversity?',
            'What are the most unusual reservoirs for human-infecting viruses?',
            'what is the most unexpected virus-human relationship?',
            'Which virus has the largest economic impact on global agriculture?',
            'Are there viruses that exist in both terrestrial and aquatic ecosystems?',
            'What viruses are common in marine biological samples as well as in humans?',
            "Are there any indications that viruses play a role in cancer that aren't already known?",
            'Are the any potential gaps in the current virus research data?',
            'Could viruses be influencing autoimmune diseases in ways not yet explored?',
            'What are the least-studied viruses in metagenomic datasets?',
            'Are there any viruses that appear to consistently co-occur with specific bacterial pathogens?',
            'What are the most significant gaps in understanding virus-host specificity?',
            'What virus families are underrepresented in environmental sampling efforts?',
            'Could there be viruses linked to rare diseases that are currently classified as idiopathic?',
            'Are there viruses with unique adaptations to extreme environments, such as hydrothermal vents?',
            'What human tissues are least explored for the presence of viruses?',
            'Are there viruses that exhibit potential as vectors for therapeutic applications but remain unexamined?',
            'Which viruses could be acting as environmental sentinels for ecosystem health?',
        ];

        return randomPrompts
            .map((prompt) => ({ value: prompt, sort: Math.random() }))
            .sort((a, b) => a.sort - b.sort)
            .map((item) => item.value);
    };

    useEffect(() => {
        const randomPrompts = getRandomizedPromptList();
        setPromptList(randomPrompts);
    }, []);

    const exampleFilters = {
        'Eimeria': [
            {
                filterId: 'label-Eimeria stiedai',
                filterType: 'label',
                filterValue: 'Eimeria stiedai',
            },
            {
                filterId: 'label-Eimeria maxima',
                filterType: 'label',
                filterValue: 'Eimeria maxima',
            },
            {
                filterId: 'label-Eimeria necatrix',
                filterType: 'label',
                filterValue: 'Eimeria necatrix',
            },
            {
                filterId: 'label-Eimeria tenella',
                filterType: 'label',
                filterValue: 'Eimeria tenella',
            },
            {
                filterId: 'label-Eimeria falciformis',
                filterType: 'label',
                filterValue: 'Eimeria falciformis',
            },
        ],
        'Coniferous Forests': [
            {
                filterId: 'biome-WWF_TEW_BIOME_03',
                filterType: 'biome',
                filterValue: 'WWF_TEW_BIOME_03',
            },
        ],
    };

    const onClickFilterText = () => {
        dispatch(toggleSidebar());
    };

    const onClickExampleFilter = (name) => {
        const filters = exampleFilters[name];
        dispatch(addManyFilters(filters));
    };

    const handleRandomPrompt = () => {
        const prompt = promptList[currentPromptIndex];
        setCurrentPromptIndex((currentPromptIndex + 1) % promptList.length);
        dispatch(clearChatMessages());
        dispatch(addChatMessage({ message: prompt, role: 'user', mode: 'global' }));
        return prompt;
    };

    const onlyShowGlobalChat = () => {
        if (chatMessages.length === 0) {
            return false;
        }
        const lastMessage = chatMessages[chatMessages.length - 1];
        return lastMessage.mode === 'global' && lastMessage.role === 'assistant';
    };

    const getExampleQuery = (name) => {
        const iconMap = {
            'Eimeria': <LabelIcon fontSize='medium' />,
            'Coniferous Forests': <GeoIcon fontSize='medium' />,
            'Prompt': <BlurOnIcon fontSize='medium' />,
        };

        const filterTypeMap = {
            'Eimeria': 'organism',
            'Coniferous Forests': '',
            'Prompt': 'database',
        };
        const onClickHandler = () => {
            if (name === 'Prompt') {
                handleRandomPrompt();
            } else {
                onClickExampleFilter(name);
            }
        };

        return (
            <Card
                sx={{
                    borderWidth: 1,
                    borderColor: 'rgba(255, 255, 255, 0.48)',
                    borderRadius: 8,
                    margin: 2,
                }}
            >
                <CardActionArea
                    onClick={() => onClickHandler()}
                    sx={{
                        padding: 2,
                        display: 'flex',
                        flex: 1,
                        flexDirection: 'row',
                        justifyContent: 'center',
                        alignItems: 'center',
                        alignContent: 'center',
                        borderWidth: 2,
                        borderColor: 'rgba(255, 255, 255, 0.48)',
                        borderRadius: 8,
                        borderStyle: 'solid',
                        height: 80,
                        width: 210,
                        gap: 1,
                    }}
                >
                    {iconMap[name]}
                    {name === 'Prompt' ? (
                        <Typography variant='body2' sx={{ textAlign: 'left' }}>
                            {`Query the global virome with a prompt`}
                        </Typography>
                    ) : (
                        <Typography variant='body2' sx={{ textAlign: 'left' }}>
                            {`Query the `}
                            <Typography variant='body2' component='span' fontStyle='italic'>
                                {name}
                            </Typography>
                            {` ${filterTypeMap[name]} virome`}
                        </Typography>
                    )}
                </CardActionArea>
            </Card>
        );
    };

    return (
        <Box
            sx={{
                height: '90vh',
                width: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
            }}
        >
            {
                <Box
                    sx={{
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'center',
                        alignItems: 'center',
                        width: '100%',
                        height: '100%',
                        mt: 4,
                    }}
                >
                    {!onlyShowGlobalChat() ? (
                        <>
                            <Box
                                alt='Open virome logo'
                                component='img'
                                sx={{
                                    height: 150,
                                    width: 150,
                                    cursor: 'pointer',
                                    mt: -10,
                                }}
                                src={Logo}
                                onClick={onClickFilterText}
                            />
                            <Typography
                                variant='h6'
                                onClick={onClickFilterText}
                                sx={{ cursor: 'pointer' }}
                            >{`Welcome to Open Virome`}</Typography>
                        </>
                    ) : null}
                    <Box
                        sx={{
                            display: 'flex',
                            flexDirection: 'row',
                            justifyContent: 'center',
                            alignItems: 'center',
                            width: '100%',
                            height: onlyShowGlobalChat() ? '100%' : 100,
                            mt: 4,
                        }}
                    >
                        <OnboardingChat />
                    </Box>

                    {!onlyShowGlobalChat() ? (
                        <Box
                            sx={{
                                backgroundColor: 'transparent',
                                display: 'flex',
                                flexDirection: 'row',
                                justifyContent: 'center',
                                alignItems: 'center',
                                mt: 6,
                            }}
                        >
                            {getExampleQuery('Eimeria')}
                            {getExampleQuery('Coniferous Forests')}
                            {getExampleQuery('Prompt')}
                        </Box>
                    ) : null}
                </Box>
            }
        </Box>
    );
};

export default OnbaordingMessage;
