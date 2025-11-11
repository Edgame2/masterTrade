export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const strategyId = searchParams.get('strategyId');
    const limit = parseInt(searchParams.get('limit') || '100');
    
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
    const url = new URL(`${apiUrl}/api/performance`);
    if (strategyId) {
      url.searchParams.set('strategyId', strategyId);
    }
    url.searchParams.set('limit', limit.toString());
    
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
    console.error('Error fetching performance data:', error);
    
    // Fallback to mock data
    const { searchParams } = new URL(request.url);
    const strategyId = searchParams.get('strategyId');
    const limit = parseInt(searchParams.get('limit') || '100');
    
    const mockPerformance = [
      { id: '1', strategy_id: strategyId || '1', timestamp: '2024-01-10T10:00:00Z', profit_loss: 125.50, win_rate: 0.67 },
      { id: '2', strategy_id: strategyId || '1', timestamp: '2024-01-10T11:00:00Z', profit_loss: 145.25, win_rate: 0.68 }
    ].slice(0, limit);
    
    return Response.json({ performance: mockPerformance, fallback: true });
  }
}
