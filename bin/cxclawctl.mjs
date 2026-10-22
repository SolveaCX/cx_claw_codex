#!/usr/bin/env node
import module from "node:module";

const major = Number(process.versions.node.split(".")[0]);
if (major < 22) {
  console.error(`CXClaw requires Node.js >= 22; current version is ${process.versions.node}`);
  process.exitCode = 1;
} else {
  module.enableCompileCache?.();
  await import("../dist/cli.js");
}
