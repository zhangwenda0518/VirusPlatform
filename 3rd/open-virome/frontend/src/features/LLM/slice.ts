import { RootState } from '../../app/store';
import { createSlice, createSelector } from '@reduxjs/toolkit';

/* Reducers */

type ChatMessage = {
    message: string;
    role: boolean;
    mode: string;
};

type ChatState = {
    chatOpen: boolean;
    chatMessages: ChatMessage[];
};

const chatSlice = createSlice({
    name: 'llm',
    initialState: {
        chatOpen: false,
        chatMessages: [],
    },
    reducers: {
        toggleChat: (state) => {
            state.chatOpen = !state.chatOpen;
        },
        addChatMessage: (state, action) => {
            state.chatMessages.push(action.payload);
        },
        clearChatMessages: (state) => {
            state.chatMessages = [];
        },
    },
});

export default chatSlice.reducer;

/* Actions */

export const { toggleChat, addChatMessage, clearChatMessages } = chatSlice.actions;

/* Selectors */

const selectLLM = (state: RootState) => state.chat;

export const selectChatOpen = createSelector([selectLLM], (state: ChatState) => state.chatOpen);
export const selectChatMessages = createSelector([selectLLM], (state: ChatState) => state.chatMessages);
