import { motion } from 'framer-motion';
import type { AnalyzeResponse } from '../types';
import { User, Clock, Radio, Film, ChevronDown } from 'lucide-react';

interface MetadataDisplayProps {
    metadata: AnalyzeResponse;
    selectedQuality: string;
    onQualityChange: (quality: string) => void;
}

export function MetadataDisplay({
    metadata,
    selectedQuality,
    onQualityChange
}: MetadataDisplayProps) {
    const formatDuration = (seconds: number): string => {
        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hrs > 0) {
            return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3 }}
            className="glass neon-border p-6"
        >
            <div className="flex flex-col md:flex-row gap-6">
                {/* Thumbnail */}
                {metadata.thumbnail && (
                    <div className="relative flex-shrink-0">
                        <div className="w-full md:w-48 h-32 rounded-lg overflow-hidden bg-dark-700">
                            <img
                                src={metadata.thumbnail}
                                alt={metadata.title}
                                className="w-full h-full object-cover"
                                onError={(e) => {
                                    (e.target as HTMLImageElement).style.display = 'none';
                                }}
                            />
                        </div>
                        {/* Live badge */}
                        {metadata.is_live && (
                            <div className="absolute top-2 left-2 flex items-center gap-1 px-2 py-1 rounded-md bg-red-500/90 backdrop-blur-sm">
                                <Radio className="w-3 h-3 text-white animate-pulse" />
                                <span className="text-xs font-bold text-white uppercase">Live</span>
                            </div>
                        )}
                    </div>
                )}

                {/* Info */}
                <div className="flex-1 min-w-0">
                    {/* Title */}
                    <h2 className="text-xl font-bold text-white mb-2 truncate">
                        {metadata.title}
                    </h2>

                    {/* Stats */}
                    <div className="flex flex-wrap items-center gap-4 text-sm text-white/70 mb-4">
                        <div className="flex items-center gap-2">
                            <User className="w-4 h-4 text-neon-green" />
                            <span>{metadata.channel}</span>
                        </div>

                        {metadata.duration && (
                            <div className="flex items-center gap-2">
                                <Clock className="w-4 h-4 text-white/50" />
                                <span>{formatDuration(metadata.duration)}</span>
                            </div>
                        )}

                        <div className="flex items-center gap-2">
                            {metadata.is_live ? (
                                <>
                                    <Radio className="w-4 h-4 text-red-500" />
                                    <span className="text-red-400">Live Stream</span>
                                </>
                            ) : (
                                <>
                                    <Film className="w-4 h-4 text-white/50" />
                                    <span>VOD</span>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Quality Selector */}
                    <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                        <label className="text-sm text-white/70 font-medium">Quality:</label>
                        <div className="relative">
                            <select
                                value={selectedQuality}
                                onChange={(e) => onQualityChange(e.target.value)}
                                className="glass-input w-full sm:w-48 px-4 py-2.5 pr-10 appearance-none cursor-pointer font-medium"
                            >
                                {metadata.formats.map((format) => (
                                    <option key={format.format_id} value={format.format_id}>
                                        {format.label}
                                    </option>
                                ))}
                            </select>
                            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/50 pointer-events-none" />
                        </div>
                    </div>
                </div>
            </div>
        </motion.div>
    );
}
