import { motion } from 'framer-motion';
import { Download, Github, Zap } from 'lucide-react';
import { DownloadForm } from './components/DownloadForm';

function App() {
    return (
        <div className="relative min-h-screen flex flex-col">
            {/* Animated background orbs */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-neon-green/10 rounded-full blur-3xl animate-float" />
                <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-neon-cyan/10 rounded-full blur-3xl animate-float" style={{ animationDelay: '-1.5s' }} />
                <div className="absolute top-1/2 right-1/3 w-64 h-64 bg-neon-pink/5 rounded-full blur-3xl animate-float" style={{ animationDelay: '-3s' }} />
            </div>

            {/* Content */}
            <div className="relative z-10 flex-1 flex flex-col">
                {/* Header */}
                <motion.header
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                    className="py-6 px-4"
                >
                    <div className="max-w-4xl mx-auto flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-neon-green to-neon-cyan flex items-center justify-center neon-glow">
                                <Download className="w-5 h-5 text-dark-900" />
                            </div>
                            <div>
                                <h1 className="text-xl font-bold">
                                    <span className="kick-logo">Kick</span>
                                    <span className="text-white">.com Downloader</span>
                                </h1>
                                <p className="text-xs text-white/50">DVR & VOD</p>
                            </div>
                        </div>

                        <a
                            href="https://github.com"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-2 rounded-lg hover:bg-white/5 transition-colors"
                        >
                            <Github className="w-5 h-5 text-white/70 hover:text-white" />
                        </a>
                    </div>
                </motion.header>

                {/* Main Content */}
                <main className="flex-1 px-4 pb-8">
                    <div className="max-w-4xl mx-auto">
                        {/* Hero Section */}
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 }}
                            className="text-center mb-10"
                        >
                            <h2 className="text-4xl md:text-5xl font-extrabold mb-4">
                                <span className="text-white">Download </span>
                                <span className="kick-logo">Kick.com</span>
                                <span className="text-white"> Streams</span>
                            </h2>
                            <p className="text-lg text-white/60 max-w-2xl mx-auto">
                                Capture live streams from the beginning with
                                <span className="text-neon-green font-semibold"> DVR Mode</span>,
                                download VODs, and clip specific time ranges.
                            </p>
                        </motion.div>

                        {/* Features Pills */}
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.2 }}
                            className="flex flex-wrap justify-center gap-3 mb-10"
                        >
                            {[
                                { icon: Zap, label: 'DVR Mode', desc: 'Record from start' },
                                { icon: Download, label: 'VOD Support', desc: 'Download past streams' },
                                { icon: Zap, label: 'Time Clipping', desc: 'Select range' },
                            ].map((feature, i) => (
                                <div
                                    key={i}
                                    className="glass-dark px-4 py-2 flex items-center gap-2 text-sm"
                                >
                                    <feature.icon className="w-4 h-4 text-neon-green" />
                                    <span className="text-white font-medium">{feature.label}</span>
                                    <span className="text-white/40">•</span>
                                    <span className="text-white/60">{feature.desc}</span>
                                </div>
                            ))}
                        </motion.div>

                        {/* Download Form */}
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.3 }}
                        >
                            <DownloadForm />
                        </motion.div>
                    </div>
                </main>

                {/* Footer */}
                <motion.footer
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.5 }}
                    className="py-6 px-4 border-t border-white/5"
                >
                    <div className="max-w-4xl mx-auto text-center">
                        <p className="text-sm text-white/40">
                            For educational purposes only. Respect content creators' rights.
                        </p>
                        <p className="text-xs text-white/20 mt-2">
                            Requires FFmpeg and yt-dlp installed locally.
                        </p>
                    </div>
                </motion.footer>
            </div>
        </div>
    );
}

export default App;
