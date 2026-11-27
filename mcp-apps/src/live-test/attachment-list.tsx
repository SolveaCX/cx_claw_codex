import { useState } from "react";
import { attachmentLinks } from "./attachments.js";

function Attachment({
  url,
  name,
  image,
  onOpen,
}: ReturnType<typeof attachmentLinks>[number] & { onOpen?: (url: string) => void }) {
  const [failed, setFailed] = useState(false);
  const preview = image && !failed;
  return (
    <button
      type="button"
      title={name}
      onClick={() => onOpen?.(url)}
      className={preview ? "lt-image-attachment" : "lt-attachment"}
    >
      {preview ? (
        <img
          src={url}
          alt={name}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      ) : (
        <>
          <span aria-hidden="true">↗</span>
          <span>{name}</span>
        </>
      )}
    </button>
  );
}

export function AttachmentList({
  attachments,
  onOpen,
}: {
  attachments?: string[];
  onOpen?: (url: string) => void;
}) {
  const links = attachmentLinks(attachments);
  if (!links.length) return null;
  return (
    <div className="lt-attachments">
      {links.map((item, index) => (
        <Attachment key={`${item.url}-${index}`} {...item} onOpen={onOpen} />
      ))}
    </div>
  );
}
