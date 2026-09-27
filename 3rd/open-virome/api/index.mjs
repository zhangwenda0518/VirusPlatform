import awsServerlessExpress from 'aws-serverless-express';
import app from './app.mjs';

// Handle ERR_CONTENT_DECODING_FAILED issue:
// https://github.com/CodeGenieApp/serverless-express/blob/master/examples/basic-starter/lambda.js
const binaryMimeTypes = [
    'application/javascript',
    'application/json',
    'application/octet-stream',
    'application/xml',
    'font/eot',
    'font/opentype',
    'font/otf',
    'image/jpeg',
    'image/png',
    'image/svg+xml',
    'text/comma-separated-values',
    'text/css',
    'text/html',
    'text/javascript',
    'text/plain',
    'text/text',
    'text/xml',
];
const server = awsServerlessExpress.createServer(app, null, binaryMimeTypes);

export const handler = (event, context) => {
    awsServerlessExpress.proxy(server, event, context);
};
