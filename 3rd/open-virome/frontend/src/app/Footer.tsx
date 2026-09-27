import React from 'react';
import { useTheme } from '@mui/material/styles';

import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import Link from '@mui/material/Link';

const Footer = () => {
    const theme = useTheme();
    const isDark = theme.palette.mode === 'dark';
    return (
        <Box
            display='flex'
            justifyContent='flex-start'
            alignItems='flex-start'
            bgcolor={isDark ? 'black' : '#f5f5f5'}
            color={isDark ? 'white' : '#333'}
            width={'100%'}
            pt={'5%'}
            pr={'10%'}
            pb={'5%'}
            pl={'3%'}
            flexDirection={'row'}
        >
            <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', width: '100%' }}>
                <Typography variant='h6' sx={{ mb: 1 }}>
                    Open Virome
                </Typography>
                <Typography variant='body2'>
                    <Link href='https://github.com/serratus-bio/open-virome/wiki/About' color='inherit' target='_blank'>
                        About
                    </Link>
                </Typography>
                <Typography variant='body2'>
                    <Link href='https://github.com/serratus-bio/open-virome/wiki' color='inherit' target='_blank'>
                        Docs
                    </Link>
                </Typography>
            </Box>
            <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', width: '100%' }}>
                <Typography variant='h6' sx={{ mb: 1 }}>
                    Support
                </Typography>
                <Typography variant='body2'>
                    <Link href='https://github.com/serratus-bio/open-virome' color='inherit' target='_blank'>
                        GitHub
                    </Link>
                </Typography>
                <Typography variant='body2'>
                    <Link
                        href='https://github.com/serratus-bio/open-virome/issues/new/choose'
                        color='inherit'
                        target='_blank'
                    >
                        Report an Issue
                    </Link>
                </Typography>
            </Box>
            <Box
                sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', width: '100%' }}
            ></Box>
        </Box>
    );
};

export default Footer;
