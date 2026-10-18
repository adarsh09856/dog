import { getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get } from '@/client/sdk.gen';
import { INDIAN_TEMPLATE_LANGUAGES } from '@/constants/languages';

/** Match template defaults to the configured speech service without changing it. */
export async function configuredTemplateLanguage(): Promise<string | null> {
    const response = await getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get();
    if (!response.data) return null;
    const config = response.data.effective_configuration;
    const tts = config.tts as { language?: string; voice?: string } | undefined;
    const stt = config.stt as { language?: string } | undefined;
    const automatic = new Set(['auto', 'multi', 'multilingual', 'caller', 'default', 'none']);
    const explicit = [tts?.language, stt?.language].find(value => value && !automatic.has(value.toLowerCase()));
    const voiceCode = tts?.voice?.match(/^([a-z]{2,3})[-_][A-Z]{2}[-_]/)?.[1];
    const code = (explicit || voiceCode)?.toLowerCase().replace('_', '-').split('-')[0];
    return code && INDIAN_TEMPLATE_LANGUAGES.some(language => language.code === code) ? code : null;
}
