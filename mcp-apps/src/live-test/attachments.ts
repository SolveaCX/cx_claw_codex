export function attachmentLinks(
  attachments: string[] = [],
): { url: string; name: string; image: boolean }[] {
  return attachments.flatMap((value) => {
    try {
      const url = new URL(value);
      if (url.protocol !== "https:" && url.protocol !== "http:") return [];
      const filename = url.pathname.split("/").filter(Boolean).pop() || url.hostname;
      let name = filename;
      try {
        name = decodeURIComponent(filename);
      } catch {
        // Malformed percent encoding should not hide an otherwise usable attachment.
      }
      // Opaque image URLs may not have an extension; let the browser detect them.
      const image = !/\.(pdf|docx?|xlsx?|pptx?|csv|txt|zip|rar|7z|mp4|mov|webm|mp3|wav)$/i.test(
        name,
      );
      return [{ url: url.href, name, image }];
    } catch {
      return [];
    }
  });
}
