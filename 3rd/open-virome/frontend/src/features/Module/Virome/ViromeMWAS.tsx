import React, { useState, useEffect, useMemo } from 'react';
import { useGetMWASQuery } from '../../../api/client.ts';
import { getMWASScatterPlotData } from './plotHelpers.ts';

import ScatterPlot from '../../../common/ScatterPlot.tsx';
import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Link from '@mui/material/Link';
import Typography from '@mui/material/Typography';
import MdOpenInNew from '@mui/icons-material/OpenInNew';
import SearchBar from '../../../common/SearchBar.tsx';
import GenerateHypothesis from '../../LLM/GenerateHypothesis.tsx';

const ViromeMWAS = ({ identifiers, virusFamilies }) => {
    const [selectedMetadata, setSelectedMetadata] = useState(null);
    const [activeMetadataType, setActiveMetadataType] = useState('');

    const { data, error, isFetching } = useGetMWASQuery({
        idColumn: 'bioproject',
        ids: identifiers ? identifiers['bioproject'].single : [],
        idRanges: identifiers ? identifiers['bioproject'].range : [],
        virusFamilies: virusFamilies ? virusFamilies : [],
        pageStart: 0,
        pageEnd: 1000,
    });

    useEffect(() => {
        if (data && data.length > 0) {
            setSelectedMetadata(data[0]);
        }
    }, [data]);

    const onEvents = {
        click: (e) => {
            const [_1, _2, bioproject, family, metadataField, metadataValue, ..._3] = e.data;
            const selectedMetadata = data.find((metadata) => {
                return (
                    metadata.bioproject === bioproject &&
                    metadata.family === family &&
                    metadata.metadata_field === metadataField &&
                    metadata.metadata_value === metadataValue
                );
            });
            if (selectedMetadata) {
                setSelectedMetadata(selectedMetadata);
            }
        },
    };

    const renderPlaceholder = () => {
        return <Skeleton variant='rectangular' width='100%' height={500} />;
    };

    const getScatterPlot = (data) => {
        if (!data) {
            return null;
        }
        return (
            <ScatterPlot
                plotData={getMWASScatterPlotData(data, activeMetadataType)}
                styles={{ width: '100%', height: '70vh', maxWidth: '100%' }}
                onEvents={onEvents}
                module="Virome"
            />
        );
    };

    const scatterPlot = useMemo(() => getScatterPlot(data), [data, activeMetadataType]);

    const renderSearchBox = () => {
        return <SearchBar placeholder={`Search results`} query={activeMetadataType} setQuery={setActiveMetadataType} />;
    };

    if (identifiers && identifiers['bioproject'].single.length === 0) {
        return null;
    }

    if ((data && data.length === 0) || error) {
        return null;
    }

    return (
        <Box sx={{ width: '100%', height: '100%' }}>
            <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                {identifiers && identifiers['bioproject'].single.length > 100 ? (
                    <Typography variant='h7' component={'div'} sx={{ mt: 2, flex: 1 }}>
                        {`Dataset is too large. Displaying partial results.`}
                    </Typography>
                ) : null}
            </Box>
            {selectedMetadata ? (
                <GenerateHypothesis identifiers={identifiers} selectedMetadata={selectedMetadata} />
            ) : null}

            <Box
                sx={{
                    display: 'flex',
                    justifyContent: 'flex-start',
                    flexDirection: 'row',
                    flex: 1,
                    width: '100%',
                    height: '100%',
                    mt: 2,
                }}
            >
                <Box sx={{ width: '55%', flexShrink: 0 }}>
                    {isFetching ? renderPlaceholder() : data ? scatterPlot : null}
                </Box>
                {selectedMetadata ? (
                    <Box sx={{ mt: 2, width: '45%', flexShrink: 0 }}>
                        {renderSearchBox()}
                        <hr />
                        <Box sx={{ mt: 2 }}>
                            <Box>
                                <Typography component='span' variant='body' sx={{ fontWeight: 'bold' }}>
                                    Attribute Name:
                                </Typography>
                                <Typography component='span' variant='body'>
                                    {` ${selectedMetadata.metadata_field}`}{' '}
                                </Typography>
                            </Box>
                            <Box>
                                <Typography component='span' variant='body' sx={{ fontWeight: 'bold' }}>
                                    Attribute Value:
                                </Typography>
                                <Typography component='span' variant='body'>
                                    {` ${selectedMetadata.metadata_value}`}{' '}
                                </Typography>
                            </Box>
                            <Box sx={{ mt: 1 }}>
                                <Typography component='span' variant='body' sx={{ fontWeight: 'bold' }}>
                                    Background set:
                                </Typography>
                                <Typography component='span' variant='body'>
                                    {` ${selectedMetadata.family} (Virus Family)`}{' '}
                                </Typography>
                            </Box>
                            <Box sx={{}}>
                                <Box sx={{ overflow: 'auto', maxHeight: 100, overflow: 'auto' }}>
                                    <Typography component='span' variant='body' sx={{ fontWeight: 'bold' }}>
                                        {'Matching Tax Species:'}
                                    </Typography>
                                    <Typography component='span' variant='body' sx={{}}>
                                        {` ${selectedMetadata.taxSpecies.join(', ')}`}
                                    </Typography>
                                </Box>
                            </Box>
                            <Box sx={{ display: 'flex', flexDirection: 'row', alignItems: 'center', mt: 2 }}>
                                <Typography component='span' variant='body' sx={{ fontWeight: 'bold' }}>
                                    BioProject:
                                </Typography>
                                <Link
                                    sx={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        flexDirection: 'row',
                                        textDecoration: 'none',
                                        ml: 1,
                                    }}
                                    href={`https://www.ncbi.nlm.nih.gov/bioproject/${selectedMetadata.bioproject}`}
                                    target='_blank'
                                >
                                    <Typography variant='body'>{selectedMetadata.bioproject}</Typography>
                                    <MdOpenInNew fontSize='small' sx={{ mb: 0.5, ml: 0.5 }} />
                                </Link>
                            </Box>
                            <Box>
                                <Box
                                    sx={{
                                        overflow: 'auto',
                                        display: 'flex',
                                        flexDirection: 'row',
                                        flexWrap: 'wrap',
                                        justifyContent: 'flex-start',
                                        maxHeight: 100,
                                        width: '100%',
                                    }}
                                >
                                    <Typography
                                        component='span'
                                        variant='body'
                                        sx={{ fontWeight: 'bold', mr: 1 }}
                                    >{`Matching BioSamples: `}</Typography>

                                    {selectedMetadata.biosamples.map((biosample) => (
                                        <Link
                                            sx={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                flexDirection: 'row',
                                                textDecoration: 'none',
                                                flex: 1,
                                                maxWidth: '20%',
                                                width: 120,
                                                minWidth: 120,
                                                mr: 2,
                                            }}
                                            href={`https://www.ncbi.nlm.nih.gov/biosample/${biosample}`}
                                            target='_blank'
                                        >
                                            <Typography variant='body'>{biosample}</Typography>
                                        </Link>
                                    ))}
                                </Box>
                                <Box sx={{ mt: 2 }}>
                                    <Typography component='span' variant='body' sx={{ fontWeight: 'bold' }}>
                                        Fold Change:
                                    </Typography>
                                    <Typography component='span' variant='body'>
                                        {` ${selectedMetadata.fold_change}`}{' '}
                                    </Typography>
                                </Box>
                                <Box>
                                    <Typography component='span' variant='body' sx={{ fontWeight: 'bold' }}>
                                        P-value:
                                    </Typography>
                                    <Typography component='span' variant='body'>
                                        {` ${selectedMetadata.p_value}`}{' '}
                                    </Typography>
                                </Box>
                            </Box>
                        </Box>
                    </Box>
                ) : null}
            </Box>
        </Box>
    );
};

export default ViromeMWAS;
