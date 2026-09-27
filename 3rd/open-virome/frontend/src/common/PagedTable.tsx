import * as React from 'react';
import Box from '@mui/material/Box';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import Paper from '@mui/material/Paper';
import { visuallyHidden } from '@mui/utils';
import ExportButton from '../common/ExportButton.tsx';
import { exportToCSV } from '../common/utils/exportHelpers.ts';

function descendingComparator<T>(a: T, b: T, orderBy: keyof T) {
    if (b[orderBy] < a[orderBy]) {
        return -1;
    }
    if (b[orderBy] > a[orderBy]) {
        return 1;
    }
    return 0;
}

type Order = 'asc' | 'desc';

function getComparator<Key extends keyof any>(
    order: Order,
    orderBy: Key,
): (a: { [key in Key]: number | string }, b: { [key in Key]: number | string }) => number {
    return order === 'desc'
        ? (a, b) => descendingComparator(a, b, orderBy)
        : (a, b) => -descendingComparator(a, b, orderBy);
}

// Since 2020 all major browsers ensure sort stability with Array.prototype.sort().
// stableSort() brings sort stability to non-modern browsers (notably IE11). If you
// only support modern browsers you can replace stableSort(exampleArray, exampleComparator)
// with exampleArray.slice().sort(exampleComparator)
function stableSort<T>(array, comparator: (a: T, b: T) => number) {
    const stabilizedThis = array.map((el, index) => [el, index] as [T, number]);
    stabilizedThis.sort((a, b) => {
        const order = comparator(a[0], b[0]);
        if (order !== 0) {
            return order;
        }
        return a[1] - b[1];
    });
    return stabilizedThis.map((el) => el[0]);
}

interface HeadCell {
    disablePadding: boolean;
    id: keyof Data;
    label: string;
    numeric: boolean;
}

interface EnhancedTableProps {
    headers: string[];
    onRequestSort: (event: React.MouseEvent<unknown>, property: keyof Data) => void;
    order: Order;
    orderBy: string;
}

function EnhancedTableHead(props: EnhancedTableProps) {
    const { headers, order, orderBy, onRequestSort } = props;
    const createSortHandler = (property: keyof Data) => (event: React.MouseEvent<unknown>) => {
        onRequestSort(event, property);
    };

    const headCells = headers.map((header) => ({
        id: header,
        numeric: false,
        disablePadding: false,
        label: header,
    }));

    return (
        <TableHead>
            <TableRow>
                {headCells.map((headCell) => (
                    <TableCell
                        key={headCell.id}
                        align={headCell.numeric ? 'right' : 'left'}
                        padding={headCell.disablePadding ? 'none' : 'normal'}
                        sortDirection={orderBy === headCell.id ? order : false}
                    >
                        <TableSortLabel
                            active={orderBy === headCell.id}
                            direction={orderBy === headCell.id ? order : 'asc'}
                            onClick={createSortHandler(headCell.id)}
                        >
                            {headCell.label}
                            {orderBy === headCell.id ? (
                                <Box component='span' sx={visuallyHidden}>
                                    {order === 'desc' ? 'sorted descending' : 'sorted ascending'}
                                </Box>
                            ) : null}
                        </TableSortLabel>
                    </TableCell>
                ))}
            </TableRow>
        </TableHead>
    );
}

const PagedTable = ({ page = 0, rows = [], headers = [], total, onPageChange, pageRows = 10, allRows = null, onExportAll = null, module = "" }) => {
    const [order, setOrder] = React.useState<Order>('asc');
    const [orderBy, setOrderBy] = React.useState('calories');
    const [dense, setDense] = React.useState(true);
    const [rowsPerPage, setRowsPerPage] = React.useState(pageRows);
    const [exporting, setExporting] = React.useState(false);

    const onRequestSort = (event: React.MouseEvent<unknown>, property: keyof Data) => {
        const isAsc = orderBy === property && order === 'asc';
        setOrder(isAsc ? 'desc' : 'asc');
        setOrderBy(property);
    };

    // Avoid a layout jump when reaching the last page with empty rows.
    const emptyRows = rows.length < rowsPerPage ? Math.max(0, rowsPerPage - rows.length) : 0;

    const visibleRows = React.useMemo(
        () => stableSort(rows, getComparator(order, orderBy)),
        [order, orderBy, page, rowsPerPage, rows],
    );

    const hasAllData = allRows && allRows.length > 0;
    const hasExportAllHandler = !!onExportAll;

    const handleExport = React.useCallback(async () => {
        if (onExportAll) {
            setExporting(true);
            try {
                await onExportAll();
            } finally {
                setExporting(false);
            }
        } else if (hasAllData) {
            exportToCSV(allRows, headers, `open-virome-${module || 'SRA'}-PagedTable.csv`);
        } else {
            exportToCSV(rows, headers, `open-virome-${module || 'SRA'}-PagedTable.csv`);
        }
    }, [rows, headers, allRows, hasAllData, onExportAll, module]);

    return (
        <Box sx={{ width: '100%', overflow: 'hidden' }}>
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 0.5 }}>
                <ExportButton
                    onClick={handleExport}
                    tooltip={exporting ? 'Downloading...' : hasExportAllHandler || hasAllData ? 'Download all as CSV' : 'Download current page as CSV'}
                />
            </Box>
            <Paper sx={{ overflow: 'hidden' }}>
                <TableContainer>
                    <Table aria-labelledby='tableTitle' size={dense ? 'small' : 'medium'}>
                        <EnhancedTableHead
                            headers={headers}
                            order={order}
                            orderBy={orderBy}
                            onRequestSort={onRequestSort}
                        />
                        <TableBody>
                            {visibleRows.map((row, index) => {
                                return (
                                    <TableRow hover tabIndex={-1} key={`${row.id}_${index}`}>
                                        {headers.map((header, index) => (
                                            <TableCell key={index} align='left'>
                                                <div
                                                    style={{
                                                        overflow: 'hidden',
                                                        textOverflow: 'ellipsis',
                                                        maxWidth: '200px',
                                                        whiteSpace: 'nowrap',
                                                    }}
                                                >
                                                    {row[header]}
                                                </div>
                                            </TableCell>
                                        ))}
                                    </TableRow>
                                );
                            })}
                            {emptyRows > 0 && (
                                <TableRow
                                    style={{
                                        height: (dense ? 33 : 53) * emptyRows,
                                    }}
                                >
                                    <TableCell colSpan={6} />
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                </TableContainer>
                <TablePagination
                    rowsPerPageOptions={[10]}
                    component='div'
                    count={total ?? 0}
                    rowsPerPage={rowsPerPage}
                    page={page}
                    onPageChange={onPageChange}
                />
            </Paper>
        </Box>
    );
};

export default PagedTable;
