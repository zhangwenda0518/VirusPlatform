import React from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { selectPalmprintOnly, togglePalmprintOnly } from '../../app/slice.ts';

import Box from '@mui/material/Box';
import Switch from '@mui/material/Switch';
import FormHelperText from '@mui/material/FormHelperText';

const PalmprintOnlyToggle = () => {
    const dispatch = useDispatch();
    const palmprintOnly = useSelector(selectPalmprintOnly);

    const onToggleClick = () => {
        dispatch(togglePalmprintOnly());
    };

    return (
        <Box sx={{ display: 'flex', alignItems: 'center', mt: -1 }}>
            <FormHelperText onClick={onToggleClick} sx={{ cursor: 'pointer' }}>
                Only include runs with palmprints
            </FormHelperText>
            <Switch checked={palmprintOnly} onChange={onToggleClick} color='primary' />
        </Box>
    );
};

export default PalmprintOnlyToggle;
