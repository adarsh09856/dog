import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingTooltip } from "@/components/onboarding/OnboardingTooltip";

vi.mock("@floating-ui/react-dom", () => ({
  arrow: () => ({}),
  autoUpdate: vi.fn(),
  flip: () => ({}),
  offset: () => ({}),
  shift: () => ({}),
  useFloating: () => ({
    refs: { setFloating: vi.fn(), setReference: vi.fn() },
    floatingStyles: {},
    middlewareData: {},
    placement: "bottom",
    isPositioned: true,
    elements: { reference: null },
  }),
}));

vi.mock("@/context/OnboardingContext", () => ({
  useOnboarding: () => ({
    hasSeenTooltip: () => false,
    markTooltipSeen: vi.fn(),
  }),
}));

describe("OnboardingTooltip theme", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("uses the configured primary palette for the surface and actions", async () => {
    render(
      <OnboardingTooltip
        tooltipKey="web_call"
        targetRef={{ current: null }}
        title="Brand theme"
        message="The tour should follow the configured brand colors."
      />,
    );

    const panel = await screen.findByText("Brand theme");
    expect(panel.parentElement?.className).toContain("bg-primary text-primary-foreground");
    expect(screen.getByRole("button", { name: "Close tooltip" }).className).toContain(
      "hover:bg-primary/80",
    );
    expect(screen.getByRole("button", { name: "Close" }).className).toContain(
      "bg-primary-foreground text-primary",
    );
  });
});
