import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

const API_URL =
    (!process.env.NODE_ENV || process.env.NODE_ENV === 'development') && !process.env.REACT_APP_USE_LAMBDA
        ? 'http://localhost:8000/'
        : 'https://zrdbegawce.execute-api.us-east-1.amazonaws.com/prod/';

export const apiSlice = createApi({
    baseQuery: fetchBaseQuery({
        baseUrl: API_URL,
        prepareHeaders: (headers) => {
            headers.set('Accept-Encoding', 'gzip,deflate');
            return headers;
        },
        responseHandler: (response) =>
            response.text().then((text) => {
                try {
                    return JSON.parse(text);
                } catch {}
                try {
                    return JSON.parse(atob(text));
                } catch {}
            }),
    }),
    keepUnusedDataFor: 10,
    tagTypes: ['Counts', 'Identifiers', 'Results'],
    endpoints: (build) => ({
        getCounts: build.query({
            query: (args) => ({
                url: 'counts',
                method: 'POST',
                body: args,
            }),
            providesTags: ['Counts'],
        }),
        getIdentifiers: build.query({
            query: (args) => ({
                url: 'identifiers',
                method: 'POST',
                body: args,
            }),
            providesTags: ['Identifiers'],
        }),
        getResult: build.query({
            query: (args) => ({
                url: 'results',
                method: 'POST',
                body: args,
            }),
            providesTags: ['Results'],
        }),
        getMWAS: build.query({
            query: (args) => ({
                url: 'mwas',
                method: 'POST',
                body: args,
            }),
        }),
        getSummaryText: build.query({
            query: (args) => ({
                url: 'summary',
                method: 'POST',
                body: args,
            }),
        }),
        getHypothesis: build.query({
            query: (args) => ({
                url: 'hypothesis',
                method: 'POST',
                body: args,
            }),
        }),
        getGlobalChat: build.query({
            query: (args) => ({
                url: 'globalChat',
                method: 'POST',
                body: args,
            }),
        }),
    }),
});

export const {
    useGetCountsQuery,
    useGetIdentifiersQuery,
    useGetResultQuery,
    useLazyGetResultQuery,
    useGetMWASQuery,
    useLazyGetSummaryTextQuery,
    useLazyGetHypothesisQuery,
    useLazyGetGlobalChatQuery,
} = apiSlice;
export const { endpoints, reducerPath, reducer, middleware } = apiSlice;
