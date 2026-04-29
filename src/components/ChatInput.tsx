import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Mic, Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAudioRecorder } from "@/lib/audioRecorder";
import { transcribeAudio } from "@/lib/audioTranscribe";
import { useSpeechToText } from "@/lib/speechToText";
import { toast } from "sonner";

interface ChatInputProps {
    value: string;
    onChange: (value: string) => void;
    onSend: (message: string) => void;
    disabled?: boolean;
}

export function ChatInput({ value, onChange, onSend, disabled }: ChatInputProps) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const [voiceOpen, setVoiceOpen] = useState(false);
    const [voiceDraft, setVoiceDraft] = useState("");
    const [transcribing, setTranscribing] = useState(false);
    const [voiceMode, setVoiceMode] = useState<"live" | "record">("live");

    const recorder = useAudioRecorder();
    const stt = useSpeechToText();

    const recordSupported = useMemo(() => {
        if (typeof window === "undefined") return false;
        return Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== "undefined";
    }, []);

    const canUseVoice = useMemo(() => {
        if (typeof window === "undefined") return false;
        // Web speech recognition generally requires a secure context (or localhost).
        const isLocalhost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
        const secure = window.isSecureContext || isLocalhost;
        return secure && (recordSupported || stt.supported);
    }, [recordSupported, stt.supported]);

    const voiceUnavailableReason = useMemo(() => {
        if (typeof window === "undefined") return "Voice input is unavailable.";
        const isLocalhost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
        if (!recordSupported && !stt.supported) return "Voice input is not supported in this browser (try Chrome/Edge).";
        if (!(window.isSecureContext || isLocalhost)) return "Voice input requires HTTPS (or localhost).";
        return "";
    }, [recordSupported, stt.supported]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (value.trim() && !disabled) {
                onSend(value.trim());
            }
        }
    };

    const handleSend = () => {
        if (value.trim() && !disabled) {
            onSend(value.trim());
        }
    };

    useEffect(() => {
        if (!voiceOpen) return;
        if (voiceMode !== "live") return;
        setVoiceDraft(stt.transcript);
    }, [stt.transcript, voiceMode, voiceOpen]);

    useEffect(() => {
        if (!voiceOpen) return;
        if (stt.error) toast.error(stt.error);
    }, [stt.error, voiceOpen]);

    const handleVoiceStart = async () => {
        if (disabled) return;
        if (!canUseVoice) {
            toast.error(voiceUnavailableReason || "Voice input is unavailable.");
            return;
        }

        setVoiceOpen(true);
        setVoiceDraft("");
        stt.setTranscript("");

        if (stt.supported) {
            setVoiceMode("live");
            const ok = stt.start();
            if (!ok && recordSupported) {
                setVoiceMode("record");
                const okRec = await recorder.start();
                if (!okRec) {
                    setVoiceOpen(false);
                    toast.error(recorder.error || "Unable to start recording.");
                }
            } else if (!ok) {
                setVoiceOpen(false);
                toast.error("Unable to start live dictation in this browser.");
            }
            return;
        }

        setVoiceMode("record");
        const okRec = await recorder.start();
        if (!okRec) {
            setVoiceOpen(false);
            toast.error(recorder.error || "Unable to start recording.");
        }
    };

    const handleVoiceCancel = () => {
        stt.abort();
        recorder.abort();
        setVoiceOpen(false);
        setVoiceDraft("");
    };

    const handleVoiceConfirm = () => {
        const text = voiceDraft.trim();
        if (!text) {
            toast.error("No text detected. Try again.");
            return;
        }
        recorder.abort();
        onChange(text);
        setVoiceOpen(false);
        // Keep focus in the main input so the user can quickly adjust and send.
        requestAnimationFrame(() => textareaRef.current?.focus());
    };

    const handleVoiceSend = () => {
        const text = voiceDraft.trim();
        if (!text) {
            toast.error("No text detected. Try again.");
            return;
        }
        if (disabled) return;
        recorder.abort();
        setVoiceOpen(false);
        onSend(text);
        requestAnimationFrame(() => textareaRef.current?.focus());
    };

    const handleVoiceRetry = async () => {
        if (disabled) return;
        if (!canUseVoice) {
            toast.error(voiceUnavailableReason || "Voice input is unavailable.");
            return;
        }
        setVoiceDraft("");
        stt.setTranscript("");
        if (voiceMode === "live") {
            stt.abort();
            const ok = stt.start();
            if (!ok) toast.error("Unable to start live dictation in this browser.");
            return;
        }
        const okRec = await recorder.start();
        if (!okRec && recorder.error) toast.error(recorder.error);
    };

    const handleVoiceModeSwitch = async (next: "live" | "record") => {
        if (disabled) return;
        if (!canUseVoice) {
            toast.error(voiceUnavailableReason || "Voice input is unavailable.");
            return;
        }

        stt.abort();
        recorder.abort();
        setVoiceMode(next);
        setVoiceDraft("");
        stt.setTranscript("");

        if (next === "live") {
            const ok = stt.start();
            if (!ok) toast.error("Unable to start live dictation in this browser.");
            return;
        }

        const okRec = await recorder.start();
        if (!okRec) toast.error(recorder.error || "Unable to start recording.");
    };

    const handleRecordStopAndTranscribe = async () => {
        const blob = await recorder.stop();
        if (!blob) {
            toast.error("No audio recorded. Try again.");
            return;
        }
        setTranscribing(true);
        try {
            const text = await transcribeAudio(blob, { filename: "audio.webm", language: navigator.language || undefined });
            setVoiceDraft(text);
            if (!text.trim()) toast.error("No speech detected in the recording. Try again.");
        } catch (e: any) {
            const message = e?.message ? String(e.message) : "Transcription failed.";
            toast.error(message);
        } finally {
            setTranscribing(false);
        }
    };

    return (
        <div className="p-4 md:p-5">
            <div className="mx-auto flex max-w-4xl items-end gap-3 rounded-[1.75rem] border border-slate-200/80 bg-white/90 p-3 shadow-[0_14px_40px_rgba(15,23,42,0.08)] backdrop-blur-sm">
                <Textarea
                    ref={textareaRef}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Type your message or select a use case..."
                    disabled={disabled}
                    className="min-h-[44px] max-h-[200px] resize-none rounded-2xl border-0 bg-slate-50 text-sm shadow-none focus-visible:ring-1"
                    rows={1}
                />
                <Button
                    onClick={handleVoiceStart}
                    disabled={disabled}
                    size="icon"
                    variant="outline"
                    className="h-12 w-12 shrink-0 rounded-2xl"
                    title={canUseVoice ? "Voice input" : "Voice input not available"}
                >
                    <Mic className="h-4 w-4" />
                </Button>
                <Button
                    onClick={handleSend}
                    disabled={!value.trim() || disabled}
                    size="icon"
                    className="h-12 w-12 shrink-0 rounded-2xl"
                >
                    <Send className="h-4 w-4" />
                </Button>
            </div>

            <Dialog open={voiceOpen} onOpenChange={(open) => (open ? setVoiceOpen(true) : handleVoiceCancel())}>
                <DialogContent className="max-w-xl">
                    <DialogHeader>
                        <DialogTitle>Voice to text</DialogTitle>
                        <DialogDescription>
                            {voiceMode === "live"
                                ? (stt.listening ? "Listening... speak now, then send or insert." : "Review and send/insert the captured text.")
                                : (recorder.recording ? "Recording... speak now, then stop to transcribe." : "Stop the recording to transcribe, then send/insert the text.")}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="flex flex-wrap gap-2">
                        <Button
                            type="button"
                            variant={voiceMode === "live" ? "default" : "outline"}
                            size="sm"
                            onClick={() => handleVoiceModeSwitch("live")}
                            disabled={!stt.supported || disabled}
                            title={stt.supported ? "Live dictation (browser)" : "Not supported in this browser"}
                        >
                            Live (browser)
                        </Button>
                        <Button
                            type="button"
                            variant={voiceMode === "record" ? "default" : "outline"}
                            size="sm"
                            onClick={() => handleVoiceModeSwitch("record")}
                            disabled={!recordSupported || disabled}
                            title={recordSupported ? "Record then transcribe via server" : "Recording not supported"}
                        >
                            Record (server)
                        </Button>
                    </div>

                    <Textarea
                        value={voiceDraft}
                        onChange={(e) => setVoiceDraft(e.target.value)}
                        placeholder={voiceMode === "live" ? (stt.listening ? "Listening..." : "Transcript will appear here") : (recorder.recording ? "Recording..." : "Transcript will appear here")}
                        className="min-h-[120px] rounded-2xl"
                    />

                    {!canUseVoice && (
                        <div className="text-xs text-muted-foreground">
                            {voiceUnavailableReason}
                        </div>
                    )}
                    {recorder.error && <div className="text-xs text-rose-600">Audio error: {recorder.error}</div>}
                    {stt.error && <div className="text-xs text-rose-600">Speech error: {stt.error}</div>}

                    <DialogFooter className="gap-2 sm:gap-0">
                        <Button variant="outline" onClick={handleVoiceCancel}>
                            Cancel
                        </Button>
                        {voiceMode === "live" ? (
                            stt.listening ? (
                                <Button onClick={stt.stop} variant="secondary" className="inline-flex items-center gap-2">
                                    <Square className="h-4 w-4" />
                                    Stop
                                </Button>
                            ) : (
                                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-2">
                                    <Button variant="secondary" onClick={handleVoiceRetry} className="inline-flex items-center gap-2" disabled={disabled || !canUseVoice}>
                                        Try again
                                    </Button>
                                    <Button onClick={handleVoiceConfirm} variant="outline" className="inline-flex items-center gap-2" disabled={!voiceDraft.trim()}>
                                        Insert
                                    </Button>
                                    <Button onClick={handleVoiceSend} className="inline-flex items-center gap-2" disabled={!voiceDraft.trim() || disabled}>
                                        Send
                                    </Button>
                                </div>
                            )
                        ) : (
                            recorder.recording ? (
                                <Button onClick={handleRecordStopAndTranscribe} variant="secondary" className="inline-flex items-center gap-2" disabled={transcribing}>
                                    <Square className="h-4 w-4" />
                                    Stop & Transcribe
                                </Button>
                            ) : (
                                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-2">
                                    <Button variant="secondary" onClick={handleVoiceRetry} className="inline-flex items-center gap-2" disabled={disabled || !canUseVoice || transcribing}>
                                        Try again
                                    </Button>
                                    <Button onClick={handleVoiceConfirm} variant="outline" className="inline-flex items-center gap-2" disabled={!voiceDraft.trim() || transcribing}>
                                        Insert
                                    </Button>
                                    <Button onClick={handleVoiceSend} className="inline-flex items-center gap-2" disabled={!voiceDraft.trim() || transcribing || disabled}>
                                        {transcribing ? (
                                            <>
                                                <Loader2 className="h-4 w-4 animate-spin" />
                                                Transcribing...
                                            </>
                                        ) : (
                                            "Send"
                                        )}
                                    </Button>
                                </div>
                            )
                        )}
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
