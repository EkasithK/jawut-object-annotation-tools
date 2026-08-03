import { z } from "zod";

/** Every response from the API arrives in this envelope, success or failure. */
const envelopeSchema = <T extends z.ZodTypeAny>(data: T) =>
  z.object({
    data: data.nullable(),
    error: z
      .object({
        code: z.string(),
        message: z.string(),
        details: z.array(z.record(z.unknown())).default([]),
      })
      .nullable(),
    meta: z.object({
      request_id: z.string(),
      timestamp: z.string(),
    }),
  });

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * The packaged app injects a per-launch token so that another local process
 * cannot drive the API by guessing the port. It is absent in development.
 */
function launchToken(): string | null {
  return (window as { __JAWUT_TOKEN__?: string }).__JAWUT_TOKEN__ ?? null;
}

async function request<T extends z.ZodTypeAny>(
  path: string,
  schema: T,
  init?: RequestInit,
): Promise<z.infer<T>> {
  const token = launchToken();
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Jawut-Token": token } : {}),
      ...init?.headers,
    },
  });

  const body: unknown = await response.json();
  const parsed = envelopeSchema(schema).parse(body);

  if (parsed.error) {
    throw new ApiError(parsed.error.code, parsed.error.message, response.status);
  }
  if (parsed.data === null) {
    throw new ApiError("EMPTY_RESPONSE", "server returned no data", response.status);
  }
  return parsed.data;
}

export const api = {
  get: <T extends z.ZodTypeAny>(path: string, schema: T) =>
    request(path, schema),

  post: <T extends z.ZodTypeAny>(path: string, schema: T, payload?: unknown) =>
    request(path, schema, {
      method: "POST",
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
    }),

  put: <T extends z.ZodTypeAny>(path: string, schema: T, payload?: unknown) =>
    request(path, schema, {
      method: "PUT",
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
    }),

  patch: <T extends z.ZodTypeAny>(path: string, schema: T, payload?: unknown) =>
    request(path, schema, {
      method: "PATCH",
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
    }),

  delete: <T extends z.ZodTypeAny>(path: string, schema: T) =>
    request(path, schema, { method: "DELETE" }),
};

export const healthSchema = z.object({
  status: z.string(),
  version: z.string(),
});

export const getHealth = () => api.get("/health", healthSchema);
