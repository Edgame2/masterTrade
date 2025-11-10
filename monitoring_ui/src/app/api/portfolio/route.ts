import { getContainer } from '../../../lib/cosmos';

export async function GET(request: Request) {
  try {
    const container = await getContainer('Positions');
    
    const query = `
      SELECT * FROM c 
      WHERE c.status = 'OPEN' 
      ORDER BY c.opened_at DESC
    `;
    
    const { resources } = await container.items
      .query(query)
      .fetchAll();
    
    const positions = resources;
    
    // Calculate portfolio summary
    const totalValue = positions.reduce((sum: number, pos: any) => sum + (pos.current_price * pos.size || 0), 0);
    const totalPnL = positions.reduce((sum: number, pos: any) => sum + (pos.pnl || 0), 0);
    const totalPnLPercent = totalValue > 0 ? (totalPnL / totalValue) * 100 : 0;
    
    return Response.json({ 
      positions,
      summary: {
        totalPositions: positions.length,
        totalValue,
        totalPnL,
        totalPnLPercent
      }
    });
  } catch (error) {
    console.error('Error fetching portfolio:', error);
    
    // Fallback to mock data
    const mockPositions = [
      {
        id: '1',
        symbol: 'BTC/USDT',
        side: 'long',
        size: 0.5,
        entry_price: 43500.50,
        current_price: 44200.00,
        pnl: 350.25,
        status: 'OPEN',
        opened_at: '2024-01-10T09:30:00Z'
      }
    ];
    
    const totalValue = mockPositions.reduce((sum, pos) => sum + (pos.current_price * pos.size), 0);
    const totalPnL = mockPositions.reduce((sum, pos) => sum + pos.pnl, 0);
    
    return Response.json({ 
      positions: mockPositions,
      summary: {
        totalPositions: mockPositions.length,
        totalValue,
        totalPnL,
        totalPnLPercent: totalValue > 0 ? (totalPnL / totalValue) * 100 : 0
      },
      fallback: true
    });
  }
}
