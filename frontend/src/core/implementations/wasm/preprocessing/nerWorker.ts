/**
 * Web Worker for running BERT NER model via Transformers.js.
 * Runs off the main thread to avoid UI blocking.
 *
 * Usage: Post { text, id } messages, receive { id, entities } responses.
 * First message triggers model download (~111MB, cached after first use).
 */

import { pipeline, env, type TokenClassificationOutput } from "@huggingface/transformers";

// Configure Transformers.js
env.allowLocalModels = false;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let nerPipeline: any = null;
let initPromise: Promise<void> | null = null;

async function initPipeline() {
  if (nerPipeline) return;
  if (initPromise) {
    await initPromise;
    return;
  }

  initPromise = (async () => {
    try {
      // Prefer WebGPU for sub-30ms inference, fall back to WASM (~2-5s)
      const device = typeof navigator !== "undefined" && "gpu" in navigator ? "webgpu" : "wasm";

      nerPipeline = await pipeline("token-classification", "Xenova/bert-base-NER", {
        device: device as "webgpu" | "wasm",
        dtype: "q8",
      });

      self.postMessage({ type: "ready" });
    } catch (err) {
      console.error("[nerWorker] Failed to initialize NER pipeline:", err);
      self.postMessage({ type: "error", error: String(err) });
      // Reset so the next request retries initialization
      initPromise = null;
    }
  })();

  await initPromise;
}

self.onmessage = async (e: MessageEvent) => {
  const { text, id } = e.data;

  if (e.data.type === "init") {
    await initPipeline();
    return;
  }

  try {
    await initPipeline();
    if (!nerPipeline) {
      self.postMessage({ id, entities: [], error: "Pipeline not initialized" });
      return;
    }

    const result = await nerPipeline(text, {
      aggregation_strategy: "simple",
    }) as TokenClassificationOutput;

    // Filter to relevant entity types (PERSON, ORG, LOC, MISC)
    // With aggregation_strategy: "simple", results include entity_group (not in base type)
    type AggregatedEntity = { entity_group: string; word: string; start?: number; end?: number; score: number };
    const entities = (result as unknown as AggregatedEntity[])
      .filter((e) => e.score >= 0.85)
      .map((e) => ({
        entity_group: e.entity_group,
        word: e.word,
        start: e.start,
        end: e.end,
        score: e.score,
      }));

    self.postMessage({ id, entities });
  } catch (err) {
    console.error("[nerWorker] NER inference error:", err);
    self.postMessage({ id, entities: [], error: String(err) });
  }
};
