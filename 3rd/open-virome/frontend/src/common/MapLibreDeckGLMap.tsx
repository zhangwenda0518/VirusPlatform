import React, { useCallback, useEffect, useRef, useState } from 'react';
import MdCopyAll from '@mui/icons-material/CopyAll';
import MdOpenInNew from '@mui/icons-material/OpenInNew';
import { deflate } from 'pako';
import { isSimpleLayout } from '../common/utils/plotHelpers.ts';
import { truncate } from '../common/utils/textFormatting.ts';
import ExportButton from '../common/ExportButton.tsx';
import { exportCanvasToPNG, exportElementToPNG } from '../common/utils/exportHelpers.ts';
import {
    WWF_BIOMES,
    AMAZON_LOCATION_API_KEY,
    LOGAN_RDS_PROXY_LAMBDA_AUTHORIZATION_HEADER,
    LOGAN_RDS_PROXY_LAMBDA_ENDPOINT,
    MAPLIBREDECKGLMAP_FETCH_DATA_ON_VIEWPORT_CHANGE,
    REGION_COUNTRIES,
} from '../features/Module/Ecology/constants.ts';

import Flag from 'react-world-flags';

// SEND TO UTIL FUNCTIONS
const aggregateArray128 = (a) => {
    let o: any = undefined;

    for (const v of a) {
        if (!o) o = {};

        if (!o[v]) o[v] = 0;

        ++o[v];
    }

    if (o)
        return Object.keys(o)
            .sort((a, b) => o[b] - o[a])
            .slice(0, 128)
            .map((k) => [k, o[k]]);
};
const arrayMapColumns = (a, c) => (a ?? []).map((v) => Object.fromEntries(c.map((_v, _i) => [_v, v[_i]])));
const bioprojectIDFromBiosample: any = async (biosample) => {
    if (!bioprojectIDFromBiosample._) bioprojectIDFromBiosample._ = {};

    if (!bioprojectIDFromBiosample._[biosample])
        bioprojectIDFromBiosample._[biosample] = (async () => {
            const response = await fetch(LOGAN_RDS_PROXY_LAMBDA_ENDPOINT, {
                body: JSON.stringify({ SELECT: "bioproject FROM sra WHERE biosample = '" + biosample + "' LIMIT 1;" }),
                headers: { Authorization: LOGAN_RDS_PROXY_LAMBDA_AUTHORIZATION_HEADER },
                method: 'POST',
            });

            if (response.status === 200) {
                const json = await response.json();

                if (json.result?.length) return json.result[0].bioproject;
            }
        })();

    return bioprojectIDFromBiosample._[biosample];
};
const pickMostRelevantGeographicalAttibute = (result) => {
    let o: any = undefined;

    const isLatLon = (name, value) => {
        if (/lat/.test(name) && /lon/.test(name)) return true;

        if (value.replace(/[^.0-9]/g, '').length / value.length > 0.6) return true;

        return false;
    };

    for (const attribute of result ?? []) {
        if (!o) o = {};

        if (!o[attribute.accession]) o[attribute.accession] = [];

        o[attribute.accession].push(attribute);
    }

    if (!o) return [];

    for (const k of Object.keys(o))
        o[k] = o[k].sort((a, b) => {
            const aLatLon = isLatLon(a.attribute_name, a.attribute_value);
            const bLatLon = isLatLon(b.attribute_name, b.attribute_value);

            return aLatLon !== bLatLon
                ? Number(bLatLon) - Number(aLatLon)
                : a.attribute_value.length !== b.attribute_value.length
                  ? b.attribute_value.length - a.attribute_value.length
                  : a.attribute_name.length - b.attribute_name.length;
        });

    return Object.values(o)
        .map((v: any) => v[0])
        .flat();
};
const selectBioproject: any = async (accession) => {
    if (!selectBioproject._) selectBioproject._ = {};

    if (!selectBioproject._[accession])
        selectBioproject._[accession] = (async () => {
            const response = await fetch(LOGAN_RDS_PROXY_LAMBDA_ENDPOINT, {
                body: JSON.stringify({ SELECT: "* FROM bioproject WHERE accession = '" + accession + "' LIMIT 1;" }),
                headers: { Authorization: LOGAN_RDS_PROXY_LAMBDA_AUTHORIZATION_HEADER },
                method: 'POST',
            });

            if (response.status === 200) {
                const json = await response.json();

                if (json.result?.length) return json.result[0];
            }
        })();

    return selectBioproject._[accession];
};
const selectBiosample: any = async (accession) => {
    if (!selectBiosample._) selectBiosample._ = {};

    if (!selectBiosample._[accession])
        selectBiosample._[accession] = (async () => {
            const response = await fetch(LOGAN_RDS_PROXY_LAMBDA_ENDPOINT, {
                body: JSON.stringify({ SELECT: "* FROM biosample WHERE accession = '" + accession + "' LIMIT 1;" }),
                headers: { Authorization: LOGAN_RDS_PROXY_LAMBDA_AUTHORIZATION_HEADER },
                method: 'POST',
            });

            if (response.status === 200) {
                const json = await response.json();

                if (json.result?.length) return json.result[0];
            }
        })();

    return selectBiosample._[accession];
};

const cyrb128 = (str) => {
    let h1 = 1779033703;
    let h2 = 3144134277;
    let h3 = 1013904242;
    let h4 = 2773480762;

    for (let i = 0, k; i < str.length; ++i) {
        k = str.charCodeAt(i);
        h1 = h2 ^ Math.imul(h1 ^ k, 597399067);
        h2 = h3 ^ Math.imul(h2 ^ k, 2869860233);
        h3 = h4 ^ Math.imul(h3 ^ k, 951274213);
        h4 = h1 ^ Math.imul(h4 ^ k, 2716044179);
    }

    h1 = Math.imul(h3 ^ (h1 >>> 18), 597399067);
    h2 = Math.imul(h4 ^ (h2 >>> 22), 2869860233);
    h3 = Math.imul(h1 ^ (h3 >>> 17), 951274213);
    h4 = Math.imul(h2 ^ (h4 >>> 19), 2716044179);

    h1 ^= h2 ^ h3 ^ h4;
    h2 ^= h1;
    h3 ^= h1;
    h4 ^= h1;

    return [h1 >>> 0, h2 >>> 0, h3 >>> 0, h4 >>> 0];
};

const gaussianRandom = (prng) => {
    const MEAN = 0;
    const STDEV = 1;

    const u = 1 - prng();
    const v = prng();
    const z = Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
    return z * STDEV + MEAN;
};

const splitmix32 = (a) => () => {
    a = (a | 0) + (0x9e3779b9 | 0);

    let t = a ^ (a >>> 16);
    t = Math.imul(t, 0x21f0aaad);
    t = t ^ (t >>> 15);
    t = Math.imul(t, 0x735a2d97);
    return ((t = t ^ (t >>> 15)) >>> 0) / 4294967296;
};

const WWF_TEW = Object.fromEntries(
    Object.entries(WWF_BIOMES).map(([k, v]) => {
        v.rgb = v.hex
            .substring(1)
            .match(/(.{1,2})/g)
            .map((_v) => parseInt(_v, 16));

        return [k, v];
    }),
);

const getIdClauses = (ids = [], idRanges = []) => {
    const clauses = [];
    const idColumn = 'accession';
    if (ids.length > 0) {
        clauses.push(`${idColumn} IN (${ids.map((id) => `'${id}'`).join(',')})`);
    }
    if (idRanges.length > 0) {
        idRanges.forEach((range) => {
            const [start, end] = range;
            clauses.push(`${idColumn} BETWEEN '${start}' AND '${end}'`);
        });
    }
    return clauses;
};
const getWhereClause = (palmprintOnly, identifiers) => {
    const identifierClauses = getIdClauses(identifiers?.biosample?.single, identifiers?.biosample?.range);
    const conditions = [];
    if (palmprintOnly) {
        conditions.push('palm_virome = true');
    }
    if (identifierClauses.length > 0) {
        conditions.push(`(${identifierClauses.join(' OR ')})`);
    }
    return conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
};

const DeckGLRenderScatterplot: any = ({
    identifiers,
    mapMode,
    mbOverlay,
    mlglMap,
    palmprintOnly,
    setAttributeName,
    setAttributeValue,
    setBiomeID,
    setBiosampleID,
    setCountryID,
    setElevation,
    setHitCount,
    setLatLon,
    setLocationCount,
    setPalmID,
    setPalmprintHitsCount,
    setRunID,
    setSOTU,
    setSOTUCount,
    setSequence,
    setSiteCount,
    setTopBiomes,
    setTopCountries,
    setTopSOTUs,
}) => {
    if (!DeckGLRenderScatterplot.n) DeckGLRenderScatterplot.n = 0;

    ++DeckGLRenderScatterplot.n;

    if (!DeckGLRenderScatterplot.p) DeckGLRenderScatterplot.p = Promise.resolve();

    DeckGLRenderScatterplot.p = DeckGLRenderScatterplot.p.then(async () => {
        if (DeckGLRenderScatterplot.n < 1 + 1) {
            const [ne, sw] = [mlglMap.getBounds().getNorthEast(), mlglMap.getBounds().getSouthWest()];

            const center = mlglMap.getCenter();
            const neswPolygon =
                'POLYGON((' +
                [
                    [ne.lng, ne.lat],
                    [sw.lng, ne.lat],
                    [sw.lng, sw.lat],
                    [ne.lng, sw.lat],
                    [ne.lng, ne.lat],
                ]
                    .map((v) => v.join(' '))
                    .join(',') +
                '))';

            let selectBGLJSON = await (async () => {
                const SELECT: any = {
                    text: `accession, attribute_name, attribute_value, ST_Y(lat_lon) as lat, ST_X(lat_lon) as lon, elevation, gm4326_id, gp4326_wwf_tew_id
                    FROM bgl_gm4326_gp4326
                    ${getWhereClause(palmprintOnly, identifiers)}
                    LIMIT 65536;`,
                };
                SELECT.deflate = btoa(
                    Array.from(deflate(SELECT.text))
                        .map((v) => String.fromCharCode(v))
                        .join(''),
                );

                let response: any = undefined;
                try {
                    response = await fetch(LOGAN_RDS_PROXY_LAMBDA_ENDPOINT, {
                        body: JSON.stringify({ SELECT: SELECT.deflate, array: true, deflate: true }),
                        headers: { Authorization: LOGAN_RDS_PROXY_LAMBDA_AUTHORIZATION_HEADER },
                        method: 'POST',
                    });
                } catch (error) {
                    console.error(error);
                }

                if (response && response.status === 200) {
                    let json = await response.json();

                    json.result = arrayMapColumns(json.result, [
                        'accession',
                        'attribute_name',
                        'attribute_value',
                        'lat',
                        'lon',
                        'elevation',
                        'gm4326_id',
                        'gp4326_wwf_tew_id',
                    ]);

                    return json;
                }
            })();

            if (!selectBGLJSON || !selectBGLJSON.result) selectBGLJSON = { result: [] };

            selectBGLJSON.result = pickMostRelevantGeographicalAttibute(selectBGLJSON.result) ?? [];

            const selectPalmVirome = await (async () => {
                const SELECT: any = {
                    text: `run, bio_sample, palm_id, sotu
                    FROM (SELECT DISTINCT(accession)
                        FROM (SELECT accession
                            FROM bgl_gm4326_gp4326
                            ${getWhereClause(palmprintOnly, identifiers)}
                            LIMIT 65536)) AS t
                    JOIN palm_virome ON t.accession = palm_virome.bio_sample;`,
                };
                SELECT.deflate = btoa(
                    Array.from(deflate(SELECT.text))
                        .map((v) => String.fromCharCode(v))
                        .join(''),
                );

                let response: any = undefined;
                try {
                    response = await fetch(LOGAN_RDS_PROXY_LAMBDA_ENDPOINT, {
                        body: JSON.stringify({ SELECT: SELECT.deflate, array: true, deflate: true }),
                        headers: { Authorization: LOGAN_RDS_PROXY_LAMBDA_AUTHORIZATION_HEADER },
                        method: 'POST',
                    });
                } catch (error) {
                    console.error(error);
                }

                if (response && response.status === 200) return await response.json();
            })();

            if (mapMode === 'CONTIGS') {
                const o = Object.fromEntries(selectBGLJSON.result.map((v) => [v.accession, v]));

                selectBGLJSON.result = (selectPalmVirome?.result ?? []).map((v) => ({
                    ...o[v[1]],
                    run: v[0],
                    palm_id: v[2],
                    sotu: v[3],
                }));
            }

            setLocationCount(new Set(selectBGLJSON.result.map((v) => v.attribute_value)).size);
            setHitCount(new Set(selectBGLJSON.result.map((v) => v.run)).size);
            setSiteCount(selectBGLJSON.result.length);
            setTopBiomes(aggregateArray128(selectBGLJSON.result.map((v) => v.gp4326_wwf_tew_id)));
            setTopCountries(aggregateArray128(selectBGLJSON.result.map((v) => v.gm4326_id)));

            const zoomDriftFactor = Math.pow(2, (16 - mlglMap.getZoom()) / 8) / 8000;

            mbOverlay.setProps({
                interleaved: true,
                layers: [
                    new (globalThis as any).deck.ScatterplotLayer({
                        data: selectBGLJSON.result,
                        getFillColor: (d) => {
                            if (!d.gp4326_wwf_tew_id) d.gp4326_wwf_tew_id = 'WWF_TEW_BIOME_99';

                            return WWF_TEW[d.gp4326_wwf_tew_id].rgb;
                        },
                        getPosition: (d) => {
                            const prng = splitmix32(cyrb128(d.accession)[0]);

                            return [
                                d.lon + gaussianRandom(prng) * zoomDriftFactor,
                                d.lat + gaussianRandom(prng) * zoomDriftFactor,
                                0,
                            ];
                        },
                        id: 'scatterplotLayer',
                        onClick: async (info, event) => {
                            if (info.object) {
                                setAttributeName(info.object.attribute_name);
                                setAttributeValue(info.object.attribute_value);

                                setBiomeID(info.object.gp4326_wwf_tew_id);
                                setBiosampleID(info.object.accession);

                                setCountryID(info.object.gm4326_id);

                                setLatLon([info.object.lat, info.object.lon].join(', '));

                                setElevation(info.object.elevation);

                                if (mapMode === 'CONTIGS') {
                                    setRunID(info.object.run);
                                    setPalmID(info.object.palm_id);
                                    setSOTU(info.object.sotu);

                                    const selectPalmViromeRun = await (async () => {
                                        let response: any = undefined;
                                        try {
                                            response = await fetch(LOGAN_RDS_PROXY_LAMBDA_ENDPOINT, {
                                                body: JSON.stringify({
                                                    SELECT:
                                                        "node_coverage, node_seq FROM palm_virome WHERE run = '" +
                                                        info.object.run +
                                                        "';",
                                                }),
                                                headers: { Authorization: LOGAN_RDS_PROXY_LAMBDA_AUTHORIZATION_HEADER },
                                                method: 'POST',
                                            });
                                        } catch (error) {
                                            console.error(error);
                                        }

                                        if (response && response.status === 200) return await response.json();
                                    })();

                                    setSequence(
                                        [
                                            '>' +
                                                info.object.run +
                                                '_' +
                                                info.object.sotu +
                                                '_coverage_' +
                                                selectPalmViromeRun.result[0].node_coverage,
                                            selectPalmViromeRun.result[0].node_seq.match(/.{1,30}/g),
                                            '',
                                        ]
                                            .flat()
                                            .join('\n'),
                                    );
                                }
                            }
                        },
                        opacity: 0.8,
                        pickable: true,
                        radiusMaxPixels: 16,
                        radiusMinPixels: 6,
                    }),
                ],
            });

            setPalmprintHitsCount(new Set(selectPalmVirome.result.map((v) => v[2])).size);

            const sOTUArray = selectPalmVirome.result.map((v) => v[3]);
            setSOTUCount(new Set(sOTUArray).size);
            setTopSOTUs(aggregateArray128(sOTUArray));
        }

        --DeckGLRenderScatterplot.n;

        if (!DeckGLRenderScatterplot.n) delete DeckGLRenderScatterplot.n;
    });
};

const MapLibreDeckGLMap = ({ identifiers, layout, palmprintOnly, style = {}, module = "" }) => {
    style = {
        ...{ height: '100%', position: 'relative', width: '100%' },
        ...style,
    };

    const mapRef = useRef(null);
    const mlglMapRef = useRef<any>(null);
    const biomesRef = useRef<HTMLDivElement>(null);
    const countriesRef = useRef<HTMLDivElement>(null);
    const sOTUsRef = useRef<HTMLDivElement>(null);
    const [attributeName, setAttributeName] = useState('');
    const [attributeValue, setAttributeValue] = useState('');
    const [biomeID, setBiomeID] = useState('');
    const [bioprojectID, setBioprojectID] = useState('');
    const [bioprojectName, setBioprojectName] = useState('');
    const [bioprojectTitle, setBioprojectTitle] = useState('');
    const [biosampleID, setBiosampleID] = useState('');
    const [biosampleTitle, setBiosampleTitle] = useState('');
    const [countryID, setCountryID] = useState('');
    const [countryRegionID, setCountryRegionID] = useState('');
    const [elevation, setElevation] = useState('');
    const [hitCount, setHitCount] = useState(0);
    const [latLon, setLatLon] = useState('');
    const [locationCount, setLocationCount] = useState(0);
    const [mapMode, setMapMode] = useState('CONTIGS');
    const [palmID, setPalmID] = useState('');
    const [palmprintHitsCount, setPalmprintHitsCount] = useState(0);
    const [runID, setRunID] = useState('');
    const [sequence, setSequence] = useState('');
    const [sOTU, setSOTU] = useState('');
    const [sOTUCount, setSOTUCount] = useState(0);
    const [siteCount, setSiteCount] = useState(0);
    const [topBiomes, setTopBiomes] = useState([]);
    const [topCountries, setTopCountries] = useState([]);
    const [topSOTUs, setTopSOTUs] = useState([]);

    useEffect(() => {
        if (mapRef.current && globalThis.maplibregl && globalThis.deck) {
            const mapRefCurrentUnsafe = mapRef.current as any;

            const mapDiv = mapRefCurrentUnsafe.appendChild(document.createElement('div'));
            Object.assign(mapDiv.style, {
                height: '100%',
                width: '100%',
                borderRadius: '8px',
            });
            const mlglMap = new (globalThis as any).maplibregl.Map({
                center: [15.529, 43.8234],
                container: mapDiv,
                style:
                    // OpenDataStandardDarkMap, OpenDataVisualizationLightMap, OpenDataVisualizationDarkMap, ESRIDarkGreyMap
                    'https://maps.geo.us-east-1.amazonaws.com/maps/v0/maps/OpenDataVisualizationLightMap/style-descriptor?key=' +
                    AMAZON_LOCATION_API_KEY,
                zoom: 0.8,
            });
            mlglMapRef.current = mlglMap;
            mlglMap.dragRotate.disable();
            mlglMap.getCanvas().style.cursor = 'crosshair';

            const mbOverlay = new (globalThis as any).deck.MapboxOverlay({ interleaved: true });
            mlglMap.addControl(mbOverlay);

            const renderScatterplot = () =>
                DeckGLRenderScatterplot({
                    identifiers,
                    mapMode,
                    mbOverlay,
                    mlglMap,
                    palmprintOnly,
                    setAttributeName,
                    setAttributeValue,
                    setBiomeID,
                    setBioprojectID,
                    setBiosampleID,
                    setCountryID,
                    setElevation,
                    setHitCount,
                    setLatLon,
                    setLocationCount,
                    setPalmID,
                    setPalmprintHitsCount,
                    setRunID,
                    setSequence,
                    setSOTU,
                    setSOTUCount,
                    setSiteCount,
                    setTopBiomes,
                    setTopCountries,
                    setTopSOTUs,
                });

            if (MAPLIBREDECKGLMAP_FETCH_DATA_ON_VIEWPORT_CHANGE) mlglMap.on('moveend', renderScatterplot);
            renderScatterplot();

            return () => {
                mlglMap.remove();

                mapDiv.remove();
            };
        }
    }, [identifiers, mapMode]);

    useEffect(() => {
        if (bioprojectID)
            selectBioproject(bioprojectID).then((data) => {
                if (data) {
                    setBioprojectName(data.name || '');
                    setBioprojectTitle(data.title || '');
                }
            });
        else {
            setBioprojectName('');
            setBioprojectTitle('');
        }
    }, [bioprojectID]);

    useEffect(() => {
        if (biosampleID) {
            bioprojectIDFromBiosample(biosampleID).then(setBioprojectID);

            selectBiosample(biosampleID).then((data) => {
                if (data) setBiosampleTitle(data.title || '');
            });
        } else {
            setBioprojectID('');
            setBiosampleTitle('');
        }
    }, [biosampleID]);

    useEffect(() => {
        if (countryID)
            setCountryRegionID(Object.keys(REGION_COUNTRIES).filter((k) => REGION_COUNTRIES[k].includes(countryID))[0]);
        else if (biomeID === 'WWF_TEW_BIOME_98' || biomeID === 'WWF_TEW_BIOME_99') setCountryRegionID('Ocean');
        else setCountryRegionID('');
    }, [biomeID, countryID]);

    const handleExport = useCallback(() => {
        const canvas = mlglMapRef.current?.getCanvas();
        if (canvas) exportCanvasToPNG(canvas, `open-virome-${module || 'Ecology'}-MapLibreDeckGLMap.png`);
    }, [module]);

    const handleExportBiomes = useCallback(() => {
        if (biomesRef.current) exportElementToPNG(biomesRef.current, `open-virome-${module || 'Ecology'}-TopBiomes.png`);
    }, [module]);

    const handleExportCountries = useCallback(() => {
        if (countriesRef.current) exportElementToPNG(countriesRef.current, `open-virome-${module || 'Ecology'}-TopCountries.png`);
    }, [module]);

    const handleExportSOTUs = useCallback(() => {
        if (sOTUsRef.current) exportElementToPNG(sOTUsRef.current, `open-virome-${module || 'Ecology'}-TopSOTUs.png`);
    }, [module]);

    const MapLibreDeckGLMapModeButton: any = ({ onClick, selected, text }) => (
        <div
            onClick={onClick}
            style={{
                backgroundColor: selected ? '#90CAF9' : '#FFF',
                borderRadius: '4px',
                color: '#000',
                cursor: 'pointer',
                display: 'inline',
                fontSize: '14px',
                fontWeight: 700,
                padding: '4px 6px 4px 6px',
                userSelect: 'none',
            }}
        >
            {text}
        </div>
    );

    return (
        <div style={style}>
            <div style={{ alignItems: 'flex-end', display: 'flex', padding: '0 6px 0 6px' }}>
                <div style={{ flex: '1 0' }}>
                    <div style={{ color: '#333', fontSize: '16px', fontWeight: 700 }}>
                        {'Showing ' +
                            siteCount.toLocaleString() +
                            ' contigs, representing ' +
                            sOTUCount.toLocaleString() +
                            ' unique species (sOTUs) from ' +
                            hitCount.toLocaleString() +
                            ' runs, across ' +
                            locationCount.toLocaleString() +
                            ' unique geographic locations.'}
                    </div>
                    {siteCount >= 1024 * 64 && (
                        <div style={{ color: '#FA0', flex: '1 0', fontSize: '14px', fontWeight: 700 }}>
                            The number of sites displayed is limited to 65.536. Download the dataset to get the whole
                            list.
                        </div>
                    )}
                </div>
                {!isSimpleLayout(layout) && (
                    <div
                        style={{
                            alignItems: 'flex-end',
                            bottom: '2px',
                            display: 'flex',
                            gap: '8px',
                            height: '16px',
                            position: 'relative',
                        }}
                    >
                        <div style={{ bottom: '1px', position: 'relative' }}>Show:</div>
                        <MapLibreDeckGLMapModeButton
                            onClick={() => setMapMode('CONTIGS')}
                            selected={mapMode === 'CONTIGS'}
                            text='Contigs'
                        />
                        <MapLibreDeckGLMapModeButton
                            onClick={() => setMapMode('SAMPLES')}
                            selected={mapMode === 'SAMPLES'}
                            text='Samples'
                        />
                        <ExportButton onClick={handleExport} />
                    </div>
                )}
            </div>
            <div ref={mapRef} style={{ height: '70vh', margin: '8px 0 0 0', position: 'relative', width: '100%' }}>
                <div
                    style={{
                        display: biosampleID ? 'flex' : 'none',
                        flexDirection: 'column',
                        gap: '8px',
                        height: '94%',
                        overflowY: 'scroll',
                        position: 'absolute',
                        right: '8px',
                        top: '8px',
                        width: '384px',
                        zIndex: 1,
                    }}
                >
                    <MapLibreDeckGLMapTooltipSection>
                        <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>RUN METADATA</div>
                        <div
                            style={{
                                backgroundColor: '#CCC',
                                height: '1px',
                                margin: '4px 0 4px 0',
                                width: '100%',
                            }}
                        ></div>
                        <div style={{ height: '4px' }}></div>
                        {mapMode === 'CONTIGS' && (
                            <>
                                <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>RUN ID</div>
                                <div
                                    style={{
                                        color: '#CCC',
                                        display: 'inline',
                                        fontSize: '16px',
                                        fontWeight: 700,
                                    }}
                                >
                                    {runID}
                                </div>
                                <div
                                    style={{
                                        alignItems: 'flex-end',
                                        display: 'inline-flex',
                                        gap: '8px',
                                        margin: '0 0 0 8px',
                                        position: 'relative',
                                        top: '2px',
                                    }}
                                >
                                    <MapLibreDeckGLMapCopyButton onClick={() => navigator.clipboard.writeText(runID)} />
                                    <MapLibreDeckGLMapURLButton
                                        href={'https://www.ncbi.nlm.nih.gov/sra/?term=' + runID}
                                    />
                                </div>
                            </>
                        )}
                        <div style={{ height: '8px' }}></div>
                        <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>BIOSAMPLE</div>
                        <div
                            style={{
                                color: '#CCC',
                                display: 'inline',
                                fontSize: '16px',
                                fontWeight: 700,
                            }}
                        >
                            {biosampleID}
                        </div>
                        <div
                            style={{
                                alignItems: 'flex-end',
                                display: 'inline-flex',
                                gap: '8px',
                                margin: '0 0 0 8px',
                                position: 'relative',
                                top: '2px',
                            }}
                        >
                            <MapLibreDeckGLMapCopyButton onClick={() => navigator.clipboard.writeText(biosampleID)} />
                            <MapLibreDeckGLMapURLButton
                                href={'https://www.ncbi.nlm.nih.gov/biosample/?term=' + biosampleID}
                            />
                        </div>
                        <div style={{ margin: '2px 0 0 0' }}>
                            {biosampleID ? <div style={{ fontSize: '14px' }}>{biosampleTitle}</div> : '\u200B'}
                        </div>
                        <div style={{ height: '8px' }}></div>
                        <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>BIOPROJECT</div>
                        <div
                            style={{
                                color: '#CCC',
                                display: 'inline',
                                fontSize: '16px',
                                fontWeight: 700,
                            }}
                        >
                            {bioprojectID}
                        </div>
                        <div
                            style={{
                                alignItems: 'flex-end',
                                display: 'inline-flex',
                                gap: '8px',
                                margin: '0 0 0 8px',
                                position: 'relative',
                                top: '2px',
                            }}
                        >
                            <MapLibreDeckGLMapCopyButton onClick={() => navigator.clipboard.writeText(bioprojectID)} />
                            <MapLibreDeckGLMapURLButton
                                href={'https://www.ncbi.nlm.nih.gov/bioproject/?term=' + bioprojectID}
                            />
                        </div>
                        <div style={{ margin: '2px 0 0 0' }}>
                            {biosampleID ? <div style={{ fontSize: '14px' }}>{biosampleTitle}</div> : '\u200B'}
                        </div>
                        <div style={{ margin: '2px 0 0 0' }}>
                            {bioprojectID ? (
                                <>
                                    <div style={{ fontSize: '14px' }}>{bioprojectName}</div>
                                    <div style={{ fontSize: '14px' }}>{bioprojectTitle}</div>
                                </>
                            ) : (
                                '\u200B'
                            )}
                        </div>
                        <div style={{ height: '4px' }}></div>
                    </MapLibreDeckGLMapTooltipSection>
                    {!isSimpleLayout(layout) && (
                        <>
                            <MapLibreDeckGLMapTooltipSection>
                                <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>
                                    GEOGRAPHICAL FEATURES
                                </div>
                                <div
                                    style={{
                                        backgroundColor: '#CCC',
                                        height: '1px',
                                        margin: '4px 0 4px 0',
                                        width: '100%',
                                    }}
                                ></div>
                                <div style={{ height: '4px' }}></div>
                                <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>ATTRIBUTE NAME</div>
                                <div style={{ fontSize: '14px', margin: '2px 0 0 0' }}>
                                    {truncate(attributeName + ': ' + attributeValue, 40)}
                                </div>
                                <div style={{ height: '8px' }}></div>
                                <div></div>
                                <div style={{ alignItems: 'baseline', display: 'flex' }}>
                                    <div style={{ flex: '1 0' }}>
                                        <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>
                                            <span>LAT / LON</span>
                                            <div
                                                style={{
                                                    alignItems: 'flex-end',
                                                    display: 'inline-flex',
                                                    gap: '8px',
                                                    margin: '0 0 0 8px',
                                                    position: 'relative',
                                                    top: '2px',
                                                }}
                                            >
                                                <MapLibreDeckGLMapCopyButton
                                                    onClick={() => navigator.clipboard.writeText(latLon)}
                                                />
                                                <MapLibreDeckGLMapURLButton
                                                    href={'https://www.google.com/maps/search/?api=1&query=' + latLon}
                                                />
                                            </div>
                                        </div>
                                        <div style={{ fontSize: '14px', margin: '2px 0 0 0' }}>{latLon}</div>
                                    </div>
                                    {elevation && (
                                        <div style={{ flex: '1 0' }}>
                                            <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>
                                                <span>ELEVATION</span>
                                            </div>
                                            <div style={{ margin: '0 0 0 0' }}>
                                                <span style={{ fontSize: '14px' }}>{elevation}</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                                <div style={{ height: '8px' }}></div>
                                <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>
                                    <span style={{ verticalAlign: 'middle' }}>BIOME</span>
                                    <span
                                        style={{
                                            backgroundColor: biomeID ? WWF_TEW[biomeID].hex : 'transparent',
                                            display: 'inline-block',
                                            height: '14px',
                                            fontSize: '14px',
                                            margin: '0 0 0 8px',
                                            verticalAlign: 'middle',
                                            width: '64px',
                                        }}
                                    />
                                </div>
                                <div style={{ margin: '2px 0 0 0' }}>
                                    <span style={{ fontSize: '14px' }}>{biomeID && WWF_TEW[biomeID].name}</span>
                                </div>
                                <div style={{ height: '8px' }}></div>
                                <div style={{ display: 'flex' }}>
                                    {countryID && (
                                        <div style={{ flex: '1 0' }}>
                                            <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>
                                                <span>COUNTRY</span>
                                            </div>
                                            <div style={{ margin: '2px 0 0 0' }}>
                                                <Flag
                                                    code={countryID}
                                                    height='16'
                                                    style={{ verticalAlign: 'middle' }}
                                                />
                                                <span
                                                    style={{
                                                        fontSize: '14px',
                                                        margin: '0 0 0 8px',
                                                        verticalAlign: 'middle',
                                                    }}
                                                >
                                                    {countryID}
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                    <div style={{ flex: '1 0' }}>
                                        <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>
                                            <span>REGION</span>
                                        </div>
                                        <div style={{ margin: '2px 0 0 0' }}>
                                            <span style={{ fontSize: '14px' }}>{countryRegionID}</span>
                                        </div>
                                    </div>
                                </div>
                                <div style={{ height: '8px' }}></div>
                            </MapLibreDeckGLMapTooltipSection>
                            {mapMode === 'CONTIGS' && (
                                <MapLibreDeckGLMapTooltipSection>
                                    <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>
                                        CONTIG CLASSIFICATION
                                    </div>
                                    <div
                                        style={{
                                            backgroundColor: '#CCC',
                                            height: '1px',
                                            margin: '4px 0 4px 0',
                                            width: '100%',
                                        }}
                                    ></div>
                                    <div style={{ height: '4px' }}></div>
                                    <div style={{ display: 'flex' }}>
                                        <div style={{ flex: '1 0' }}>
                                            <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>
                                                PALM ID
                                            </div>
                                            <div style={{ fontSize: '14px', margin: '2px 0 0 0' }}>{palmID}</div>
                                        </div>
                                        <div style={{ flex: '1 0' }}>
                                            <div style={{ color: '#CCC', fontSize: '12px', fontWeight: 700 }}>sOTU</div>
                                            <div style={{ fontSize: '14px', margin: '2px 0 0 0' }}>{sOTU}</div>
                                        </div>
                                    </div>
                                    <div style={{ height: '8px' }}></div>
                                    <div
                                        style={{
                                            color: '#CCC',
                                            display: 'inline',
                                            fontSize: '12px',
                                            fontWeight: 700,
                                            margin: '0 0 0 4px',
                                        }}
                                    >
                                        <div style={{ display: 'inline', verticalAlign: 'top' }}>
                                            SEQUENCE [BLAST
                                            <MapLibreDeckGLMapURLButton
                                                fontSize='16px'
                                                href={
                                                    'https://blast.ncbi.nlm.nih.gov/Blast.cgi?PAGE_TYPE=BlastSearch&USER_FORMAT_DEFAULTS=on&SET_SAVED_SEARCH=true&PAGE=Proteins&PROGRAM=blastp&QUERY=' +
                                                    sequence.split(/\n/).slice(1).join('') +
                                                    '&JOB_TITLE=' +
                                                    sequence.split(/\n/)[0].substring(1) +
                                                    '&GAPCOSTS=11%201&DATABASE=nr&BLAST_PROGRAMS=blastp&MAX_NUM_SEQ=100&SHORT_QUERY_ADJUST=on&EXPECT=0.05&WORD_SIZE=6&MATRIX_NAME=BLOSUM62&COMPOSITION_BASED_STATISTICS=2&PROG_DEFAULTS=on&SHOW_OVERVIEW=on&SHOW_LINKOUT=on&ALIGNMENT_VIEW=Pairwise&MASK_CHAR=2&MASK_COLOR=1&GET_SEQUENCE=on&NEW_VIEW=on&NUM_OVERVIEW=100&DESCRIPTIONS=100&ALIGNMENTS=100&FORMAT_OBJECT=Alignment&FORMAT_TYPE=HTML'
                                                }
                                            />
                                            ]
                                        </div>
                                    </div>
                                    <textarea
                                        rows='4'
                                        style={{
                                            backgroundColor: 'transparent',
                                            color: '#FFF',
                                            fontSize: '14px',
                                            margin: '2px 0 0 0',
                                            overflowWrap: 'normal',
                                            padding: '4px 4px 4px 4px',
                                            resize: 'none',
                                            width: '100%',
                                        }}
                                        value={sequence}
                                    />
                                </MapLibreDeckGLMapTooltipSection>
                            )}
                        </>
                    )}
                </div>
            </div>
            {!isSimpleLayout(layout) && (
                <div style={{ display: 'flex', gap: '24px', margin: '16px 0 0 0', padding: '0 8px 0 8px' }}>
                    <div style={{ flex: '1 0', position: 'relative' }} ref={biomesRef}>
                        <div style={{ position: 'absolute', right: 4, top: 0, zIndex: 10 }}>
                            <ExportButton onClick={handleExportBiomes} />
                        </div>
                        <div style={{ color: '#CCC', fontSize: '14px', fontWeight: 700 }}>Top Biomes</div>
                        <div
                            style={{ backgroundColor: '#CCC', height: '1px', margin: '4px 0 4px 0', width: '100%' }}
                        ></div>
                        {topBiomes.length && (
                            <div
                                style={{
                                    display: 'flex',
                                    fontSize: '14px',
                                    gap: '12px',
                                    maxHeight: '256px',
                                    overflowY: 'scroll',
                                }}
                            >
                                <div style={{ flex: '0 0' }}>
                                    {topBiomes.map(
                                        (v, i) =>
                                            v[0] != 'null' && (
                                                <div
                                                    key={i}
                                                    style={{
                                                        height: 'calc(48px + 2px)',
                                                        fontSize: '14px',
                                                        lineHeight: '15px',
                                                        margin: '4px 0 0 0',
                                                        overflow: 'hidden',
                                                        textAlign: 'right',
                                                        textOverflow: 'ellipsis',
                                                        width: '128px',
                                                    }}
                                                >
                                                    <span style={{ position: 'relative', top: '2px' }}>
                                                        {WWF_TEW[v[0]].name}
                                                    </span>
                                                </div>
                                            ),
                                    )}
                                </div>
                                <div style={{ flex: '0 0' }}>
                                    {topBiomes.map(
                                        (v, i) =>
                                            v[0] != 'null' && (
                                                <div
                                                    key={i}
                                                    style={{
                                                        height: 'calc(48px + 2px)',
                                                        fontSize: '14px',
                                                        fontWeight: 700,
                                                        lineHeight: '18px',
                                                        margin: '4px 0 0 0',
                                                        position: 'relative',
                                                        textAlign: 'center',
                                                        top: '4px',
                                                        width: '48px',
                                                    }}
                                                >
                                                    <div>{v[1].toLocaleString()}</div>
                                                    <div style={{ left: '1px', position: 'relative' }}>
                                                        {((v[1] / siteCount) * 100).toFixed(2) + '%'}
                                                    </div>
                                                </div>
                                            ),
                                    )}
                                </div>
                                <div style={{ flex: '1 0' }}>
                                    {topBiomes.map(
                                        (v, i) =>
                                            v[0] != 'null' && (
                                                <div
                                                    key={i}
                                                    style={{
                                                        height: 'calc(48px + 2px)',
                                                        margin: '4px 0 0 0',
                                                        position: 'relative',
                                                    }}
                                                >
                                                    <div
                                                        style={{
                                                            backgroundColor: WWF_TEW[v[0]].hex,
                                                            height: '100%',
                                                            position: 'relative',
                                                            width: (v[1] / topBiomes[0][1]) * 100 + '%',
                                                        }}
                                                    ></div>
                                                </div>
                                            ),
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                    <div style={{ flex: '1 0', position: 'relative' }} ref={countriesRef}>
                        <div style={{ position: 'absolute', right: 4, top: 0, zIndex: 10 }}>
                            <ExportButton onClick={handleExportCountries} />
                        </div>
                        <div style={{ color: '#CCC', fontSize: '14px', fontWeight: 700 }}>Top Countries</div>
                        <div
                            style={{ backgroundColor: '#CCC', height: '1px', margin: '4px 0 4px 0', width: '100%' }}
                        ></div>
                        {topCountries.length && (
                            <div
                                style={{
                                    display: 'flex',
                                    fontSize: '14px',
                                    gap: '12px',
                                    maxHeight: '256px',
                                    overflowY: 'scroll',
                                }}
                            >
                                <div style={{ flex: '0 0' }}>
                                    {topCountries.map(
                                        (v, i) =>
                                            v[0] !== 'null' && (
                                                <div
                                                    key={i}
                                                    style={{
                                                        height: 'calc(48px + 2px)',
                                                        margin: '4px 0 0 0',
                                                        textAlign: 'right',
                                                        width: '48px',
                                                    }}
                                                >
                                                    <div style={{ position: 'relative', top: '2px' }}>{v[0]}</div>
                                                    <Flag
                                                        code={v[0]}
                                                        height='14'
                                                        style={{
                                                            margin: '0 0 0 4px',
                                                            verticalAlign: 'middle',
                                                            width: '24px',
                                                        }}
                                                    />
                                                </div>
                                            ),
                                    )}
                                </div>
                                <div style={{ flex: '0 0' }}>
                                    {topCountries.map(
                                        (v, i) =>
                                            v[0] != 'null' && (
                                                <div
                                                    key={i}
                                                    style={{
                                                        height: 'calc(48px + 2px)',
                                                        fontSize: '14px',
                                                        fontWeight: 700,
                                                        lineHeight: '18px',
                                                        margin: '4px 0 0 0',
                                                        position: 'relative',
                                                        textAlign: 'center',
                                                        top: '4px',
                                                        width: '48px',
                                                    }}
                                                >
                                                    <div>{v[1].toLocaleString()}</div>
                                                    <div style={{ left: '1px', position: 'relative' }}>
                                                        {((v[1] / siteCount) * 100).toFixed(2) + '%'}
                                                    </div>
                                                </div>
                                            ),
                                    )}
                                </div>
                                <div style={{ flex: '1 0' }}>
                                    {topCountries.map(
                                        (v, i) =>
                                            v[0] !== 'null' && (
                                                <div
                                                    key={i}
                                                    style={{
                                                        height: 'calc(48px + 2px)',
                                                        margin: '4px 0 0 0',
                                                        position: 'relative',
                                                    }}
                                                >
                                                    <div
                                                        style={{
                                                            backgroundColor: '#AAA',
                                                            height: '100%',
                                                            position: 'relative',
                                                            width: (v[1] / topCountries[0][1]) * 100 + '%',
                                                        }}
                                                    ></div>
                                                </div>
                                            ),
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                    <div style={{ flex: '1 0', position: 'relative' }} ref={sOTUsRef}>
                        <div style={{ position: 'absolute', right: 4, top: 0, zIndex: 10 }}>
                            <ExportButton onClick={handleExportSOTUs} />
                        </div>
                        <div style={{ color: '#CCC', fontSize: '14px', fontWeight: 700 }}>Top sOTUs</div>
                        <div
                            style={{ backgroundColor: '#CCC', height: '1px', margin: '4px 0 4px 0', width: '100%' }}
                        ></div>
                        {topSOTUs.length && (
                            <div
                                style={{
                                    display: 'flex',
                                    fontSize: '14px',
                                    gap: '12px',
                                    maxHeight: '256px',
                                    overflowY: 'scroll',
                                }}
                            >
                                <div style={{ flex: '0 0' }}>
                                    {topSOTUs.map((v, i) => (
                                        <div
                                            key={i}
                                            style={{
                                                height: 'calc(48px + 2px)',
                                                margin: '4px 0 0 0',
                                                textAlign: 'right',
                                            }}
                                        >
                                            <span style={{ position: 'relative', top: '2px' }}>{v[0]}</span>
                                        </div>
                                    ))}
                                </div>
                                <div style={{ flex: '0 0' }}>
                                    {topSOTUs.map(
                                        (v, i) =>
                                            v[0] != 'null' && (
                                                <div
                                                    key={i}
                                                    style={{
                                                        height: 'calc(48px + 2px)',
                                                        fontSize: '14px',
                                                        fontWeight: 700,
                                                        lineHeight: '18px',
                                                        margin: '4px 0 0 0',
                                                        position: 'relative',
                                                        textAlign: 'center',
                                                        top: '4px',
                                                        width: '48px',
                                                    }}
                                                >
                                                    <div>{v[1].toLocaleString()}</div>
                                                    <div style={{ left: '1px', position: 'relative' }}>
                                                        {((v[1] / sOTUCount) * 100).toFixed(2) + '%'}
                                                    </div>
                                                </div>
                                            ),
                                    )}
                                </div>
                                <div style={{ flex: '1 0' }}>
                                    {topSOTUs.map((v, i) => (
                                        <div
                                            key={i}
                                            style={{
                                                height: 'calc(48px + 2px)',
                                                margin: '4px 0 0 0',
                                                position: 'relative',
                                            }}
                                        >
                                            <div
                                                style={{
                                                    backgroundColor: '#AAA',
                                                    height: '100%',
                                                    position: 'relative',
                                                    width: (v[1] / topSOTUs[0][1]) * 100 + '%',
                                                }}
                                            ></div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

const MapLibreDeckGLMapCopyButton = ({ ...props }) => (
    <MdCopyAll
        style={{
            color: '#333',
            cursor: 'pointer',
            fontSize: '16px',
            userSelect: 'none',
        }}
        {...props}
    />
);
const MapLibreDeckGLMapURLButton = ({ fontSize, ...props }) => {
    if (!fontSize) fontSize = '18px';

    return (
        <a style={{ color: '#333', userSelect: 'none' }} target='_blank' {...props}>
            <MdOpenInNew style={{ fontSize, verticalAlign: 'bottom' }} />
        </a>
    );
};

const MapLibreDeckGLMapTooltipSection = ({ children, ...props }) => {
    return (
        <div
            style={{
                backgroundColor: 'rgba(18, 18, 18, 0.8)',
                borderRadius: '6px',
                color: '#FFF',
                padding: '12px 16px 12px 16px',
            }}
            {...props}
        >
            {children}
        </div>
    );
};

export default MapLibreDeckGLMap;
