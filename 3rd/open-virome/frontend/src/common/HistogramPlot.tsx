import React, { useRef } from 'react';
import ReactEcharts from 'echarts-for-react';
import ExportButton from '../common/ExportButton.tsx';
import { exportEChartsToPNG } from '../common/utils/exportHelpers.ts';
import { useTheme } from '@mui/material/styles';

const HistogramPlot = ({ plotData = {}, styles = {}, onEvents = {}, module = "" }) => {
    const theme = useTheme();
    const isDark = theme.palette.mode === 'dark';
    const textColor = isDark ? 'white' : '#333';
    const echartsRef = useRef<any>(null);
    const defaultConfig = {
        backgroundColor: 'transparent',
        textStyle: { color: textColor },
        subtextStyle: { color: textColor },
        legend: { textStyle: { color: textColor } },
        tooltip: {
            trigger: 'item',
            axisPointer: {
                type: 'shadow',
            },
        },
        xAxis: {
            type: 'value',
        },
        yAxis: {
            type: 'value',
        },
        series: [],
    };

    const options: any = {
        ...defaultConfig,
        ...plotData,
    };
    if (options.textStyle) options.textStyle.color = textColor;
    if (options.subtextStyle) options.subtextStyle.color = textColor;
    if (options.legend?.textStyle) options.legend.textStyle.color = textColor;
    if (options.title?.textStyle) options.title.textStyle.color = textColor;
    if (options.series) {
        options.series.forEach((s: any) => {
            if (s.label?.color) s.label.color = textColor;
        });
    }

    options.series.forEach((obj) => {
        obj.barWidth = '101%';
    });

    return (
        <div style={{ position: 'relative' }}>
            <div style={{ position: 'absolute', right: 8, top: 8, zIndex: 10 }}>
                <ExportButton
                    onClick={() => {
                        const instance = echartsRef.current?.getEchartsInstance();
                        if (instance) exportEChartsToPNG(instance, `open-virome-${module || 'SRA'}-HistogramPlot.png`);
                    }}
                />
            </div>
            <ReactEcharts ref={echartsRef} option={options} style={styles} onEvents={onEvents} />
        </div>
    );
};

export default HistogramPlot;
