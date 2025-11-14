import NextAuth, { NextAuthOptions } from 'next-auth';
import GoogleProvider from 'next-auth/providers/google';
import CredentialsProvider from 'next-auth/providers/credentials';

const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID || '',
      clientSecret: process.env.GOOGLE_CLIENT_SECRET || '',
    }),
    // Dev/Testing bypass - only enable if DEV_MODE is true
    ...(process.env.DEV_MODE === 'true' ? [
      CredentialsProvider({
        id: 'dev-credentials',
        name: 'Dev Login',
        credentials: {
          username: { label: 'Username', type: 'text', placeholder: 'dev' },
        },
        async authorize(credentials) {
          // Simple dev bypass - accept any username
          if (credentials?.username) {
            return {
              id: 'dev-user-001',
              email: `${credentials.username}@dev.local`,
              name: credentials.username,
            };
          }
          return null;
        },
      }),
    ] : []),
  ],
  callbacks: {
    async signIn({ user, account, profile }) {
      // Add custom sign-in logic here
      // For example, check if user email is whitelisted
      return true;
    },
    async session({ session, token }) {
      // Add user id to session
      if (session.user) {
        (session.user as any).id = token.sub || '';
      }
      return session;
    },
    async jwt({ token, user, account }) {
      if (user) {
        token.id = user.id;
      }
      return token;
    },
  },
  pages: {
    signIn: '/auth/signin',
    error: '/auth/error',
  },
  session: {
    strategy: 'jwt',
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },
  secret: process.env.NEXTAUTH_SECRET,
};

const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };
