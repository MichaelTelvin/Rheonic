import { Fragment, useEffect, useState, type ReactNode } from "react";

import { PublicLayout } from "./PublicLayout";
import { Seo } from "./Seo";

type LegalDocumentPageProps = {
  title: string;
  description: string;
  path: string;
  markdownPath: string;
};

type InlineToken =
  | { type: "text"; value: string }
  | { type: "code"; value: string }
  | { type: "strong"; value: string }
  | { type: "link"; label: string; href: string }
  | { type: "email"; value: string };

function normalizeMarkdown(md: string): string {
  return md.replace(/\r\n/g, "\n").replace(/^[\t ]*[•]\s+/gm, "- ");
}

function parseInlineMarkdown(text: string): InlineToken[] {
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b)/gi;
  const tokens: InlineToken[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      tokens.push({ type: "text", value: text.slice(lastIndex, index) });
    }

    const value = match[0];
    if (value.startsWith("`") && value.endsWith("`")) {
      tokens.push({ type: "code", value: value.slice(1, -1) });
    } else if (value.startsWith("**") && value.endsWith("**")) {
      tokens.push({ type: "strong", value: value.slice(2, -2) });
    } else if (value.startsWith("[")) {
      const linkMatch = value.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (linkMatch) {
        tokens.push({ type: "link", label: linkMatch[1], href: linkMatch[2] });
      } else {
        tokens.push({ type: "text", value });
      }
    } else {
      tokens.push({ type: "email", value });
    }

    lastIndex = index + value.length;
  }

  if (lastIndex < text.length) {
    tokens.push({ type: "text", value: text.slice(lastIndex) });
  }

  return tokens;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  return parseInlineMarkdown(text).map((token, index) => {
    switch (token.type) {
      case "code":
        return <code key={index}>{token.value}</code>;
      case "strong":
        return <strong key={index}>{token.value}</strong>;
      case "link":
        return (
          <a key={index} href={token.href} target="_blank" rel="noreferrer">
            {token.label}
          </a>
        );
      case "email":
        return (
          <a key={index} href={`mailto:${token.value}`}>
            {token.value}
          </a>
        );
      default:
        return <Fragment key={index}>{token.value}</Fragment>;
    }
  });
}

function renderMarkdown(md: string): ReactNode[] {
  const lines = normalizeMarkdown(md).split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let firstParagraph = true;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const codeLines: string[] = [];
      const language = line.slice(3).trim();
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) {
        i += 1;
      }
      out.push(
        <pre key={`pre-${out.length}`}>
          <code className={language ? `language-${language}` : undefined}>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (line.startsWith("### ")) {
      out.push(<h3 key={`h3-${out.length}`}>{renderInlineMarkdown(line.slice(4).trim())}</h3>);
      i += 1;
      continue;
    }

    if (line.startsWith("## ")) {
      out.push(<h2 key={`h2-${out.length}`}>{renderInlineMarkdown(line.slice(3).trim())}</h2>);
      i += 1;
      continue;
    }

    if (line.startsWith("# ")) {
      out.push(<h1 key={`h1-${out.length}`}>{renderInlineMarkdown(line.slice(2).trim())}</h1>);
      i += 1;
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(<li key={`ol-item-${i}`}>{renderInlineMarkdown(lines[i].replace(/^\d+\.\s+/, ""))}</li>);
        i += 1;
      }
      out.push(<ol key={`ol-${out.length}`}>{items}</ol>);
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(<li key={`ul-item-${i}`}>{renderInlineMarkdown(lines[i].replace(/^[-*]\s+/, ""))}</li>);
        i += 1;
      }
      out.push(<ul key={`ul-${out.length}`}>{items}</ul>);
      continue;
    }

    const paragraphLines = [trimmed];
    i += 1;
    while (i < lines.length) {
      const nextLine = lines[i];
      const nextTrimmed = nextLine.trim();
      if (
        !nextTrimmed ||
        nextLine.startsWith("#") ||
        nextLine.startsWith("```") ||
        /^\d+\.\s+/.test(nextLine) ||
        /^[-*]\s+/.test(nextLine)
      ) {
        break;
      }
      paragraphLines.push(nextTrimmed);
      i += 1;
    }

    out.push(
      <p key={`p-${out.length}`} className={firstParagraph ? "docs-lead" : undefined}>
        {renderInlineMarkdown(paragraphLines.join(" "))}
      </p>,
    );
    firstParagraph = false;
  }

  return out;
}

export function LegalDocumentPage({
  title,
  description,
  path,
  markdownPath,
}: LegalDocumentPageProps): JSX.Element {
  const [content, setContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadContent(): Promise<void> {
      try {
        const response = await fetch(markdownPath, { headers: { Accept: "text/markdown,text/plain" } });
        if (!response.ok) {
          throw new Error(`Failed to load ${markdownPath}: ${response.status}`);
        }
        const markdown = await response.text();
        if (!active) {
          return;
        }
        setContent(markdown);
        setError(null);
      } catch (loadError) {
        if (!active) {
          return;
        }
        const message = loadError instanceof Error ? loadError.message : "Failed to load document.";
        setError(message);
        setContent("");
      }
    }

    void loadContent();

    return () => {
      active = false;
    };
  }, [markdownPath]);

  return (
    <PublicLayout navAuthHref="/login" navAuthLabel="Sign in" shellClassName="public-shell--marketing" showDocsLink={false}>
      <Seo title={`${title} | Rheonic`} description={description} path={path} />
      <section className="landing-marketing">
        <div className="docs-article-shell">
          <article className="docs-article docs-markdown">
            <p className="docs-eyebrow">Legal</p>
            {error ? <p>We couldn&apos;t load this document right now.</p> : null}
            {content ? renderMarkdown(content) : !error ? <p>Loading document...</p> : null}
          </article>
        </div>
      </section>
    </PublicLayout>
  );
}
