const triggerDownload = (url: string, filename: string) => {
    const link = document.createElement('a');
    link.download = filename;
    link.href = url;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
};

export const exportEChartsToPNG = (instance: any, filename: string) => {
    const url = instance.getDataURL({
        type: 'png',
        pixelRatio: 6,
        backgroundColor: '#FFFFFF',
    });
    triggerDownload(url, filename);
};

export const exportCytoscapeToPNG = (cy: any, filename: string) => {
    const url = cy.png({
        full: true,
        bg: '#FFFFFF',
    });
    triggerDownload(url, filename);
};

export const exportElementToPNG = async (element: HTMLElement, filename: string) => {
    const html2canvas = (await import('html2canvas')).default;
    const canvas = await html2canvas(element, {
        backgroundColor: '#FFFFFF',
        scale: 2,
    });
    triggerDownload(canvas.toDataURL('image/png'), filename);
};

export const exportCanvasToPNG = (canvas: HTMLCanvasElement, filename: string) => {
    const url = canvas.toDataURL('image/png');
    triggerDownload(url, filename);
};

export const exportToCSV = (rows: Record<string, any>[], headers: string[], filename: string) => {
    const headerLine = headers.join(',');
    const dataLines = rows.map((row) =>
        headers
            .map((h) => {
                const val = row[h] ?? '';
                const str = String(val);
                return str.includes(',') || str.includes('"') || str.includes('\n')
                    ? `"${str.replace(/"/g, '""')}"`
                    : str;
            })
            .join(',')
    );
    const csv = [headerLine, ...dataLines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    triggerDownload(url, filename);
    URL.revokeObjectURL(url);
};
