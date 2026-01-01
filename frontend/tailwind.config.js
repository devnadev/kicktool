/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                neon: {
                    green: '#53FC18',
                    cyan: '#18FCE8',
                    pink: '#FC18A8',
                },
                dark: {
                    900: '#0a0a0f',
                    800: '#12121a',
                    700: '#1a1a25',
                    600: '#252530',
                }
            },
            animation: {
                'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
                'gradient-x': 'gradient-x 3s ease infinite',
                'shimmer': 'shimmer 2s linear infinite',
            },
            keyframes: {
                'pulse-glow': {
                    '0%, 100%': {
                        boxShadow: '0 0 20px rgba(83, 252, 24, 0.3)',
                    },
                    '50%': {
                        boxShadow: '0 0 40px rgba(83, 252, 24, 0.6)',
                    },
                },
                'gradient-x': {
                    '0%, 100%': {
                        backgroundPosition: '0% 50%',
                    },
                    '50%': {
                        backgroundPosition: '100% 50%',
                    },
                },
                'shimmer': {
                    '0%': {
                        transform: 'translateX(-100%)',
                    },
                    '100%': {
                        transform: 'translateX(100%)',
                    },
                },
            },
            backdropBlur: {
                xs: '2px',
            },
        },
    },
    plugins: [],
}
