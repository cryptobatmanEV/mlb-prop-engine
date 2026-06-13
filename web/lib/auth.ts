import type { NextAuthOptions } from 'next-auth';
import DiscordProvider from 'next-auth/providers/discord';

export const authOptions: NextAuthOptions = {
  providers: [
    DiscordProvider({
      clientId:     process.env.DISCORD_CLIENT_ID!,
      clientSecret: process.env.DISCORD_CLIENT_SECRET!,
    }),
  ],
  session: {
    strategy: 'jwt',
  },
  callbacks: {
    async jwt({ token, profile }) {
      if (profile) {
        const discordProfile = profile as { id: string; username: string; avatar?: string | null };
        token.discordId = discordProfile.id;
        token.discordUsername = discordProfile.username;
        if (discordProfile.avatar) {
          token.discordAvatar = `https://cdn.discordapp.com/avatars/${discordProfile.id}/${discordProfile.avatar}.png`;
        }
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.discordId as string;
        session.user.username = token.discordUsername as string;
        session.user.image = (token.discordAvatar as string | undefined) ?? session.user.image;
      }
      return session;
    },
  },
};
