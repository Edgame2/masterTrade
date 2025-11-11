export const dynamic = 'force-dynamic';

// API endpoint to fetch strategies from backend API Gateway
export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status');
    
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
    const url = new URL(`${apiUrl}/api/strategies`);
    if (status) {
      url.searchParams.set('status', status);
    }
    
    const response = await fetch(url.toString(), {
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    if (!response.ok) {
      throw new Error(`API responded with status ${response.status}`);
    }
    
    const data = await response.json();
    return Response.json(data);
  } catch (error) {
    console.error('Error fetching strategies:', error);
    
    // Fallback to mock data if backend is not available
    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status');
    
    const mockStrategies = [
      {
        id: '1',
        name: 'RSI + MACD Strategy',
        status: 'active',
        performance_score: 0.85,
        total_trades: 45,
        win_rate: 0.67,
        profit_loss: 1250.45
      },
      {
        id: '2',
        name: 'Bollinger Bands Mean Reversion',
        status: status === 'active' ? 'active' : 'inactive',
        performance_score: 0.72,
        total_trades: 32,
        win_rate: 0.59,
        profit_loss: 890.12
      }
    ];
    
    let strategies = mockStrategies;
    if (status) {
      strategies = strategies.filter((s: any) => s.status === status);
    }
    
    return Response.json({ strategies, fallback: true });
  }
}
