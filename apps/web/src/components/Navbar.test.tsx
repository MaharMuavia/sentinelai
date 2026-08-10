import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Navbar } from "./Navbar";

const { usePathname } = vi.hoisted(() => ({
  usePathname: vi.fn(() => "/"),
}));

vi.mock("next/navigation", () => ({
  usePathname,
}));

describe("Navbar", () => {
  beforeEach(() => {
    usePathname.mockReturnValue("/");
  });

  it("opens and closes the accessible mobile navigation", () => {
    render(<Navbar />);
    const menuButton = screen.getByRole("button", { name: "Open navigation menu" });

    expect(menuButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation", { name: "Mobile navigation" })).not.toBeInTheDocument();

    fireEvent.click(menuButton);

    expect(screen.getByRole("button", { name: "Close navigation menu" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: "Mobile navigation" })).toBeInTheDocument();
  });

  it("marks the current route for assistive technology", () => {
    usePathname.mockReturnValue("/dashboard");

    render(<Navbar />);

    for (const link of screen.getAllByRole("link", { name: "Dashboard" })) {
      expect(link).toHaveAttribute("aria-current", "page");
    }
  });
});
