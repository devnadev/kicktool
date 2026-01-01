import { motion } from 'framer-motion';
import type { DownloadProgress } from '../types';
import { Download, CheckCircle, XCircle, Loader2, Clock, Zap } from 'lucide-react';

interface ProgressBarProps {
    progress: DownloadProgress | null;
    isConnected: boolean;
}

export function ProgressBar({ progress, isConnected }: ProgressBarProps) {
    if (!progress) {
        return null;
    }

    const isComplete = progress.status === 'completed';
    const isFailed = progress.status === 'failed' || progress.status === 'cancelled';
    const isProcessing = progress.status === 'processing';

    const getStatusIcon = () => {
        if (isComplete) return <CheckCircle className="w-5 h-5 text-neon-green" />;
        if (isFailed) return <XCircle className="w-5 h-5 text-red-500" />;
        if (isProcessing) return <Loader2 className="w-5 h-5 text-neon-cyan animate-spin" />;
        return <Download className="w-5 h-5 text-neon-green animate-pulse" />;
    };

    const getStatusColor = () => {
        if (isComplete) return 'border-neon-green/50';
        if (isFailed) return 'border-red-500/50';
        return 'border-neon-green/30';
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className={`glass p-6 ${getStatusColor()}`}
        >
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                    {getStatusIcon()}
                    <span className="font-semibold text-white">
                        {isComplete ? 'Download Complete' :
                            isFailed ? 'Download Failed' :
                                isProcessing ? 'Processing...' : 'Downloading...'}
                    </span>
                </div>

                {/* Connection indicator */}
                <div className="flex items-center gap-2 text-sm">
                    <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-neon-green' : 'bg-yellow-500'}`} />
                    <span className="text-white/60">
                        {isConnected ? 'Live' : 'Reconnecting...'}
                    </span>
                </div>
            </div>

            {/* Progress Bar */}
            <div className="progress-bar mb-4">
                <motion.div
                    className="progress-fill"
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(progress.progress, 100)}%` }}
                    transition={{ duration: 0.3, ease: 'easeOut' }}
                />
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                {/* Progress */}
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-neon-green/10 flex items-center justify-center">
                        <span className="text-neon-green font-bold text-xs">%</span>
                    </div>
                    <div>
                        <p className="text-white/50 text-xs">Progress</p>
                        <p className="text-white font-medium">{progress.progress.toFixed(1)}%</p>
                    </div>
                </div>

                {/* Speed */}
                {progress.speed && (
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-neon-cyan/10 flex items-center justify-center">
                            <Zap className="w-4 h-4 text-neon-cyan" />
                        </div>
                        <div>
                            <p className="text-white/50 text-xs">Speed</p>
                            <p className="text-white font-medium">{progress.speed}</p>
                        </div>
                    </div>
                )}

                {/* Downloaded */}
                {progress.downloaded && (
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-neon-pink/10 flex items-center justify-center">
                            <Download className="w-4 h-4 text-neon-pink" />
                        </div>
                        <div>
                            <p className="text-white/50 text-xs">Downloaded</p>
                            <p className="text-white font-medium">{progress.downloaded}</p>
                        </div>
                    </div>
                )}

                {/* ETA */}
                {progress.eta && !isComplete && (
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center">
                            <Clock className="w-4 h-4 text-white" />
                        </div>
                        <div>
                            <p className="text-white/50 text-xs">ETA</p>
                            <p className="text-white font-medium">{progress.eta}</p>
                        </div>
                    </div>
                )}
            </div>

            {/* Message */}
            <div className="mt-4 pt-4 border-t border-white/10">
                <p className={`text-sm ${isFailed ? 'text-red-400' : 'text-white/70'}`}>
                    {progress.error || progress.message}
                </p>
            </div>

            {/* Completion message */}
            {isComplete && (
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="mt-4 p-3 rounded-lg bg-neon-green/10 border border-neon-green/30"
                >
                    <p className="text-neon-green text-sm font-medium">
                        ✨ Your download is ready! Check your downloads folder.
                    </p>
                </motion.div>
            )}
        </motion.div>
    );
}
