import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getUsageHistory: vi.fn(),
  openPreview: vi.fn(),
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ isAuthenticated: true, loading: false }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "UTC" }));
vi.mock("@/client/sdk.gen", () => ({ getUsageHistoryApiV1OrganizationsUsageRunsGet: mocks.getUsageHistory }));
vi.mock("@/components/MediaPreviewDialog", () => ({
  MediaPreviewDialog: () => ({ openPreview: mocks.openPreview, dialog: <div data-testid="media-preview" /> }),
}));

import CallRecordingsList from "./CallRecordingsList";

afterEach(() => {
  cleanup();
  mocks.getUsageHistory.mockReset();
  mocks.openPreview.mockReset();
});

it("lists saved call audio separately from runs without recordings and opens playback", async () => {
  mocks.getUsageHistory.mockResolvedValue({
    data: {
      runs: [
        {
          id: 42,
          workflow_id: 7,
          workflow_name: "Support agent",
          name: "Call",
          created_at: "2026-10-30T10:00:00Z",
          call_duration_seconds: 74,
          call_type: "inbound",
          caller_number: "+15551234567",
          recording_url: "recordings/run-42.wav",
          transcript_url: "transcripts/run-42.txt",
        },
        {
          id: 41,
          workflow_id: 7,
          workflow_name: "Support agent",
          name: "Call",
          created_at: "2026-10-30T09:00:00Z",
          call_duration_seconds: 20,
          recording_url: null,
        },
      ],
      total_count: 2,
      total_pages: 1,
    },
  });

  render(<CallRecordingsList />);

  const play = await screen.findByRole("button", { name: "Play full call recording for run 42" });
  expect(screen.getByText("1 recording on this page · 2 completed calls checked")).toBeTruthy();
  expect(screen.getByText("Support agent")).toBeTruthy();
  fireEvent.click(play);
  expect(mocks.openPreview).toHaveBeenCalledWith("recordings/run-42.wav", "transcripts/run-42.txt", 42);
});

it("explains when a page of completed calls has no saved recording", async () => {
  mocks.getUsageHistory.mockResolvedValue({
    data: {
      runs: [{
        id: 41,
        workflow_id: 7,
        workflow_name: "Support agent",
        name: "Call",
        created_at: "2026-10-30T09:00:00Z",
        call_duration_seconds: 20,
      }],
      total_count: 1,
      total_pages: 1,
    },
  });

  render(<CallRecordingsList />);

  await waitFor(() => expect(screen.getByText("No call recordings on this page")).toBeTruthy());
  expect(screen.getByText(/Only calls saved with recording audio appear here/)).toBeTruthy();
});
