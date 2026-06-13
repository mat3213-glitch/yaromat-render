import {Config} from '@remotion/cli/config';

// H.264 mp4, совместимо с пулом/площадками. Качество — для песочницы достаточно CRF по умолчанию.
Config.setVideoImageFormat('jpeg');
Config.setCodec('h264');
Config.setPixelFormat('yuv420p');
Config.setOverwriteOutput(true);
