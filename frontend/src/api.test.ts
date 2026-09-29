import { afterEach, describe, expect, it, vi } from "vitest";
import { reportProductView } from "./api";

// The one piece of observability that lives in the browser: telling the server that a
// product was opened, because the detail does not ask the server for anything else.

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("reportProductView", () => {
  it("sends one POST to the product's views and does not wait for the answer", () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = reportProductView(3);

    // Nothing to await: the page carries on at once, whatever the server does.
    expect(result).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/products\/3\/views$/), {
      method: "POST",
    });
  });

  it("keeps quiet when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    expect(() => reportProductView(3)).not.toThrow();
    // Give the rejected promise time to settle. An error nobody catches would make vitest
    // fail the whole run with "Unhandled Rejection", which is what this test is guarding.
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
});
