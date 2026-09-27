import { truncate, abbreviateNumber } from '../../../common/utils/textFormatting.ts';
import { histogram } from 'echarts-stat';

// https://github.com/ecomfe/echarts-stat?tab=readme-ov-file#return-value-only-for-standalone-usage
export function histogramBins(values) {
    let bins = histogram(values, 'squareRoot');
    bins.data.forEach((bin, index) => {
        bins.data[index][1] += bins.data[index][1];
    });
    return bins;
}

export const getTargetControlPlotData = (
    targetRows = [],
    controlRows = [],
    countKey = 'count',
    maxRows = undefined,
) => {
    let colKey = countKey;
    if (countKey === 'percent') {
        colKey = 'count';
    }

    const parseCount = (value) => {
        let val;
        switch (colKey) {
            case 'gbp':
                val = parseFloat(parseFloat(value).toFixed(1));
            case 'count':
            case 'percent':
                val = Math.round(parseFloat(value));
            default:
                val = parseInt(value);
        }
        if (isNaN(val)) {
            return 0;
        }
        return val;
    };

    const targetRowsSet = new Set(targetRows);
    const mergedRows = [...targetRows, ...controlRows].reduce((acc, row) => {
        const name = row.name || 'N/A';
        const count = parseCount(row[colKey]);
        const existingRow = acc.find((r) => r.name === name);
        const isInTarget = targetRowsSet.has(row);
        if (existingRow) {
            existingRow.target += isInTarget ? count : 0;
            existingRow.control += isInTarget ? 0 : count;
        } else {
            acc.push({
                name,
                target: isInTarget ? count : 0,
                control: isInTarget ? 0 : count,
            });
        }
        return acc;
    }, []);

    // Subtract target from control count
    mergedRows.forEach((row) => {
        row.target = parseCount(row.target);
        row.control = parseCount(Math.max(row.control - row.target, 0));
    });

    // Calculate percentage of set
    if (countKey === 'percent') {
        const totalTarget = mergedRows.reduce((acc, row) => acc + row.target, 0);
        const totalControl = mergedRows.reduce((acc, row) => acc + row.control, 0);
        mergedRows.forEach((row) => {
            row.target = Math.round((row.target / totalTarget) * 100);
            row.control = Math.round((row.control / totalControl) * 100);
        });
    }

    mergedRows.sort((a, b) => a.target + a.control - (b.target + b.control));

    if (maxRows && mergedRows.length > maxRows) {
        const others = mergedRows.slice(0, mergedRows.length - maxRows).reduce(
            (acc, row) => {
                acc.target += row.target;
                acc.control += row.control;
                return acc;
            },
            { name: 'Other', target: 0, control: 0 },
        );

        mergedRows.splice(0, mergedRows.length - maxRows, others);
    }

    const maxCount = Math.max(...mergedRows.flatMap((row) => [row.target, row.control]));

    const getZoomPercentage = (desiredRows, totalRows) => {
        if (totalRows <= desiredRows) {
            return 0;
        }
        const percentage = (desiredRows / totalRows) * 100;
        return Math.min(100, Math.max(0, 100 - percentage));
    };
    const dataZoom = [
        {
            type: 'inside',
            id: 'insideY',
            yAxisIndex: 0,
            start: 100,
            end: getZoomPercentage(10, mergedRows.length),
            zoomOnMouseWheel: false,
            moveOnMouseMove: true,
            moveOnMouseWheel: true,
        },
    ];

    return {
        xAxis: {
            type: 'value',
            max: maxCount,
            axisLabel: {
                formatter: abbreviateNumber,
            },
        },
        yAxis: {
            type: 'category',
            axisLabel: {
                formatter: (value) => truncate(value, 20),
            },
        },
        dataset: {
            dimensions: ['name', 'target', 'control'],
            source: mergedRows,
        },
        series: [
            {
                name: 'Target',
                type: 'bar',
                stack: 'total',
                label: {
                    show: true,
                    color: 'white',
                },
                emphasis: {
                    focus: 'series',
                },
                color: 'cornflowerblue',
            },
            {
                name: 'Control',
                type: 'bar',
                stack: 'total',
                label: {
                    show: true,
                    color: 'white',
                },
                emphasis: {
                    focus: 'series',
                },
                color: 'grey',
            },
        ],
        dataZoom: dataZoom,
    };
};

export const getBioprojectSizePlotData = (controlRows = []) => {
    const values = controlRows.map((row) => parseInt(row['count']));
    const bins = histogramBins(values);
    const maxRuns = Math.max(...bins.data.map((bin) => bin[3]));

    const tooltipFormatter = (args) => {
        const count = args[0].value[1];
        const runs = args[0].value[4];
        return `${args[0].marker} ${count} ${args[0].seriesName} <br />  &ensp; &ensp;  ${runs} Runs`;
    };

    return {
        xAxis: {
            name: 'Runs (n)',
            nameLocation: 'middle',
            nameGap: 24,
            boundaryGap: ['0%', '5%'],
            max: maxRuns,
            // type: maxRuns > 1000 ? 'log' : 'value',
            axisLabel: {
                formatter: abbreviateNumber,
            },
        },
        yAxis: {
            name: 'Count',
            nameLocation: 'middle',
            nameGap: 40,
            minInterval: 1,
            boundaryGap: ['0%', '10%'],
            // type: maxCount > 100 ? 'log' : 'value',
        },
        legend: {
            show: false,
        },
        tooltip: {
            trigger: 'axis',
            formatter: tooltipFormatter,
        },
        title: {
            text: 'BioProject size',
            textStyle: {
                color: 'white',
                fontSize: 14,
                fontWeight: 'normal',
                fontStyle: 'italic',
            },
            left: 0,
            top: 20,
        },
        grid: {
            left: 55,
            right: 15,
        },
        series: [
            {
                name: `BioProjects`,
                type: 'bar',
                stack: 'total',
                label: {
                    show: false,
                    color: 'white',
                },
                emphasis: {
                    focus: 'series',
                },
                color: 'gray',
                data: bins.data,
            },
        ],
    };
};

export const getBioprojectTargetPercentagePlotData = (controlRows = [], targetRows = []) => {
    const percentageToNumRuns = controlRows.map((row) => {
        const bioprojectId = row['name'];
        const targetRow = targetRows.find((targetRow) => targetRow['name'] === bioprojectId);
        let percentage = targetRow ? parseInt((parseFloat(targetRow['count']) / parseFloat(row['count'])) * 100) : 0;
        if (percentage == 100) {
            percentage = 99;
        }
        return percentage;
    });

    const bins = histogramBins(percentageToNumRuns);

    const tooltipFormatter = (args) => {
        const count = args[0].value[1];
        const percentage = args[0].value[4];
        return `${args[0].marker} ${count} ${args[0].seriesName} <br />  &ensp; &ensp;  ${percentage}% in target set`;
    };

    return {
        xAxis: {
            type: 'value',
            name: 'Target (%)',
            nameLocation: 'middle',
            nameGap: 25,
            boundaryGap: ['-10%', '0%'],
            max: 100,
            axisLabel: {
                formatter: abbreviateNumber,
            },
        },
        yAxis: {
            name: 'Count',
            nameLocation: 'middle',
            nameGap: 40,
            minInterval: 1,
            boundaryGap: ['0%', '10%'],
            // type: maxCount > 100 ? 'log' : 'value',
        },
        grid: {
            left: 55,
            right: 15,
        },
        title: {
            text: '% of BioProject in Target set',
            textStyle: {
                color: 'white',
                fontSize: 14,
                fontWeight: 'normal',
                fontStyle: 'italic',
            },
            left: 0,
            top: 20,
        },
        visualMap: {
            show: false,
            type: 'continuous',
            min: 0,
            max: 100,
            dimension: 0,
            inRange: {
                color: ['grey', 'cornflowerblue'],
            },
        },
        tooltip: {
            trigger: 'axis',
            formatter: tooltipFormatter,
        },
        legend: {
            show: false,
        },
        series: [
            {
                name: `BioProjects`,
                type: 'bar',
                stack: 'total',
                label: {
                    show: false,
                    color: 'white',
                },
                emphasis: {
                    focus: 'series',
                },
                color: 'gray',
                data: bins.data,
            },
        ],
    };
};

export const getBioprojectSizeVsPercentagePlotData = (controlRows = [], targetRows = []) => {
    const rows = controlRows.map((row) => {
        const bioprojectId = row['name'];
        const targetRow = targetRows.find((targetRow) => targetRow['name'] === bioprojectId);
        const percentage = targetRow ? parseInt((parseFloat(targetRow['count']) / parseFloat(row['count'])) * 100) : 0;
        return [parseInt(row['count']), percentage, bioprojectId];
    });

    const tooltipFormatter = (args) => {
        const bioprojectId = rows[args.dataIndex][2];
        const percentage = args.value[1];
        const runs = rows[args.dataIndex][0];
        return `${args.marker} Bioproject: ${bioprojectId} <br /> &ensp; &ensp; ${percentage}% Target  <br />  &ensp; &ensp; ${runs} Runs <br />`;
    };

    return {
        xAxis: {
            name: 'Runs (n)',
            nameLocation: 'middle',
            nameGap: 25,
            boundaryGap: ['5%', '5%'],
            type: 'value',
            axisLabel: {
                formatter: abbreviateNumber,
            },
        },
        yAxis: {
            type: 'value',
            name: 'Target (%)',
            nameLocation: 'middle',
            nameGap: 20,
            minInterval: 1,
            boundaryGap: ['5%', '5%'],
            axisLabel: {
                formatter: abbreviateNumber,
            },
        },
        title: {
            text: 'Runs per BioProject vs. BioProject runs in Target set (%)',
            textStyle: {
                color: 'white',
                fontSize: 14,
                fontWeight: 'normal',
                fontStyle: 'italic',
            },
            left: 0,
            top: 20,
        },
        visualMap: {
            show: false,
            type: 'continuous',
            min: 0,
            max: 100,
            dimension: 1,
            inRange: {
                color: ['grey', 'cornflowerblue'],
            },
        },
        dataset: {
            dimensions: ['count', 'percentage'],
            source: [...rows],
        },
        tooltip: {
            trigger: 'item',
            axisPointer: {
                type: 'shadow',
            },
            formatter: tooltipFormatter,
        },
        legend: {
            show: false,
        },
        series: [
            {
                name: `BioProjects size (n runs)`,
                type: 'scatter',
                label: {
                    show: false,
                    color: 'white',
                },
                emphasis: {
                    focus: 'series',
                },
                color: 'gray',
            },
        ],
    };
};
