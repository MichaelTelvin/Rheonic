import { useEffect } from "react";

interface SeoProps {
  title: string;
  description: string;
  path?: string;
  type?: "website" | "article";
  imagePath?: string;
  noindex?: boolean;
  jsonLd?: Record<string, unknown>;
}

function upsertMeta(name: string, content: string, attribute: "name" | "property" = "name"): void {
  let node = document.head.querySelector(`meta[${attribute}="${name}"]`) as HTMLMetaElement | null;
  if (!node) {
    node = document.createElement("meta");
    node.setAttribute(attribute, name);
    document.head.appendChild(node);
  }
  node.content = content;
}

function upsertCanonical(href: string): void {
  let node = document.head.querySelector('link[rel="canonical"]') as HTMLLinkElement | null;
  if (!node) {
    node = document.createElement("link");
    node.rel = "canonical";
    document.head.appendChild(node);
  }
  node.href = href;
}

function upsertJsonLd(jsonLd: Record<string, unknown>): void {
  const id = "rheonic-seo-jsonld";
  let node = document.head.querySelector(`script#${id}`) as HTMLScriptElement | null;
  if (!node) {
    node = document.createElement("script");
    node.id = id;
    node.type = "application/ld+json";
    document.head.appendChild(node);
  }
  node.textContent = JSON.stringify(jsonLd);
}

export function Seo({
  title,
  description,
  path = "/",
  type = "website",
  imagePath = import.meta.env.VITE_OG_IMAGE || "/landing/og-image.png",
  noindex = false,
  jsonLd,
}: SeoProps): null {
  useEffect(() => {
    const origin = window.location.origin;
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const canonicalUrl = `${origin}${normalizedPath}`;
    const imageUrl = imagePath.startsWith("http") ? imagePath : `${origin}${imagePath}`;

    document.title = title;
    upsertCanonical(canonicalUrl);
    upsertMeta("description", description);
    upsertMeta("robots", noindex ? "noindex, nofollow" : "index, follow");

    upsertMeta("og:type", type, "property");
    upsertMeta("og:site_name", "Rheonic", "property");
    upsertMeta("og:title", title, "property");
    upsertMeta("og:description", description, "property");
    upsertMeta("og:url", canonicalUrl, "property");
    upsertMeta("og:image", imageUrl, "property");

    upsertMeta("twitter:card", "summary_large_image");
    upsertMeta("twitter:title", title);
    upsertMeta("twitter:description", description);
    upsertMeta("twitter:image", imageUrl);

    if (jsonLd) {
      upsertJsonLd(jsonLd);
    }
  }, [description, imagePath, jsonLd, noindex, path, title, type]);

  return null;
}
