import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConnectionStatus } from "./ConnectionStatus";

describe("ConnectionStatus", () => {
  it("uses the shared brand color while connecting", () => {
    render(<ConnectionStatus connectionStatus="connecting" />);

    expect(screen.getByText("Establishing Connection...").parentElement?.classList.contains("text-primary")).toBe(true);
  });

  it("reports connected and failed states", () => {
    const { rerender } = render(<ConnectionStatus connectionStatus="connected" />);
    expect(screen.getByText("Connected").textContent).toBe("Connected");

    rerender(<ConnectionStatus connectionStatus="failed" />);
    expect(screen.getByText("Connection Failed").textContent).toBe("Connection Failed");
  });
});
