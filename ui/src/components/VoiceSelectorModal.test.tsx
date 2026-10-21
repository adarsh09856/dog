import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ voices: vi.fn(), preview: vi.fn(), auth: { user: { id: 'test-user' }, loading: false } }));
vi.mock('@/lib/auth', () => ({ useAuth: () => mocks.auth }));
vi.mock('@/client/sdk.gen', () => ({ getVoicesApiV1UserConfigurationsVoicesProviderGet: mocks.voices }));
vi.mock('@/client/client.gen', () => ({ client: { get: mocks.preview } }));
import { VoiceSelectorModal } from './VoiceSelectorModal';

describe('configured voice language', () => {
    afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
    beforeEach(() => {
        mocks.voices.mockReset();
        mocks.voices.mockResolvedValue({ data: { voices: [], facets: { languages: ['en', 'hi'] } } });
    });

    it('filters the selected provider and model by the configured language, including after a change', async () => {
        const props = { provider: 'piper', model: 'piper', value: '', onChange: vi.fn(), source: 'local' as const };
        const view = render(<VoiceSelectorModal {...props} outputLanguage="en" />);
        fireEvent.click(screen.getByRole('button', { name: 'Select a voice' }));
        await waitFor(() => expect(mocks.voices).toHaveBeenCalledWith(expect.objectContaining({
            path: { provider: 'piper' }, query: { model: 'piper', language: 'en' },
        })));
        view.rerender(<VoiceSelectorModal {...props} outputLanguage="hi" />);
        await waitFor(() => expect(mocks.voices).toHaveBeenLastCalledWith(expect.objectContaining({
            query: { model: 'piper', language: 'hi' },
        })));
    });

    it('does not send the STT auto-detection sentinel as a voice language', async () => {
        render(<VoiceSelectorModal provider="piper" model="piper" value="" onChange={vi.fn()} outputLanguage="multi" />);
        fireEvent.click(screen.getByRole('button', { name: 'Select a voice' }));
        await waitFor(() => expect(mocks.voices).toHaveBeenCalledWith(expect.objectContaining({ query: { model: 'piper' } })));
    });

    it('shows a voice’s supported languages instead of claiming TTS auto-detection', async () => {
        mocks.voices.mockResolvedValue({ data: {
            voices: [{
                voice_id: 'Inaya', name: 'Inaya — Indian Hindi and Hinglish', provider: 'speaches',
                language: 'multi', languages: ['hi-IN', 'en-IN'], gender: 'female', accent: 'in',
            }],
            facets: { languages: ['hi-IN', 'en-IN'] },
        } });
        render(<VoiceSelectorModal
            provider="speaches" model="indus-pocket-tts" value="Inaya" onChange={vi.fn()}
            source="local" outputLanguage="hi"
        />);
        expect(await screen.findByText(/Hindi, English \(India\)/)).toBeTruthy();
        expect(screen.queryByText('Multilingual (Auto-detect)')).toBeNull();
    });

    it('cannot commit a saved voice that is absent from the filtered catalog', async () => {
        const onChange = vi.fn();
        render(<VoiceSelectorModal provider="piper" model="piper" value="hi_IN-pratham-medium" onChange={onChange} outputLanguage="en" />);
        fireEvent.click(screen.getByRole('button', { name: 'hi_IN-pratham-medium' }));
        await screen.findByText('No voices match these filters');
        fireEvent.click(screen.getByRole('button', { name: 'Use this voice' }));
        expect(onChange).not.toHaveBeenCalled();
        await screen.findByText('Choose an available voice for the selected model and language.');
    });

    it('previews the selected model in the configured language', async () => {
        mocks.voices.mockResolvedValue({ data: { voices: [{
            voice_id: 'voice-1', name: 'Test voice', provider: 'google',
            preview_url: '/api/v1/user/configurations/voices/google/voice-1/preview',
        }], facets: { languages: ['hi'] } } });
        // Stop at the request boundary; audio quality is verified separately in live calls.
        mocks.preview.mockReturnValue(new Promise(() => {}));
        render(<VoiceSelectorModal provider="google" model="selected-model" value="" onChange={vi.fn()} outputLanguage="hi" />);
        fireEvent.click(screen.getByRole('button', { name: 'Select a voice' }));
        fireEvent.click(await screen.findByRole('button', { name: 'Play preview' }));
        expect(mocks.preview).toHaveBeenCalledWith(expect.objectContaining({
            url: '/api/v1/user/configurations/voices/google/voice-1/preview?language=hi&model=selected-model',
        }));
    });

    it('returns selected regional language metadata so the editor can synchronize recognition', async () => {
        const voice = { voice_id: 'TAM_F', name: 'Tamil — Female', provider: 'speaches',
            gender: 'female', language: 'ta-IN', languages: ['ta-IN'] };
        mocks.voices.mockResolvedValue({ data: { voices: [voice], facets: { languages: ['ta-IN'] } } });
        const onChange = vi.fn();
        render(<VoiceSelectorModal provider="speaches" model="indic-vits-rasa-13" value="" onChange={onChange} source="local" />);
        fireEvent.click(screen.getByRole('button', { name: 'Select a voice' }));
        fireEvent.click(await screen.findByText('Tamil — Female'));
        fireEvent.click(screen.getByRole('button', { name: 'Use this voice' }));
        expect(onChange).toHaveBeenCalledWith('TAM_F', voice);
        expect(mocks.voices).toHaveBeenLastCalledWith(expect.objectContaining({ query: { model: 'indic-vits-rasa-13' } }));
    });
});
