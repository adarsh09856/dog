import { mergeConfig } from 'vitest/config';
import base from './vitest.config.mts';
export default mergeConfig(base, { css: { postcss: { plugins: [] } } });
