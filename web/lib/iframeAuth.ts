import { createHmac, timingSafeEqual } from 'crypto';

export type IframeIdentity = {
  discordId:       string;
  discordUsername: string;
};

// Verifies the HMAC token theevcave.com signs over `discord_id:discord_user`
// using the shared IFRAME_SECRET, so a client can't claim someone else's
// Discord identity by editing localStorage/headers.
export function verifyIframeIdentity(
  discordId: string | null,
  discordUser: string | null,
  token: string | null,
): IframeIdentity | null {
  const secret = process.env.IFRAME_SECRET;
  if (!secret || !discordId || !discordUser || !token) return null;

  const expected = createHmac('sha256', secret).update(`${discordId}:${discordUser}`).digest('hex');
  const expectedBuf = Buffer.from(expected);
  const tokenBuf    = Buffer.from(token);
  if (expectedBuf.length !== tokenBuf.length || !timingSafeEqual(expectedBuf, tokenBuf)) return null;

  return { discordId, discordUsername: discordUser };
}

// Reads and verifies the identity headers a request sends (see
// app/lib/iframeIdentity.ts on the client for how these are set).
export function getVerifiedIdentity(req: Request): IframeIdentity | null {
  return verifyIframeIdentity(
    req.headers.get('x-discord-id'),
    req.headers.get('x-discord-user'),
    req.headers.get('x-discord-token'),
  );
}
