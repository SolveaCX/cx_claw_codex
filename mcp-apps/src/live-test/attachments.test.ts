import { describe, expect, test } from "bun:test";
import { attachmentLinks } from "./attachments.js";

describe("attachment links", () => {
  test("shows filenames without signed query strings and tolerates bad encoding", () => {
    expect(
      attachmentLinks([
        "https://example.com/proof%20of%20purchase.pdf?signature=secret",
        "https://example.com/%broken.jpg",
        "https://example.com/",
      ]).map((item) => item.name),
    ).toEqual(["proof of purchase.pdf", "%broken.jpg", "example.com"]);
  });
  test("ignores executable and malformed links and accepts old records", () => {
    expect(attachmentLinks(["javascript:alert(1)", "data:text/html,test", "not a url"])).toEqual(
      [],
    );
    expect(attachmentLinks()).toEqual([]);
  });
});

test("previews image and opaque URLs while keeping documents and videos as file links", () => {
  expect(
    attachmentLinks([
      "https://example.com/receipt.JPG?signature=abc",
      "https://example.com/download?id=123",
      "https://example.com/manual.pdf",
      "https://example.com/demo.mp4",
    ]).map((item) => item.image),
  ).toEqual([true, true, false, false]);
});
