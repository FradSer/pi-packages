import { readFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import type { ImageContent } from "@earendil-works/pi-ai";
import { resizeImage } from "@earendil-works/pi-coding-agent";

const IMAGE_EXTENSIONS = new Set([".gif", ".jpeg", ".jpg", ".png", ".webp"]);
const PATH_PATTERN = /(?:"([^"]+\.(?:gif|jpe?g|png|webp))"|'([^']+\.(?:gif|jpe?g|png|webp))'|((?:~|\/)(?:\\ |[^\s])+\.(?:gif|jpe?g|png|webp)))/gi;
const IMAGE_PATH_HINT = /\.(?:gif|jpe?g|png|webp)(?:[\s"']|$)/i;

function unescapePath(value: string): string {
  const unescaped = value.replace(/\\ /g, " ");
  if (unescaped === "~") return process.env.HOME ?? unescaped;
  if (unescaped.startsWith("~/")) {
    return resolve(process.env.HOME ?? "~", unescaped.slice(2));
  }
  return resolve(unescaped);
}

function mimeTypeForPath(path: string): string | undefined {
  switch (extname(path).toLowerCase()) {
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".png":
      return "image/png";
    case ".gif":
      return "image/gif";
    case ".webp":
      return "image/webp";
    default:
      return undefined;
  }
}

export interface ExtractedInputImages {
  text: string;
  images: ImageContent[];
  paths: string[];
}

function removeImageFileTags(text: string): string {
  return text.replace(
    /<file\s+name=(?:"[^"]*\.(?:gif|jpe?g|png|webp)"|'[^']*\.(?:gif|jpe?g|png|webp)'|[^>]*\.(?:gif|jpe?g|png|webp))>[^<]*<\/file>/gi,
    "",
  );
}

export function mayContainInputImage(text: string): boolean {
  return IMAGE_PATH_HINT.test(text);
}

export async function extractInputImages(text: string): Promise<ExtractedInputImages> {
  const searchText = removeImageFileTags(text);
  const byPath = new Map<string, { raw: string; path: string }>();
  for (const line of searchText.split("\n")) {
    const value = line.trim();
    if (!(value.startsWith("/") || value.startsWith("~/"))) continue;
    const path = unescapePath(value);
    if (!IMAGE_EXTENSIONS.has(extname(path).toLowerCase())) continue;
    byPath.set(path, { raw: value, path });
  }
  for (const match of searchText.matchAll(PATH_PATTERN)) {
    const value = match[1] ?? match[2] ?? match[3];
    if (!value) continue;
    const path = unescapePath(value);
    if (!IMAGE_EXTENSIONS.has(extname(path).toLowerCase())) continue;
    byPath.set(path, { raw: match[0], path });
  }
  const candidates = [...byPath.values()];

  const images: ImageContent[] = [];
  const consumed = new Set<string>();
  const paths: string[] = [];
  for (const candidate of candidates) {
    try {
      const mimeType = mimeTypeForPath(candidate.path);
      if (!mimeType) continue;
      const bytes = await readFile(candidate.path);
      if (bytes.length === 0) continue;
      const resized = await resizeImage(bytes, mimeType);
      if (!resized) continue;
      images.push({ type: "image", data: resized.data, mimeType: resized.mimeType });
      consumed.add(candidate.raw);
      paths.push(candidate.path);
    } catch {
      // A path-looking string that is not a readable image remains normal text.
    }
  }

  let cleaned = searchText;
  for (const raw of consumed) cleaned = cleaned.replace(raw, "");
  cleaned = cleaned.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();

  return { text: cleaned, images, paths };
}
