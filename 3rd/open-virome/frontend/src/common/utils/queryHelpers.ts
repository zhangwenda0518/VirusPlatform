import { moduleConfig } from '../../features/Module/constants.ts';

export const getFilterQuery = ({ filters, excludeType = '' }) => {
    return filters
        .filter((filter) => filter.filterType !== excludeType)
        .map((filter) => ({
            filterType: filter.filterType,
            filterValue: filter.filterValue,
            groupByKey: moduleConfig[filter.filterType].groupByKey,
        }));
};

export const handleIdKeyIrregularities = (idKey) => {
    if (['run', 'run_id', 'acc'].includes(idKey)) {
        return 'run';
    }
    if (['bioproject', 'bioproject_id', 'accession'].includes(idKey)) {
        return 'bioproject';
    }
    if (['biosample', 'biosample_id'].includes(idKey)) {
        return 'biosample';
    }
    return idKey;
};
