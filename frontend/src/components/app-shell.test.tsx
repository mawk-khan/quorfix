import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/lib/auth/session-provider";
import type { Session } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

import { AppShell } from "./app-shell";

// A local wrapper (rather than test-utils's renderWithProviders) because
// this suite needs `rerender` to re-enter the *same* provider tree — RTL's
// rerender() replaces whatever element tree it's given, so re-rendering
// with a bare <AppShell> after an initial renderWithProviders() call would
// unmount SessionProvider/QueryClientProvider along with it.
function renderShell(children: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (node: ReactElement) => (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <AppShell>{node}</AppShell>
      </SessionProvider>
    </QueryClientProvider>
  );
  const result = render(wrap(children));
  return {
    ...result,
    rerender: (next: ReactElement) => result.rerender(wrap(next)),
  };
}

const pushMock = vi.fn();
let mockPathname = "/bugs";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => mockPathname,
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
  logout: vi.fn(),
}));

import { getSession } from "@/lib/api/auth";

function mockAuthenticated(overrides: Partial<Session> = {}): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role: "administrator",
    user: { id: "u1", email: "admin@example.com", first_name: "Ada", last_name: "Admin" },
    organization: { id: "o1", name: "Acme" },
    ...overrides,
  } as Session);
}

describe("AppShell", () => {
  beforeEach(() => {
    mockPathname = "/bugs";
    pushMock.mockClear();
  });

  it("renders a skip link targeting #main-content", async () => {
    mockAuthenticated();
    renderWithProviders(
      <AppShell>
        <main id="main-content" tabIndex={-1}>
          page content
        </main>
      </AppShell>,
    );

    const skipLink = await screen.findByRole("link", { name: /skip to main content/i });
    expect(skipLink).toHaveAttribute("href", "#main-content");
  });

  it("marks the current route's nav link with aria-current", async () => {
    mockAuthenticated();
    renderWithProviders(
      <AppShell>
        <main id="main-content" tabIndex={-1} />
      </AppShell>,
    );

    const bugsLink = await screen.findByRole("link", { name: "Bugs" });
    expect(bugsLink).toHaveAttribute("aria-current", "page");
    const projectsLink = screen.getByRole("link", { name: "Projects" });
    expect(projectsLink).not.toHaveAttribute("aria-current");
  });

  it("moves focus to the new page's main landmark on client-side navigation", async () => {
    mockAuthenticated();
    const { rerender } = renderShell(
      <main id="main-content" tabIndex={-1}>
        bugs page
      </main>,
    );
    await screen.findByRole("link", { name: "Bugs" });
    expect(screen.getByText("bugs page")).not.toHaveFocus();

    mockPathname = "/projects";
    rerender(
      <main id="main-content" tabIndex={-1}>
        projects page
      </main>,
    );

    expect(await screen.findByText("projects page")).toHaveFocus();
  });

  it("does not steal focus on first mount", async () => {
    mockAuthenticated();
    const user = userEvent.setup();
    render(<button type="button">outside</button>);
    const outsideButton = screen.getByRole("button", { name: "outside" });
    await user.click(outsideButton);
    expect(outsideButton).toHaveFocus();

    renderWithProviders(
      <AppShell>
        <main id="main-content" tabIndex={-1}>
          bugs page
        </main>
      </AppShell>,
    );
    await screen.findByRole("link", { name: "Bugs" });

    expect(outsideButton).toHaveFocus();
  });

  it("renders no demo banner by default", async () => {
    mockAuthenticated();
    renderWithProviders(
      <AppShell>
        <main id="main-content" tabIndex={-1} />
      </AppShell>,
    );

    await screen.findByRole("link", { name: "Bugs" });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders the demo banner text when the session provides one", async () => {
    mockAuthenticated({ demo_banner: "This is a shared demo environment." });
    renderWithProviders(
      <AppShell>
        <main id="main-content" tabIndex={-1} />
      </AppShell>,
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "This is a shared demo environment.",
    );
  });

  it("renders the demo banner on public routes too, before sign-in", async () => {
    mockPathname = "/sign-in";
    vi.mocked(getSession).mockResolvedValue({
      authenticated: false,
      role: null,
      user: null,
      organization: null,
      demo_banner: "Demo data may be reset at any time.",
    } as Session);

    renderWithProviders(
      <AppShell>
        <main id="main-content" tabIndex={-1}>
          sign-in page
        </main>
      </AppShell>,
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Demo data may be reset at any time.",
    );
    expect(screen.getByText("sign-in page")).toBeInTheDocument();
  });
});
