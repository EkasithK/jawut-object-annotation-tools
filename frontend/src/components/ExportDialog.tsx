import { useState } from "react";

import { ApiError } from "../api/client";
import {
  runExport,
  type ExportLayout,
  type ExportResult,
} from "../api/export";
import { Dialog } from "./Dialog";
import { PathField } from "./PathField";

const DEFAULTS = { train: 70, val: 15, test: 15 };

export function ExportDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [destination, setDestination] = useState("");
  const [layout, setLayout] = useState<ExportLayout>("split");
  const [percentages, setPercentages] = useState(DEFAULTS);
  const [seed, setSeed] = useState(42);
  const [includeUnlabeled, setIncludeUnlabeled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const total = percentages.train + percentages.val + percentages.test;
  const ratiosValid = total === 100;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      setResult(
        await runExport({
          destination: destination.trim(),
          layout,
          ratios: {
            train: percentages.train / 100,
            val: percentages.val / 100,
            test: percentages.test / 100,
          },
          seed,
          includeUnlabeled,
        }),
      );
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function close() {
    setResult(null);
    setError(null);
    onClose();
  }

  return (
    <Dialog open={open} title="Export dataset" onClose={close}>
      {result ? (
        <>
          <p className="text-[14px] leading-relaxed">
            Wrote <span className="font-mono">{result.images_exported}</span> images
            and <span className="font-mono">{result.boxes_exported}</span> boxes.
          </p>
          {result.empty_labels > 0 && (
            <p className="mt-1 text-[13px] text-ink-muted">
              <span className="font-mono">{result.empty_labels}</span> background
              images exported with an empty label file.
            </p>
          )}

          <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
            {Object.entries(result.counts_per_split).map(([split, count]) => (
              <div key={split} className="border border-line py-2">
                <dt className="font-mono text-[12px] uppercase tracking-wider font-medium text-ink-faint">
                  {split}
                </dt>
                <dd className="font-mono text-[16px]">{count}</dd>
              </div>
            ))}
          </dl>

          <p className="mt-3 break-all font-mono text-[12px] text-ink-faint">
            {result.destination}
          </p>

          <button
            onClick={close}
            className="mt-4 w-full bg-accent px-3 py-2 text-[14px] font-medium
              text-on-accent transition-colors hover:bg-accent-hover"
          >
            Done
          </button>
        </>
      ) : (
        <form onSubmit={(e) => void submit(e)}>
          <PathField
            id="export-destination"
            label="Destination folder"
            value={destination}
            onChange={setDestination}
            placeholder="C:\datasets\helmet_v2"
            hint="Must be empty or not exist yet. Browse to the parent, then add a
              new folder name to the end."
            autoFocus
          />

          <fieldset className="mt-4">
            <legend className="mb-1.5 text-[12px] uppercase tracking-wider font-medium text-ink-muted">
              Layout
            </legend>
            <div className="grid grid-cols-2 gap-2">
              <LayoutOption
                id="layout-split"
                checked={layout === "split"}
                onSelect={() => setLayout("split")}
                title="Split"
                hint="train / val / test, stratified by class"
              />
              <LayoutOption
                id="layout-flat"
                checked={layout === "flat"}
                onSelect={() => setLayout("flat")}
                title="Flat"
                hint="one images and labels pair, split later"
              />
            </div>
          </fieldset>

          {layout === "split" && (
            <div className="mt-4">
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="text-[12px] uppercase tracking-wider font-medium text-ink-muted">
                  Ratios
                </span>
                <span
                  className={`font-mono text-[12px] ${
                    ratiosValid ? "text-ink-faint" : "text-status-review"
                  }`}
                >
                  {total}%
                </span>
              </div>
              <div className="grid grid-cols-4 gap-2">
                {(["train", "val", "test"] as const).map((key) => (
                  <div key={key}>
                    <label
                      htmlFor={`ratio-${key}`}
                      className="mb-1 block font-mono text-[12px] uppercase text-ink-faint"
                    >
                      {key}
                    </label>
                    <input
                      id={`ratio-${key}`}
                      type="number"
                      min={0}
                      max={100}
                      value={percentages[key]}
                      onChange={(e) =>
                        setPercentages({
                          ...percentages,
                          [key]: Number(e.target.value),
                        })
                      }
                      className="w-full border border-line bg-surface-2 px-2 py-1.5
                        font-mono text-[13px] focus:border-accent focus:outline-none"
                    />
                  </div>
                ))}
                <div>
                  <label
                    htmlFor="export-seed"
                    className="mb-1 block font-mono text-[12px] uppercase text-ink-faint"
                  >
                    seed
                  </label>
                  <input
                    id="export-seed"
                    type="number"
                    value={seed}
                    onChange={(e) => setSeed(Number(e.target.value))}
                    className="w-full border border-line bg-surface-2 px-2 py-1.5
                      font-mono text-[13px] focus:border-accent focus:outline-none"
                  />
                </div>
              </div>
            </div>
          )}

          <label className="mt-4 flex items-center gap-2 text-[13px]">
            <input
              type="checkbox"
              checked={includeUnlabeled}
              onChange={(e) => setIncludeUnlabeled(e.target.checked)}
              className="accent-accent"
            />
            Include images nobody has opened
          </label>
          <p className="ml-6 mt-0.5 text-[12px] leading-relaxed text-ink-faint">
            Off by default: exporting them as empty labels would claim they contain
            no objects.
          </p>

          <button
            type="submit"
            disabled={busy || !destination.trim() || (layout === "split" && !ratiosValid)}
            className="mt-4 w-full bg-accent px-3 py-2 text-[14px] font-medium
              text-on-accent transition-colors hover:bg-accent-hover
              disabled:bg-surface-3 disabled:text-ink-faint"
          >
            {busy ? "Exporting…" : "Export"}
          </button>
        </form>
      )}

      {error && (
        <p className="mt-4 border-l-2 border-status-review bg-surface-2 px-3 py-2 text-[13px]">
          {error}
        </p>
      )}
    </Dialog>
  );
}

function LayoutOption({
  id,
  checked,
  onSelect,
  title,
  hint,
}: {
  id: string;
  checked: boolean;
  onSelect: () => void;
  title: string;
  hint: string;
}) {
  return (
    <label
      htmlFor={id}
      className={`cursor-pointer border px-2.5 py-2 transition-colors ${
        checked ? "border-accent bg-surface-2" : "border-line hover:border-line-strong"
      }`}
    >
      <input
        id={id}
        type="radio"
        name="export-layout"
        checked={checked}
        onChange={onSelect}
        className="sr-only"
      />
      <span className="block text-[13px] font-medium">{title}</span>
      <span className="mt-0.5 block text-[12px] leading-snug text-ink-faint">
        {hint}
      </span>
    </label>
  );
}
