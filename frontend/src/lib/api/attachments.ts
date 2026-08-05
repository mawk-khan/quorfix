import { ApiError, apiClient } from "./client";
import { getCsrfToken } from "./csrf";
import type { Attachment, AttachmentInitiateResponse, PaginatedResponse } from "./types";

// Dedicated query-key helpers, matching commentKeys/notificationKeys' shape.
export const attachmentKeys = {
  all: ["attachments"] as const,
  lists: (bugId: string) => [...attachmentKeys.all, bugId] as const,
  list: (bugId: string, page: number) => [...attachmentKeys.lists(bugId), page] as const,
};

// Mirrors apps.attachments.validators.ALLOWED_CONTENT_TYPES — a client-side
// UX guardrail only. The backend's own allow-list plus byte-signature check
// (verify_uploaded_content) remains the sole authorization/security boundary;
// this list exists so obviously-invalid files are rejected before a request
// is even sent, not to replace server-side validation.
export const ALLOWED_ATTACHMENT_CONTENT_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "application/pdf",
  "text/plain",
  "text/csv",
  "application/json",
  "application/zip",
  "video/mp4",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
]);

// Mirrors settings.MAX_ATTACHMENT_SIZE_BYTES.
export const MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024;

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

export function listAttachments(bugId: string, page = 1): Promise<PaginatedResponse<Attachment>> {
  const qs = page > 1 ? `?page=${page}` : "";
  return apiClient.get<PaginatedResponse<Attachment>>(`/bugs/${bugId}/attachments/${qs}`);
}

export interface InitiateAttachmentUploadInput {
  original_filename: string;
  content_type: string;
  size_bytes: number;
}

export function initiateAttachmentUpload(
  bugId: string,
  data: InitiateAttachmentUploadInput,
): Promise<AttachmentInitiateResponse> {
  return apiClient.post<AttachmentInitiateResponse>(`/bugs/${bugId}/attachments/`, data);
}

export function removeAttachment(bugId: string, attachmentId: string): Promise<Attachment> {
  return apiClient.delete<Attachment>(`/bugs/${bugId}/attachments/${attachmentId}/`);
}

export interface UploadAttachmentBytesOptions {
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
}

// The backend builds `upload.url` via DRF's reverse(request=request), which
// resolves to an absolute URL using whatever Host header Django itself saw
// — inside Docker Compose that is the internal "backend:8000" address, not
// the browser-facing origin. Every other request in this app goes through
// the Next.js same-origin "/api/*" proxy (frontend/next.config.ts) precisely
// so the session cookie always applies; sending the XHR straight to the
// backend's own absolute URL would bypass that proxy and the cookie
// wouldn't be attached at all (a different host, not just a different
// port). Reducing to just the path keeps this upload on the same origin as
// everything else.
function toSameOriginPath(url: string): string {
  try {
    return new URL(url, window.location.origin).pathname;
  } catch {
    return url;
  }
}

// Uses XMLHttpRequest directly — it is the only browser API that exposes
// upload progress (fetch does not). The File is appended to FormData and
// handed to the browser to stream; it is never read fully into memory here.
export function uploadAttachmentBytes(
  uploadUrl: string,
  file: File,
  options: UploadAttachmentBytesOptions = {},
): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", toSameOriginPath(uploadUrl));

    const csrfToken = getCsrfToken();
    if (csrfToken) {
      xhr.setRequestHeader("X-CSRFToken", csrfToken);
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && options.onProgress) {
        options.onProgress(event.loaded / event.total);
      }
    };

    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as Attachment);
      } else {
        reject(new ApiError(xhr.status, body));
      }
    };

    xhr.onerror = () => reject(new ApiError(0, null));
    xhr.onabort = () => reject(new ApiError(0, null));

    if (options.signal) {
      if (options.signal.aborted) {
        xhr.abort();
        return;
      }
      options.signal.addEventListener("abort", () => xhr.abort());
    }

    const formData = new FormData();
    formData.append("file", file);
    xhr.withCredentials = true;
    xhr.send(formData);
  });
}

// Fetches the file as a blob (rather than a plain <a href> navigation) so a
// 404 — the file was removed or is otherwise unavailable — can be handled
// gracefully in the UI instead of navigating the whole page to a raw JSON
// error response. Always saves via a forced download, never renders the
// blob inline (no target="_blank"/iframe), and always uses the
// server-provided filename, never a client-derived one.
export async function downloadAttachment(
  bugId: string,
  attachmentId: string,
  filename: string,
): Promise<void> {
  const response = await fetch(`/api/bugs/${bugId}/attachments/${attachmentId}/download/`, {
    credentials: "include",
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
