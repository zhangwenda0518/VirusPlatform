import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSelector } from 'react-redux';
import { isSummaryView, isSimpleLayout } from '../../../common/utils/plotHelpers.ts';
import { getViromeGraphData, getViromeScatterPlotData } from './plotHelpers.ts';
import { useGetResultQuery } from '../../../api/client.ts';
import { moduleConfig } from '../../Module/constants.ts';
import { handleIdKeyIrregularities } from '../../../common/utils/queryHelpers.ts';
import { selectAllFilters } from '../../Query/slice.ts';
import cytoscape from 'cytoscape';

import NetworkPlot from '../../../common/NetworkPlot.tsx';
import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import DropDownSelect from '../../../common/DropdownSelect.tsx';
import ScatterPlot from '../../../common/ScatterPlot.tsx';
import ViromeSummaryTable from './ViromeSummaryTable.tsx';
import RadioButtonsGroup from '../../../common/RadioButtonsGroup.tsx';
import ViromeMWAS from './ViromeMWAS.tsx';

const ViromeLayout = ({ identifiers, sectionLayout }) => {
    const allFilters = useSelector(selectAllFilters);
    const [randomized, setRandomized] = useState(0);
    const [activeSubgraph, setActiveSubgraph] = useState('1');
    const [isSummaryTableOpen, setIsSummaryTableOpen] = useState(false);
    const [selectedNetworkItem, setSelectedNetworkItem] = useState(null);
    const [activeModule, setActiveModule] = useState('species');
    const [headlessCy, setHeadlessCy] = useState(
        cytoscape({
            headless: true,
            elements: [],
        }),
    );
    const containerRef = React.useRef(null);

    const {
        data: resultData,
        error: resultError,
        isFetching: resultIsFetching,
    } = useGetResultQuery(
        {
            idColumn: moduleConfig[activeModule].resultsIdColumn,
            ids: identifiers
                ? identifiers[handleIdKeyIrregularities(moduleConfig[activeModule].resultsIdColumn)].single
                : [],
            idRanges: identifiers
                ? identifiers[handleIdKeyIrregularities(moduleConfig[activeModule].resultsIdColumn)].range
                : [],
            table: moduleConfig[activeModule].resultsTable,
            pageStart: 0,
            pageEnd: isSummaryView(identifiers) ? 100 : undefined,
            sortBy: isSummaryView(identifiers) ? 'gb_pid' : undefined,
        },
        {
            skip: !identifiers,
        },
    );

    const getFilteredResultData = () => {
        // If virome filters are applied, we only want to plot data that matches the filters
        // (i.e. exclude all other viruses that co-occur in the matching runs)
        if (allFilters.length === 0 || !resultData) {
            return resultData;
        }

        const familyFilters = allFilters.filter((filter) => filter.filterType === 'family');
        const speciesFilters = allFilters.filter((filter) => filter.filterType === 'species');
        const sotuFilters = allFilters.filter((filter) => filter.filterType === 'sotu');

        let filteredData = resultData;
        if (familyFilters.length > 0) {
            filteredData = filteredData.filter((row) => {
                return familyFilters.some((filter) => row['tax_family'] === filter.filterValue);
            });
        }

        if (speciesFilters.length > 0) {
            filteredData = filteredData.filter((row) => {
                return speciesFilters.some((filter) => row['tax_species'] === filter.filterValue);
            });
        }

        if (sotuFilters.length > 0) {
            filteredData = filteredData.filter((row) => {
                return sotuFilters.some((filter) => row['sotu'] === filter.filterValue);
            });
        }
        return filteredData;
    };

    useEffect(() => {
        if (headlessCy) {
            const filteredResultData = getFilteredResultData();
            const plotData = getViromeGraphData(filteredResultData, moduleConfig[activeModule].groupByKey);
            headlessCy.json({ elements: plotData });
            headlessCy.ready(() => {
                const componentLabels = getComponentOptions();
                if (activeSubgraph !== componentLabels[0]) {
                    setActiveSubgraph(componentLabels[0]);
                } else {
                    setRandomized(randomized + 1);
                }
            });
        }
    }, [resultData, activeModule]);

    useEffect(() => {
        setIsSummaryTableOpen(false);
    }, [sectionLayout, identifiers, activeModule]);

    const getNetworkPlotData = () => {
        if (activeSubgraph === 'All') {
            const filteredResultData = getFilteredResultData();
            return getViromeGraphData(filteredResultData, moduleConfig[activeModule].groupByKey);
        }
        const components = headlessCy.elements().components();
        components.sort((a, b) => b.length - a.length);

        if (!components[parseInt(activeSubgraph) - 1]) {
            return [];
        }
        return components[parseInt(activeSubgraph) - 1].jsons();
    };

    const getComponentOptions = () => {
        const numComponents = headlessCy.elements().components().length;
        let componentLabels;
        if (headlessCy.elements().length < 500 || numComponents < 2) {
            componentLabels = Array.from({ length: numComponents + 1 }, (_, i) => {
                if (i === 0) {
                    return 'All';
                }
                return i.toString();
            });
        } else {
            componentLabels = Array.from({ length: numComponents }, (_, i) => {
                return (i + 1).toString();
            });
        }
        return componentLabels;
    };

    const renderPlaceholder = () => {
        if (resultError) {
            return (
                <Box>
                    <Typography variant='h6'>Error loading data</Typography>
                </Box>
            );
        }
        if (resultIsFetching) {
            return (
                <Box
                    sx={{
                        display: 'flex',
                        justifyContent: 'flex-start',
                        alignItems: 'flex-start',
                        flexDirection: 'row',
                        width: '100%',
                    }}
                >
                    {isSimpleLayout(sectionLayout) ? (
                        <Skeleton variant='rectangular' width={'100%'} height={'70vh'} />
                    ) : (
                        <>
                            <Skeleton variant='rectangular' width={'50%'} height={'70vh'} sx={{ mr: 4 }} />
                            <Skeleton variant='rectangular' width={'50%'} height={'70vh'} />
                        </>
                    )}
                </Box>
            );
        }
        return (
            <Box
                sx={{
                    display: 'flex',
                    justifyContent: 'flex-start',
                    alignItems: 'flex-start',
                    height: 200,
                    width: '100%',
                }}
            >
                <Typography variant='h6'>No data available</Typography>
            </Box>
        );
    };

    const renderDropdown = () => {
        return (
            <Box>
                <DropDownSelect
                    options={getComponentOptions()}
                    activeOption={activeSubgraph}
                    label='Virome Component'
                    setActiveOption={(event) => {
                        setActiveSubgraph(event.target.value);
                    }}
                    styles={{ width: 150 }}
                />
            </Box>
        );
    };

    const renderLabelRadioButtons = () => {
        const moduleKeys = {
            sotu: 'sOTU',
            family: 'Virus Family',
            species: 'GenBank Top Hit',
        };
        return (
            <Box sx={{ ml: 1 }}>
                <RadioButtonsGroup
                    items={moduleKeys}
                    selected={activeModule}
                    onChange={(event) => {
                        setActiveModule(event.target.value);
                    }}
                    props={{ row: true }}
                />
            </Box>
        );
    };

    const onNetworkPlotClick = useCallback((data) => {
        setIsSummaryTableOpen(true);
        setSelectedNetworkItem(data);
    }, []);

    const plotData = useMemo(() => getNetworkPlotData(), [activeSubgraph, randomized]);

    const renderNetworkFigure = () => {
        return (
            <Box ref={containerRef}>
                <NetworkPlot plotData={plotData} onNodeClick={onNetworkPlotClick} onEdgeClick={onNetworkPlotClick} module="Virome"/>
            </Box>
        );
    };

    const onScatterPlotEvents = {
        click: (params) => {
            if (params.data && params.data[2] !== undefined) {
                const subGraph = params.data[2] + 1;
                setActiveSubgraph(subGraph.toString());
            }
        },
    };

    const renderScatterPlot = () => {
        const components = headlessCy.elements().components();
        components.sort((a, b) => b.length - a.length);

        const rows = components.map((component, index) => {
            const nodes = component.filter((ele) => ele.isNode());
            const edges = component.filter((ele) => ele.isEdge());
            return [nodes.length, edges.length, index];
        });

        const plotData = getViromeScatterPlotData(rows);

        return <ScatterPlot plotData={plotData} styles={{ height: '70vh' }} onEvents={onScatterPlotEvents} module="Virome"/>;
    };

    const shouldRenderPlaceholder = (isError, isFetching, data) => {
        return isError || isFetching || !data || data.length === 0;
    };

    const getVirusFamilies = () => {
        const filteredResultData = getFilteredResultData();
        if (!filteredResultData) {
            return [];
        }
        const allTaxFamilies = filteredResultData.map((row) => row['tax_family']);
        return [...new Set(allTaxFamilies)];
    };

    return (
        <Box sx={{ width: '100%', height: '100%' }}>
            {resultData && resultData.length > 1000 ? (
                <Box
                    sx={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'center', height: '100%', mb: 2 }}
                >
                    <Typography variant='h6'>Dataset is too large. Displaying components of subsample. </Typography>
                </Box>
            ) : null}
            {shouldRenderPlaceholder(resultError, resultIsFetching, resultData) ? (
                renderPlaceholder()
            ) : (
                <Box
                    sx={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        flexDirection: 'row',
                        height: '100%',
                    }}
                >
                    <Box sx={{ flex: 1, width: '50%' }}>{renderNetworkFigure()}</Box>
                    <Box sx={{ flex: 1, display: 'flex', justifyContent: 'center', flexDirection: 'column' }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            {renderDropdown()}
                            {renderLabelRadioButtons()}
                        </Box>
                        {isSummaryTableOpen ? (
                            <ViromeSummaryTable
                                selectedItem={selectedNetworkItem}
                                onClose={() => setIsSummaryTableOpen(false)}
                                rows={resultData}
                                activeModule={activeModule}
                                maxWidth={containerRef.current.clientWidth}
                            />
                        ) : (
                            renderScatterPlot()
                        )}
                    </Box>
                </Box>
            )}
            {isSimpleLayout(sectionLayout) ? null : (
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%' }}>
                    <ViromeMWAS identifiers={identifiers} virusFamilies={getVirusFamilies()} />
                </Box>
            )}
        </Box>
    );
};

export default React.memo(ViromeLayout);
