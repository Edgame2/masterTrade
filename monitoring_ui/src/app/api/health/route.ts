import { getDatabaseInfo } from '../../../lib/cosmos';

export async function GET() {
  try {
    const dbInfo = await getDatabaseInfo();
    return Response.json(dbInfo);
  } catch (error) {
    return Response.json({ 
      connected: false, 
      error: 'Failed to connect to Cosmos DB',
      details: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
}