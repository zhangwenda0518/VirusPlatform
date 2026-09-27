import { RootState } from '../../app/store';
import { createSlice, createEntityAdapter, createSelector } from '@reduxjs/toolkit';

/* Reducers */

type Filter = {
    filterId: string;
    filterType: string;
    filterValue: string;
};

const filtersAdapter = createEntityAdapter({
    selectId: (filter: Filter) => `${filter.filterType}-${filter.filterValue}`,
    sortComparer: (a, b) => a.filterId.localeCompare(b.filterId),
});

const emptyInitialState = filtersAdapter.getInitialState();

const filtersSlice = createSlice({
    name: 'filters',
    initialState: emptyInitialState,
    reducers: {
        addFilter: filtersAdapter.addOne,
        addManyFilters: filtersAdapter.addMany,
        removeFilter: filtersAdapter.removeOne,
        removeManyFilters: filtersAdapter.removeMany,
        removeAllFilters: filtersAdapter.removeAll,
    },
});

export default filtersSlice.reducer;

/* Actions */

export const { addFilter, addManyFilters, removeFilter, removeAllFilters, removeManyFilters } = filtersSlice.actions;

/* Selectors */

export const {
    selectAll: selectAllFilters,
    selectById: selectFilterById,
    selectIds: selectFilterIds,
    selectEntities: selectFilterEntities,
    selectTotal: selectTotalFilters,
} = filtersAdapter.getSelectors((state: RootState) => state.filters);

export const selectFiltersByType = createSelector(
    [selectAllFilters, (_: RootState, type: string) => type],
    (filters, type) => filters.filter((filter) => filter.filterType === type),
);
