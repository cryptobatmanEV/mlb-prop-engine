import TrackerClient from './TrackerClient';

export default function TrackerPage() {
  const redirectUri = `${process.env.NEXTAUTH_URL}/api/auth/callback/discord`;
  const discordAuthUrl =
    `https://discord.com/api/oauth2/authorize` +
    `?client_id=${process.env.DISCORD_CLIENT_ID}` +
    `&redirect_uri=${encodeURIComponent(redirectUri)}` +
    `&response_type=code` +
    `&scope=identify`;

  return <TrackerClient discordAuthUrl={discordAuthUrl} />;
}
