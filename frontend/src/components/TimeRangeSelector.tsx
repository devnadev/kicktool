import { motion } from 'framer-motion';
import { Clock, Scissors } from 'lucide-react';

interface TimeRangeSelectorProps {
    startTime: string;
    endTime: string;
    onStartChange: (time: string) => void;
    onEndChange: (time: string) => void;
    duration: number | null;
}

export function TimeRangeSelector({
    startTime,
    endTime,
    onStartChange,
    onEndChange,
    duration
}: TimeRangeSelectorProps) {
    const formatDurationHint = (seconds: number): string => {
        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-dark p-5 mt-4"
        >
            <div className="flex items-center gap-2 mb-4">
                <Scissors className="w-4 h-4 text-neon-green" />
                <span className="text-sm font-semibold text-white">Time Range Clipping</span>
                <span className="text-xs text-white/40 ml-2">(Optional)</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Start Time */}
                <div>
                    <label className="flex items-center gap-2 text-sm text-white/70 mb-2">
                        <Clock className="w-3 h-3" />
                        Start Time
                    </label>
                    <input
                        type="text"
                        value={startTime}
                        onChange={(e) => onStartChange(e.target.value)}
                        placeholder="00:00:00"
                        className="glass-input w-full px-4 py-2.5 text-center font-mono tracking-wider"
                    />
                </div>

                {/* End Time */}
                <div>
                    <label className="flex items-center gap-2 text-sm text-white/70 mb-2">
                        <Clock className="w-3 h-3" />
                        End Time
                    </label>
                    <input
                        type="text"
                        value={endTime}
                        onChange={(e) => onEndChange(e.target.value)}
                        placeholder={duration ? formatDurationHint(duration) : '00:00:00'}
                        className="glass-input w-full px-4 py-2.5 text-center font-mono tracking-wider"
                    />
                </div>
            </div>

            {/* Help text */}
            <p className="text-xs text-white/40 mt-3">
                Format: HH:MM:SS (e.g., 00:10:30 for 10 minutes 30 seconds).
                {duration && (
                    <span className="text-neon-green/70"> Total duration: {formatDurationHint(duration)}</span>
                )}
            </p>
        </motion.div>
    );
}
