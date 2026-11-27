import { expect, test } from "bun:test";
import { reportMarkdown } from "./report-markdown.js";

test("renders readable Markdown and plain spreadsheet text from one source", () => {
  const source =
    "### 定位\n\n**节点「售后支持」**\n\n1. 检查条件\n2. 保留 `QUALITY_HANDOFF` 原值\n   - 核对下一步\n\n> 待复测\n\n```text\n**literal** <node>\n```";
  const { html, text } = reportMarkdown(source);
  expect(html).toContain("<strong>节点「售后支持」</strong>");
  expect(html).toContain("<ol>");
  expect(html).toContain("<blockquote>");
  expect(text).toContain("节点「售后支持」");
  expect(text).toContain("2. 保留 QUALITY_HANDOFF 原值");
  expect(text).toContain("• 核对下一步");
  expect(text).not.toContain("###");
  expect(text).not.toContain("**节点");
  expect(text).toContain("**literal** <node>");
});

test("keeps customer HTML, URLs and media inert without losing visible content", () => {
  const source =
    "<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[click](javascript:alert%281%29) ![photo](https://example.com/pixel)\n\nQUALITY_HANDOFF WAIT a_b_c";
  const { html, text } = reportMarkdown(source);
  expect(html).not.toMatch(/<(script|img|a)\b/i);
  expect(html).toContain("&lt;script&gt;");
  expect(html).toContain("photo");
  expect(text).toContain("QUALITY_HANDOFF WAIT a_b_c");
  expect(text).toContain("javascript:alert%281%29");
});

test("keeps literal code, escaped punctuation, entities and nested lists readable", () => {
  const result = reportMarkdown("A &amp; B\\_C\n\n- **父节点**\n  - 子节点\n\n`&amp; **原文**`");
  expect(result.text).toContain("A & B_C");
  expect(result.text).toContain("• 父节点\n  • 子节点");
  expect(result.text).toContain("&amp; **原文**");
});
