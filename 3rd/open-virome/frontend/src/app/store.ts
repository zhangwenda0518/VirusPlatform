import { configureStore } from '@reduxjs/toolkit';
import { setupListeners } from '@reduxjs/toolkit/query';
import rootReducer from './rootReducer';
import { middleware as apiMiddleware } from '../api/client.ts';
import { moduleConfig } from '../features/Module/constants.ts';
import ReduxQuerySync from 'redux-query-sync';

export const store = configureStore({
    reducer: rootReducer,
    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(apiMiddleware),
});

setupListeners(store.dispatch);

// Synchronize URL query string with filters in Redux store
ReduxQuerySync({
    store,
    params: {
        filters: {
            selector: (state) => {
                return state?.filters?.ids ?? [];
            },
            action: (value) => {
                if (value === undefined || value.length === 0) {
                    return { type: 'filters/removeAllFilters' };
                }
                return { type: 'filters/addManyFilters', payload: value };
            },
            stringToValue: (string) => {
                if (string === undefined || string === '[]') {
                    return [];
                }

                try {
                    const filterIds = JSON.parse(string);
                    const validFilterTypes = Object.keys(moduleConfig);

                    const filters = filterIds.map((filterId) => {
                        const [filterType, ...filterValue] = filterId.split('-');
                        if (!validFilterTypes.includes(filterType)) {
                            return null;
                        }
                        return {
                            filterId,
                            filterType,
                            filterValue: filterValue.join('-'),
                        };
                    });
                    return filters.filter(Boolean);
                } catch (e) {
                    return [];
                }
            },
            valueToString: (value) => {
                return JSON.stringify(value);
            },
        },
        palmprintOnly: {
            selector: (state) => {
                return state?.app?.palmprintOnly;
            },
            action: (value) => {
                if (value === undefined) {
                    return { type: 'skip' };
                }
                return { type: 'app/togglePalmprintOnly' };
            },
            stringToValue: (string) => {
                return string === 'true';
            },
            valueToString: (value) => {
                return value ? 'true' : 'false';
            },
        },
    },
    initialTruth: 'location',
    replaceState: true,
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
