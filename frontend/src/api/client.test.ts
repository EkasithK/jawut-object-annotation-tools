import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, fetchObjectUrl } from "./client";

const IMAGE_PATH = "/api/v1/images/abc/file";
const TOKEN = "test-launch-token";

/** Stand in for the browser globals `fetchObjectUrl` reaches for. */
function stubBrowser(token: string | null, response: Partial<Response>): {
  fetch: ReturnType<typeof vi.fn>;
  createObjectURL: ReturnType<typeof vi.fn>;
} {
  const fetch = vi.fn().mockResolvedValue(response);
  const createObjectURL = vi.fn().mockReturnValue("blob:stub");

  vi.stubGlobal("window", token === null ? {} : { __JAWUT_TOKEN__: token });
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("URL", { createObjectURL });

  return { fetch, createObjectURL };
}

const okResponse = (): Partial<Response> => ({
  ok: true,
  status: 200,
  blob: () => Promise.resolve(new Blob(["jpeg-bytes"])),
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchObjectUrl", () => {
  /**
   * The regression this exists for: the canvas used to assign the image
   * endpoint straight to `image.src`. An image element sends no headers, so the
   * request arrived without the launch token, the server answered 401, and the
   * canvas sat on "loading image" forever. It only worked in development, where
   * no token is set — which is why the suite stayed green while the packaged
   * application could not display a single image.
   */
  it("sends the launch token, which an image element could not", async () => {
    const { fetch } = stubBrowser(TOKEN, okResponse());

    await fetchObjectUrl(IMAGE_PATH);

    expect(fetch).toHaveBeenCalledWith(IMAGE_PATH, {
      headers: { "X-Jawut-Token": TOKEN },
    });
  });

  it("omits the header in development, where there is no token", async () => {
    const { fetch } = stubBrowser(null, okResponse());

    await fetchObjectUrl(IMAGE_PATH);

    expect(fetch).toHaveBeenCalledWith(IMAGE_PATH, { headers: {} });
  });

  it("returns an object URL built from the response body", async () => {
    const { createObjectURL } = stubBrowser(TOKEN, okResponse());

    expect(await fetchObjectUrl(IMAGE_PATH)).toBe("blob:stub");
    expect(createObjectURL).toHaveBeenCalledOnce();
  });

  it("raises rather than resolving to an unusable URL", async () => {
    stubBrowser(TOKEN, { ok: false, status: 401 });

    await expect(fetchObjectUrl(IMAGE_PATH)).rejects.toBeInstanceOf(ApiError);
  });
});
