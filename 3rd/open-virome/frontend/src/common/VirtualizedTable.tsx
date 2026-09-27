import React, { useCallback, useEffect } from 'react';

import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Checkbox from '@mui/material/Checkbox';
import Box from '@mui/material/Box';
import { TableVirtuoso, TableComponents } from 'react-virtuoso';
import ExportButton from '../common/ExportButton.tsx';
import { exportToCSV } from '../common/utils/exportHelpers.ts';

interface Data {
    name: string;
    count: number;
    selected?: boolean;
}
interface ColumnData {
    dataKey: keyof Data;
    label: string;
    numeric?: boolean;
    width: number;
}

const defaultColumns: ColumnData[] = [
    {
        width: 120,
        label: 'Name',
        dataKey: 'name',
    },
    {
        width: 40,
        label: 'Count',
        dataKey: 'count',
        numeric: true,
    },
];

const VirtuosoTableComponents: TableComponents<Data> = {
    Scroller: React.forwardRef<HTMLDivElement>((props: any, ref) => (
        <TableContainer
            {...props}
            ref={ref}
            sx={{ boxShadow: 'none', backgroundImage: 'none', backgroundColor: 'transparent', ...(props.sx || {}) }}
        />
    )),
    Table: (props) => <Table {...props} sx={{ borderCollapse: 'separate', tableLayout: 'fixed' }} />,
    TableHead,
    TableRow: ({ item: _item, ...props }) => <TableRow {...props} />,
    TableBody: React.forwardRef<HTMLTableSectionElement>((props, ref) => <TableBody {...props} ref={ref} />),
};

const VirtualizedTable = ({ rows = [], columns = defaultColumns, onRowClick, searchBar, module = "" }) => {
    const disableSelectAll = (rows) => rows.length === 0 || rows.length > 100;
    const hasCheckedRows = (rows) => rows.length > 0 && rows.some((row) => row.selected);

    const fixedHeaderContent = (columns: ColumnData[], rows, onSelectAllClick) => {
        const isChecked = !disableSelectAll(rows) && rows.length > 0 && rows.every((row) => row.selected);
        return (
            <TableRow>
                <TableCell padding='checkbox' sx={{ width: 8, pl: 2, backgroundColor: 'background.paper' }}>
                    <Checkbox
                        color='primary'
                        checked={isChecked}
                        onChange={onSelectAllClick}
                        inputProps={{
                            'aria-label': 'select all rows',
                        }}
                        disabled={!hasCheckedRows(rows) && disableSelectAll(rows)}
                        indeterminate={hasCheckedRows(rows) && disableSelectAll(rows)}
                    />
                </TableCell>
                {columns.map((column, index) => (
                    <TableCell
                        key={column.dataKey}
                        variant='head'
                        align={column.numeric || false ? 'right' : 'left'}
                        style={{ width: column.width }}
                        sx={{ backgroundColor: 'background.paper', pl: 2 }}
                    >
                        {!!searchBar && index === 0 ? searchBar : column.label}
                    </TableCell>
                ))}
            </TableRow>
        );
    };

    const rowContent = (_index: number, row: Data) => {
        const labelId = `enhanced-table-checkbox-${_index}`;
        return (
            <React.Fragment>
                <TableCell padding='checkbox'>
                    <Checkbox
                        color='primary'
                        checked={row.selected}
                        inputProps={{
                            'aria-labelledby': labelId,
                        }}
                        sx={{ ml: 1.5, mt: 1, mb: 1 }}
                        onChange={() => onRowClick(row)}
                    />
                </TableCell>
                {defaultColumns.map((column) => (
                    <TableCell
                        key={column.dataKey}
                        align={column.numeric || false ? 'right' : 'left'}
                        onClick={() => onRowClick(row)}
                        sx={{
                            cursor: 'pointer',
                        }}
                    >
                        {row[column.dataKey] ?? 'N/A'}
                    </TableCell>
                ))}
            </React.Fragment>
        );
    };

    const onSelectAllClick = (event) => {
        if (disableSelectAll(rows)) {
            const selectedRows = rows.filter((row) => row.selected);
            selectedRows.forEach((row) => {
                onRowClick(row);
            });
        } else if (event.target.checked) {
            rows.forEach((row) => {
                if (!row.selected) {
                    onRowClick(row);
                }
            });
        } else {
            rows.forEach((row) => {
                if (row.selected) {
                    onRowClick(row);
                }
            });
        }
    };

    const sortRowsBySelected = (rows) =>
        rows.sort((a, b) => {
            if (a.selected && !b.selected) {
                return -1;
            }
            if (!a.selected && b.selected) {
                return 1;
            }
            return 0;
        });

    const sortRowsByColumn = (rows, column) => {
        return rows.sort((a, b) => b[column] - a[column]);
    };

    useEffect(() => {
        sortRowsByColumn(rows, 'count');
        sortRowsBySelected(rows);
    }, [rows.length]);

    const columnKeys = columns.map((c) => c.dataKey as string);
    const handleExport = useCallback(() => {
        exportToCSV(rows, columnKeys, `open-virome-${module || 'filter'}-VirtualizedTable.csv`);
    }, [rows, columnKeys, module]);

    return (
        <Box sx={{ position: 'relative' }}>
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 0.5 }}>
                <ExportButton onClick={handleExport} tooltip="Download CSV" />
            </Box>
            <Box sx={{ height: '75vh', width: '100%' }}>
            <TableVirtuoso
                data={rows}
                components={VirtuosoTableComponents}
                fixedHeaderContent={() => fixedHeaderContent(columns, rows, onSelectAllClick)}
                itemContent={rowContent}
            />
            </Box>
        </Box>
    );
};

export default VirtualizedTable;
