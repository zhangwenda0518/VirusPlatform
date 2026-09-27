import { load } from '@fingerprintjs/botd';

export const isBotDetected = async () => {
    try {
        const botd = await load();
        const detect = await botd.detect();
        return detect && detect.bot === true;
    } catch (error) {
        console.error(error);
        return true;
    }
};
