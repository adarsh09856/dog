import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getModels: vi.fn(), test: vi.fn() }));
vi.mock("@/lib/kodewavesApi", () => ({
  adminApi: { getIndicSttModels: mocks.getModels, testIndicStt: mocks.test },
}));

import IndicSttTest from "./IndicSttTest";

afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("offers every installed scheduled Indian language and tests the selected language", async () => {
  mocks.getModels.mockResolvedValue({
    model: "indicconformer-ctc-int8",
    status: "online",
    languages: ["as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur"],
  });
  mocks.test.mockResolvedValue({ success: true, model: "indicconformer-ctc-int8", language: "hi", transcript: "नमस्ते", latency_ms: 170 });
  render(<IndicSttTest />);

  const language = await screen.findByLabelText("Recognition language");
  await waitFor(() => expect(language.querySelectorAll("option")).toHaveLength(22));
  fireEvent.change(screen.getByLabelText("Indic speech test WAV"), { target: { files: [new File(["wav"], "speech.wav", { type: "audio/wav" })] } });
  fireEvent.click(screen.getByRole("button", { name: "Run Indian-language test" }));

  expect(await screen.findByText("नमस्ते")).toBeTruthy();
  expect(mocks.test).toHaveBeenCalledWith("hi", expect.any(String));
});

it("does not run a test when the local IndicConformer service is unavailable", async () => {
  mocks.getModels.mockResolvedValue({ model: "indicconformer-ctc-int8", languages: [], status: "offline", detail: "IndicConformer STT is unavailable" });
  render(<IndicSttTest />);
  expect(await screen.findByText("IndicConformer STT is unavailable")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Run Indian-language test" }).hasAttribute("disabled")).toBe(true);
});
