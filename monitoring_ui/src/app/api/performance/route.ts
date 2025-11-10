import { getContainer } from '../../../lib/cosmos';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const strategyId = searchParams.get('strategyId');
    const limit = parseInt(searchParams.get('limit') || '100');
    
    const container = await getContainer('StrategyPerformance');
    
    let query = 'SELECT * FROM c';
    const parameters: any[] = [];
    
    if (strategyId) {
      query += ' WHERE c.strategy_id = @strategyId';
      parameters.push({ name: '@strategyId', value: strategyId });
    }
    
    query += ' ORDER BY c.timestamp DESC';
    query += ` OFFSET 0 LIMIT ${limit}`;
    
    const { resources } = await container.items
      .query({ query, parameters })
      .fetchAll();
    
    return Response.json({ performance: resources });
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
