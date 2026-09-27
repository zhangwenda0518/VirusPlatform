import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { toggleSidebar, togglePalmprintOnly, selectPalmprintOnly } from '../../app/slice.ts';
import { removeAllFilters } from './slice.ts';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Logo from '../../common/assets/ov_hex_dark.png';

const NoResultsMessage = () => {
    const dispatch = useDispatch();
    const palmprintOnly = useSelector(selectPalmprintOnly);

    const onClickFilterText = () => {
        dispatch(removeAllFilters());
        dispatch(toggleSidebar());
    };

    const onClickPalmprintOnly = () => {
        dispatch(togglePalmprintOnly());
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
            <Box
                alt='Open virome logo'
                component='img'
                sx={{
                    height: 150,
                    width: 150,
                    cursor: 'pointer',
                    mt: -20,
                }}
                src={Logo}
                onClick={onClickFilterText}
            />
            <Typography variant='h6'>{`No results found.`}</Typography>
            <Typography variant='h6'>
                <Typography
                    onClick={onClickFilterText}
                    paragraph
                    variant='h6'
                    component='span'
                    color='primary'
                    style={{ cursor: 'pointer' }}
                >
                    {`Clear filters`}
                </Typography>
                {palmprintOnly ? (
                    <>
                        {', include runs '}
                        <Typography
                            onClick={onClickPalmprintOnly}
                            paragraph
                            variant='h6'
                            component='span'
                            color='primary'
                            style={{ cursor: 'pointer' }}
                        >
                            {`without viruses,`}
                        </Typography>
                    </>
                ) : null}
                {' or try again later.'}
            </Typography>
        </Box>
    );
};

export default NoResultsMessage;
