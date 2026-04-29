import { useCallback, useEffect, useRef, useState } from "react";

type RecorderState = {
  recording: boolean;
  error: string | null;
  mimeType: string;
};

function pickMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
  ];
  for (const c of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported?.(c)) return c;
  }
  return "";
}

export function useAudioRecorder() {
  const [state, setState] = useState<RecorderState>({
    recording: false,
    error: null,
    mimeType: pickMimeType(),
  });

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  const start = useCallback(async () => {
    setState((s) => ({ ...s, error: null }));
    chunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onerror = () => {
        setState((s) => ({ ...s, error: "MediaRecorder error", recording: false }));
      };

      recorder.onstart = () => setState((s) => ({ ...s, recording: true, mimeType }));
      recorder.onstop = () => setState((s) => ({ ...s, recording: false }));

      recorder.start(250);
      return true;
    } catch (e: any) {
      const name = e?.name ? String(e.name) : "";
      if (name === "NotAllowedError" || name === "SecurityError") {
        setState((s) => ({ ...s, error: "Microphone permission blocked." }));
      } else if (name === "NotFoundError") {
        setState((s) => ({ ...s, error: "No microphone found." }));
      } else {
        setState((s) => ({ ...s, error: e?.message ? String(e.message) : "Unable to access microphone." }));
      }
      return false;
    }
  }, []);

  const stop = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return null;

    const blob = await new Promise<Blob | null>((resolve) => {
      try {
        recorder.onstop = () => {
          const mimeType = recorder.mimeType || state.mimeType || "audio/webm";
          const out = new Blob(chunksRef.current, { type: mimeType });
          resolve(out.size ? out : null);
        };
        recorder.stop();
      } catch {
        resolve(null);
      }
    });

    try {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    } catch {
      // no-op
    } finally {
      streamRef.current = null;
      recorderRef.current = null;
    }

    return blob;
  }, [state.mimeType]);

  const abort = useCallback(() => {
    try {
      recorderRef.current?.stop();
    } catch {
      // no-op
    }
    try {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    } catch {
      // no-op
    } finally {
      streamRef.current = null;
      recorderRef.current = null;
      chunksRef.current = [];
      setState((s) => ({ ...s, recording: false }));
    }
  }, []);

  useEffect(() => {
    return () => abort();
  }, [abort]);

  return {
    recording: state.recording,
    error: state.error,
    mimeType: state.mimeType,
    start,
    stop,
    abort,
  };
}

