// Companion extension for the vscode-agent-bridge MCP server (design #70/#71).
//
// At activation: idempotently installs the five cline-sr hook scripts to
// ~/Documents/Cline/Hooks/, checks cline-sr's hooksEnabled flag, and — when
// BRIDGE_PORT is present in the environment (only true inside the dedicated
// bridge window) — holds one persistent WebSocket to the MCP server. The
// socket is the window's liveness signal; task prompts arrive over it and are
// submitted to cline-sr via its vscode://cline-sr.cline-sr/task URI handler.

import * as vscode from "vscode";
import * as crypto from "crypto";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import WebSocket from "ws";

const HOOK_NAMES = [
  "TaskStart",
  "PreToolUse",
  "PostToolUse",
  "TaskComplete",
  "TaskCancel",
];
const HOOK_MARKER = "vscode-agent-bridge hook";
const HOOKS_DIR = path.join(os.homedir(), "Documents", "Cline", "Hooks");
const GLOBAL_STATE_FILE = path.join(
  os.homedir(),
  ".cline-sr",
  "data",
  "globalState.json"
);
const RECONNECT_DELAY_MS = 3000;

let ws: WebSocket | undefined;
let reconnectTimer: NodeJS.Timeout | undefined;
let noConnectTimer: NodeJS.Timeout | undefined;
let disposed = false;
let output: vscode.OutputChannel | undefined;

function log(level: "INFO" | "ERROR", message: string): void {
  output?.appendLine(`${new Date().toISOString()} [${level}] ${message}`);
}

export function activate(context: vscode.ExtensionContext): void {
  // OutputChannel creation failure is non-fatal (ADR-0069): the extension
  // keeps running; errors then surface only in the developer console.
  try {
    output = vscode.window.createOutputChannel("Agent Bridge");
    context.subscriptions.push(output);
  } catch (err) {
    console.error(`vscode-agent-bridge: OutputChannel creation failed: ${err}`);
  }

  installHooks(context);

  const port = process.env.BRIDGE_PORT;
  if (!port) {
    return; // not the dedicated bridge window — hooks refreshed, nothing else to do
  }

  if (hooksDisabled()) {
    vscode.window.showErrorMessage(
      "vscode-agent-bridge: cline-sr hooks are disabled, so the bridge cannot " +
        "observe task lifecycle. Enable Hooks in cline-sr's settings webview, " +
        "then reload this window."
    );
    return;
  }

  connect(port);
  noConnectTimer = setTimeout(() => {
    if (ws === undefined) {
      vscode.commands.executeCommand("workbench.action.closeWindow");
    }
  }, 30_000);
  context.subscriptions.push({
    dispose: () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (noConnectTimer) clearTimeout(noConnectTimer);
      ws?.close();
    },
  });
}

export function deactivate(): void {
  disposed = true;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (noConnectTimer) clearTimeout(noConnectTimer);
  ws?.close();
}

function connect(port: string): void {
  ws = new WebSocket(`ws://127.0.0.1:${port}/ws`);
  let wasOpen = false;

  ws.on("open", () => {
    wasOpen = true;
    log("INFO", `WS connected to bridge on port ${port}`);
    if (noConnectTimer) {
      clearTimeout(noConnectTimer);
      noConnectTimer = undefined;
    }
  });

  ws.on("message", (data) => {
    let msg: { type?: string; prompt?: string };
    try {
      msg = JSON.parse(data.toString());
    } catch {
      return;
    }
    if (msg.type === "submit" && typeof msg.prompt === "string") {
      submitToClineSr(msg.prompt);
    }
  });

  const closeWindow = () => {
    vscode.commands.executeCommand("workbench.action.closeWindow");
  };

  const retry = () => {
    log("INFO", wasOpen ? "WS disconnected from bridge" : "WS failed to connect to bridge");
    ws = undefined;
    if (disposed) {
      return;
    }
    closeWindow();
  };
  ws.on("close", retry);
  ws.on("error", (err) => {
    // close fires after error; retry is scheduled there
    log("ERROR", `WS error: ${err instanceof Error ? err.message : err}`);
  });
}

function submitToClineSr(prompt: string): void {
  log("INFO", `cline-sr task URI invoked (prompt length: ${prompt.length})`);
  const uri = vscode.Uri.parse(
    `${vscode.env.uriScheme}://cline-sr.cline-sr/task?prompt=${encodeURIComponent(prompt)}`
  );
  vscode.env.openExternal(uri).then(undefined, (err: unknown) => {
    // Log the error's message only — never the uri/prompt content (ADR-0069).
    const detail = err instanceof Error ? err.message : String(err);
    log("ERROR", `task submission to cline-sr failed: ${detail}`);
    vscode.window.showErrorMessage(
      `vscode-agent-bridge: task submission to cline-sr failed: ${err}`
    );
  });
}

function hooksDisabled(): boolean {
  // cline-sr defaults hooksEnabled to true when the key is absent (bundle:
  // `function jR(t){return t??!0}`), so only an explicit false blocks.
  try {
    const state = JSON.parse(fs.readFileSync(GLOBAL_STATE_FILE, "utf8"));
    return state.hooksEnabled === false;
  } catch {
    return false;
  }
}

function installHooks(context: vscode.ExtensionContext): void {
  const templatesDir = path.join(context.extensionPath, "hooks");
  const collisions: string[] = [];

  fs.mkdirSync(HOOKS_DIR, { recursive: true });

  for (const name of HOOK_NAMES) {
    const template = fs.readFileSync(path.join(templatesDir, name), "utf8");
    const target = path.join(HOOKS_DIR, name);

    let existing: string | undefined;
    try {
      existing = fs.readFileSync(target, "utf8");
    } catch {
      existing = undefined;
    }

    if (existing !== undefined) {
      if (sha256(existing) === sha256(template)) {
        continue; // up to date
      }
      if (!existing.includes(HOOK_MARKER)) {
        collisions.push(name);
        continue; // someone else's hook — never overwrite
      }
      // ours but stale: fall through and rewrite
    }

    fs.writeFileSync(target, template, { mode: 0o755 });
    fs.chmodSync(target, 0o755);
  }

  if (collisions.length > 0) {
    vscode.window.showWarningMessage(
      `vscode-agent-bridge: existing hook script(s) not owned by the bridge ` +
        `were left untouched: ${collisions.join(", ")} (in ${HOOKS_DIR}). ` +
        `The bridge will not receive these lifecycle events.`
    );
  }
}

function sha256(s: string): string {
  return crypto.createHash("sha256").update(s).digest("hex");
}
