import { Marked, type Token } from "marked";
import { decodeHTML } from "entities";

const escapeHtml = (text: string) =>
  text.replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c]!,
  );

// Render only Markdown structure. Customer HTML and external media remain inert text.
const markdown = new Marked({
  breaks: true,
  gfm: true,
  renderer: {
    html: ({ text, block }) =>
      block ? `<div class="markdown-literal">${escapeHtml(text)}</div>` : escapeHtml(text),
    link({ tokens, href }) {
      return `${this.parser.parseInline(tokens)} (${escapeHtml(href)})`;
    },
    image: ({ text, href }) =>
      `<span class="attachment">图片：${escapeHtml(text || "未命名")} (${escapeHtml(href)})</span>`,
  },
});

function plainTokens(tokens: Token[]): string {
  return tokens
    .map((token): string => {
      switch (token.type) {
        case "space":
          return "";
        case "br":
          return "\n";
        case "hr":
          return "\n——\n";
        case "code":
          return token.text + "\n\n";
        case "html":
        case "escape":
        case "codespan":
          return token.text;
        case "heading":
        case "paragraph":
        case "blockquote":
          return plainTokens(token.tokens ?? []) + "\n\n";
        case "strong":
        case "em":
          return plainTokens(token.tokens ?? []);
        case "del":
          return `〔划去：${plainTokens(token.tokens ?? [])}〕`;
        case "link":
          return `${plainTokens(token.tokens ?? [])} (${token.href})`;
        case "image":
          return `图片：${token.text || "未命名"} (${token.href})`;
        case "list":
          return (
            token.items
              .map((item: { tokens: Token[]; task: boolean; checked?: boolean }, index: number) => {
                const prefix = token.ordered ? `${Number(token.start) + index}. ` : "• ";
                const content = item.tokens
                  .map((part) => plainTokens([part]).trimEnd())
                  .join("\n")
                  .replace(/\n/g, "\n  ");
                return prefix + (item.task ? (item.checked ? "☑ " : "☐ ") : "") + content;
              })
              .join("\n") + "\n\n"
          );
        case "table":
          return (
            [token.header, ...token.rows]
              .map((row: { tokens: Token[] }[]) =>
                row.map((cell) => plainTokens(cell.tokens)).join(" | "),
              )
              .join("\n") + "\n\n"
          );
        case "text":
          return token.tokens ? plainTokens(token.tokens) : decodeHTML(token.text);
        case "def":
          return "";
        default:
          return token.raw;
      }
    })
    .join("");
}

export function reportMarkdown(source: string): { html: string; text: string } {
  return {
    html: markdown.parse(source, { async: false }),
    text: plainTokens(markdown.lexer(source)).trimEnd(),
  };
}
