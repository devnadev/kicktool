import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Download, Radio, Loader2, AlertCircle } from 'lucide-react';
import type { AnalyzeResponse, DownloadRequest, DownloadProgress } from '../types';
import { MetadataDisplay } from './MetadataDisplay';
import { TimeRangeSelector } from './TimeRangeSelector';
import { ProgressBar } from './ProgressBar';
import { useSSE } from '../hooks/useSSE';

const API_BASE = '';

export function DownloadForm() {
    // URL and analysis state
    const [url, setUrl] = useState('');
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [metadata, setMetadata] = useState<AnalyzeResponse | null>(null);
    const [analyzeError, setAnalyzeError] = useState<string | null>(null);

    // Download options
    const [selectedQuality, setSelectedQuality] = useState('best');
    const [dvrMode, setDvrMode] = useState(false);
    const [startTime, setStartTime] = useState('');
    const [endTime, setEndTime] = useState('');

    // Download state
    const [isStartingDownload, setIsStartingDownload] = useState(false);
    const [downloadError, setDownloadError] = useState<string | null>(null);
    const [taskId, setTaskId] = useState<string | null>(null);

    // SSE hook
    const { progress, isConnected, connect } = useSSE({
        onComplete: (p: DownloadProgress) => {
            console.log('Download completed:', p);
        },
        onError: (err: string) => {
            setDownloadError(err);
        }
    });

    // Validate Kick.com URL
    const isValidUrl = useCallback((input: string): boolean => {
        const pattern = /^https?:\/\/(www\.)?kick\.com\/[\w-]+/i;
        return pattern.test(input);
    }, []);

    // Analyze URL
    const handleAnalyze = async () => {
        if (!url.trim()) return;

        setIsAnalyzing(true);
        setAnalyzeError(null);
        setMetadata(null);
        setTaskId(null);

        try {
            const response = await fetch(`${API_BASE}/api/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url.trim() })
            });

            const data: AnalyzeResponse = await response.json();

            if (!data.success) {
                setAnalyzeError(data.error || 'Failed to analyze URL');
                return;
            }

            setMetadata(data);
            setSelectedQuality(data.formats[0]?.format_id || 'best');

            // Auto-enable DVR mode for live streams
            if (data.is_live) {
                setDvrMode(true);
            }
        } catch (err) {
            setAnalyzeError('Network error. Make sure the backend is running.');
            console.error('Analyze error:', err);
        } finally {
            setIsAnalyzing(false);
        }
    };

    // Start download
    const handleDownload = async () => {
        if (!metadata) return;

        setIsStartingDownload(true);
        setDownloadError(null);

        try {
            const request: DownloadRequest = {
                url: url.trim(),
                quality: selectedQuality,
                dvr_mode: dvrMode,
                start_time: startTime.trim() || null,
                end_time: endTime.trim() || null,
                output_filename: null
            };

            const response = await fetch(`${API_BASE}/api/download`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(request)
            });

            const data = await response.json();

            if (!data.success) {
                setDownloadError(data.error || 'Failed to start download');
                return;
            }

            // Store task ID and connect to SSE
            setTaskId(data.task_id);
            connect(data.task_id);
        } catch (err) {
            setDownloadError('Network error. Make sure the backend is running.');
            console.error('Download error:', err);
        } finally {
            setIsStartingDownload(false);
        }
    };

    // Reset form
    const handleReset = () => {
        setUrl('');
        setMetadata(null);
        setAnalyzeError(null);
        setDownloadError(null);
        setTaskId(null);
        setStartTime('');
        setEndTime('');
        setDvrMode(false);
    };

    const isDownloading = taskId && progress &&
        ['pending', 'downloading', 'processing'].includes(progress.status);

    return (
        <div className="space-y-6">
            {/* URL Input Section */}
            <motion.div
                className="glass neon-border p-6"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
            >
                <div className="flex flex-col gap-4">
                    {/* Input and Analyze button */}
                    <div className="flex flex-col sm:flex-row gap-3">
                        <div className="relative flex-1">
                            <input
                                type="url"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && !isAnalyzing && handleAnalyze()}
                                placeholder="https://kick.com/streamer or kick.com/video/..."
                                className="glass-input w-full pl-12 pr-4 py-4 text-lg"
                                disabled={isAnalyzing || !!isDownloading}
                            />
                            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40" />
                        </div>

                        <button
                            onClick={handleAnalyze}
                            disabled={!url.trim() || isAnalyzing || !!isDownloading}
                            className="btn-secondary flex items-center justify-center gap-2 min-w-[140px]"
                        >
                            {isAnalyzing ? (
                                <>
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                    <span>Analyzing...</span>
                                </>
                            ) : (
                                <>
                                    <Search className="w-5 h-5" />
                                    <span>Analyze</span>
                                </>
                            )}
                        </button>
                    </div>

                    {/* URL validation hint */}
                    {url && !isValidUrl(url) && (
                        <p className="text-sm text-yellow-400/80 flex items-center gap-2">
                            <AlertCircle className="w-4 h-4" />
                            Enter a valid Kick.com URL (e.g., https://kick.com/xqc)
                        </p>
                    )}
                </div>
            </motion.div>

            {/* Error Display */}
            <AnimatePresence mode="wait">
                {(analyzeError || downloadError) && (
                    <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="glass-dark border border-red-500/30 p-4 rounded-xl"
                    >
                        <div className="flex items-start gap-3">
                            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                            <div>
                                <p className="text-red-400 font-medium">Error</p>
                                <p className="text-white/70 text-sm mt-1">
                                    {analyzeError || downloadError}
                                </p>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Metadata Display */}
            <AnimatePresence mode="wait">
                {metadata && (
                    <motion.div
                        key="metadata"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                    >
                        <MetadataDisplay
                            metadata={metadata}
                            selectedQuality={selectedQuality}
                            onQualityChange={setSelectedQuality}
                        />

                        {/* DVR Mode Toggle (for live streams) */}
                        {metadata.is_live && (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="glass-dark p-4 mt-4 flex items-center justify-between"
                            >
                                <div className="flex items-center gap-3">
                                    <Radio className="w-5 h-5 text-neon-green" />
                                    <div>
                                        <p className="text-white font-medium">DVR Mode (Recommended)</p>
                                        <p className="text-white/50 text-sm">
                                            Download from the beginning of the stream, not just from now
                                        </p>
                                    </div>
                                </div>
                                <label className="relative inline-flex items-center cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={dvrMode}
                                        onChange={(e) => setDvrMode(e.target.checked)}
                                        className="sr-only peer"
                                    />
                                    <div className="w-11 h-6 bg-dark-600 peer-focus:ring-2 peer-focus:ring-neon-green/50 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-neon-green"></div>
                                </label>
                            </motion.div>
                        )}

                        {/* Time Range Selector - Always available */}
                        <TimeRangeSelector
                            startTime={startTime}
                            endTime={endTime}
                            onStartChange={setStartTime}
                            onEndChange={setEndTime}
                            duration={metadata.duration}
                        />

                        {/* Download Button */}
                        {!taskId && (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="mt-6"
                            >
                                <button
                                    onClick={handleDownload}
                                    disabled={isStartingDownload}
                                    className="btn-primary w-full py-4 text-lg flex items-center justify-center gap-3"
                                >
                                    {isStartingDownload ? (
                                        <>
                                            <Loader2 className="w-6 h-6 animate-spin" />
                                            <span>Starting Download...</span>
                                        </>
                                    ) : (
                                        <>
                                            <Download className="w-6 h-6" />
                                            <span>Download Now</span>
                                        </>
                                    )}
                                </button>
                            </motion.div>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Progress Display */}
            <AnimatePresence mode="wait">
                {taskId && (
                    <motion.div
                        key="progress"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                    >
                        <ProgressBar
                            progress={progress}
                            isConnected={isConnected}
                        />

                        {/* New Download Button (after completion) */}
                        {progress && ['completed', 'failed', 'cancelled'].includes(progress.status) && (
                            <motion.button
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                onClick={handleReset}
                                className="btn-secondary w-full mt-4 py-3"
                            >
                                Start New Download
                            </motion.button>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
