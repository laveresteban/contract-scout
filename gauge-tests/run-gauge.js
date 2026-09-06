const { existsSync } = require("fs");
const { delimiter, join } = require("path");
const { spawnSync } = require("child_process");

const windows = process.platform === "win32";
const pythonDir = join(__dirname, ".venv", windows ? "Scripts" : "bin");
const python = join(pythonDir, windows ? "python.exe" : "python");
const gauge = join(__dirname, "node_modules", "@getgauge", "cli", "bin", windows ? "gauge.exe" : "gauge");

function run(command, args, env = process.env) {
  const result = spawnSync(command, args, { cwd: __dirname, env, stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status || 1);
}

if (!existsSync(python)) {
  run(process.env.PYTHON || "python", ["-m", "venv", ".venv"]);
  run(python, ["-m", "pip", "install", "getgauge==0.5.1"]);
}

const env = { ...process.env, PATH: `${pythonDir}${delimiter}${process.env.PATH}` };
run(gauge, ["run", "specs"], env);
