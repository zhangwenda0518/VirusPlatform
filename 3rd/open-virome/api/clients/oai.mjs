import 'dotenv/config';
import { AzureOpenAI } from 'openai';

const DEFAULT_MODEL = 'o1';
const OPENAI_MODEL_CONFIGS = {
    o1: {
        endpoint: process.env.OPENAI_ENDPOINT_o1,
        apiKey: process.env.OPENAI_TOKEN,
        apiVersion: '2024-09-01-preview',
    },
    gpt4o: {
        endpoint: process.env.OPENAI_ENDPOINT_gpt4o,
        apiKey: process.env.OPENAI_TOKEN,
        apiVersion: '2024-09-01-preview',
    },
    gpt4oMini: {
        endpoint: process.env.OPENAI_ENDPOINT_gpt4o_mini,
        apiKey: process.env.OPENAI_TOKEN,
        apiVersion: '2024-09-01-preview',
    },
    // This model has a content filter policy with higher sensitivity used for high risk biosafety levels
    gpt4oMini2: {
        endpoint: process.env.OPENAI_ENDPOINT_gpt4o_mini2,
        apiKey: process.env.OPENAI_TOKEN,
        apiVersion: '2024-09-01-preview',
    },
};

const getOpenAIClient = (configName) => {
    const config = OPENAI_MODEL_CONFIGS[configName];
    return new AzureOpenAI(config);
};

export const runLLMCompletion = async (messages, modelName = DEFAULT_MODEL, temperature = 0.8) => {
    if (!messages) {
        return { error: 'No messages provided!' };
    }
    try {
        const openai = getOpenAIClient(modelName);
        const result = await openai.chat.completions.create({
            messages,
            temperature,
        });
        return {
            text: result.choices[0].message.content,
        };
    } catch (error) {
        console.error(error);
        return { error: error.message };
    }
};

export const streamLLMCompletion = async (messages, modelName = DEFAULT_MODEL, temperature = 0.8) => {
    if (!messages) {
        return { error: 'No messages provided!' };
    }
    try {
        const openai = getOpenAIClient(modelName);
        const result = await openai.chat.completions.create({
            messages,
            temperature,
            stream: true,
        });
        let collectedData = '';
        for await (const chunk of result) {
            collectedData += chunk?.choices[0]?.delta?.content ?? '';
        }
        return {
            text: collectedData,
        };
    } catch (error) {
        console.error(error);
        return { error: error.message };
    }
};
