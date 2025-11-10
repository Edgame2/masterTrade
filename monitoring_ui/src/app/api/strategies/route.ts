import { getContainer } from '../../../lib/cosmos';

// API endpoint to fetch strategies from Cosmos DB
export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status');
    
    const container = await getContainer('Strategies');
    
    let query = 'SELECT * FROM c';
    const parameters: any[] = [];
    
    if (status) {
      query += ' WHERE c.status = @status';
      parameters.push({ name: '@status', value: status });
    }
    
    query += ' ORDER BY c.performance_score DESC';
    
    const { resources } = await container.items
      .query({ query, parameters })
      .fetchAll();
    
    return Response.json({ strategies: resources });
  } catch (error) {
    console.error('Error fetching strategies:', error);
    
    // Fallback to mock data if Cosmos DB is not available
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
