import React, { useState } from 'react';
import { useSelector } from 'react-redux';
import { selectAllFilters } from '../Query/slice.ts';
import { getFilterQuery } from '../../common/utils/queryHelpers.ts';
import { useLazyGetHypothesisQuery } from '../../api/client.ts';
import { formatLLMGeneratedText } from './textFormatting.tsx';

import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import CheckIcon from '@mui/icons-material/Check';
import { useTheme } from '@mui/material/styles';
import GenerateButton from './GenerateButton.tsx';

const GenerateHypothesis = ({ identifiers, selectedMetadata }) => {
    const theme = useTheme();
    const resultBg = theme.palette.mode === 'dark' ? '#484848' : '#f5f5f5';
    const filters = useSelector(selectAllFilters);

    const [getHypothesisText, { data: hypothesisData, isFetching: isFetchingHypothesis, error: errorHypothesis }] =
        useLazyGetHypothesisQuery();

    const [hypothesisClicked, setHypothesisClicked] = useState(false);
    const [copied, setCopied] = useState(false);

    const onButtonClick = async () => {
        if (isFetchingHypothesis || hypothesisClicked) {
            return;
        }
        setHypothesisClicked(true);
        try {
            await getHypothesisText({
            idColumn: 'bioproject',
            ids: identifiers ? identifiers['bioproject'].single : [],
            idRanges: identifiers ? identifiers['bioproject'].range : [],
            filters: getFilterQuery({ filters }),
            selectedMetadata: selectedMetadata,
            }).unwrap();
        } finally {
            setHypothesisClicked(false);
        }
    };

    const renderPlaceholder = () => {
        if (isFetchingHypothesis) {
            return <Skeleton variant='text' width={'100%'} height={60} />;
        }
        return null;
    };

    const hypothesisTextIsNonEmpty = () => hypothesisData && hypothesisData?.text?.length > 0;

    const handleCopy = () => {
        navigator.clipboard.writeText(hypothesisData?.text || '').then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    };

    return (
        <Box
            sx={{
                display: 'flex',
                width: '100%',
                justifyContent: 'space-between',
                justifyItems: 'flex-start',
                height: hypothesisTextIsNonEmpty() || isFetchingHypothesis ? '100%' : 0,
                mt: 4,
                mb: 6,
            }}
        >
            <Box
                sx={{
                    flex: 1,
                    minWidth: '90%',
                    maxHeight: 300,
                }}
            >
                {renderPlaceholder()}
                {!isFetchingHypothesis && hypothesisTextIsNonEmpty() ? (
                    <Box
                        sx={{
                            backgroundColor: resultBg,
                            p: 2,
                            borderRadius: 2,
                            overflow: 'auto',
                            maxHeight: 300,
                        }}
                    >
                        <Typography variant='body' sx={{ mt: 2, mb: 4, whiteSpace: 'pre-wrap' }}>
                            {formatLLMGeneratedText(hypothesisData?.text, hypothesisData?.conversation)}
                        </Typography>
                    </Box>
                ) : null}
            </Box>
            <Box
                sx={{
                    zIndex: 10,
                    flex: 1,
                    display: 'flex',
                    justifyContent: 'flex-end',
                    alignItems: 'center',
                    height: 45,
                }}
            >
                {hypothesisTextIsNonEmpty() && (
                    <Tooltip title={copied ? 'Copied!' : 'Copy to clipboard'}>
                        <IconButton onClick={handleCopy} size="small" sx={{ mr: 1 }}>
                            {copied ? <CheckIcon fontSize="small" color="success" /> : <ContentCopyIcon fontSize="small" />}
                        </IconButton>
                    </Tooltip>
                )}
                <GenerateButton onButtonClick={onButtonClick} title={'Generate Hypothesis'} />
            </Box>
        </Box>
    );
};

export default GenerateHypothesis;
