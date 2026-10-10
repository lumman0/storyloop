import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import Ajv2020 from "ajv/dist/2020.js";
import standalone from "ajv/dist/standalone/index.js";
import { compile } from "json-schema-to-typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
const output = resolve(root, "web/src/lib/generated");
const localPython = resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const python = process.env.CONTRACT_PYTHON || (existsSync(localPython) ? localPython : "python");
const check = process.argv.includes("--check");
const schemas = JSON.parse(execFileSync(python, [resolve(root, "scripts/export_contracts.py")], { cwd: root, encoding: "utf8" }));
const artifacts = new Map([["schemas.json", JSON.stringify(schemas, null, 2) + "\n"]]);
for (const [name, schema] of Object.entries(schemas)) {
  artifacts.set(`${name}.ts`, await compile(schema, name, {
    bannerComment: "/* Generated from api/contracts.py. Run npm run contracts:generate. */",
    additionalProperties: false, unknownAny: true,
  }));
  const ajv = new Ajv2020({ strict: true, allowUnionTypes: true, coerceTypes: false,
    useDefaults: false, removeAdditional: false, code: { source: true, esm: true, lines: true } });
  // Pydantic's discriminator mapping is an annotation. oneOf/const enforce the union.
  ajv.addKeyword("discriminator");
  const validate = ajv.compile(schema);
  artifacts.set(`${name}.validator.js`, "// Generated from api/contracts.py.\n" + standalone(ajv, validate).trimEnd() + "\n");
  artifacts.set(`${name}.validator.d.ts`, `import type { ${name} } from "./${name}";\nexport default function validate(value: unknown): value is ${name};\n`);
}
const stale = [];
for (const [name, content] of artifacts) {
  const path = resolve(output, name);
  if (check) {
    const existing = await readFile(path, "utf8").catch(() => null);
    if (existing !== content) stale.push(name);
  } else {
    await mkdir(output, { recursive: true });
    await writeFile(path, content, "utf8");
  }
}
if (stale.length) throw new Error(`Player contracts are stale: ${stale.join(", ")}. Run npm run contracts:generate.`);
console.log(check ? "Player contracts match the Python source." : "Player contracts generated.");
