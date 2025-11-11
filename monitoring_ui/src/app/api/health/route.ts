export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
    
    const response = await fetch(`${apiUrl}/health`, {
      cache: 'no-store',
    });
    
    if (!response.ok) {
      throw new Error(`API health check failed with status ${response.status}`);
    }
    
    const data = await response.json();
    return Response.json(data);
  } catch (error) {
    return Response.json({ 
      connected: false, 
      error: 'Failed to connect to API Gateway',
      details: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
}