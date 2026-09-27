import { tissueImageMap } from "./tissueImageMap.ts";

export const isSimpleLayout = (sectionLayout) => {
    return sectionLayout === 'simple';
};

export const isSummaryView = (identifiers) => {
    return identifiers && identifiers.run.totalCount === -1;
};

export const shouldDisableFigureView = (identifiers, sectionKey = '') => {
    if (!identifiers) {
        return true;
    }
    return identifiers?.run?.totalCount > 400000;
};

export const chooseFigure = (bestTissues) => {
    if (!bestTissues) {
        return "";
    }
    const tissues = Object.values(bestTissues).map(item => item.tissue);
    for (const tissue of tissues) {
        if(tissueImageMap[tissue]){
            return tissueImageMap[tissue];
        }
    }
    return "";
};

