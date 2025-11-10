#!/bin/bash

echo "🚀 MasterTrade Monitoring UI - Quick Setup"
echo "=========================================="
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

echo "✅ Node.js version: $(node --version)"
echo ""

# Navigate to monitoring_ui directory
cd "$(dirname "$0")/monitoring_ui"

# Install dependencies
echo "📦 Installing dependencies..."
npm install

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo ""
echo "✅ Dependencies installed successfully"
echo ""

# Check if .env.local exists
if [ ! -f ".env.local" ]; then
    echo "⚙️  Creating .env.local file..."
    cp .env.local.example .env.local
    echo "✅ .env.local created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env.local with your credentials:"
    echo "   - Google OAuth Client ID & Secret"
    echo "   - NextAuth Secret (generate with: openssl rand -base64 32)"
    echo "   - Azure Cosmos DB credentials"
    echo ""
else
    echo "✅ .env.local already exists"
    echo ""
fi

echo "=========================================="
echo "🎉 Setup Complete!"
echo ""
echo "Next steps:"
echo "1. Edit monitoring_ui/.env.local with your credentials"
echo "2. Run: cd monitoring_ui && npm run dev"
echo "3. Open: http://localhost:3000"
echo ""
echo "📚 See monitoring_ui/README.md for detailed setup instructions"
echo "=========================================="
