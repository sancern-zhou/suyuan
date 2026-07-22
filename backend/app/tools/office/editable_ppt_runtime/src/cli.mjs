#!/usr/bin/env node
import { fileURLToPath } from "node:url";

import { SCHEMA_VERSION } from "./contracts.mjs";
import { compileDeck, inspectProject, renderPreview } from "./compile.mjs";

async function readStdin() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  return input.trim();
}

export async function handleRequest(request) {
  if (!request || typeof request !== "object") throw new Error("request must be an object");
  if (request.command === "health") {
    return { success: true, runtime: "editable-ppt", schemaVersion: SCHEMA_VERSION };
  }
  if (request.command === "inspect") return inspectProject(request.projectDir);
  if (request.command === "preview") {
    return renderPreview(request.projectDir, request.outputDir, {
      pages: request.pages,
      dirtySlides: request.dirtySlides,
      cacheDir: request.cacheDir,
    });
  }
  if (request.command === "compile") {
    return compileDeck(request.projectDir, request.outputDir, {
      pages: request.pages,
      dirtySlides: request.dirtySlides,
      cacheDir: request.cacheDir,
      editable: request.editable,
      fileName: request.fileName,
      fallbacks: request.fallbacks,
    });
  }
  throw new Error(`unsupported command: ${request.command}`);
}

async function main() {
  try {
    const input = await readStdin();
    let request;
    try {
      request = JSON.parse(input);
    } catch (error) {
      throw new Error(`COMPILER_PROTOCOL_ERROR: invalid JSON: ${error.message}`);
    }
    const result = await handleRequest(request);
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stderr.write(`${String(error.message || error)}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === fileURLToPath(new URL(`file://${process.argv[1]}`))) {
  main();
}
