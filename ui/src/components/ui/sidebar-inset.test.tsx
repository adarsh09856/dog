import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SidebarInset } from "./sidebar";

afterEach(cleanup);

describe("SidebarInset responsive sizing", () => {
  it("allows the workspace pane to shrink beside the fixed sidebar", () => {
    render(
      <div className="flex w-full">
        <aside style={{ width: "16rem", flexShrink: 0 }} />
        <SidebarInset>Workspace content</SidebarInset>
      </div>,
    );

    expect(screen.getByRole("main").className).toContain("min-w-0");
  });
});
