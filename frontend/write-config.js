const fs = require("fs");
const path = require("path");

const apiBase = (process.env.API_BASE || "").replace(/\/$/, "");
const outputPath = path.join(__dirname, "config.js");

const contents = `// Generated at build time. Set API_BASE in Vercel project environment variables.
window.API_BASE = ${JSON.stringify(apiBase)};
`;

fs.writeFileSync(outputPath, contents, "utf8");
console.log(`Wrote ${outputPath} (API_BASE ${apiBase ? "set" : "empty"})`);
