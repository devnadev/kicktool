import { useState, useEffect, useCallback, useRef } from 'react';
import type { DownloadProgress } from '../types';

interface UseSSEOptions {
    onProgress?: (progress: DownloadProgress) => void;
    onComplete?: (progress: DownloadProgress) => void;
    onError?: (error: string) => void;
}

interface UseSSEReturn {
    progress: DownloadProgress | null;
    isConnected: boolean;
    error: string | null;
    connect: (taskId: string) => void;
    disconnect: () => void;
}

export function useSSE(options: UseSSEOptions = {}): UseSSEReturn {
    const [progress, setProgress] = useState<DownloadProgress | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const eventSourceRef = useRef<EventSource | null>(null);
    const taskIdRef = useRef<string | null>(null);

    const disconnect = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
            eventSourceRef.current = null;
        }
        setIsConnected(false);
        taskIdRef.current = null;
    }, []);

    const connect = useCallback((taskId: string) => {
        // Close existing connection
        disconnect();

        taskIdRef.current = taskId;
        setError(null);

        const eventSource = new EventSource(`/api/events/${taskId}`);
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
            setIsConnected(true);
            console.log(`SSE connected for task ${taskId}`);
        };

        eventSource.addEventListener('progress', (event) => {
            try {
                const data: DownloadProgress = JSON.parse(event.data);
                setProgress(data);

                if (options.onProgress) {
                    options.onProgress(data);
                }

                // Check for completion or failure
                if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
                    if (options.onComplete) {
                        options.onComplete(data);
                    }
                    disconnect();
                }
            } catch (err) {
                console.error('Failed to parse SSE data:', err);
            }
        });

        eventSource.onerror = (err) => {
            console.error('SSE error:', err);
            setError('Connection lost. Reconnecting...');

            // Attempt reconnection after 2 seconds
            setTimeout(() => {
                if (taskIdRef.current) {
                    connect(taskIdRef.current);
                }
            }, 2000);
        };
    }, [disconnect, options]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            disconnect();
        };
    }, [disconnect]);

    return {
        progress,
        isConnected,
        error,
        connect,
        disconnect
    };
}
