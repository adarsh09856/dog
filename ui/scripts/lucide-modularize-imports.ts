import { readdirSync,readFileSync } from "node:fs";
import path from "node:path";

import ts from "typescript";

const SOURCE_EXTENSIONS = new Set([".js", ".jsx", ".ts", ".tsx"]);

function sourceFiles(directory: string): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
        const fullPath = path.join(directory, entry.name);
        if (entry.isDirectory()) {
            return sourceFiles(fullPath);
        }
        return SOURCE_EXTENSIONS.has(path.extname(entry.name)) && !entry.name.endsWith(".d.ts")
            ? [fullPath]
            : [];
    });
}

function exportedIconFiles(rootIndex: string): Map<string, string> {
    const exports = new Map<string, string>();
    const reexports = /export\s*\{([^}]+)\}\s*from\s*["']\.\/icons\/([^"']+\.js)["']/g;

    for (const match of rootIndex.matchAll(reexports)) {
        const [, bindings, file] = match;
        for (const binding of bindings.split(",")) {
            const alias = binding.trim().match(/^default\s+as\s+([A-Za-z_$][\w$]*)$/);
            if (alias) exports.set(alias[1], file);
        }
    }

    return exports;
}

/**
 * Build a Next modularizeImports lookup for the Lucide value imports used by
 * this UI. Lucide's root barrel also exports an `icons` namespace, which makes
 * webpack parse every icon when app code imports from the root entrypoint.
 */
export function buildLucideModularizeImports(
    sourceDirectories: string[],
    rootIndex: string,
): Record<string, string> {
    const exportedFiles = exportedIconFiles(rootIndex);
    const importedNames = new Set<string>();

    for (const file of sourceDirectories.flatMap(sourceFiles)) {
        const source = ts.createSourceFile(
            file,
            readFileSync(file, "utf8"),
            ts.ScriptTarget.Latest,
            true,
        );

        for (const statement of source.statements) {
            if (
                !ts.isImportDeclaration(statement) ||
                !ts.isStringLiteral(statement.moduleSpecifier) ||
                statement.moduleSpecifier.text !== "lucide-react"
            ) {
                continue;
            }

            const clause = statement.importClause;
            if (!clause || clause.isTypeOnly) continue;
            if (clause.name) {
                throw new Error(`Default Lucide import is not supported: ${file}`);
            }

            const bindings = clause.namedBindings;
            if (!bindings) continue;
            if (ts.isNamespaceImport(bindings)) {
                throw new Error(`Lucide namespace import loads the full icon barrel: ${file}`);
            }

            for (const element of bindings.elements) {
                if (element.isTypeOnly) continue;
                importedNames.add(element.propertyName?.text ?? element.name.text);
            }
        }
    }

    const mapping: Record<string, string> = {};
    const missing: string[] = [];
    for (const name of [...importedNames].sort()) {
        const file = exportedFiles.get(name);
        if (!file) {
            missing.push(name);
            continue;
        }
        mapping[name] = `lucide-react/dist/esm/icons/${file}`;
    }

    if (missing.length > 0) {
        throw new Error(`Lucide imports missing direct icon modules: ${missing.join(", ")}`);
    }

    return mapping;
}
