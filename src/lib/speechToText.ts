import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const w = window as any;
  return (w.SpeechRecognition || w.webkitSpeechRecognition) ?? null;
}

export function useSpeechToText({ lang }: { lang?: string } = {}) {
  const supported = useMemo(() => (typeof window === "undefined" ? false : Boolean(getSpeechRecognitionCtor())), []);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const shouldRestartRef = useRef(false);
  const restartingRef = useRef(false);

  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(() => {
    setError(null);

    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      setError("Speech recognition is not supported in this browser.");
      return false;
    }

    shouldRestartRef.current = true;

    const recognition = new Ctor();
    recognitionRef.current = recognition;
    recognition.lang = lang || navigator.language || "en-US";
    recognition.interimResults = true;
    recognition.continuous = true;

    let finalText = "";

    recognition.onresult = (event: any) => {
      try {
        let interimText = "";
        const results = event?.results;
        if (!results) return;

        for (let i = event.resultIndex ?? 0; i < results.length; i++) {
          const res = results[i];
          const alt = res?.[0];
          const text = String(alt?.transcript ?? "");
          if (!text) continue;
          if (res?.isFinal) finalText += text;
          else interimText += text;
        }

        const next = `${finalText} ${interimText}`.replace(/\s+/g, " ").trim();
        setTranscript(next);
      } catch {
        // ignore
      }
    };

    recognition.onerror = (event: any) => {
      const code = event?.error ? String(event.error) : "speech_recognition_error";
      setError(code);
      setListening(false);
      // Some errors (like not-allowed) shouldn't restart.
      if (code === "not-allowed" || code === "service-not-allowed") shouldRestartRef.current = false;
    };

    recognition.onend = () => {
      setListening(false);
      if (!shouldRestartRef.current) return;
      if (restartingRef.current) return;
      restartingRef.current = true;
      // Chrome sometimes ends sessions automatically; restart for "live typing" UX.
      setTimeout(() => {
        restartingRef.current = false;
        if (!shouldRestartRef.current) return;
        try {
          recognition.start();
          setListening(true);
        } catch {
          // ignore
        }
      }, 250);
    };

    try {
      recognition.start();
      setListening(true);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to start speech recognition.");
      setListening(false);
      return false;
    }
  }, [lang]);

  const stop = useCallback(() => {
    shouldRestartRef.current = false;
    const recognition = recognitionRef.current;
    if (!recognition) return;
    try {
      recognition.stop();
    } catch {
      // no-op
    } finally {
      setListening(false);
    }
  }, []);

  const abort = useCallback(() => {
    shouldRestartRef.current = false;
    const recognition = recognitionRef.current;
    if (!recognition) return;
    try {
      recognition.abort();
    } catch {
      // no-op
    } finally {
      setListening(false);
    }
  }, []);

  useEffect(() => {
    return () => {
      shouldRestartRef.current = false;
      const recognition = recognitionRef.current;
      if (!recognition) return;
      try {
        recognition.abort();
      } catch {
        // no-op
      }
      recognitionRef.current = null;
    };
  }, []);

  return {
    supported,
    listening,
    transcript,
    error,
    start,
    stop,
    abort,
    setTranscript,
  };
}

