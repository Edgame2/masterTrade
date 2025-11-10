# MasterTrade Monitoring UI

A Next.js Progressive Web App (PWA) for monitoring the MasterTrade AI trading bot with real-time updates, strategy performance visualization, and portfolio tracking.

## Features

- 🔐 **Google OAuth Authentication** - Secure login with Google accounts
- 📊 **Real-time Dashboard** - Live updates via WebSocket connections
- 📈 **Strategy Performance** - Track all active and historical strategies
- 💰 **Portfolio Overview** - Monitor positions, P&L, and portfolio value
- 📱 **PWA Support** - Install as a mobile app with offline capabilities
- 🌙 **Dark Mode** - Beautiful dark theme for better viewing
- 🎨 **Modern UI** - Built with Tailwind CSS and React components

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Authentication**: NextAuth.js with Google OAuth
- **Database**: Azure Cosmos DB
- **Charts**: Recharts
- **Icons**: React Icons
- **WebSocket**: Socket.io Client

## Prerequisites

- Node.js 18+ 
- npm or yarn
- Google Cloud Console project for OAuth credentials
- Azure Cosmos DB account

## Setup Instructions

### 1. Install Dependencies

```bash
cd monitoring_ui
npm install
```

### 2. Configure Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google+ API
4. Create OAuth 2.0 credentials:
   - Application type: Web application
   - Authorized redirect URIs: `http://localhost:3000/api/auth/callback/google`
5. Copy Client ID and Client Secret

### 3. Configure Environment Variables

Create `.env.local` file:

```bash
cp .env.local.example .env.local
```

Edit `.env.local` with your credentials:

```env
# Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# NextAuth
NEXTAUTH_SECRET=$(openssl rand -base64 32)
NEXTAUTH_URL=http://localhost:3000

# Azure Cosmos DB
COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE=masterTrade

# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

### 4. Run Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### 5. Build for Production

```bash
npm run build
npm start
```

## Project Structure

```
monitoring_ui/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── api/               # API routes
│   │   │   ├── auth/         # NextAuth configuration
│   │   │   ├── strategies/   # Strategy endpoints
│   │   │   ├── portfolio/    # Portfolio endpoints
│   │   │   └── performance/  # Performance endpoints
│   │   ├── auth/             # Authentication pages
│   │   ├── layout.tsx        # Root layout
│   │   ├── page.tsx          # Home page
│   │   └── globals.css       # Global styles
│   ├── components/            # React components
│   │   ├── Dashboard.tsx     # Main dashboard
│   │   ├── StrategyList.tsx  # Strategy list
│   │   ├── PortfolioOverview.tsx
│   │   ├── PerformanceChart.tsx
│   │   └── LivePositions.tsx
│   └── hooks/                 # Custom React hooks
│       └── useWebSocket.ts    # WebSocket hook
├── public/                    # Static files
│   └── manifest.json         # PWA manifest
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── next.config.js
```

## API Endpoints

### Strategy Endpoints
- `GET /api/strategies` - Get all strategies
- `GET /api/strategies?status=ACTIVE` - Filter by status

### Portfolio Endpoints
- `GET /api/portfolio` - Get portfolio summary and positions

### Performance Endpoints
- `GET /api/performance` - Get performance history
- `GET /api/performance?strategyId=xxx` - Filter by strategy
- `GET /api/performance?limit=100` - Limit results

## WebSocket Events

The app connects to the backend WebSocket server for real-time updates:

- `connect` - Connection established
- `disconnect` - Connection lost
- `update` - Receive real-time data updates
- `portfolio_update` - Portfolio value changes
- `position_update` - Position changes
- `strategy_update` - Strategy status changes

## PWA Features

### Installation
Users can install the app on their device:
- Chrome: Click "Install" in address bar
- Mobile: "Add to Home Screen"

### Offline Support
- Service worker caches static assets
- Offline fallback page
- Background sync for data

### Push Notifications
Configure push notifications for:
- Strategy performance alerts
- Position updates
- Risk warnings
- System notifications

## Security

- Google OAuth 2.0 authentication
- JWT session tokens
- Secure HTTP headers
- CORS protection
- Environment variable encryption
- API key protection

## Deployment

### Vercel (Recommended)

```bash
npm install -g vercel
vercel
```

### Docker

```bash
docker build -t mastertrade-ui .
docker run -p 3000:3000 mastertrade-ui
```

### Environment Variables for Production

Set in your hosting platform:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `NEXTAUTH_SECRET`
- `NEXTAUTH_URL` (production URL)
- `COSMOS_ENDPOINT`
- `COSMOS_KEY`
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_WS_URL`

## Customization

### Themes
Edit `tailwind.config.js` to customize colors and themes.

### Components
All components are in `src/components/` and can be customized.

### API Integration
Modify API routes in `src/app/api/` to integrate with your backend.

## Troubleshooting

### OAuth Errors
- Verify redirect URIs in Google Console
- Check `NEXTAUTH_URL` matches your domain
- Ensure `NEXTAUTH_SECRET` is set

### Cosmos DB Connection
- Verify endpoint and key
- Check network connectivity
- Ensure database and containers exist

### WebSocket Issues
- Check `NEXT_PUBLIC_WS_URL` is correct
- Verify backend WebSocket server is running
- Check CORS settings

## License

MIT License - See LICENSE file for details
