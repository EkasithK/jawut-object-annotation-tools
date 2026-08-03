import { z } from "zod";

import { api } from "./client";

const capabilitiesSchema = z.object({
  native_dialogs: z.boolean(),
});

const browseSchema = z.object({
  path: z.string().nullable(),
});

/** What a Browse button asks for. */
export type BrowseKind = "folder" | "data_yaml";

/**
 * Asked once per launch and remembered: whether native dialogs work cannot
 * change while the process is alive, and every path field would otherwise ask.
 */
let capabilities: Promise<boolean> | null = null;

export function nativeDialogsAvailable(): Promise<boolean> {
  capabilities ??= api
    .get("/api/v1/system/capabilities", capabilitiesSchema)
    .then((c) => c.native_dialogs)
    .catch(() => false);
  return capabilities;
}

/** Opens a native chooser. Resolves to `null` when the user cancels. */
export async function browse(
  kind: BrowseKind,
  startIn = "",
): Promise<string | null> {
  const result = await api.post("/api/v1/system/browse", browseSchema, {
    kind,
    start_in: startIn,
  });
  return result.path;
}
