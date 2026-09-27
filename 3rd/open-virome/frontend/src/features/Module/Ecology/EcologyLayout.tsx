import React from 'react';
import Box from '@mui/material/Box';
import MapPlot from '../../../common/MapLibreDeckGLMap.tsx';

const EcologyLayout = ({ identifiers, sectionLayout, palmprintOnly }) => {
    return (
        <Box
            sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                width: '100%',
                height: '100%',
                mb: 10,
            }}
        >
            <MapPlot identifiers={identifiers} layout={sectionLayout} palmprintOnly={palmprintOnly} module="Ecology"/>
        </Box>
    );
};

export default React.memo(EcologyLayout);
