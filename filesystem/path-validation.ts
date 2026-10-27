import fs from "fs/promises";
import path from "path";
import os from 'os';

// Normalize all paths consistently
export function normalizePath(p: string): string {
  return path.normalize(p);
}

export function expandHome(filepath: string): string {
  if (filepath.startsWith('~/') || filepath === '~') {
    return path.join(os.homedir(), filepath.slice(1));
  }
  return filepath;
}

// Component-aware containment: p is dir itself or below it (no sibling-prefix matches)
export function isPathWithinAllowedDirectories(p: string, allowedDirectories: string[]): boolean {
  const normalized = normalizePath(p);
  return allowedDirectories.some(dir => {
    const prefix = dir.endsWith(path.sep) ? dir : dir + path.sep;
    return normalized === dir || normalized.startsWith(prefix);
  });
}

// Security utilities. allowedDirectories must be normalized realpaths.
export async function validatePath(requestedPath: string, allowedDirectories: string[]): Promise<string> {
  const expandedPath = expandHome(requestedPath);
  const absolute = path.isAbsolute(expandedPath)
    ? path.resolve(expandedPath)
    : path.resolve(process.cwd(), expandedPath);

  const normalizedRequested = normalizePath(absolute);

  // Check if path is within allowed directories
  if (!isPathWithinAllowedDirectories(normalizedRequested, allowedDirectories)) {
    throw new Error(`Access denied - path outside allowed directories: ${absolute} not in ${allowedDirectories.join(', ')}`);
  }

  // Handle symlinks by checking their real path
  let realPath: string;
  try {
    realPath = await fs.realpath(absolute);
  } catch (error: any) {
    if (error?.code !== 'ENOENT') {
      throw error;
    }
    // For new files that don't exist yet, verify parent directory.
    // A dangling symlink (leaf exists but its target does not) is rejected.
    const leaf = await fs.lstat(absolute).catch((e: any) => {
      if (e?.code === 'ENOENT') return null;
      throw e;
    });
    if (leaf) {
      throw new Error("Access denied - dangling symlink");
    }
    const parentDir = path.dirname(absolute);
    let realParentPath: string;
    try {
      realParentPath = await fs.realpath(parentDir);
    } catch {
      throw new Error(`Parent directory does not exist: ${parentDir}`);
    }
    if (!isPathWithinAllowedDirectories(realParentPath, allowedDirectories)) {
      throw new Error("Access denied - parent directory outside allowed directories");
    }
    return path.join(realParentPath, path.basename(absolute));
  }

  if (!isPathWithinAllowedDirectories(realPath, allowedDirectories)) {
    throw new Error("Access denied - symlink target outside allowed directories");
  }
  return realPath;
}
