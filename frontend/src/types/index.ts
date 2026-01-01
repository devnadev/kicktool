// TypeScript interfaces for the application

export interface StreamFormat {
    format_id: string;
    resolution: string;
    label: string;
    fps: number | null;
}

export interface AnalyzeResponse {
    success: boolean;
    url: string;
    title: string;
    channel: string;
    thumbnail: string | null;
    duration: number | null;
    is_live: boolean;
    formats: StreamFormat[];
    error: string | null;
}

export interface DownloadRequest {
    url: string;
    quality: string;
    dvr_mode: boolean;
    start_time: string | null;
    end_time: string | null;
    output_filename: string | null;
}

export interface DownloadResponse {
    success: boolean;
    task_id: string;
    message: string;
    error: string | null;
}

export interface DownloadProgress {
    task_id: string;
    status: 'pending' | 'downloading' | 'processing' | 'completed' | 'failed' | 'cancelled';
    progress: number;
    speed: string;
    downloaded: string;
    eta: string;
    message: string;
    error: string | null;
}

export interface TaskStatus {
    task_id: string;
    status: string;
    progress: number;
    speed: string;
    downloaded: string;
    eta: string;
    message: string;
    output_path: string | null;
    error: string | null;
}
