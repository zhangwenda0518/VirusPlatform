import React, { useState, useEffect } from 'react';
import { moduleConfig } from '../../Module/constants.ts';

import CrossIcon from '@mui/icons-material/Clear';
import PagedTable from '../../../common/PagedTable.tsx';
import Link from '@mui/material/Link';
import MdOpenInNew from '@mui/icons-material/OpenInNew';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';

const ViromeSummaryTable = ({ activeModule, selectedItem, onClose, rows, maxWidth }) => {
    const [page, setPage] = useState(0);
    const isRun = selectedItem?.type === 'run';
    const isVirus = selectedItem?.type === 'virus';
    const isEdge = selectedItem?.isNode === false;

    useEffect(() => {
        setPage(0);
    }, [rows, selectedItem]);

    let title = '';
    const renderTitle = () => {
        if (isRun) {
            // Add Link to SRA website for SRA / BioProject
            // Retrieve BioProject for Run
            // TODO: Display BioProject "Title" below in small text
            title = `Run: ${selectedItem?.id} | ${getSciName()}`;
        }
        if (isVirus) {
            title = `Virus: ${selectedItem?.id}`;
        }
        if (isEdge) {
            title = `${selectedItem?.source} ⇔ ${selectedItem?.target}`;
        }
        return <Typography variant='h6'>{title}</Typography>;
    };

    if (!selectedItem) {
        return null;
    }

    const getResultTableRows = () => {
        if (isRun) {
            return rows.filter((row) => row['run'] === selectedItem?.id);
        }
        if (isVirus) {
            const virusKey = moduleConfig[activeModule].groupByKey;
            return rows.filter((row) => row[virusKey] === selectedItem?.id);
        }
        if (isEdge) {
            const virusKey = moduleConfig[activeModule].groupByKey;
            return rows.filter((row) => row['run'] === selectedItem?.source && row[virusKey] === selectedItem?.target);
        }
        return [];
    };

    const getSciName = () => {
        const filteredRows = getResultTableRows();
        const runBioSample = filteredRows[0];
        return runBioSample['scientific_name'];
    };

    /*const getBiosample = () => {
        const filteredRows = getResultTableRows();
        const runBioSample = filteredRows[0];
        return (runBioSample['bio_sample']);
    };

    const getBioproject = () => {
        const filteredRows = getResultTableRows();
        const runBioProject = filteredRows[0];
        return (runBioProject['bio_project']);
    };*/

    const renderNodeSummary = () => {
        if (isRun) {
            return renderRunSummary();
        }
        if (isVirus) {
            return renderVirusSummary();
        }
        if (isEdge) {
            return renderContigSummary();
        }
        return [];
    };
    //| bioSample: ${getBiosample()} | bioProject: ${getBioproject()}
    const renderRunSummary = () => {
        const filteredRows = getResultTableRows();
        const firstRow = filteredRows[0];
        const runBioSample = firstRow['bio_sample'];
        const runBioProject = firstRow['bio_project'];
        return (
            <>
                {/*Summary Table Box*/}
                <Box
                    sx={{
                        display: 'flex',
                        flexDirection: 'row',
                        justifyContent: 'space-between',
                        alignItems: 'space-between',
                        width: '100%',
                        mt: 0,
                    }}
                >
                    {/*bioSample Stats*/}
                    {/*TODO: retrieve bioSample title and display under link*/}
                    <Box sx={{ display: 'flex', flex: 1, flexBasis: '50%', maxWidth: '45%' }}>
                        <Typography variant='body'>{`bioSample: `}</Typography>
                        <Link
                            sx={{
                                alignItems: 'center',
                                flexDirection: 'column',
                                textDecoration: 'none',
                            }}
                            href={`https://www.ncbi.nlm.nih.gov/biosample/${runBioSample}`}
                            target='_blank'
                        >
                            <Typography variant='body'> &nbsp; {runBioSample}</Typography>
                            <MdOpenInNew fontSize='small' sx={{ mb: -0.5, ml: 0.5 }} />
                        </Link>
                    </Box>
                    {/*bioProject Stats*/}
                    {/*TODO: retrieve bioProject title and display under link*/}
                    <Box sx={{ display: 'flex', flex: 1, flexBasis: '50%', maxWidth: '45%' }}>
                        <Typography variant='body'>{`bioProject: `}</Typography>
                        <Link
                            sx={{
                                alignItems: 'center',
                                flexDirection: 'column',
                                textDecoration: 'none',
                            }}
                            href={`https://www.ncbi.nlm.nih.gov/bioproject/?term=${runBioProject}`}
                            target='_blank'
                        >
                            <Typography variant='body'> &nbsp; {runBioProject}</Typography>
                            <MdOpenInNew fontSize='small' sx={{ mb: -0.5, ml: 0.5 }} />
                        </Link>
                    </Box>
                </Box>
            </>
        );
    };

    const renderVirusSummary = () => {
        const filteredRows = getResultTableRows();
        const topPalmId = filteredRows.sort((a, b) => b['node_pid'] - a['node_pid'])[0];
        const topGenBankId = filteredRows.sort((a, b) => b['gb_pid'] - a['gb_pid'])[0];
        return (
            <>
                {/*Summary Table Box*/}
                <Box
                    sx={{
                        display: 'flex',
                        flexDirection: 'row',
                        justifyContent: 'space-between',
                        alignItems: 'space-between',
                        width: '100%',
                        mt: 0,
                    }}
                >
                    {/*GenBank Hit Stats*/}
                    <Box sx={{ flex: 1, flexBasis: '50%', maxWidth: '45%' }}>
                        <Typography variant='body'>{`Top GenBank Hit (${topGenBankId['gb_pid']}% aa id)`}</Typography>
                        <Typography sx={{ mt: 0.5 }} variant='body2'>
                            {`${topPalmId['tax_species']} ${topGenBankId['tax_family'] ? `(${topGenBankId['tax_family']})` : ''}`}
                        </Typography>
                        <Link
                            sx={{
                                display: 'flex',
                                alignItems: 'center',
                                flexDirection: 'row',
                                textDecoration: 'none',
                            }}
                            href={`https://www.ncbi.nlm.nih.gov/nuccore/${topGenBankId?.gb_acc}`}
                            target='_blank'
                        >
                            <Typography variant='body2'>{topGenBankId['gb_acc']}</Typography>
                            <MdOpenInNew fontSize='small' sx={{ mb: 0.5, ml: 0.5 }} />
                        </Link>
                    </Box>
                    {/*palmDB Hit Stats*/}
                    <Box sx={{ flex: 1, flexBasis: '50%', maxWidth: '45%' }}>
                        <Typography variant='body'>{`Top Palmprint Hit (${topPalmId['node_pid']}% aa id)`}</Typography>
                        <Typography
                            sx={{ mt: 0.5 }}
                            variant='body2'
                        >{`${topPalmId['palm_id']} - ${topPalmId['nickname']}`}</Typography>
                        <Link
                            sx={{
                                display: 'flex',
                                alignItems: 'center',
                                flexDirection: 'row',
                                textDecoration: 'none',
                            }}
                            href={`https://blast.ncbi.nlm.nih.gov/Blast.cgi?PAGE_TYPE=BlastSearch&USER_FORMAT_DEFAULTS=on&SET_SAVED_SEARCH=true&PAGE=Proteins&PROGRAM=blastp&QUERY=${topPalmId?.node_seq}&JOB_TITLE=palmID_${topPalmId?.palm_id}&GAPCOSTS=11%201&DATABASE=nr&BLAST_PROGRAMS=blastp&MAX_NUM_SEQ=100&SHORT_QUERY_ADJUST=on&EXPECT=0.05&WORD_SIZE=6&MATRIX_NAME=BLOSUM62&COMPOSITION_BASED_STATISTICS=2&PROG_DEFAULTS=on&SHOW_OVERVIEW=on&SHOW_LINKOUT=on&ALIGNMENT_VIEW=Pairwise&MASK_CHAR=2&MASK_COLOR=1&GET_SEQUENCE=on&NEW_VIEW=on&NUM_OVERVIEW=100&DESCRIPTIONS=100&ALIGNMENTS=100&FORMAT_OBJECT=Alignment&FORMAT_TYPE=HTML`}
                            target='_blank'
                        >
                            <Typography variant='body2'>BLAST</Typography>
                            <MdOpenInNew fontSize='small' sx={{ mb: 0.5, ml: 0.5 }} />
                        </Link>
                    </Box>
                </Box>
            </>
        );
    };

    const renderContigSummary = () => {
        const filteredRows = getResultTableRows();
        const contigRow = filteredRows[0];
        const contigRun = contigRow['run'];
        const contigSotu = contigRow['sotu'];
        const contigPalm = contigRow['palm_id'];
        const contigCoverage = contigRow['node_coverage'];
        var contigSeq = contigRow['node_seq'].replace(/(.{50})/g, `$1\n`);

        return (
            <>
                {/*Summary Table Box*/}
                <Box
                    sx={{
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        alignItems: 'space-between',
                        width: '100%',
                        mt: 0,
                    }}
                >
                    {/*Fasta Display*/}
                    <Box sx={{ flex: 1, flexBasis: '50%', maxWidth: '100%' }}>
                        <Typography fontFamily='monospace' variant='body'>
                            {`>${contigRun}_${contigSotu}_coverage_${contigCoverage}\n`}
                        </Typography>
                    </Box>
                    <Box sx={{ flex: 1, flexBasis: '50%', maxWidth: '100%' }}>
                        <Typography fontFamily='monospace' variant='body' whiteSpace='pre-wrap'>
                            {`${contigSeq}`}
                        </Typography>
                    </Box>
                    {/*BLAST Sequence*/}
                    <Box sx={{ flex: 1, mt: 2, flexBasis: '50%', maxWidth: '45%' }}>
                        <Link
                            sx={{
                                display: 'flex',
                                alignItems: 'center',
                                flexDirection: 'row',
                                textDecoration: 'none',
                            }}
                            href={`https://blast.ncbi.nlm.nih.gov/Blast.cgi?PAGE_TYPE=BlastSearch&USER_FORMAT_DEFAULTS=on&SET_SAVED_SEARCH=true&PAGE=Proteins&PROGRAM=blastp&QUERY=${contigSeq}&JOB_TITLE=${contigRun}_${contigPalm}&GAPCOSTS=11%201&DATABASE=nr&BLAST_PROGRAMS=blastp&MAX_NUM_SEQ=100&SHORT_QUERY_ADJUST=on&EXPECT=0.05&WORD_SIZE=6&MATRIX_NAME=BLOSUM62&COMPOSITION_BASED_STATISTICS=2&PROG_DEFAULTS=on&SHOW_OVERVIEW=on&SHOW_LINKOUT=on&ALIGNMENT_VIEW=Pairwise&MASK_CHAR=2&MASK_COLOR=1&GET_SEQUENCE=on&NEW_VIEW=on&NUM_OVERVIEW=100&DESCRIPTIONS=100&ALIGNMENTS=100&FORMAT_OBJECT=Alignment&FORMAT_TYPE=HTML`}
                            target='_blank'
                        >
                            <Typography variant='body2'>BLAST</Typography>
                            <MdOpenInNew fontSize='small' sx={{ mb: 0.5, ml: 0.5 }} />
                        </Link>
                    </Box>
                </Box>
            </>
        );
    };

    const getRowsPerPage = () => {
        return maxWidth > 700 ? 10 : 5;
    };

    const onPageChange = (event: unknown, newPage: number) => {
        setPage(newPage);
    };

    const getPagedRows = () => {
        const rowsPerPage = getRowsPerPage();
        const startIndex = page * rowsPerPage;
        const endIndex = startIndex + rowsPerPage;
        return getResultTableRows().slice(startIndex, endIndex);
    };

    const renderTable = () => {
        const filteredRows = getResultTableRows();
        return (
            <Box sx={{ mt: 2, maxWidth: maxWidth - 26 }}>
                <PagedTable
                    page={page}
                    onPageChange={onPageChange}
                    total={filteredRows.length}
                    rows={getPagedRows()}
                    headers={Object.keys(filteredRows[0])}
                    pageRows={getRowsPerPage()}
                    allRows={filteredRows}
                    module="Virome"
                />
            </Box>
        );
    };

    return !getResultTableRows()?.length > 0 ? (
        <Typography variant='h6'>No data available</Typography>
    ) : (
        // Virome Summary Box Pop-up
        <Box
            sx={{
                mt: 1,
                marginLeft: '10px',
                display: 'flex',
                flexDirection: 'column',
                width: '95%',
                height: '100%',
                backgroundColor: 'background.paper',
                borderRadius: 2,
                padding: 1.5,
            }}
        >
            {/*Node Display Name*/}
            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'left',
                    width: '100%',
                    mb: 1,
                }}
            >
                {renderTitle()}
                {/*TODO: Add "Maximize" button to make Table Full-screen*/}
                <Button
                    close-window
                    onClick={onClose}
                    sx={{
                        'minWidth': 12,
                        'justifySelf': 'flex-end',
                        'alignSelf': 'flex-start',
                        'backgroundColor': 'transparent',
                        '&:hover': {
                            backgroundColor: 'warning',
                        },
                    }}
                >
                    <CrossIcon />
                </Button>
            </Box>

            <Box sx={{ width: '100%' }}>
                {renderNodeSummary()}
                {renderTable()}
            </Box>
        </Box>
    );
};

export default ViromeSummaryTable;
