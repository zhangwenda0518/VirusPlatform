import React from 'react';
import { isSimpleLayout } from '../../../common/utils/plotHelpers.ts';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TargetControlFigure from './TargetControlFigure.tsx';
import BioprojectFigure from './BioprojectFigure.tsx';
import GenerateSummary from '../../LLM/GenerateSummary.tsx';

const SRARunLayout = ({ identifiers, sectionLayout, palmprintOnly }) => {
    const getFigures = () => {
        if (isSimpleLayout(sectionLayout)) {
            return (
                <Box sx={{ flex: 1, width: '100%' }}>
                    <TargetControlFigure
                        identifiers={identifiers}
                        moduleKey={'label'}
                        figureType={'bar'}
                        sectionLayout={sectionLayout}
                        palmprintOnly={palmprintOnly}
                    />
                </Box>
            );
        } else {
            return (
                <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                    <Typography variant='h6' sx={{ mt: 2, mb: 2 }}>
                        {`Run Label`}
                    </Typography>
                    <Box sx={{ flex: 1, width: '100%', mb: 2 }}>
                        <TargetControlFigure
                            identifiers={identifiers}
                            moduleKey={'label'}
                            figureType={'bar'}
                            sectionLayout={sectionLayout}
                            palmprintOnly={palmprintOnly}
                        />
                    </Box>
                    <Typography variant='h6' sx={{ mt: 2, mb: 2 }}>
                        {`Run Technology`}
                    </Typography>
                    <Box sx={{ flex: 1, width: '100%', mb: 2 }}>
                        <TargetControlFigure
                            identifiers={identifiers}
                            moduleKey={'seqType'}
                            figureType={'polar'}
                            sectionLayout={sectionLayout}
                            palmprintOnly={palmprintOnly}
                        />
                    </Box>
                    <Typography variant='h6' sx={{ mt: 2, mb: 2 }}>
                        {`BioProject`}
                    </Typography>
                    <Box sx={{ flex: 1, width: '100%' }}>
                        <BioprojectFigure identifiers={identifiers} palmprintOnly={palmprintOnly} />
                    </Box>
                </Box>
            );
        }
    };

    return (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            {getFigures()}
        </Box>
    );
};

export default React.memo(SRARunLayout);
