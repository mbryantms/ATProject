#!/usr/bin/env node
/**
 * citeproc_bridge.js — Citation formatting bridge for Django.
 *
 * Reads a JSON request from stdin, runs citeproc-js to format citations
 * and bibliography entries, writes JSON result to stdout.
 *
 * Input JSON:
 * {
 *   "items": [ {CSL-JSON item objects with "id" field}, ... ],
 *   "style": "apa",                    // style filename (without .csl)
 *   "citationClusters": [              // ordered list of citation clusters as they appear in the document
 *     {
 *       "citationItems": [{"id": "smith2024climate", "locator": "42-56", "label": "page"}],
 *       "properties": {"noteIndex": 0}
 *     }
 *   ],
 *   "stylePath": "/path/to/styles/",   // directory containing .csl files
 *   "localePath": "/path/to/locales/", // directory containing locale XML files
 *   "lang": "en-US"                    // optional, defaults to "en-US"
 * }
 *
 * Output JSON:
 * {
 *   "bibliography": [
 *     ["smith2024climate", "<div class=\"csl-entry\">Smith, J. (2024). Climate change...</div>"]
 *   ],
 *   "citations": [
 *     "(Smith, 2024, pp. 42-56)"
 *   ]
 * }
 *
 * On error, outputs:
 * { "error": "description of the error" }
 */

'use strict';

const fs = require('fs');
const path = require('path');
const CSL = require('citeproc');

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => (data += chunk));
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

function loadFile(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

function buildSys(items, localePath, _lang) {
  const itemMap = {};
  for (const item of items) {
    itemMap[item.id] = item;
  }

  return {
    retrieveLocale(langCode) {
      const localeFile = path.join(localePath, `locales-${langCode}.xml`);
      try {
        return loadFile(localeFile);
      } catch {
        // Fall back to en-US if requested locale is not available
        const fallback = path.join(localePath, 'locales-en-US.xml');
        return loadFile(fallback);
      }
    },
    retrieveItem(id) {
      return itemMap[id] || null;
    },
  };
}

async function main() {
  let input;
  try {
    const raw = await readStdin();
    input = JSON.parse(raw);
  } catch (e) {
    process.stdout.write(JSON.stringify({ error: `Invalid JSON input: ${e.message}` }));
    process.exit(1);
  }

  const {
    items = [],
    style = 'apa',
    citationClusters = [],
    stylePath = path.join(__dirname, 'styles'),
    localePath = path.join(__dirname, 'locales'),
    lang = 'en-US',
  } = input;

  if (items.length === 0) {
    process.stdout.write(JSON.stringify({ bibliography: [], citations: [] }));
    process.exit(0);
  }

  // Load CSL style
  let styleXml;
  try {
    const styleName = style.endsWith('.csl') ? style.replace(/\.csl$/, '') : style;
    const styleFile = path.join(stylePath, `${styleName}.csl`);
    styleXml = loadFile(styleFile);
  } catch (e) {
    process.stdout.write(
      JSON.stringify({ error: `Failed to load style "${style}": ${e.message}` }),
    );
    process.exit(1);
  }

  // Build citeproc engine
  const sys = buildSys(items, localePath, lang);
  let citeproc;
  try {
    citeproc = new CSL.Engine(sys, styleXml, lang);
  } catch (e) {
    process.stdout.write(
      JSON.stringify({ error: `Failed to initialize citeproc: ${e.message}` }),
    );
    process.exit(1);
  }

  // Register all items
  const itemIds = items.map((item) => item.id);
  citeproc.updateItems(itemIds);

  // Process citation clusters in document order to get inline citation text
  const citationResults = [];
  const citationsPre = [];

  for (let i = 0; i < citationClusters.length; i++) {
    const cluster = citationClusters[i];
    // Ensure cluster has a citationID
    if (!cluster.citationID) {
      cluster.citationID = `cite-${i}`;
    }
    if (!cluster.properties) {
      cluster.properties = { noteIndex: 0 };
    }

    const citationsPost = [];
    // Process this cluster; citationsPre contains all previously processed clusters
    const result = citeproc.processCitationCluster(
      cluster,
      citationsPre,
      citationsPost,
    );

    // result[1] is an array of [index, text, citationID] triples
    // The last entry corresponds to the current citation
    if (result[1] && result[1].length > 0) {
      // Find the entry for the current citation
      const currentEntry = result[1].find((r) => r[2] === cluster.citationID);
      if (currentEntry) {
        citationResults.push(currentEntry[1]);
      } else {
        // Fallback: use the last entry
        citationResults.push(result[1][result[1].length - 1][1]);
      }
    } else {
      citationResults.push('');
    }

    // Add this cluster to citationsPre for subsequent clusters
    citationsPre.push([cluster.citationID, cluster.properties.noteIndex || 0]);
  }

  // Generate bibliography
  let bibliography = [];
  try {
    const bibResult = citeproc.makeBibliography();
    if (bibResult) {
      const [bibParams, bibEntries] = bibResult;
      // Map each bibliography entry to its item ID
      const bibIds = bibParams.entry_ids || [];
      for (let i = 0; i < bibEntries.length; i++) {
        const id = bibIds[i]
          ? Array.isArray(bibIds[i])
            ? bibIds[i][0]
            : bibIds[i]
          : `unknown-${i}`;
        bibliography.push([id, bibEntries[i].trim()]);
      }
    }
  } catch (_e) {
    // Bibliography generation can fail for some styles (e.g., note-only styles)
    // This is not fatal — we still have inline citations
  }

  process.stdout.write(
    JSON.stringify({
      bibliography,
      citations: citationResults,
    }),
  );
}

main().catch((e) => {
  process.stdout.write(JSON.stringify({ error: `Unexpected error: ${e.message}` }));
  process.exit(1);
});
